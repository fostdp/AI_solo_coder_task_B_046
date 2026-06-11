/**
 * 网络效应图层组件 - 核心逻辑
 *
 * 特性：
 * - 基于Leaflet GeoJSON + Canvas叠加渲染
 * - 节点按 role 着色与动画（核心枢纽脉冲）
 * - 边按 connection_strength 映射线宽与线型
 * - 关键节点高亮光晕效果
 * - 右键菜单切换显示模式
 * - 节点中心性弹窗卡片
 */

const API_BASE_NETWORK = `${window.location.origin}/api`;

class NetworkLayer {
    constructor(options = {}) {
        this.options = Object.assign({
            nodeStyles: {
                core_hub:     { color: '#e53e3e', size: 20, shape: 'circle',   pulse: true,  label: '核心枢纽' },
                transit:      { color: '#3182ce', size: 14, shape: 'circle',   pulse: false, label: '中转节点' },
                terminal:     { color: '#38a169', size: 10, shape: 'circle',   pulse: false, label: '终端节点' },
                isolated:     { color: '#a0aec0', size: 10, shape: 'diamond',  pulse: false, label: '孤立节点' }
            },
            edgeStyles: {
                strong:   { color: '#1a365d', width: 3, dash: null,  label: '强连接' },
                medium:   { color: '#2c5282', width: 2, dash: null,  label: '中连接' },
                weak:     { color: '#63b3ed', width: 1, dash: '4,3', label: '弱连接' }
            },
            highlightColor: '#ecc94b',
            highlightGlowRadius: 22,
            zIndex: 380
        }, options);

        this.map = null;
        this.networkData = null;
        this.nodeLayer = null;
        this.edgeLayer = null;
        this.highlightLayer = null;
        this.canvasOverlay = null;
        this.canvas = null;
        this.ctx = null;

        this._animationFrame = null;
        this._pulsePhase = 0;
        this._running = false;

        this._showCriticalOnly = false;
        this._showCoreOnly = false;
        this._showEdges = true;

        this._contextMenuEl = null;
        this._popupEl = null;

        this._currentRegion = null;
        this._hoveredNodeId = null;
        this._eventHandlers = {};
    }

    addTo(map) {
        this.map = map;
        this._initCanvas();
        this._initPopup();
        this._initContextMenu();
        this._initEvents();
        return this;
    }

    remove() {
        this._stopAnimation();
        if (this.nodeLayer) {
            try { this.map.removeLayer(this.nodeLayer); } catch(e) {}
            this.nodeLayer = null;
        }
        if (this.edgeLayer) {
            try { this.map.removeLayer(this.edgeLayer); } catch(e) {}
            this.edgeLayer = null;
        }
        if (this.highlightLayer) {
            try { this.map.removeLayer(this.highlightLayer); } catch(e) {}
            this.highlightLayer = null;
        }
        if (this.canvasOverlay && this.canvasOverlay.parentNode) {
            this.canvasOverlay.parentNode.removeChild(this.canvasOverlay);
            this.canvasOverlay = null;
        }
        if (this._contextMenuEl && this._contextMenuEl.parentNode) {
            this._contextMenuEl.parentNode.removeChild(this._contextMenuEl);
            this._contextMenuEl = null;
        }
        if (this._popupEl && this._popupEl.parentNode) {
            this._popupEl.parentNode.removeChild(this._popupEl);
            this._popupEl = null;
        }
        this.map = null;
        this.networkData = null;
    }

    on(event, callback) {
        if (!this._eventHandlers[event]) {
            this._eventHandlers[event] = [];
        }
        this._eventHandlers[event].push(callback);
    }

    _emit(event, data) {
        if (this._eventHandlers[event]) {
            this._eventHandlers[event].forEach(cb => cb(data));
        }
    }

    _initCanvas() {
        this.canvas = document.createElement('canvas');
        this.canvas.style.position = 'absolute';
        this.canvas.style.top = '0';
        this.canvas.style.left = '0';
        this.canvas.style.pointerEvents = 'none';
        this.canvas.style.zIndex = this.options.zIndex;

        this.canvasOverlay = L.DomUtil.create('div', 'net-effect-overlay');
        this.canvasOverlay.style.position = 'absolute';
        this.canvasOverlay.style.top = '0';
        this.canvasOverlay.style.left = '0';
        this.canvasOverlay.style.width = '100%';
        this.canvasOverlay.style.height = '100%';
        this.canvasOverlay.style.pointerEvents = 'none';
        this.canvasOverlay.appendChild(this.canvas);

        this.map.getPane('overlayPane').appendChild(this.canvasOverlay);
        this.ctx = this.canvas.getContext('2d');
        this._resize();
    }

    _initPopup() {
        this._popupEl = document.createElement('div');
        this._popupEl.className = 'net-effect-popup';
        this._popupEl.style.cssText = `
            position: absolute;
            z-index: 1001;
            background: rgba(26, 32, 44, 0.96);
            color: white;
            padding: 10px 14px;
            border-radius: 8px;
            font-size: 12px;
            line-height: 1.7;
            pointer-events: none;
            display: none;
            box-shadow: 0 6px 20px rgba(0,0,0,0.4);
            border: 1px solid rgba(255,255,255,0.12);
            max-width: 260px;
        `;
        this.map.getContainer().appendChild(this._popupEl);
    }

    _initContextMenu() {
        this._contextMenuEl = document.createElement('div');
        this._contextMenuEl.className = 'net-effect-context-menu';
        this._contextMenuEl.style.cssText = `
            position: absolute;
            z-index: 1002;
            background: white;
            border-radius: 6px;
            box-shadow: 0 4px 16px rgba(0,0,0,0.2);
            padding: 4px 0;
            font-size: 12px;
            min-width: 180px;
            display: none;
            border: 1px solid #e2e8f0;
        `;
        const items = [
            { key: 'critical', label: '只看关键节点', icon: '⭐' },
            { key: 'core',     label: '只看核心枢纽',   icon: '🔴' },
            { key: 'edges',    label: '显示/隐藏连线',  icon: '🔗' },
            { key: 'reset',    label: '重置视图',       icon: '🔄' }
        ];
        this._contextMenuEl.innerHTML = items.map(it => `
            <div class="ctx-item" data-key="${it.key}" style="padding:6px 14px;cursor:pointer;display:flex;align-items:center;gap:8px;">
                <span>${it.icon}</span><span>${it.label}</span>
            </div>
        `).join('');

        this._contextMenuEl.querySelectorAll('.ctx-item').forEach(el => {
            el.addEventListener('click', () => {
                const key = el.dataset.key;
                this._handleContextAction(key);
                this._hideContextMenu();
            });
            el.addEventListener('mouseenter', () => { el.style.background = '#edf2f7'; });
            el.addEventListener('mouseleave', () => { el.style.background = 'transparent'; });
        });

        document.addEventListener('click', () => this._hideContextMenu());
        this.map.getContainer().addEventListener('contextmenu', (e) => {
            if (!this.networkData) return;
            e.preventDefault();
            const rect = this.map.getContainer().getBoundingClientRect();
            this._contextMenuEl.style.left = (e.clientX - rect.left) + 'px';
            this._contextMenuEl.style.top = (e.clientY - rect.top) + 'px';
            this._contextMenuEl.style.display = 'block';
        });

        this.map.getContainer().appendChild(this._contextMenuEl);
    }

    _hideContextMenu() {
        if (this._contextMenuEl) {
            this._contextMenuEl.style.display = 'none';
        }
    }

    _handleContextAction(key) {
        switch (key) {
            case 'critical':
                this._showCriticalOnly = !this._showCriticalOnly;
                if (this._showCriticalOnly) this._showCoreOnly = false;
                this._renderLayers();
                break;
            case 'core':
                this._showCoreOnly = !this._showCoreOnly;
                if (this._showCoreOnly) this._showCriticalOnly = false;
                this._renderLayers();
                break;
            case 'edges':
                this._showEdges = !this._showEdges;
                this._renderLayers();
                break;
            case 'reset':
                this._showCriticalOnly = false;
                this._showCoreOnly = false;
                this._showEdges = true;
                this._renderLayers();
                break;
        }
    }

    _initEvents() {
        this.map.on('move', () => this._onMove());
        this.map.on('zoom', () => this._onMove());
        this.map.on('moveend', () => this._onMoveEnd());
        this.map.on('zoomend', () => this._onMoveEnd());
        this.map.on('resize', () => {
            this._resize();
            this._renderCanvas();
        });
    }

    _resize() {
        if (!this.canvas || !this.map) return;
        const size = this.map.getSize();
        const dpr = window.devicePixelRatio || 1;
        this.canvas.width = size.x * dpr;
        this.canvas.height = size.y * dpr;
        this.canvas.style.width = size.x + 'px';
        this.canvas.style.height = size.y + 'px';
        this.ctx.scale(dpr, dpr);
        this._canvasWidth = size.x;
        this._canvasHeight = size.y;
    }

    _onMove() {
        this._renderCanvas();
    }

    _onMoveEnd() {
        this._renderCanvas();
    }

    _startAnimation() {
        if (this._running || !this.networkData) return;
        const hasPulse = this.networkData.features?.some(f =>
            f.geometry?.type === 'Point' &&
            this.options.nodeStyles[f.properties?.node_role]?.pulse
        );
        if (!hasPulse) return;
        this._running = true;
        const start = performance.now();
        const loop = (now) => {
            if (!this._running) return;
            const elapsed = now - start;
            this._pulsePhase = (Math.sin(elapsed / 1500 * Math.PI * 2) + 1) / 2;
            this._renderCanvas();
            this._animationFrame = requestAnimationFrame(loop);
        };
        this._animationFrame = requestAnimationFrame(loop);
    }

    _stopAnimation() {
        this._running = false;
        if (this._animationFrame) {
            cancelAnimationFrame(this._animationFrame);
            this._animationFrame = null;
        }
    }

    async loadNetwork(region) {
        if (!this.map) return;
        this._currentRegion = region;
        try {
            const regionRes = await fetch(`${API_BASE_NETWORK}/regions/${encodeURIComponent(region)}/latest`);
            if (!regionRes.ok) throw new Error(`区域查询失败: ${regionRes.status}`);
            const regionInfo = await regionRes.json();
            const analysisId = regionInfo.analysis_id || regionInfo.id;
            if (!analysisId) throw new Error('无有效分析ID');

            const netRes = await fetch(`${API_BASE_NETWORK}/analysis/${analysisId}/network.geojson`);
            if (!netRes.ok) throw new Error(`网络数据查询失败: ${netRes.status}`);
            const geojson = await netRes.json();
            this.setNetworkData(geojson);
        } catch (e) {
            console.warn('加载网络数据失败:', e);
            throw e;
        }
    }

    updateData(geojson) {
        this.setNetworkData(geojson);
    }

    setNetworkData(geojson) {
        this._stopAnimation();
        this.networkData = geojson;
        this._renderLayers();
        this._startAnimation();
    }

    _filterNodes(features) {
        return features.filter(f => {
            if (f.geometry?.type !== 'Point') return false;
            const role = f.properties?.node_role || 'terminal';
            const isCritical = f.properties?.critical || f.properties?.betweenness_centrality > 0.1;
            const isCore = role === 'core_hub';
            if (this._showCriticalOnly && !isCritical) return false;
            if (this._showCoreOnly && !isCore) return false;
            return true;
        });
    }

    _filterEdges(features, visibleNodeIds) {
        if (!this._showEdges) return [];
        return features.filter(f => {
            if (f.geometry?.type !== 'LineString') return false;
            const coords = f.geometry.coordinates;
            if (!coords || coords.length < 2) return false;
            if (this._showCriticalOnly || this._showCoreOnly) {
                const fromId = f.properties?.from_site_id || f.properties?.source;
                const toId = f.properties?.to_site_id || f.properties?.target;
                if (!visibleNodeIds.has(fromId) && !visibleNodeIds.has(toId)) return false;
            }
            return true;
        });
    }

    _renderLayers() {
        if (!this.map || !this.networkData) return;
        if (this.nodeLayer) { try { this.map.removeLayer(this.nodeLayer); } catch(e) {} }
        if (this.edgeLayer) { try { this.map.removeLayer(this.edgeLayer); } catch(e) {} }
        if (this.highlightLayer) { try { this.map.removeLayer(this.highlightLayer); } catch(e) {} }

        const features = this.networkData.features || [];
        const nodes = this._filterNodes(features);
        const nodeIds = new Set(nodes.map(n => n.properties?.site_id || n.properties?.id));
        const edges = this._filterEdges(features, nodeIds);

        this.edgeLayer = L.geoJSON({ type: 'FeatureCollection', features: edges }, {
            style: (feat) => {
                const strength = feat.properties?.connection_strength ?? feat.properties?.strength ?? 0.5;
                let style;
                if (strength > 0.7) style = this.options.edgeStyles.strong;
                else if (strength >= 0.3) style = this.options.edgeStyles.medium;
                else style = this.options.edgeStyles.weak;
                return {
                    color: style.color,
                    weight: style.width,
                    opacity: 0.85,
                    dashArray: style.dash,
                    lineCap: 'round'
                };
            },
            onEachFeature: (feat, layer) => {
                const props = feat.properties || {};
                const strength = ((props.connection_strength ?? props.strength ?? 0) * 100).toFixed(0);
                const from = props.from_name || props.source_name || '节点';
                const to = props.to_name || props.target_name || '节点';
                layer.bindTooltip(`${escapeHtml(from)} ↔ ${escapeHtml(to)}<br/>连接强度: ${strength}%`, {
                    direction: 'auto', className: 'edge-tooltip', sticky: true
                });
            }
        }).addTo(this.map);

        this.nodeLayer = L.geoJSON({ type: 'FeatureCollection', features: nodes }, {
            pointToLayer: (feat, latlng) => {
                const props = feat.properties || {};
                const role = props.node_role || 'terminal';
                const conf = this.options.nodeStyles[role] || this.options.nodeStyles.terminal;
                const siteId = props.site_id || props.id;
                const name = props.site_name || props.name || ('节点#' + siteId);

                let icon;
                if (conf.shape === 'diamond') {
                    icon = L.divIcon({
                        className: 'net-node-diamond',
                        html: `<svg width="${conf.size + 6}" height="${conf.size + 6}" viewBox="0 0 ${conf.size + 6} ${conf.size + 6}" style="overflow:visible;">
                            <polygon points="${(conf.size + 6) / 2},3 ${conf.size + 3},${(conf.size + 6) / 2} ${(conf.size + 6) / 2},${conf.size + 3} 3,${(conf.size + 6) / 2}"
                                     fill="${conf.color}" stroke="white" stroke-width="2"
                                     style="filter: drop-shadow(0 1px 3px rgba(0,0,0,0.3));"/>
                        </svg>`,
                        iconSize: [conf.size + 6, conf.size + 6],
                        iconAnchor: [(conf.size + 6) / 2, (conf.size + 6) / 2]
                    });
                } else {
                    const r = conf.size / 2;
                    icon = L.divIcon({
                        className: 'net-node-circle',
                        html: `<svg width="${conf.size + 8}" height="${conf.size + 8}" viewBox="0 0 ${conf.size + 8} ${conf.size + 8}" style="overflow:visible;">
                            <circle cx="${(conf.size + 8) / 2}" cy="${(conf.size + 8) / 2}" r="${r}"
                                    fill="${conf.color}" stroke="white" stroke-width="2.5"
                                    style="filter: drop-shadow(0 2px 5px rgba(0,0,0,0.35));"/>
                        </svg>`,
                        iconSize: [conf.size + 8, conf.size + 8],
                        iconAnchor: [(conf.size + 8) / 2, (conf.size + 8) / 2]
                    });
                }

                const marker = L.marker(latlng, { icon });
                marker.bindTooltip(`<strong>${escapeHtml(name)}</strong><br/>${conf.label}${props.centrality !== undefined ? `<br/>中心性: ${props.centrality.toFixed(3)}` : ''}`, {
                    direction: 'top', className: 'node-tooltip', offset: [0, -12]
                });
                marker.on('click', () => {
                    this.showNodePopup(siteId, latlng, props);
                    this._emit('nodeClick', { siteId, latlng, props });
                });
                return marker;
            }
        }).addTo(this.map);

        this.highlightLayer = L.layerGroup().addTo(this.map);
        this._renderCanvas();
    }

    _renderCanvas() {
        if (!this.ctx || !this.canvas || !this.networkData) return;
        this._resize();
        this.ctx.clearRect(0, 0, this._canvasWidth, this._canvasHeight);
        const features = this.networkData.features || [];
        const nodes = features.filter(f => f.geometry?.type === 'Point');

        for (const node of nodes) {
            const role = node.properties?.node_role || 'terminal';
            const conf = this.options.nodeStyles[role];
            if (!conf || !conf.pulse) continue;
            if (this._showCriticalOnly && !node.properties?.critical && !(node.properties?.betweenness_centrality > 0.1)) continue;
            if (this._showCoreOnly && role !== 'core_hub') continue;

            const coords = node.geometry.coordinates;
            const p = this.map.latLngToContainerPoint([coords[1], coords[0]]);
            const baseR = conf.size / 2 + 2;
            const pulseR = baseR + 4 + this._pulsePhase * 10;
            const alpha = 0.55 * (1 - this._pulsePhase);

            this.ctx.beginPath();
            this.ctx.arc(p.x, p.y, pulseR, 0, Math.PI * 2);
            this.ctx.strokeStyle = `rgba(${this._hexToRgb(conf.color)}, ${alpha})`;
            this.ctx.lineWidth = 2;
            this.ctx.stroke();

            if (this._pulsePhase < 0.5) {
                this.ctx.beginPath();
                this.ctx.arc(p.x, p.y, pulseR * 0.75, 0, Math.PI * 2);
                this.ctx.fillStyle = `rgba(${this._hexToRgb(conf.color)}, ${alpha * 0.25})`;
                this.ctx.fill();
            }
        }
    }

    _hexToRgb(hex) {
        const h = hex.replace('#', '');
        const bigint = parseInt(h, 16);
        const r = (bigint >> 16) & 255;
        const g = (bigint >> 8) & 255;
        const b = bigint & 255;
        return `${r}, ${g}, ${b}`;
    }

    highlightCriticalNodes() {
        if (!this.highlightLayer || !this.map) return;
        this.highlightLayer.clearLayers();
        if (!this.networkData) return;
        const features = this.networkData.features || [];
        const critical = features.filter(f =>
            f.geometry?.type === 'Point' &&
            (f.properties?.critical || (f.properties?.betweenness_centrality ?? 0) > 0.1)
        );
        for (const node of critical) {
            const coords = node.geometry.coordinates;
            const latlng = [coords[1], coords[0]];
            const props = node.properties || {};
            const role = props.node_role || 'terminal';
            const conf = this.options.nodeStyles[role] || {};
            const baseR = conf.size ? conf.size / 2 : 10;
            const circle = L.circleMarker(latlng, {
                radius: baseR + this.options.highlightGlowRadius / 5,
                weight: 0,
                fillColor: this.options.highlightColor,
                fillOpacity: 0.0
            }).addTo(this.highlightLayer);
            const glow = L.circleMarker(latlng, {
                radius: baseR + 5,
                weight: 3,
                color: this.options.highlightColor,
                opacity: 0.9,
                fillColor: this.options.highlightColor,
                fillOpacity: 0.25
            }).addTo(this.highlightLayer);
        }
    }

    showNodePopup(site_id, latlng, props) {
        if (!this._popupEl || !this.map) return;
        const p = props || {};
        const cent = p.betweenness_centrality ?? p.centrality;
        const centStr = cent !== undefined && cent !== null ? (cent * 100).toFixed(1) + '%' : '—';
        const deg = p.degree ?? p.connection_count;
        const degStr = deg !== undefined && deg !== null ? deg + ' 条' : '—';
        const close = p.closeness_centrality;
        const closeStr = close !== undefined && close !== null ? (close * 100).toFixed(1) + '%' : '—';
        const role = p.node_role || 'terminal';
        const roleLabel = (this.options.nodeStyles[role] || {}).label || role;
        const point = this.map.latLngToContainerPoint(latlng);
        this._popupEl.innerHTML = `
            <div style="font-weight:600;margin-bottom:8px;color:#fbd38d;font-size:13px;">${escapeHtml(p.site_name || p.name || ('节点#' + site_id))}</div>
            <div style="display:grid;grid-template-columns:auto 1fr;gap:3px 10px;color:#e2e8f0;">
                <span>节点类型:</span><span style="color:#fff;">${roleLabel}</span>
                <span>中心性:</span><span style="color:#9ae6b4;font-weight:600;">${centStr}</span>
                <span>连接数:</span><span style="color:#fff;">${degStr}</span>
                <span>接近中心:</span><span style="color:#90cdf4;">${closeStr}</span>
                ${p.critical ? '<span style="grid-column:1/3;margin-top:4px;color:#fbd38d;">⭐ 关键节点（关节点）</span>' : ''}
            </div>
        `;
        const rect = this.map.getContainer().getBoundingClientRect();
        const pw = this._popupEl.offsetWidth || 240;
        const ph = this._popupEl.offsetHeight || 120;
        const fx = Math.min(point.x + 14, rect.width - pw - 10);
        const fy = Math.max(10, Math.min(point.y - ph - 14, rect.height - ph - 10));
        this._popupEl.style.left = fx + 'px';
        this._popupEl.style.top = fy + 'px';
        this._popupEl.style.display = 'block';
        clearTimeout(this._popupTimer);
        this._popupTimer = setTimeout(() => this._hideNodePopup(), 6000);
    }

    _hideNodePopup() {
        if (this._popupEl) {
            this._popupEl.style.display = 'none';
        }
    }

    setShowEdges(show) {
        this._showEdges = show;
        this._renderLayers();
    }

    setCriticalOnly(only) {
        this._showCriticalOnly = only;
        if (only) this._showCoreOnly = false;
        this._renderLayers();
    }

    setCoreOnly(only) {
        this._showCoreOnly = only;
        if (only) this._showCriticalOnly = false;
        this._renderLayers();
    }

    show() {
        if (this.nodeLayer) this.nodeLayer.addTo(this.map);
        if (this.edgeLayer) this.edgeLayer.addTo(this.map);
        if (this.highlightLayer) this.highlightLayer.addTo(this.map);
        if (this.canvasOverlay) this.canvasOverlay.style.display = 'block';
        this._startAnimation();
        this._renderCanvas();
    }

    hide() {
        if (this.nodeLayer) try { this.map.removeLayer(this.nodeLayer); } catch(e) {}
        if (this.edgeLayer) try { this.map.removeLayer(this.edgeLayer); } catch(e) {}
        if (this.highlightLayer) try { this.map.removeLayer(this.highlightLayer); } catch(e) {}
        if (this.canvasOverlay) this.canvasOverlay.style.display = 'none';
        this._stopAnimation();
        this._hideNodePopup();
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text || '';
    return div.innerHTML;
}
