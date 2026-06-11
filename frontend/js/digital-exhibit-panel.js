/**
 * 数字化展示与VR面板 v1.0
 *
 * 特性：
 * - 动态插入Tab到现有详情面板
 * - 照片上传区 + 重建方法选择
 * - 9步进度条 + 重建状态
 * - 3D模型查看器占位（伪3D旋转动画）
 * - VR热点列表
 * - 重建日志accordion
 */

const API_BASE_EXHIBIT = `${window.location.origin}/api`;

const RECONSTRUCTION_STEPS = [
    { key: 'upload',       name: '上传照片',        icon: '📷' },
    { key: 'feature',       name: '特征点提取',      icon: '🔍' },
    { key: 'match',         name: '特征点匹配',      icon: '🔗' },
    { key: 'sparse',       name: '稀疏点云生成',    icon: '✨' },
    { key: 'dense',        name: '稠密重建',        icon: '🌐' },
    { key: 'mesh',         name: '网格生成',        icon: '📐' },
    { key: 'texture',    name: '纹理映射',        icon: '🎨' },
    { key: 'optimize',     name: '模型优化',        icon: '⚡' },
    { key: 'complete',     name: '输出完成',        icon: '✅' }
];

class DigitalExhibitPanel {
    constructor(options = {}) {
        this.options = Object.assign({
            threeCDN: 'https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js'
        }, options);

        this.sitePanelEl = null;
        this.currentSiteId = null;
        this.reconstructionStatus = null;
        this.modelData = null;
        this.vrHotspots = [];
        this.reconstructionLogs = [];
        this._statusPollTimer = null;
        this._tabContainerEl = null;
        this._tabContentEl = null;
        this._3dCanvasEl = null;
        this._3dCtx = null;
        this._rotationAnimFrame = null;
        this._viewParams = { rotX: 0.3, rotY: 0, zoom: 1, rotVx: 0.004, rotVy: 0.006, isDragging: false, lastX: 0, lastY: 0, showIrrigation: false, vrMode: false };

        this._methodOptions = [
            { value: 'sfm',     name: 'SfM 运动恢复结构', desc: '适用于大量无序照片，全自动' },
            { value: 'nerf',      name: 'NeRF 神经辐射场', desc: '高质量新视角合成，精度高' },
            { value: 'photogrammetry', name: '摄影测量法', desc: '传统算法，快速' }
        ];
    }

    init(sitePanelEl) {
        this.sitePanelEl = sitePanelEl;
        this._injectStyles();
        this._buildTabStructure();
        this.bindEvents();
    }

    _injectStyles() {
        if (document.getElementById('digital-exhibit-styles')) return;
        const style = document.createElement('style');
        style.id = 'digital-exhibit-styles';
        style.textContent = `
            .de-tabs { display: flex; border-bottom: 1px solid #e2e8f0; margin-bottom: 14px; margin-top: 16px; }
            .de-tab { padding: 8px 16px; cursor: pointer; font-size: 13px; color: #718096; border-bottom: 2px solid transparent; transition: all 0.2s; user-select: none; }
            .de-tab.active { color: #2b6cb0; border-bottom-color: #2b6cb0; font-weight: 600; }
            .de-tab:hover:not(.active):hover { color: #4a5568; background: #f7fafc; }
            .de-panel { display: none; animation: fadeIn 0.3s ease; }
            .de-panel.active { display: block; }
            @keyframes fadeIn { from { opacity: 0; opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }

            .de-upload-zone { border: 2px dashed #cbd5e0; border-radius: 8px; padding: 24px; text-align: center; cursor: pointer; transition: all 0.2s; background: #f7fafc; margin-bottom: 14px; }
            .de-upload-zone.dragover { border-color: #4299e1; background: #ebf8ff; }
            .de-upload-zone-icon { font-size: 40px; margin-bottom: 8px; }
            .de-upload-zone-text { color: #4a5568; font-size: 13px; }
            .de-upload-zone-hint { color: #a0aec0; font-size: 11px; margin-top: 4px; }

            .de-form-row { margin-bottom: 12px; }
            .de-form-label { display: block; font-size: 12px; color: #4a5568; margin-bottom: 4px; font-weight: 600; }
            .de-select, .de-btn { width: 100%; }
            .de-select { padding: 7px 10px; border: 1px solid #cbd5e0; border-radius: 5px; font-size: 12px; background: white; }
            .de-btn { padding: 9px 14px; border: none; border-radius: 6px; font-size: 13px; font-weight: 600; cursor: pointer; transition: all 0.2s; }
            .de-btn-primary { background: #2b6cb0; color: white; }
            .de-btn-primary:hover:not(:disabled) { background: #2c5282; }
            .de-btn:disabled { opacity: 0.6; cursor: not-allowed; }
            .de-btn-secondary { background: #e2e8f0; color: #2d3748; }
            .de-btn-secondary:hover { background: #cbd5e0; }
            .de-btn-small { padding: 6px 10px; font-size: 11px; }

            .de-progress-wrap { background: #f7fafc; border-radius: 8px; padding: 12px; margin-bottom: 14px; }
            .de-progress-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
            .de-progress-stage { font-size: 12px; font-weight: 600; color: #2d3748; }
            .de-progress-pct { font-size: 12px; color: #2b6cb0; font-weight: 700; }
            .de-progress-bar { height: 8px; background: #e2e8f0; border-radius: 4px; overflow: hidden; margin-bottom: 10px; }
            .de-progress-fill { height: 100%; background: linear-gradient(90deg, #4299e1, #2b6cb0); border-radius: 4px; transition: width 0.4s ease; }

            .de-steps { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; }
            .de-step { padding: 8px 6px; background: white; border-radius: 5px; text-align: center; font-size: 11px; color: #a0aec0; border: 1px solid #e2e8f0; opacity: 0.7; }
            .de-step.active { background: #ebf8ff; color: #2b6cb0; border-color: #bee3f8; font-weight: 600; opacity: 1; }
            .de-step.done { background: #f0fff4; color: #2f855a; border-color: #c6f6d5; }
            .de-step-icon { font-size: 16px; display: block; margin-bottom: 3px; }

            .de-viewer-wrap { border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden; margin-bottom: 14px; background: #1a202c; }
            .de-viewer-canvas { width: 100%; height: 220px; display: block; background: radial-gradient(ellipse at center, #2d3748 0%, #1a202c 70%); }
            .de-viewer-toolbar { display: flex; gap: 4px; padding: 8px; background: #f7fafc; border-top: 1px solid #e2e8f0; flex-wrap: wrap; align-items: center; }
            .de-viewer-btn { padding: 5px 9px; font-size: 11px; background: white; border: 1px solid #e2e8f0; border-radius: 4px; cursor: pointer; transition: all 0.15s; }
            .de-viewer-btn:hover { background: #edf2f7; }
            .de-viewer-btn.active { background: #bee3f8; border-color: #4299e1; color: #2b6cb0; }
            .de-viewer-spacer { flex: 1; }

            .de-checkbox-label { font-size: 11px; color: #4a5568; display: inline-flex; align-items: center; gap: 4px; user-select: none; }
            .de-checkbox { }

            .de-hotspots { margin-bottom: 14px; }
            .de-hotspots-title { font-size: 12px; font-weight: 600; color: #2d3748; margin-bottom: 8px; }
            .de-hotspot-list { display: flex; flex-direction: column; gap: 5px; max-height: 150px; overflow-y: auto; }
            .de-hotspot-item { padding: 7px 10px; background: #f7fafc; border-radius: 5px; cursor: pointer; font-size: 12px; display: flex; justify-content: space-between; align-items: center; border: 1px solid transparent; transition: all 0.15s; }
            .de-hotspot-item:hover { background: #ebf8ff; border-color: #bee3f8; }
            .de-hotspot-pos { font-size: 10px; color: #718096; font-family: monospace; }

            .de-log-wrap { }
            .de-log-title { font-size: 12px; font-weight: 600; color: #2d3748; margin-bottom: 8px; }
            .de-accordion { border: 1px solid #e2e8f0; border-radius: 6px; overflow: hidden; }
            .de-accordion-item { border-bottom: 1px solid #e2e8f0; }
            .de-accordion-item:last-child { border-bottom: none; }
            .de-accordion-head { padding: 8px 12px; background: #f7fafc; cursor: pointer; display: flex; justify-content: space-between; align-items: center; font-size: 12px; font-weight: 500; color: #4a5568; user-select: none; }
            .de-accordion-head:hover { background: #edf2f7; }
            .de-accordion-body { padding: 0 12px; background: white; display: none; }
            .de-accordion-item.open .de-accordion-body { display: block; }
            .de-accordion-item.open .de-accordion-head { background: #ebf8ff; color: #2b6cb0; }
            .de-accordion-icon { transition: transform 0.2s; }
            .de-accordion-item.open .de-accordion-icon { transform: rotate(90deg); }
            .de-log-line { font-family: monospace; font-size: 11px; color: #4a5568; padding: 4px 0; border-bottom: 1px dashed #edf2f7; white-space: pre-wrap; word-break: break-all; }
            .de-log-line:last-child { border-bottom: none; }
            .de-log-time { color: #a0aec0; margin-right: 6px; }

            .de-empty { padding: 16px; text-align: center; color: #a0aec0; font-size: 12px; }
            .de-tag { display: inline-block; padding: 2px 7px; border-radius: 10px; font-size: 10px; font-weight: 600; }
            .de-tag-ok { background: #c6f6d5; color: #22543d; }
            .de-tag-info { background: #bee3f8; color: #2a4365; }
            .de-tag-warn { background: #feebc8; color: #7b341e; }
        `;
        document.head.appendChild(style);
    }

    _buildTabStructure() {
        const header = this.sitePanelEl.querySelector('.panel-header') || this.sitePanelEl;
        const tabContainer = document.createElement('div');
        tabContainer.className = 'de-tabs';
        tabContainer.innerHTML = `
            <div class="de-tab" data-tab="basic">基本信息</div>
            <div class="de-tab active" data-tab="3dvr">3D/VR</div>
        `;
        this.sitePanelEl.insertBefore(tabContainer, this.sitePanelEl.querySelector('.panel-content') || header.nextSibling);

        const contentWrap = this.sitePanelEl.querySelector('.panel-content') || this.sitePanelEl;
        this._basicContent = contentWrap;

        this._3dvrPanel = document.createElement('div');
        this._3dvrPanel.className = 'de-panel active';
        this._3dvrPanel.innerHTML = this._render3dvrHtml();
        contentWrap.parentNode.insertBefore(this._3dvrPanel, contentWrap.nextSibling);

        tabContainer.querySelectorAll('.de-tab').forEach(tab => {
            tab.addEventListener('click', () => {
                tabContainer.querySelectorAll('.de-tab').forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                const key = tab.dataset.tab;
                if (key === 'basic') {
                    contentWrap.style.display = 'block';
                    this._3dvrPanel.classList.remove('active');
                } else {
                        contentWrap.style.display = 'none';
                        this._3dvrPanel.classList.add('active');
                        setTimeout(() => this._init3dCanvas(), 50);
                    }
            });
        });
    }

    _render3dvrHtml() {
        return `
            <div class="de-upload-zone" id="deUploadZone">
                <div class="de-upload-zone-icon">📸</div>
                <div class="de-upload-zone-text">拖拽照片到此或点击上传</div>
                <div class="de-upload-zone-hint">支持 JPG/PNG，建议 20 张以上多角度照片</div>
                <input type="file" id="deFileInput" multiple accept="image/*" style="display:none;">
            </div>

            <div class="de-form-row">
                <label class="de-form-label">重建方法</label>
                <select class="de-select" id="deMethodSelect">
                    ${this._methodOptions.map(m => `<option value="${m.value}">${m.name} — ${m.desc}</option>`).join('')}
                </select>
            </div>

            <button class="de-btn de-btn-primary" id="deStartBtn" style="margin-bottom:14px;">🚀 开始重建</button>

            <div class="de-progress-wrap" id="deProgressWrap" style="display:none;">
                <div class="de-progress-header">
                    <span class="de-progress-stage" id="deProgressStage">等待中...</span>
                    <span class="de-progress-pct" id="deProgressPct">0%</span>
                </div>
                <div class="de-progress-bar"><div class="de-progress-fill" id="deProgressFill" style="width:0%"></div></div>
                <div class="de-steps" id="deSteps">
                    ${RECONSTRUCTION_STEPS.map(s => `<div class="de-step" data-key="${s.key}"><span class="de-step-icon">${s.icon}</span>${s.name}</div>`).join('')}
                </div>
            </div>

            <div class="de-viewer-wrap" id="deViewerWrap" style="display:none;">
                <canvas class="de-viewer-canvas" id="de3dCanvas"></canvas>
                <div class="de-viewer-toolbar">
                    <button class="de-viewer-btn" data-act="zoom-in">🔍+</button>
                    <button class="de-viewer-btn" data-act="zoom-out">🔍-</button>
                    <button class="de-viewer-btn" data-act="rotate-left">↺</button>
                    <button class="de-viewer-btn" data-act="rotate-right">↻</button>
                    <button class="de-viewer-btn" data-act="pan-up">↑</button>
                    <button class="de-viewer-btn" data-act="pan-down">↓</button>
                    <div class="de-viewer-spacer"></div>
                    <label class="de-checkbox-label"><input type="checkbox" class="de-checkbox" id="deShowIrrigation"> 叠加灌溉区</label>
                    <button class="de-viewer-btn" id="deToggleVR">🥽 VR模式</button>
                    <button class="de-viewer-btn" id="deToggleAR">📱 AR模式</button>
                </div>
            </div>

            <div class="de-hotspots" id="deHotspotsWrap" style="display:none;">
                <div class="de-hotspots-title">📍 VR热点 (${this.vrHotspots.length})</div>
                <div class="de-hotspot-list" id="deHotspotList"></div>
            </div>

            <div class="de-log-wrap">
                <div class="de-log-title">📋 重建日志</div>
                <div class="de-accordion" id="deAccordion">
                    ${RECONSTRUCTION_STEPS.map(s => `
                        <div class="de-accordion-item" data-key="${s.key}">
                            <div class="de-accordion-head">
                        <span>${s.icon} ${s.name}</span>
                        <span class="de-accordion-icon">▶</span>
                    </div>
                    <div class="de-accordion-body"></div>
                </div>
                    `).join('')}
                </div>
            </div>
        `;
    }

    bindEvents() {
        const uploadZone = this.sitePanelEl.querySelector('#deUploadZone');
        const fileInput = this.sitePanelEl.querySelector('#deFileInput');
        uploadZone?.addEventListener('click', () => fileInput?.click());
        uploadZone?.addEventListener('dragover', (e) => { e.preventDefault(); uploadZone.classList.add('dragover'); });
        uploadZone?.addEventListener('dragleave', () => uploadZone.classList.remove('dragover'));
        uploadZone?.addEventListener('drop', (e) => {
            e.preventDefault();
            uploadZone.classList.remove('dragover');
            if (e.dataTransfer?.files?.length) {
                this._handleFiles(e.dataTransfer.files);
            }
        });
        fileInput?.addEventListener('change', (e) => {
            if (e.target.files?.length) this._handleFiles(e.target.files);
        });

        const startBtn = this.sitePanelEl.querySelector('#deStartBtn');
        startBtn?.addEventListener('click', () => this._startReconstruction());

        this.sitePanelEl.querySelectorAll('.de-viewer-btn')?.forEach(btn => {
            const act = btn.dataset.act;
            if (!act) return;
            btn.addEventListener('click', () => this._handleViewerAction(act));
        });

        this.sitePanelEl.querySelector('#deShowIrrigation')?.addEventListener('change', (e) => {
            this._viewParams.showIrrigation = e.target.checked;
        });

        this.sitePanelEl.querySelector('#deToggleVR')?.addEventListener('click', (e) => {
            this._viewParams.vrMode = !this._viewParams.vrMode;
            e.currentTarget.classList.toggle('active', this._viewParams.vrMode);
            showToast(this._viewParams.vrMode ? 'VR模式已开启（占位模拟' : 'VR模式已关闭', 'info');
        });

        this.sitePanelEl.querySelectorAll('.de-accordion-item')?.forEach(item => {
            const head = item.querySelector('.de-accordion-head');
            head?.addEventListener('click', () => item.classList.toggle('open'));
        });

        const canvas = this.sitePanelEl.querySelector('#de3dCanvas');
        if (canvas) {
            canvas.addEventListener('mousedown', (e) => { this._viewParams.isDragging = true; this._viewParams.lastX = e.clientX; this._viewParams.lastY = e.clientY; });
            window.addEventListener('mouseup', () => this._viewParams.isDragging = false);
            window.addEventListener('mousemove', (e) => {
                if (this._viewParams.isDragging) {
                    const dx = e.clientX - this._viewParams.lastX;
                    const dy = e.clientY - this._viewParams.lastY;
                    this._viewParams.rotY += dx * 0.01;
                    this._viewParams.rotX += dy * 0.01;
                    this._viewParams.lastX = e.clientX;
                    this._viewParams.lastY = e.clientY;
                }
            });
            canvas.addEventListener('wheel', (e) => {
                e.preventDefault();
                this._viewParams.zoom *= e.deltaY > 0 ? 0.9 : 1.1;
                this._viewParams.zoom = Math.max(0.3, Math.min(3, this._viewParams.zoom));
            }, { passive: false });
        }
    }

    _handleFiles(files) {
        showToast(`已选择 ${files.length} 张照片，准备重建...`, 'info');
    }

    async _startReconstruction() {
        if (!this.currentSiteId) return;
        const method = this.sitePanelEl.querySelector('#deMethodSelect')?.value || 'sfm';
        showToast('正在启动重建任务...', 'info');
        try {
            const res = await fetch(`${API_BASE_EXHIBIT}/sites/${this.currentSiteId}/reconstruct`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ method, photos_count: 42 })
            });
            if (!res.ok) throw new Error('请求失败');
            this._startStatusPoll();
        } catch (e) {
            console.warn('启动重建失败:', e);
            showToast('启动重建失败，使用模拟进度', 'warning');
            this._simulateProgress();
        }
    }

    _startStatusPoll() {
        clearInterval(this._statusPollTimer);
        const wrap = this.sitePanelEl.querySelector('#deProgressWrap');
        if (wrap) wrap.style.display = 'block';
        this._statusPollTimer = setInterval(async () => {
            try {
                const res = await fetch(`${API_BASE_EXHIBIT}/sites/${this.currentSiteId}/status`);
                if (res.ok) {
                    const status = await res.json();
                    this.updateProgress(status);
                    if (status?.step === 'complete' || status?.progress >= 100) {
                        clearInterval(this._statusPollTimer);
                        this._showViewer();
                    }
                }
            } catch (e) {
                console.warn('轮询状态失败:', e);
            }
        }, 2000);
    }

    _simulateProgress() {
        clearInterval(this._statusPollTimer);
        const wrap = this.sitePanelEl.querySelector('#deProgressWrap');
        if (wrap) wrap.style.display = 'block';
        let stepIdx = 0;
        let progress = 0;
        this._statusPollTimer = setInterval(() => {
            progress += Math.random() * 8 + 2;
            if (progress >= 100) progress = 100;
            const stepKey = RECONSTRUCTION_STEPS[Math.min(stepIdx, RECONSTRUCTION_STEPS.length - 1)].key;
            if (progress > (stepIdx + 1) * (100 / 9) && stepIdx < RECONSTRUCTION_STEPS.length - 1) stepIdx++;
            this.updateProgress({
                step: stepKey, progress: Math.round(progress), stage_name: RECONSTRUCTION_STEPS[stepIdx].name,
                logs: [{ time: new Date().toISOString(), message: `正在执行${RECONSTRUCTION_STEPS[stepIdx].name}...` }]
            });
            if (progress >= 100) {
                clearInterval(this._statusPollTimer);
                setTimeout(() => this._showViewer(), 500);
            }
        }, 800);
    }

    updateProgress(status) {
        this.reconstructionStatus = status;
        const stageEl = this.sitePanelEl.querySelector('#deProgressStage');
        const pctEl = this.sitePanelEl.querySelector('#deProgressPct');
        const fillEl = this.sitePanelEl.querySelector('#deProgressFill');
        const pct = Math.max(0, Math.min(100, status?.progress ?? 0));
        const stageName = status?.stage_name || status?.step || '处理中';
        if (stageEl) stageEl.textContent = stageName;
        if (pctEl) pctEl.textContent = pct.toFixed(0) + '%';
        if (fillEl) fillEl.style.width = pct + '%';
        const stepEl = this.sitePanelEl.querySelector('#deSteps');
        if (stepEl) {
            const currentIdx = RECONSTRUCTION_STEPS.findIndex(s => s.key === (status?.step || 'upload'));
            stepEl.querySelectorAll('.de-step').forEach((el, i) => {
                el.classList.remove('active', 'done');
                if (i < currentIdx) el.classList.add('done');
                else if (i === currentIdx) el.classList.add('active');
            });
        }
        if (status?.logs?.length) this._appendLogs(status.step || 'upload', status.logs);
    }

    _appendLogs(stepKey, logs) {
        const accItem = this.sitePanelEl.querySelector(`.de-accordion-item[data-key="${stepKey}"]`);
        if (!accItem) return;
        const body = accItem.querySelector('.de-accordion-body');
        if (!body) return;
        logs.forEach(log => {
            const line = document.createElement('div');
            line.className = 'de-log-line';
            const timeStr = log.time ? new Date(log.time).toLocaleTimeString() : new Date().toLocaleTimeString();
            line.innerHTML = `<span class="de-log-time">[${timeStr}]</span>${escapeHtml(log.message || '')}`;
            body.appendChild(line);
        });
    }

    _showViewer() {
        const wrap = this.sitePanelEl.querySelector('#deViewerWrap');
        const hotWrap = this.sitePanelEl.querySelector('#deHotspotsWrap');
        if (wrap) wrap.style.display = 'block';
        if (hotWrap) hotWrap.style.display = 'block';
        this._renderHotspots([
            { name: '进水口', pos: 'X:0.2,Y:0.3,Z:-0.1' },
            { name: '主坝体', pos: 'X:0.0,Y:0.1,Z:0.5' },
            { name: '泄洪道', pos: 'X:-0.4,Y:0.2,Z:0.2' },
            { name: '古渠首', pos: 'X:0.3,Y:0.15,Z:-0.3' }
        ]);
        setTimeout(() => this._init3dCanvas(), 50);
        showToast('3D模型重建完成！', 'success');
    }

    _renderHotspots(hotspots) {
        this.vrHotspots = hotspots;
        const title = this.sitePanelEl.querySelector('#deHotspotsTitle');
        const list = this.sitePanelEl.querySelector('#deHotspotList');
        if (title) title.textContent = `📍 VR热点 (${hotspots.length})`;
        if (!list) return;
        list.innerHTML = hotspots.map((h, i) => `
            <div class="de-hotspot-item" data-idx="${i}">
                <span>🎯 ${escapeHtml(h.name)}</span>
                <span class="de-hotspot-pos">${escapeHtml(h.pos)}</span>
            </div>
        `).join('');
        list.querySelectorAll('.de-hotspot-item').forEach(el => {
            el.addEventListener('click', () => {
                const idx = parseInt(el.dataset.idx);
                const hs = hotspots[idx];
                this._flyToHotspot(hs);
                showToast(`跳转到：${hs.name}`, 'info');
            });
        });
    }

    _flyToHotspot(hs) {
        this._viewParams.rotY += (Math.random() - 0.5) * 0.5;
        this._viewParams.rotX = 0.2 + Math.random() * 0.3;
        this._viewParams.zoom = 1.4;
    }

    _init3dCanvas() {
        const canvas = this.sitePanelEl.querySelector('#de3dCanvas');
        if (!canvas) return;
        this._3dCanvasEl = canvas;
        const dpr = window.devicePixelRatio || 1;
        const rect = canvas.getBoundingClientRect();
        canvas.width = rect.width * dpr;
        canvas.height = rect.height * dpr;
        const ctx = canvas.getContext('2d');
        ctx.scale(dpr, dpr);
        this._3dCtx = ctx;
        this._start3dLoop();
    }

    _start3dLoop() {
        cancelAnimationFrame(this._rotationAnimFrame);
        const loop = () => {
            this._draw3dScene();
            this._rotationAnimFrame = requestAnimationFrame(loop);
        };
        this._rotationAnimFrame = requestAnimationFrame(loop);
    }

    _handleViewerAction(act) {
        switch (act) {
            case 'zoom-in': this._viewParams.zoom = Math.min(3, this._viewParams.zoom * 1.2); break;
            case 'zoom-out': this._viewParams.zoom = Math.max(0.3, this._viewParams.zoom / 1.2); break;
            case 'rotate-left': this._viewParams.rotY -= 0.3; break;
            case 'rotate-right': this._viewParams.rotY += 0.3; break;
            case 'pan-up': this._viewParams.rotX -= 0.2; break;
            case 'pan-down': this._viewParams.rotX += 0.2; break;
        }
    }

    _draw3dScene() {
        if (!this._3dCtx || !this._3dCanvasEl) return;
        const ctx = this._3dCtx;
        const canvas = this._3dCanvasEl;
        const rect = canvas.getBoundingClientRect();
        const W = rect.width;
        const H = rect.height;
        ctx.clearRect(0, 0, W, H);

        if (!this._viewParams.isDragging) {
            this._viewParams.rotY += this._viewParams.rotVy;
        }

        const cx = W / 2;
        const cy = H / 2;
        const scale = Math.min(W, H) * 0.28 * this._viewParams.zoom;
        const cosX = Math.cos(this._viewParams.rotX);
        const sinX = Math.sin(this._viewParams.rotX);
        const cosY = Math.cos(this._viewParams.rotY);
        const sinY = Math.sin(this._viewParams.rotY);

        const project = (x, y, z) => {
            let x1 = x * cosY - z * sinY;
            let z1 = x * sinY + z * cosY;
            let y1 = y * cosX - z1 * sinX;
            let z2 = y * sinX + z1 * cosX;
            const persp = 3 / (3 + z2);
            return [cx + x1 * scale * persp, cy - y1 * scale * persp, z2];
        };

        const damVerts = [
            [-1, -0.4, -0.6], [1, -0.4, -0.6], [1, 0.3, -0.4], [-1, 0.3, -0.4],
            [-1, -0.4, 0.6], [1, -0.4, 0.6], [1, 0.1, 0.5], [-1, 0.1, 0.5]
        ];

        const damFaces = [
            { v: [0, 1, 2, 3], c: '#8b5a2b' },
            { v: [4, 5, 6, 7], c: '#a0522d' },
            { v: [0, 3, 7, 4], c: '#6b4226' },
            { v: [1, 5, 6, 2], c: '#7b341e' },
            { v: [3, 2, 6, 7], c: '#cd853f' },
            { v: [0, 4, 5, 1], c: '#8b4513' }
        ];

        const waterVerts = [
            [-0.9, -0.4, -0.55], [0.9, -0.4, -0.55], [0.9, -0.35, -0.3], [-0.9, -0.35, -0.3],
            [-0.9, -0.4, 0.55], [0.9, -0.4, 0.55], [0.9, -0.35, 0.4], [-0.9, -0.35, 0.4]
        ];

        const groundVerts = [
            [-1.5, -0.5, -1.2], [1.5, -0.5, -1.2], [1.5, -0.5, 1.2], [-1.5, -0.5, 1.2]
        ];

        const shade = (hex, fz) => {
            const h = hex.replace('#', '');
            const bigint = parseInt(h, 16);
            let r = (bigint >> 16) & 255, g = (bigint >> 8) & 255, b = bigint & 255;
            const s = 0.6 + Math.max(0, Math.min(1, 0.4 - fz * 0.35));
            return `rgb(${Math.round(r * s)},${Math.round(g * s)},${Math.round(b * s)})`;
        };

        const projectedDam = damVerts.map(v => project(...v));
        const damFacesZ = damFaces.map(f => {
            const zAvg = f.v.reduce((s, i) => s + projectedDam[i][2], 0) / f.v.length;
            return { ...f, z: zAvg };
        }).sort((a, b) => b.z - a.z);

        damFacesZ.forEach(f => {
            ctx.beginPath();
            const p0 = projectedDam[f.v[0]];
            ctx.moveTo(p0[0], p0[1]);
            for (let i = 1; i < f.v.length; i++) {
                const p = projectedDam[f.v[i]];
                ctx.lineTo(p[0], p[1]);
            }
            ctx.closePath();
            ctx.fillStyle = shade(f.c, f.z);
            ctx.fill();
            ctx.strokeStyle = 'rgba(0,0,0,0.4)';
            ctx.lineWidth = 1;
            ctx.stroke();
        });

        const pw = waterVerts.map(v => project(...v));
        const waterFaces = [
            { v: [0, 1, 2, 3], z: (pw[0][2] + pw[1][2] + pw[2][2] + pw[3][2]) / 4 },
            { v: [4, 5, 6, 7], z: (pw[4][2] + pw[5][2] + pw[6][2] + pw[7][2]) / 4 },
            { v: [0, 3, 7, 4], z: (pw[0][2] + pw[3][2] + pw[7][2] + pw[4][2]) / 4 },
            { v: [1, 5, 6, 2], z: (pw[1][2] + pw[5][2] + pw[6][2] + pw[2][2]) / 4 },
            { v: [3, 2, 6, 7], z: (pw[3][2] + pw[2][2] + pw[6][2] + pw[7][2]) / 4 },
            { v: [0, 4, 5, 1], z: (pw[0][2] + pw[4][2] + pw[5][2] + pw[1][2]) / 4 }
        ].sort((a, b) => b.z - a.z);

        waterFaces.forEach(f => {
            ctx.beginPath();
            const p0 = pw[f.v[0]];
            ctx.moveTo(p0[0], p0[1]);
            for (let i = 1; i < f.v.length; i++) {
                const p = pw[f.v[i]];
                ctx.lineTo(p[0], p[1]);
            }
            ctx.closePath();
            ctx.fillStyle = `rgba(66, 153, 225, ${0.55 - f.z * 0.1})`;
            ctx.fill();
            ctx.strokeStyle = 'rgba(49, 130, 206, 0.8)';
            ctx.lineWidth = 0.8;
            ctx.stroke();
        });

        if (this._viewParams.showIrrigation) {
            const igVerts = [
                [-2.2, -0.49, -0.8], [2.2, -0.49, -0.8],
                [2.8, -0.49, 0.2], [-2.8, -0.49, 0.2],
                [3.2, -0.49, 1.0], [-3.2, -0.49, 1.0]
            ];
            const igPts = igVerts.map(v => project(...v));
            const fillRings = [
                [igPts[0], igPts[1], igPts[3], igPts[2]],
                [igPts[2], igPts[3], igPts[5], igPts[4]]
            ];
            fillRings.forEach(ring => {
                ctx.beginPath();
                ctx.moveTo(ring[0][0], ring[0][1]);
                for (let i = 1; i < ring.length; i++) ctx.lineTo(ring[i][0], ring[i][1]);
                ctx.closePath();
                ctx.fillStyle = 'rgba(104, 159, 56, 0.35)';
                ctx.fill();
                ctx.strokeStyle = 'rgba(56, 139, 38, 0.7)';
                ctx.lineWidth = 0.6;
                ctx.stroke();
            });
        }

        const gp = groundVerts.map(v => project(...v));
        ctx.beginPath();
        ctx.moveTo(gp[0][0], gp[0][1]);
        for (let i = 1; i < gp.length; i++) ctx.lineTo(gp[i][0], gp[i][1]);
        ctx.closePath();
        ctx.fillStyle = 'rgba(139, 119, 101, 0.3)';
        ctx.fill();
        ctx.strokeStyle = 'rgba(107, 66, 38, 0.5)';
        ctx.lineWidth = 0.8;
        ctx.stroke();

        if (this._viewParams.vrMode) {
            ctx.strokeStyle = 'rgba(66, 153, 225, 0.35)';
            ctx.lineWidth = 2;
            ctx.strokeRect(6, 6, W - 12, H - 12);
            ctx.beginPath();
            ctx.moveTo(W / 2, 6);
            ctx.lineTo(W / 2, H - 6);
            ctx.stroke();
            ctx.fillStyle = 'rgba(66, 153, 225, 0.9)';
            ctx.font = 'bold 12px sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText('🥽 VR 视图模式 (模拟)', W / 2, 22);
        }

        ctx.fillStyle = 'rgba(255, 255, 255, 0.85)';
        ctx.font = '10px sans-serif';
        ctx.textAlign = 'left';
        ctx.fillText(`旋转: (${this._viewParams.rotX.toFixed(2)}, ${this._viewParams.rotY.toFixed(2)}) 缩放: ${this._viewParams.zoom.toFixed(2)}x`, 10, H - 10);
    }

    async loadSite(site_id) {
        this.currentSiteId = site_id;
        clearInterval(this._statusPollTimer);
        this.reconstructionStatus = null;
        this._resetUI();
        try {
            const res = await fetch(`${API_BASE_EXHIBIT}/sites/${site_id}/status`);
            if (res.ok) {
                const status = await res.json();
                if (status) this.updateProgress(status);
                if (status?.step === 'complete' || status?.progress >= 100) {
                    this._showViewer();
                } else if (status?.progress > 0) {
                    const wrap = this.sitePanelEl.querySelector('#deProgressWrap');
                    if (wrap) wrap.style.display = 'block';
                    this._startStatusPoll();
                }
            }
        } catch (e) {
                console.warn('加载重建状态失败:', e);
            }
        try {
            const mRes = await fetch(`${API_BASE_EXHIBIT}/sites/${site_id}/model`);
            if (mRes.ok) this.modelData = await mRes.json();
        } catch (e) {
            console.warn('加载模型信息失败:', e);
        }
    }

    _resetUI() {
        const wrap = this.sitePanelEl.querySelector('#deProgressWrap');
        const vw = this.sitePanelEl.querySelector('#deViewerWrap');
        const hw = this.sitePanelEl.querySelector('#deHotspotsWrap');
        if (wrap) wrap.style.display = 'none';
        if (vw) vw.style.display = 'none';
        if (hw) hw.style.display = 'none';
        const fill = this.sitePanelEl.querySelector('#deProgressFill');
        if (fill) fill.style.width = '0%';
        this.sitePanelEl.querySelectorAll('.de-step').forEach(el => el.classList.remove('active', 'done'));
        this.sitePanelEl.querySelectorAll('.de-accordion-body').forEach(b => b.innerHTML = '');
        cancelAnimationFrame(this._rotationAnimFrame);
    }

    destroy() {
        clearInterval(this._statusPollTimer);
        cancelAnimationFrame(this._rotationAnimFrame);
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text || '';
    return div.innerHTML;
}
