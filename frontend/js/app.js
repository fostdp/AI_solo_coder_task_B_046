const API_BASE = 'http://localhost:8000/api';

const appState = {
    map: null,
    sitesLayer: null,
    supplyRangesLayer: null,
    supplyRangeRenderer: null,
    canvasLayer: null,
    sites: [],
    filteredSites: [],
    supplyRanges: [],
    selectedSite: null,
    showSupplyRange: true,
    showHexagon: true,
    sizeByArea: true,
    colorByStatus: true,
    useHighPerformanceRenderer: true
};

const STATUS_COLORS = {
    '完好': '#38a169',
    '部分损毁': '#d69e2e',
    '完全废弃': '#e53e3e'
};

const TYPE_NAMES = {
    '渠': '渠道',
    '堰': '堰坝',
    '陂': '陂塘',
    '塘': '水塘',
    '井': '水井'
};

function hexToRadius(irrigationArea) {
    if (!appState.sizeByArea) return 14;
    if (irrigationArea < 10) return 10;
    if (irrigationArea < 100) return 14;
    if (irrigationArea < 1000) return 20;
    return 28;
}

function getColor(status, site) {
    if (!appState.colorByStatus) {
        const dynColors = ['#2b6cb0', '#2c5282', '#1a365d', '#3182ce', '#4299e1'];
        return dynColors[(site.dynasty_order - 1) % dynColors.length];
    }
    return STATUS_COLORS[status] || '#718096';
}

function initMap() {
    appState.map = L.map('map', {
        center: [34.0, 110.0],
        zoom: 5,
        minZoom: 4,
        maxZoom: 14
    });

    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/">CARTO</a>',
        subdomains: 'abcd',
        maxZoom: 19
    }).addTo(appState.map);

    const southWest = L.latLng(18, 73);
    const northEast = L.latLng(53, 135);
    appState.map.setMaxBounds(L.latLngBounds(southWest, northEast));

    initCanvasLayer();
    loadDynasties();
    loadSites();
    loadStatistics();
    checkAlerts();
}

function initCanvasLayer() {
    appState.canvasLayer = L.canvas({ padding: 0.5 });
    appState.sitesLayer = L.layerGroup().addTo(appState.map);
    appState.supplyRangesLayer = L.layerGroup().addTo(appState.map);

    if (appState.useHighPerformanceRenderer && typeof SupplyRangeRenderer !== 'undefined') {
        appState.supplyRangeRenderer = new SupplyRangeRenderer(appState.map, {
            onClick: (range) => {
                if (range.siteId) selectSite(range.siteId);
            }
        });
    }
}

function drawHexagon(ctx, x, y, radius, fillColor, strokeColor) {
    const angle = Math.PI / 3;
    ctx.beginPath();
    for (let i = 0; i < 6; i++) {
        const px = x + radius * Math.cos(angle * i - Math.PI / 2);
        const py = y + radius * Math.sin(angle * i - Math.PI / 2);
        if (i === 0) ctx.moveTo(px, py);
        else ctx.lineTo(px, py);
    }
    ctx.closePath();
    ctx.fillStyle = fillColor;
    ctx.fill();
    ctx.strokeStyle = strokeColor || 'rgba(255,255,255,0.9)';
    ctx.lineWidth = 2;
    ctx.stroke();
}

function renderSites() {
    appState.sitesLayer.clearLayers();
    appState.supplyRangesLayer.clearLayers();

    const sitesToRender = appState.filteredSites.length > 0 ? appState.filteredSites : appState.sites;

    if (appState.showHexagon) {
        const hexLayer = L.layerGroup();
        sitesToRender.forEach(site => {
            const latlng = [site.latitude, site.longitude];
            const radius = hexToRadius(site.irrigation_area);
            const color = getColor(site.preservation_status, site);

            const icon = L.divIcon({
                className: 'hex-marker',
                html: createHexSVG(radius, color),
                iconSize: [radius * 2 + 4, radius * 2 + 4],
                iconAnchor: [radius + 2, radius + 2]
            });

            const marker = L.marker(latlng, { icon: icon, site: site });
            marker.bindPopup(createPopupContent(site));
            marker.on('click', () => selectSite(site.id));
            marker.addTo(hexLayer);
        });
        hexLayer.addTo(appState.sitesLayer);
    } else {
        sitesToRender.forEach(site => {
            const latlng = [site.latitude, site.longitude];
            const color = getColor(site.preservation_status, site);
            const marker = L.circleMarker(latlng, {
                radius: hexToRadius(site.irrigation_area) * 0.6,
                fillColor: color,
                color: 'white',
                weight: 2,
                opacity: 1,
                fillOpacity: 0.9
            });
            marker.bindPopup(createPopupContent(site));
            marker.on('click', () => selectSite(site.id));
            marker.addTo(appState.sitesLayer);
        });
    }

    if (appState.showSupplyRange) {
        loadSupplyRanges();
    }
}

function createHexSVG(radius, color) {
    const size = radius * 2 + 8;
    const cx = size / 2;
    const cy = size / 2;
    const points = [];
    for (let i = 0; i < 6; i++) {
        const angle = (Math.PI / 3) * i - Math.PI / 2;
        const px = cx + radius * Math.cos(angle);
        const py = cy + radius * Math.sin(angle);
        points.push(`${px},${py}`);
    }
    return `
        <svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" style="overflow:visible;pointer-events:none;">
            <polygon points="${points.join(' ')}" 
                     fill="${color}" 
                     fill-opacity="0.92"
                     stroke="white" 
                     stroke-width="2.5"
                     style="filter: drop-shadow(0 2px 6px rgba(0,0,0,0.25));"/>
        </svg>
    `;
}

function createPopupContent(site) {
    const score = site.total_score ? `<div class="popup-row"><span class="popup-label">评分：</span><span class="popup-value">${site.total_score?.toFixed(1)} (${site.grade})</span></div>` : '';
    const pot = site.restoration_potential !== undefined ? `<div class="popup-row"><span class="popup-label">修复潜力：</span><span class="popup-value">${site.restoration_potential ? '✅ 有' : '❌ 无'}</span></div>` : '';

    return `
        <div style="padding:4px;">
            <div class="popup-title">${escapeHtml(site.name)}</div>
            <div class="popup-row"><span class="popup-label">朝代：</span><span class="popup-value">${site.dynasty}</span></div>
            <div class="popup-row"><span class="popup-label">类型：</span><span class="popup-value">${TYPE_NAMES[site.site_type] || site.site_type}</span></div>
            <div class="popup-row"><span class="popup-label">灌溉面积：</span><span class="popup-value">${site.irrigation_area.toFixed(1)} 亩</span></div>
            <div class="popup-row"><span class="popup-label">保存状态：</span><span class="popup-value" style="color:${STATUS_COLORS[site.preservation_status]}">${site.preservation_status}</span></div>
            ${score}
            ${pot}
            <button class="popup-btn" onclick="selectSite(${site.id});window.L._popupHandlersAdded=true;">查看详情</button>
        </div>
    `;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text || '';
    return div.innerHTML;
}

async function loadDynasties() {
    try {
        const res = await fetch(`${API_BASE}/dynasties`);
        const dynasties = await res.json();
        const select = document.getElementById('filterDynasty');
        dynasties.forEach(d => {
            const opt = document.createElement('option');
            opt.value = d.name;
            opt.textContent = `${d.name} (${d.start_year}~${d.end_year})`;
            select.appendChild(opt);
        });
    } catch (e) {
        console.warn('加载朝代失败:', e);
    }
}

async function loadSites() {
    try {
        showToast('正在加载遗迹数据...', 'info');
        const res = await fetch(`${API_BASE}/sites/geojson`);
        const data = await res.json();
        appState.sites = data.features.map(f => ({
            id: f.id,
            longitude: f.geometry.coordinates[0],
            latitude: f.geometry.coordinates[1],
            ...f.properties
        }));
        renderSites();
        showToast(`成功加载 ${appState.sites.length} 处遗迹`, 'success');
    } catch (e) {
        showToast('加载数据失败，请确认后端已启动', 'error');
        console.error(e);
    }
}

async function loadSupplyRanges() {
    try {
        const res = await fetch(`${API_BASE}/restoration/supply-ranges`);
        const data = await res.json();
        appState.supplyRanges = data.features || [];

        if (appState.supplyRangeRenderer) {
            appState.supplyRangeRenderer.setRanges(appState.supplyRanges);
            if (!appState.showSupplyRange) {
                appState.supplyRangeRenderer.hide();
            }
        } else {
            data.features.forEach(f => {
                const layer = L.geoJSON(f, {
                    style: {
                        color: '#4299e1',
                        weight: 1.5,
                        fillColor: '#4299e1',
                        fillOpacity: 0.2,
                        dashArray: '4, 4'
                    }
                });
                layer.bindPopup(`
                    <strong>灌溉区范围</strong><br/>
                    原始灌溉能力: ${f.properties.original_capacity?.toFixed(2)} 亩<br/>
                    实际灌溉能力: ${f.properties.actual_capacity?.toFixed(2)} 亩<br/>
                    可服务人口: 约 ${f.properties.supply_population || 0} 人
                `);
                layer.addTo(appState.supplyRangesLayer);
            });
        }
    } catch (e) {
        console.warn('加载灌溉范围失败:', e);
    }
}

async function loadStatistics() {
    try {
        const res = await fetch(`${API_BASE}/statistics`);
        const stats = await res.json();

        document.getElementById('statTotal').textContent = stats.total_sites;
        document.getElementById('statGood').textContent = stats.by_status['完好'] || 0;
        document.getElementById('statWarn').textContent = stats.by_status['部分损毁'] || 0;
        document.getElementById('statDanger').textContent = stats.by_status['完全废弃'] || 0;
        document.getElementById('statPotential').textContent = stats.high_potential_count;
        document.getElementById('statAlerts').textContent = stats.alerts_count;
    } catch (e) {
        console.warn('加载统计失败:', e);
    }
}

async function checkAlerts() {
    try {
        const res = await fetch(`${API_BASE}/alerts?alert_level=紧急&acknowledged=false&limit=5`);
        const alerts = await res.json();
        if (alerts.length > 0) {
            showAlertBanner(alerts[0].message);
        }
    } catch (e) {
        console.warn(e);
    }
}

function applyFilters() {
    const type = document.getElementById('filterType').value;
    const dynasty = document.getElementById('filterDynasty').value;
    const status = document.getElementById('filterStatus').value;
    const minArea = parseFloat(document.getElementById('minArea').value);
    const maxArea = parseFloat(document.getElementById('maxArea').value);

    appState.filteredSites = appState.sites.filter(s => {
        if (type && s.site_type !== type) return false;
        if (dynasty && s.dynasty !== dynasty) return false;
        if (status && s.preservation_status !== status) return false;
        if (!isNaN(minArea) && s.irrigation_area < minArea) return false;
        if (!isNaN(maxArea) && s.irrigation_area > maxArea) return false;
        return true;
    });

    renderSites();
    showToast(`筛选完成，共 ${appState.filteredSites.length} 处遗迹`, 'info');
}

function resetFilters() {
    document.getElementById('filterType').value = '';
    document.getElementById('filterDynasty').value = '';
    document.getElementById('filterStatus').value = '';
    document.getElementById('minArea').value = '';
    document.getElementById('maxArea').value = '';
    appState.filteredSites = [];
    renderSites();
}

async function selectSite(siteId) {
    appState.selectedSite = siteId;
    const panel = document.getElementById('panelContent');
    panel.innerHTML = '<div class="loading">加载详细信息中</div>';
    document.getElementById('detailPanel').scrollTop = 0;

    try {
        const [compRes, hydroRes, sectionRes] = await Promise.all([
            fetch(`${API_BASE}/sites/${siteId}/comprehensive`),
            fetch(`${API_BASE}/sites/${siteId}/hydrology-trend`),
            fetch(`${API_BASE}/sites/${siteId}/cross-section`)
        ]);

        const comp = await compRes.json();
        const hydro = await hydroRes.json();
        const section = await sectionRes.json();

        if (comp.restoration === null) {
            try {
                await fetch(`${API_BASE}/sites/${siteId}/restore`, { method: 'POST' });
                const newComp = await (await fetch(`${API_BASE}/sites/${siteId}/comprehensive`)).json();
                comp.restoration = newComp.restoration;
            } catch (e) { console.warn(e); }
        }

        if (comp.assessment === null) {
            try {
                await fetch(`${API_BASE}/sites/${siteId}/assess`, { method: 'POST' });
                const newComp = await (await fetch(`${API_BASE}/sites/${siteId}/comprehensive`)).json();
                comp.assessment = newComp.assessment;
            } catch (e) { console.warn(e); }
        }

        renderDetailPanel(comp, hydro, section);

        if (appState.supplyRangeRenderer) {
            appState.supplyRangeRenderer.setSelected(siteId);
        }

        const site = appState.sites.find(s => s.id === siteId);
        if (site) {
            appState.map.flyTo([site.latitude, site.longitude], 10, { duration: 0.8 });
        }

        loadStatistics();
    } catch (e) {
        panel.innerHTML = `<div class="empty-state"><p>加载失败：${e.message}</p></div>`;
        console.error(e);
    }
}

function renderDetailPanel(comp, hydro, section) {
    const panel = document.getElementById('panelContent');
    const site = comp.site;
    const assessment = comp.assessment;
    const restoration = comp.restoration;

    let html = '';

    html += `<div class="site-info-section">
        <div class="site-name">${escapeHtml(site.name)}</div>
        <div class="site-badges">
            <span class="badge badge-dynasty">${site.dynasty}</span>
            <span class="badge badge-type">${TYPE_NAMES[site.site_type] || site.site_type}</span>
            <span class="badge badge-status ${site.preservation_status}">${site.preservation_status}</span>
            ${assessment ? `<span class="badge badge-grade">${assessment.grade}</span>` : ''}
        </div>
        <div class="info-grid">
            <div class="info-item"><span class="info-label">经度</span><span class="info-value">${site.longitude.toFixed(4)}°E</span></div>
            <div class="info-item"><span class="info-label">纬度</span><span class="info-value">${site.latitude.toFixed(4)}°N</span></div>
            <div class="info-item"><span class="info-label">坝高</span><span class="info-value">${site.dam_height ? site.dam_height + ' m' : '—'}</span></div>
            <div class="info-item"><span class="info-label">渠长</span><span class="info-value">${site.canal_length ? site.canal_length + ' km' : '—'}</span></div>
            <div class="info-item"><span class="info-label">灌溉面积</span><span class="info-value">${site.irrigation_area.toFixed(1)} 亩</span></div>
            <div class="info-item"><span class="info-label">工程类型</span><span class="info-value">${site.site_type}</span></div>
        </div>
        <div class="site-description">${escapeHtml(site.description || '暂无描述')}</div>
    </div>`;

    if (assessment) {
        const ad = assessment.assessment_details || {};
        html += `<div class="site-info-section">
            <div class="section-title">可持续性评估 (AHP层次分析法)</div>
            <div class="score-display">
                <div class="score-number">${assessment.total_score.toFixed(1)}</div>
                <div class="score-label">综合评分</div>
                <div class="score-grade">等级 ${assessment.grade}</div>
                <div class="potential-flag ${assessment.restoration_potential ? 'yes' : 'no'}">
                    ${assessment.restoration_potential ? '✅ 具备恢复利用潜力' : '❌ 暂不具备恢复利用潜力'}
                </div>
            </div>
            <div class="score-bars">
                ${renderScoreBar('结构完整性', assessment.structural_score, 'structural-bar')}
                ${renderScoreBar('水文条件', assessment.hydrological_score, 'hydrological-bar')}
                ${renderScoreBar('经济价值', assessment.economic_score, 'economic-bar')}
                ${renderScoreBar('文化价值', assessment.cultural_score, 'cultural-bar')}
                ${renderScoreBar('环境协调性', assessment.environmental_score, 'environmental-bar')}
            </div>
            ${ad.recommendations && ad.recommendations.length > 0 ? `
                <div class="section-title" style="margin-top:20px;">专家建议</div>
                <ul class="recommendations">
                    ${ad.recommendations.map(r => `<li>${escapeHtml(r)}</li>`).join('')}
                </ul>
            ` : ''}
        </div>`;
    }

    if (restoration) {
        html += `<div class="site-info-section">
            <div class="section-title">功能复原结果</div>
            <div class="restoration-data">
                <div class="restoration-card">
                    <div class="restoration-label">原始灌溉能力</div>
                    <div class="restoration-value">${restoration.original_irrigation_capacity?.toFixed(1) || '0'} <span class="restoration-unit">亩</span></div>
                </div>
                <div class="restoration-card actual">
                    <div class="restoration-label">当前实际能力</div>
                    <div class="restoration-value">${restoration.actual_irrigation_capacity?.toFixed(1) || '0'} <span class="restoration-unit">亩</span></div>
                </div>
            </div>
            <div class="info-grid" style="margin-top:12px;">
                <div class="info-item"><span class="info-label">可服务人口</span><span class="info-value">约 ${restoration.supply_population || 0} 人</span></div>
                <div class="info-item"><span class="info-label">能力保持率</span><span class="info-value">${restoration.original_irrigation_capacity > 0 ? ((restoration.actual_irrigation_capacity / restoration.original_irrigation_capacity) * 100).toFixed(1) : 0}%</span></div>
            </div>
            ${restoration.restoration_notes ? `<div class="restoration-notes">📊 ${escapeHtml(restoration.restoration_notes)}</div>` : ''}
        </div>`;
    }

    html += `<div class="site-info-section">
        <div class="section-title">水文变化趋势 (每10年)</div>
        <div class="chart-container">
            <canvas id="hydroChart"></canvas>
        </div>
        <div class="chart-legend">
            <span class="chart-legend-item"><span class="chart-legend-color" style="background:#4299e1;"></span>降雨量 (mm)</span>
            <span class="chart-legend-item"><span class="chart-legend-color" style="background:#38b2ac;"></span>径流量 (万m³)</span>
            <span class="chart-legend-item"><span class="chart-legend-color" style="background:#ed8936;"></span>气温 (℃)</span>
        </div>
    </div>`;

    html += `<div class="site-info-section">
        <div class="section-title">结构剖面图 (${site.site_type})</div>
        <div class="cross-section-container">
            <canvas id="crossSectionCanvas"></canvas>
        </div>
    </div>`;

    panel.innerHTML = html;

    setTimeout(() => {
        drawHydroChart('hydroChart', hydro);
        drawCrossSection('crossSectionCanvas', section);
    }, 50);
}

function renderScoreBar(label, value, barClass) {
    return `<div class="score-bar-item">
        <div class="score-bar-header">
            <span class="score-bar-label">${label}</span>
            <span class="score-bar-value">${value.toFixed(1)}</span>
        </div>
        <div class="score-bar-track">
            <div class="score-bar-fill ${barClass}" style="width:${Math.min(100, value)}%"></div>
        </div>
    </div>`;
}

function drawHydroChart(canvasId, hydroData) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    const container = canvas.parentElement;
    canvas.width = container.clientWidth;
    canvas.height = container.clientHeight;
    const W = canvas.width;
    const H = canvas.height;
    ctx.clearRect(0, 0, W, H);

    const padding = { top: 20, right: 60, bottom: 36, left: 50 };
    const chartW = W - padding.left - padding.right;
    const chartH = H - padding.top - padding.bottom;

    const trend = hydroData.trend || [];
    if (trend.length < 2) {
        ctx.font = '13px sans-serif';
        ctx.fillStyle = '#a0aec0';
        ctx.textAlign = 'center';
        ctx.fillText('数据不足', W / 2, H / 2);
        return;
    }

    const sampleRate = Math.max(1, Math.floor(trend.length / 40));
    const sampled = trend.filter((_, i) => i % sampleRate === 0);

    const years = sampled.map(d => d.year);
    const rains = sampled.map(d => d.rainfall);
    const runoffs = sampled.map(d => d.runoff);
    const temps = sampled.map(d => d.temperature || 15);

    const yearMin = Math.min(...years);
    const yearMax = Math.max(...years);
    const rainMin = Math.min(...rains) * 0.9;
    const rainMax = Math.max(...rains) * 1.1;
    const runMin = Math.min(...runoffs) * 0.9;
    const runMax = Math.max(...runoffs) * 1.1;
    const tempMin = Math.min(...temps) - 2;
    const tempMax = Math.max(...temps) + 2;

    ctx.strokeStyle = '#e2e8f0';
    ctx.lineWidth = 1;
    for (let i = 0; i <= 5; i++) {
        const y = padding.top + chartH * (i / 5);
        ctx.beginPath(); ctx.moveTo(padding.left, y); ctx.lineTo(W - padding.right, y); ctx.stroke();
        const val = rainMax - (rainMax - rainMin) * (i / 5);
        ctx.fillStyle = '#718096'; ctx.font = '10px sans-serif'; ctx.textAlign = 'right';
        ctx.fillText(val.toFixed(0), padding.left - 6, y + 3);
    }

    for (let i = 0; i <= 5; i++) {
        const x = padding.left + chartW * (i / 5);
        ctx.beginPath(); ctx.moveTo(x, padding.top); ctx.lineTo(x, padding.top + chartH); ctx.stroke();
        const yr = yearMin + (yearMax - yearMin) * (i / 5);
        ctx.fillStyle = '#718096'; ctx.font = '10px sans-serif'; ctx.textAlign = 'center';
        const yrStr = yr < 0 ? `前${Math.abs(yr)}` : `${yr}`;
        ctx.fillText(yrStr, x, padding.top + chartH + 18);
    }

    const yearMin2 = Math.min(...years);
    const xScale = (year) => padding.left + chartW * ((year - yearMin2) / (yearMax - yearMin2));
    const yRain = (v) => padding.top + chartH * (1 - (v - rainMin) / (rainMax - rainMin));
    const yRun = (v) => padding.top + chartH * (1 - (v - runMin) / (runMax - runMin));
    const yTemp = (v) => padding.top + chartH * (1 - (v - tempMin) / (tempMax - tempMin));

    ctx.strokeStyle = '#4299e1'; ctx.lineWidth = 2; ctx.beginPath();
    rains.forEach((v, i) => {
        const x = xScale(years[i]), y = yRain(v);
        i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    }); ctx.stroke();

    ctx.strokeStyle = '#38b2ac'; ctx.lineWidth = 2; ctx.beginPath();
    runoffs.forEach((v, i) => {
        const x = xScale(years[i]), y = yRun(v);
        i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    }); ctx.stroke();

    ctx.strokeStyle = '#ed8936'; ctx.lineWidth = 1.5; ctx.setLineDash([4, 3]); ctx.beginPath();
    temps.forEach((v, i) => {
        const x = xScale(years[i]), y = yTemp(v);
        i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    }); ctx.stroke(); ctx.setLineDash([]);

    for (let i = 0; i <= 3; i++) {
        const y = padding.top + chartH * (i / 3);
        const val = runMax - (runMax - runMin) * (i / 3);
        ctx.fillStyle = '#319795'; ctx.font = '9px sans-serif'; ctx.textAlign = 'left';
        ctx.fillText(val.toFixed(0) + ' 径流', W - padding.right + 4, y + 3);
    }

    ctx.fillStyle = '#2d3748'; ctx.font = '10px sans-serif'; ctx.textAlign = 'center';
    ctx.fillText('年份', W / 2, H - 4);
}

function drawCrossSection(canvasId, sectionData) {
    const canvas = document.getElementById(canvasId);
    if (!canvas || !sectionData) return;

    const ctx = canvas.getContext('2d');
    const container = canvas.parentElement;
    canvas.width = container.clientWidth;
    canvas.height = container.clientHeight;
    const W = canvas.width;
    const H = canvas.height;
    ctx.clearRect(0, 0, W, H);

    const padding = { top: 20, right: 30, bottom: 40, left: 50 };
    const chartW = W - padding.left - padding.right;
    const chartH = H - padding.top - padding.bottom;

    const cs = sectionData.cross_section || {};
    const nPts = (cs.x_normalized || []).length;

    if (nPts < 2) {
        ctx.font = '13px sans-serif';
        ctx.fillStyle = '#a0aec0';
        ctx.textAlign = 'center';
        ctx.fillText('剖面数据不足', W / 2, H / 2);
        return;
    }

    const ground = cs.ground_profile || [];
    const structure = cs.structure_profile || [];
    const water = cs.water_profile || [];

    const allY = [...ground, ...structure.map(v => v ?? 0), ...water.map(v => v ?? 0)].filter(v => !isNaN(v));
    const yMin = Math.min(...allY) * 1.1;
    const yMax = Math.max(...allY) * 1.1 + 0.5;

    ctx.strokeStyle = '#cbd5e0';
    ctx.lineWidth = 0.5;
    for (let i = 0; i <= 6; i++) {
        const y = padding.top + chartH * (i / 6);
        ctx.beginPath(); ctx.moveTo(padding.left, y); ctx.lineTo(W - padding.right, y); ctx.stroke();
        const val = yMax - (yMax - yMin) * (i / 6);
        ctx.fillStyle = '#718096'; ctx.font = '10px sans-serif'; ctx.textAlign = 'right';
        ctx.fillText(val.toFixed(1) + 'm', padding.left - 5, y + 3);
    }

    for (let i = 0; i <= 5; i++) {
        const x = padding.left + chartW * (i / 5);
        ctx.beginPath(); ctx.moveTo(x, padding.top); ctx.lineTo(x, padding.top + chartH); ctx.stroke();
    }

    const xScale = (i) => padding.left + chartW * (i / (nPts - 1));
    const yScale = (v) => {
        if (v === null || v === undefined || isNaN(v)) return null;
        return padding.top + chartH * (1 - (v - yMin) / (yMax - yMin));
    };

    const waterPoints = water.map((v, i) => ({ x: xScale(i), y: yScale(v) })).filter(p => p.y !== null);
    if (waterPoints.length >= 2) {
        const groundPts = ground.map((v, i) => ({ x: xScale(i), y: yScale(v) }));
        ctx.fillStyle = 'rgba(66, 153, 225, 0.35)';
        ctx.beginPath();
        let started = false;
        waterPoints.forEach((wp, idx) => {
            const gp = groundPts.find(g => Math.abs(g.x - wp.x) < 2);
            if (gp) {
                if (!started) { ctx.moveTo(wp.x, Math.min(wp.y, gp.y)); started = true; }
                else ctx.lineTo(wp.x, Math.min(wp.y, gp.y));
            }
        });
        for (let i = waterPoints.length - 1; i >= 0; i--) {
            const wp = waterPoints[i];
            const gp = groundPts.find(g => Math.abs(g.x - wp.x) < 2);
            if (gp) ctx.lineTo(wp.x, gp.y);
        }
        ctx.closePath(); ctx.fill();

        ctx.strokeStyle = '#3182ce';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        waterPoints.forEach((p, i) => i === 0 ? ctx.moveTo(p.x, p.y) : ctx.lineTo(p.x, p.y));
        ctx.stroke();
    }

    const structPts = structure.map((v, i) => ({ x: xScale(i), y: yScale(v) }));
    const validStruct = structPts.filter(p => p.y !== null);
    if (validStruct.length >= 2) {
        const structGrad = ctx.createLinearGradient(0, padding.top, 0, padding.top + chartH);
        structGrad.addColorStop(0, '#8b5a2b');
        structGrad.addColorStop(1, '#5c3317');
        ctx.fillStyle = structGrad;
        ctx.beginPath();
        let firstIdx = structPts.findIndex(p => p.y !== null);
        let lastIdx = -1;
        for (let i = structPts.length - 1; i >= 0; i--) if (structPts[i].y !== null) { lastIdx = i; break; }

        if (firstIdx >= 0 && lastIdx >= 0) {
            const groundLeftY = yScale(ground[firstIdx] ?? yMin);
            ctx.moveTo(structPts[firstIdx].x, Math.max(structPts[firstIdx].y, groundLeftY));

            for (let i = firstIdx; i <= lastIdx; i++) {
                if (structPts[i].y !== null) ctx.lineTo(structPts[i].x, structPts[i].y);
            }
            const groundRightY = yScale(ground[lastIdx] ?? yMin);
            ctx.lineTo(structPts[lastIdx].x, Math.max(structPts[lastIdx].y, groundRightY));
            for (let i = lastIdx; i >= firstIdx; i--) {
                const gy = yScale(ground[i] ?? yMin);
                ctx.lineTo(structPts[i].x, Math.max(gy, structPts[i].y ?? groundLeftY));
            }
            ctx.closePath(); ctx.fill();
        }

        ctx.strokeStyle = '#2d3748';
        ctx.lineWidth = 2;
        ctx.beginPath();
        started = false;
        validStruct.forEach((p, i) => {
            if (p.y !== null) {
                if (!started) { ctx.moveTo(p.x, p.y); started = true; }
                else ctx.lineTo(p.x, p.y);
            }
        });
        ctx.stroke();
    }

    const groundPts = ground.map((v, i) => ({ x: xScale(i), y: yScale(v) }));
    if (groundPts.length >= 2) {
        ctx.fillStyle = 'rgba(139, 119, 101, 0.25)';
        ctx.beginPath();
        ctx.moveTo(groundPts[0].x, H - padding.bottom);
        groundPts.forEach(p => ctx.lineTo(p.x, p.y));
        ctx.lineTo(groundPts[groundPts.length - 1].x, H - padding.bottom);
        ctx.closePath(); ctx.fill();

        ctx.strokeStyle = '#6b4226';
        ctx.lineWidth = 2.5;
        ctx.beginPath();
        groundPts.forEach((p, i) => i === 0 ? ctx.moveTo(p.x, p.y) : ctx.lineTo(p.x, p.y));
        ctx.stroke();
    }

    ctx.fillStyle = '#2d3748'; ctx.font = '10px sans-serif'; ctx.textAlign = 'center';
    ctx.fillText('横剖面 (m) →', W / 2, H - 8);
    ctx.save();
    ctx.translate(12, H / 2); ctx.rotate(-Math.PI / 2);
    ctx.fillText('高程 (m)', 0, 0);
    ctx.restore();

    const legendY = 6;
    const legends = [
        { color: '#8b5a2b', label: '水工结构' },
        { color: 'rgba(66, 153, 225, 0.6)', label: '水体', border: true },
        { color: '#6b4226', label: '地面' }
    ];
    let lx = padding.left;
    ctx.font = '10px sans-serif';
    legends.forEach(l => {
        ctx.fillStyle = l.color;
        ctx.fillRect(lx, legendY, 12, 10);
        if (l.border) { ctx.strokeStyle = '#3182ce'; ctx.lineWidth = 1; ctx.strokeRect(lx, legendY, 12, 10); }
        ctx.fillStyle = '#2d3748'; ctx.textAlign = 'left';
        ctx.fillText(l.label, lx + 16, legendY + 9);
        lx += ctx.measureText(l.label).width + 40;
    });
}

function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    const icons = { success: '✅', error: '❌', warning: '⚠️', info: 'ℹ️' };
    toast.className = `toast ${type}`;
    toast.innerHTML = `<span>${icons[type] || 'ℹ️'}</span><span>${message}</span>`;
    container.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(100%)';
        toast.style.transition = 'all 0.3s';
        setTimeout(() => toast.remove(), 300);
    }, 3500);
}

function showAlertBanner(message) {
    const banner = document.getElementById('alertBanner');
    document.getElementById('alertText').textContent = message;
    banner.style.display = 'block';
}

function setupSearch() {
    const input = document.getElementById('searchInput');
    const results = document.getElementById('searchResults');
    const btn = document.getElementById('searchBtn');

    function performSearch() {
        const q = input.value.trim().toLowerCase();
        if (!q) { results.classList.remove('active'); results.innerHTML = ''; return; }
        const matched = appState.sites
            .filter(s => s.name.toLowerCase().includes(q))
            .slice(0, 10);

        if (matched.length === 0) {
            results.innerHTML = '<div class="search-result-item"><span class="search-result-meta">未找到匹配的遗迹</span></div>';
        } else {
            results.innerHTML = matched.map(s => `
                <div class="search-result-item" data-id="${s.id}">
                    <div class="search-result-name">${escapeHtml(s.name)}</div>
                    <div class="search-result-meta">${s.dynasty} · ${s.site_type} · ${s.preservation_status}</div>
                </div>
            `).join('');
        }
        results.classList.add('active');
    }

    input.addEventListener('input', performSearch);
    btn.addEventListener('click', performSearch);
    input.addEventListener('keypress', e => e.key === 'Enter' && performSearch());

    results.addEventListener('click', e => {
        const item = e.target.closest('.search-result-item');
        if (item && item.dataset.id) {
            selectSite(parseInt(item.dataset.id));
            results.classList.remove('active');
            input.value = '';
        }
    });

    document.addEventListener('click', e => {
        if (!e.target.closest('.search-box')) results.classList.remove('active');
    });
}

async function handleRestoreAll() {
    if (!confirm('确认计算全部300处遗迹的功能复原？可能需要较长时间。')) return;
    showToast('正在计算功能复原...', 'info');
    try {
        const res = await fetch(`${API_BASE}/restore-all`, { method: 'POST' });
        const result = await res.json();
        showToast(`功能复原完成：成功 ${result.success}/${result.processed}`, 'success');
        loadSites();
        loadStatistics();
        if (appState.showSupplyRange) loadSupplyRanges();
    } catch (e) {
        showToast('计算失败', 'error');
    }
}

async function handleAssessAll() {
    if (!confirm('确认对全部遗迹进行可持续性评估？')) return;
    showToast('正在评估可持续性...', 'info');
    try {
        const res = await fetch(`${API_BASE}/assess-all`, { method: 'POST' });
        const result = await res.json();
        showToast(`评估完成：成功 ${result.success}/${result.processed}`, 'success');
        loadSites();
        loadStatistics();
    } catch (e) {
        showToast('评估失败', 'error');
    }
}

async function handleImportData() {
    if (!confirm('确认导入模拟数据？会先导入水文数据，再导入遗迹数据。')) return;
    showToast('正在导入水文数据...', 'info');
    try {
        await fetch(`${API_BASE}/import/hydrology`, { method: 'POST' });
        showToast('水文数据导入完成，正在导入遗迹...', 'info');
        const res = await fetch(`${API_BASE}/import/sites`, { method: 'POST' });
        const r = await res.json();
        showToast(`导入完成：新增 ${r.imported} 处遗迹`, 'success');
        loadSites();
        loadStatistics();
    } catch (e) {
        showToast('导入失败：' + e.message, 'error');
        console.error(e);
    }
}

function setupEventListeners() {
    document.getElementById('applyFilter').addEventListener('click', applyFilters);
    document.getElementById('resetFilter').addEventListener('click', resetFilters);

    document.getElementById('restoreAllBtn').addEventListener('click', handleRestoreAll);
    document.getElementById('assessAllBtn').addEventListener('click', handleAssessAll);
    document.getElementById('importDataBtn').addEventListener('click', handleImportData);

    document.getElementById('showSupplyRange').addEventListener('change', e => {
        appState.showSupplyRange = e.target.checked;
        if (appState.supplyRangeRenderer) {
            if (e.target.checked) {
                appState.supplyRangeRenderer.show();
            } else {
                appState.supplyRangeRenderer.hide();
            }
        } else {
            if (e.target.checked) {
                if (appState.supplyRanges.length === 0) loadSupplyRanges();
                appState.supplyRangesLayer.addTo(appState.map);
            } else {
                appState.supplyRangesLayer.remove();
            }
        }
    });
    document.getElementById('showHexagon').addEventListener('change', e => {
        appState.showHexagon = e.target.checked;
        renderSites();
    });
    document.getElementById('sizeByArea').addEventListener('change', e => {
        appState.sizeByArea = e.target.checked;
        renderSites();
    });
    document.getElementById('colorByStatus').addEventListener('change', e => {
        appState.colorByStatus = e.target.checked;
        renderSites();
    });

    document.getElementById('closePanel').addEventListener('click', () => {
        document.getElementById('panelContent').innerHTML = `
            <div class="empty-state">
                <p>在地图上点击遗迹以查看详细信息</p>
                <div class="hint-icon">🗺️</div>
            </div>`;
        appState.selectedSite = null;
    });

    document.getElementById('alertClose').addEventListener('click', () => {
        document.getElementById('alertBanner').style.display = 'none';
    });

    let resizeTimer;
    window.addEventListener('resize', () => {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(() => {
            if (appState.selectedSite) selectSite(appState.selectedSite);
        }, 200);
    });

    setupSearch();
}

window.selectSite = selectSite;

document.addEventListener('DOMContentLoaded', () => {
    initMap();
    setupEventListeners();
});
