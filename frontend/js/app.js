/**
 * 古代水利工程遗迹系统 - 主应用
 * 职责：状态管理、API调用、组件协调、事件绑定
 * 依赖：water_heritage_map.js、hydro_profile.js、supply-range-renderer.js
 * 新增依赖：benefit-renderer.js、climate-risk-renderer.js、network-layer.js、digital-exhibit-panel.js
 */

// ========== API 配置 ==========
const API_BASE = `${window.location.origin}/api`;

// ========== 应用状态 ==========
const appState = {
    map: null,
    sites: [],
    supplyRanges: [],
    selectedSite: null,
    benefitRenderer: null,
    climateRiskRenderer: null,
    networkLayer: null,
    digitalExhibitPanel: null,
    showBenefit: false,
    showClimateRisk: false,
    showNetwork: false,
    currentNetworkRegion: null,
    assessmentComputeLoading: null
};

// ========== 常量 ==========
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

const DEFAULT_RISK_SCENARIO = 'RCP4.5';
const DEFAULT_RISK_YEAR = 2050;

// ========== 初始化 ==========
function initApp() {
    appState.map = new WaterHeritageMap('map', {
        onSiteSelect: handleSiteSelect
    });

    if (typeof BenefitRenderer !== 'undefined') {
        appState.benefitRenderer = new BenefitRenderer(appState.map.map, {
            onClick: (hit) => {
                if (hit?.zone?.site_id) appState.map.selectSite(hit.zone.site_id);
            }
        });
        appState.benefitRenderer.hide();
    }

    if (typeof ClimateRiskRenderer !== 'undefined') {
        appState.climateRiskRenderer = new ClimateRiskRenderer(appState.map.map, {
            onClick: (zone) => {
                if (zone?.site_id) appState.map.selectSite(zone.site_id);
            }
        });
        appState.climateRiskRenderer.hide();
    }

    if (typeof NetworkLayer !== 'undefined') {
        appState.networkLayer = new NetworkLayer();
        appState.networkLayer.addTo(appState.map.map);
        appState.networkLayer.hide();
    }

    loadDynasties();
    loadSites();
    loadStatistics();
    checkAlerts();

    setupEventListeners();
    setupSearch();
    _injectAdvancedToolbar();

    setTimeout(() => {
        const detailPanel = document.getElementById('detailPanel');
        if (detailPanel && typeof DigitalExhibitPanel !== 'undefined') {
            appState.digitalExhibitPanel = new DigitalExhibitPanel();
            appState.digitalExhibitPanel.init(detailPanel);
        }
    }, 300);
}

function _injectAdvancedToolbar() {
    const sidebar = document.querySelector('.sidebar');
    if (!sidebar) return;

    const section = document.createElement('div');
    section.className = 'sidebar-section';
    section.id = 'advancedToolbar';
    section.innerHTML = `
        <h3>高级功能图层</h3>
        <label class="checkbox-item">
            <input type="checkbox" id="showBenefitZones">
            <span>显示受益区</span>
        </label>
        <div id="climateControlGroup" style="margin-top:4px;margin-left:22px;display:none;">
        </div>

        <label class="checkbox-item">
            <input type="checkbox" id="showClimateRisk">
            <span>显示气候风险区</span>
        </label>
        <div id="riskControlGroup" style="margin:4px 0 4px 22px;display:none;">
            <div style="font-size:11px;color:#718096;margin:4px 0;">
                <label style="display:inline-block;width:44px;">情景:</label>
                <select id="riskScenarioSelect" style="padding:2px 4px;font-size:11px;border:1px solid #cbd5e0;border-radius:3px;width:calc(100% - 50px);">
                    <option value="RCP2.6">RCP2.6 (低排放)</option>
                    <option value="RCP4.5" selected>RCP4.5 (中低)</option>
                    <option value="RCP8.5">RCP8.5 (高排放)</option>
                </select>
            </div>
            <div style="font-size:11px;color:#718096;margin:4px 0;">
                <label style="display:inline-block;width:44px;">年份:</label>
                <select id="riskYearSelect" style="padding:2px 4px;font-size:11px;border:1px solid #cbd5e0;border-radius:3px;width:calc(100% - 50px);">
                    <option value="2030">2030年</option>
                    <option value="2050" selected>2050年</option>
                    <option value="2070">2070年</option>
                    <option value="2100">2100年</option>
                </select>
            </div>
        </div>

        <label class="checkbox-item">
            <input type="checkbox" id="showNetwork">
            <span>显示水利网络</span>
        </label>
        <div id="networkControlGroup" style="margin:4px 0 4px 22px;display:none;">
            <div style="font-size:11px;color:#718096;margin:4px 0;">
                <label style="display:inline-block;width:44px;">区域:</label>
                <select id="networkRegionSelect" style="padding:2px 4px;font-size:11px;border:1px solid #cbd5e0;border-radius:3px;width:calc(100% - 50px);">
                    <option value="">-- 选择区域 --</option>
                    <option value="关中平原">关中平原</option>
                    <option value="成都平原">成都平原</option>
                    <option value="江南地区">江南地区</option>
                    <option value="中原地区">中原地区</option>
                </select>
            </div>
        </div>

        <button id="enterVRBtn" class="btn btn-info btn-small" style="margin-top:8px;width:100%;display:none;">🥽 进入VR模式</button>

        <button id="computeAllAssessments" class="btn btn-warning btn-small" style="margin-top:10px;width:100%;">
            ⚡ 一键计算全部新数据
        </button>
    `;

    const existingSections = sidebar.querySelectorAll('.sidebar-section');
    if (existingSections.length >= 3) {
        sidebar.insertBefore(section, existingSections[3]);
    } else {
        sidebar.appendChild(section);
    }

    const showBenefitEl = section.querySelector('#showBenefitZones');
    const showClimateEl = section.querySelector('#showClimateRisk');
    const showNetworkEl = section.querySelector('#showNetwork');
    const climateGroup = section.querySelector('#riskControlGroup');
    const riskScenarioEl = section.querySelector('#riskScenarioSelect');
    const riskYearEl = section.querySelector('#riskYearSelect');
    const regionEl = section.querySelector('#networkRegionSelect');
    const networkGroup = section.querySelector('#networkControlGroup');
    const vrBtn = section.querySelector('#enterVRBtn');
    const batchBtn = section.querySelector('#computeAllAssessments');

    showBenefitEl?.addEventListener('change', (e) => {
        appState.showBenefit = e.target.checked;
        if (appState.benefitRenderer) {
            e.target.checked ? appState.benefitRenderer.show() : appState.benefitRenderer.hide();
        }
        if (e.target.checked && appState.selectedSite) {
            _triggerLoadBenefitForSelected();
        }
    });

    showClimateEl?.addEventListener('change', (e) => {
        appState.showClimateRisk = e.target.checked;
        if (appState.climateRiskRenderer) {
            e.target.checked ? appState.climateRiskRenderer.show() : appState.climateRiskRenderer.hide();
        }
        if (climateGroup) climateGroup.style.display = e.target.checked ? 'block' : 'none';
        if (e.target.checked && appState.selectedSite) {
            _triggerLoadClimateForSelected();
        }
    });

    riskScenarioEl?.addEventListener('change', () => {
        if (appState.climateRiskRenderer) {
            const yr = parseInt(riskYearEl.value);
            appState.climateRiskRenderer.setScenario(riskScenarioEl.value, yr);
        }
    });
    riskYearEl?.addEventListener('change', () => {
        if (appState.climateRiskRenderer) {
            appState.climateRiskRenderer.setScenario(riskScenarioEl.value, parseInt(riskYearEl.value));
        }
    });

    showNetworkEl?.addEventListener('change', (e) => {
        appState.showNetwork = e.target.checked;
        if (appState.networkLayer) {
            e.target.checked ? appState.networkLayer.show() : appState.networkLayer.hide();
        }
        if (networkGroup) networkGroup.style.display = e.target.checked ? 'block' : 'none';
    });

    regionEl?.addEventListener('change', async () => {
        if (!appState.networkLayer || !regionEl.value) return;
        appState.currentNetworkRegion = regionEl.value;
        try {
            showToast(`加载网络数据: ${regionEl.value}...`, 'info');
            await appState.networkLayer.loadNetwork(regionEl.value);
            showToast('网络加载成功', 'success');
        } catch (e) {
            showToast('网络加载失败', 'error');
        }
    });

    vrBtn?.addEventListener('click', () => {
        showToast('VR模式启动中...（模拟', 'info');
    });

    batchBtn?.addEventListener('click', () => {
        if (appState.selectedSite) {
            _batchTriggerAllAssessments(appState.selectedSite);
        } else {
            showToast('请先选择一个遗迹', 'warning');
        }
    });
}

function _triggerLoadBenefitForSelected() {
}

function _triggerLoadClimateForSelected() {
}

// ========== 数据加载 ==========
async function loadDynasties() {
    try {
        const res = await fetch(`${API_BASE}/dynasties`);
        const dynasties = await res.json();
        const select = document.getElementById('filterDynasty');
        if (select) {
            dynasties.forEach(d => {
                const opt = document.createElement('option');
                opt.value = d.name;
                opt.textContent = `${d.name} (${d.start_year}~${d.end_year})`;
                select.appendChild(opt);
            });
        }
    } catch (e) {
        console.warn('加载朝代失败:', e);
    }
}

async function loadSites() {
    try {
        showToast('正在加载遗迹数据...', 'info');
        const res = await fetch(`${API_BASE}/sites?limit=300`);
        const sites = await res.json();
        appState.sites = sites;
        appState.map.setSites(sites);
        showToast(`成功加载 ${sites.length} 处遗迹`, 'success');
    } catch (e) {
        showToast('加载数据失败，请确认后端已启动', 'error');
        console.error(e);
    }
}

async function loadSupplyRanges() {
    try {
        const res = await fetch(`${API_BASE}/supply-ranges?limit=300`);
        const data = await res.json();
        const ranges = data.features || [];
        appState.supplyRanges = ranges;
        appState.map.setSupplyRanges(ranges);
    } catch (e) {
        console.warn('加载灌溉范围失败:', e);
    }
}

async function loadStatistics() {
    try {
        const res = await fetch(`${API_BASE}/statistics`);
        const stats = await res.json();

        document.getElementById('statTotal').textContent = stats.total_sites;
        document.getElementById('statGood').textContent = stats.by_status?.['完好'] || 0;
        document.getElementById('statWarn').textContent = stats.by_status?.['部分损毁'] || 0;
        document.getElementById('statDanger').textContent = stats.by_status?.['完全废弃'] || 0;
        document.getElementById('statPotential').textContent = stats.high_potential_count || 0;
        document.getElementById('statAlerts').textContent = stats.alerts_count || 0;
    } catch (e) {
        console.warn('加载统计失败:', e);
    }
}

async function checkAlerts() {
    try {
        const res = await fetch(`${API_BASE}/alerts?alert_level=高&acknowledged=false&limit=5`);
        const alerts = await res.json();
        if (alerts.length > 0) {
            showAlertBanner(alerts[0].message);
        }
    } catch (e) {
        console.warn(e);
    }
}

// ========== 筛选 ==========
function applyFilters() {
    const type = document.getElementById('filterType')?.value;
    const dynasty = document.getElementById('filterDynasty')?.value;
    const status = document.getElementById('filterStatus')?.value;
    const minArea = parseFloat(document.getElementById('minArea')?.value);
    const maxArea = parseFloat(document.getElementById('maxArea')?.value);

    const count = appState.map.applyFilters({
        type: type || undefined,
        dynasty: dynasty || undefined,
        status: status || undefined,
        minArea: isNaN(minArea) ? undefined : minArea,
        maxArea: isNaN(maxArea) ? undefined : maxArea,
    });

    showToast(`筛选完成，共 ${count} 处遗迹`, 'info');
}

function resetFilters() {
    document.getElementById('filterType').value = '';
    document.getElementById('filterDynasty').value = '';
    document.getElementById('filterStatus').value = '';
    document.getElementById('minArea').value = '';
    document.getElementById('maxArea').value = '';
    appState.map.resetFilters();
}

// ========== 详情面板 ==========
async function handleSiteSelect(siteId) {
    appState.selectedSite = siteId;
    const panel = document.getElementById('panelContent');
    panel.innerHTML = '<div class="loading">加载详细信息中</div>';
    document.getElementById('detailPanel').scrollTop = 0;

    try {
        await loadSiteComprehensive(siteId);
    } catch (e) {
        panel.innerHTML = `<div class="empty-state"><p>加载失败：${e.message}</p></div>`;
        console.error(e);
    }
}

async function loadSiteComprehensive(site_id) {
    try {
        const [compRes, hydroRes, sectionRes] = await Promise.all([
            fetch(`${API_BASE}/sites/${site_id}/comprehensive`),
            fetch(`${API_BASE}/hydrology/by-site/${site_id}?period=all`),
            fetch(`${API_BASE}/cross-section/${site_id}`)
        ]);

        const comp = await compRes.json();
        const hydro = await hydroRes.json();
        const section = await sectionRes.json();

        if (comp.restoration === null) {
            try {
                await fetch(`${API_BASE}/restoration/${site_id}?async_mode=false`, { method: 'POST' });
                const newComp = await (await fetch(`${API_BASE}/sites/${site_id}/comprehensive`)).json();
                comp.restoration = newComp.restoration;
                loadSupplyRanges();
            } catch (e) { console.warn('自动复原失败:', e); }
        }

        if (comp.assessment === null) {
            try {
                await fetch(`${API_BASE}/assessment/${site_id}?async_mode=false`, { method: 'POST' });
                const newComp = await (await fetch(`${API_BASE}/sites/${site_id}/comprehensive`)).json();
                comp.assessment = newComp.assessment;
            } catch (e) { console.warn('自动评估失败:', e); }
        }

        renderDetailPanel(comp, hydro, section);
        appState.map.setSelected(site_id);
        loadStatistics();

        const site = comp.site;

        if (comp.agriculture_impact && appState.benefitRenderer && appState.showBenefit) {
            try {
                const agriImpact = Array.isArray(comp.agriculture_impact) ? comp.agriculture_impact : [comp.agriculture_impact];
                const benefitZones = agriImpact.map(ai => ({
                    site_id: ai.site_id || site_id,
                    site_name: ai.site_name || site?.name,
                    yield_increase_rate: ai.yield_increase_rate ?? ai.rate ?? 0,
                    core_geom: ai.core_geom || ai.core_zone,
                    radiating_geom: ai.radiating_geom || ai.radiating_zone,
                    marginal_geom: ai.marginal_geom || ai.marginal_zone
                }));
                appState.benefitRenderer.setBenefitZones(benefitZones);
            } catch (e) { console.warn('加载受益区失败:', e); }
        }

        if (comp.climate_assessments && appState.climateRiskRenderer && appState.showClimateRisk) {
            try {
                const assessments = Array.isArray(comp.climate_assessments) ? comp.climate_assessments : [comp.climate_assessments];
                const riskZones = assessments.map(ca => ({
                    site_id: ca.site_id || site_id,
                    site_name: ca.site_name || site?.name,
                    risk_level: ca.risk_level || ca.level || 3,
                    vulnerability_score: ca.vulnerability_score ?? ca.score,
                    flood_depth: ca.flood_depth,
                    drought_spei: ca.drought_spei,
                    suggestions: ca.suggestions || ca.recommendations || [],
                    geom: ca.geom || ca.zone_geom || ca.geometry
                }));
                const scenarioEl = document.querySelector('#riskScenarioSelect');
                const yearEl = document.querySelector('#riskYearSelect');
                const sc = scenarioEl?.value || DEFAULT_RISK_SCENARIO;
                const yr = parseInt(yearEl?.value) || DEFAULT_RISK_YEAR;
                appState.climateRiskRenderer.setRiskZones(riskZones, sc, yr);
            } catch (e) { console.warn('加载风险区失败:', e); }
        }

        if (comp.network_membership && appState.networkLayer && appState.showNetwork) {
            try {
                const region = comp.network_membership.region || comp.network_membership.region_name || site?.region;
                if (region) {
                    const regionSelect = document.querySelector('#networkRegionSelect');
                    if (regionSelect) regionSelect.value = region;
                    appState.currentNetworkRegion = region;
                    await appState.networkLayer.loadNetwork(region);
                    setTimeout(() => appState.networkLayer.highlightCriticalNodes && appState.networkLayer.highlightCriticalNodes(), 800);
                }
            } catch (e) { console.warn('加载网络失败:', e); }
        }

        if (appState.digitalExhibitPanel) {
            try {
                await appState.digitalExhibitPanel.loadSite(site_id);
                const vrBtn = document.querySelector('#enterVRBtn');
                if (vrBtn) vrBtn.style.display = (comp.site?.has_3d_model || comp.model_available) ? 'inline-block' : 'none';
            } catch (e) { console.warn('加载数字展陈失败:', e); }
        }

    } catch (e) {
        throw e;
    }
}

async function _batchTriggerAllAssessments(site_id) {
    showToast('正在计算新功能数据...', 'info');
    const site = appState.sites.find(s => s.id === site_id);
    const region = site?.region || site?.region_name || 'default';

    const tasks = [];

    tasks.push(fetch(`${API_BASE}/agriculture/sites/${site_id}/impact`, { method: 'POST' }).catch(e => { console.warn('农业影响计算失败:', e); return null; }));
    tasks.push(fetch(`${API_BASE}/climate/sites/${site_id}/assess`, { method: 'POST' }).catch(e => { console.warn('气候评估计算失败:', e); return null; }));
    tasks.push(fetch(`${API_BASE}/network/analyze/region`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ region: region })
    }).catch(e => { console.warn('网络分析计算失败:', e); return null; }));

    try {
        await Promise.all(tasks);
        showToast('计算任务已提交，异步计算中', 'success');
        setTimeout(async () => {
            if (appState.selectedSite) {
                handleSiteSelect(appState.selectedSite);
            }
        }, 2500);
    } catch (e) {
        showToast('部分任务提交完成，部分数据可能稍后就绪', 'warning');
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
        </div>`;

        if (assessment.group_decision_info) {
            const gdi = assessment.group_decision_info;
            html += `<div class="site-info-section" style="margin-top:10px;">
                <div class="section-title">群决策信息</div>
                <div class="info-grid" style="font-size:12px;">
                    <div class="info-item"><span class="info-label">专家数量</span><span class="info-value">${gdi.expert_count || 5} 位</span></div>
                    <div class="info-item"><span class="info-label">分歧度</span><span class="info-value">${gdi.disagreement_description || '—'}</span></div>
                </div>
            </div>`;
        }
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

        if (restoration.parameter_estimation) {
            const pe = restoration.parameter_estimation;
            html += `<div class="site-info-section" style="margin-top:10px;">
                <div class="section-title">参数估计</div>
                <div class="info-grid" style="font-size:12px;">
                    <div class="info-item"><span class="info-label">可靠度</span><span class="info-value">${pe.reliability?.toFixed(1) || '—'}%</span></div>
                    <div class="info-item"><span class="info-label">估计参数</span><span class="info-value">${pe.estimated_params_count || 0} 个</span></div>
                </div>
            </div>`;
        }

        if (restoration.uncertainty_analysis) {
            const ua = restoration.uncertainty_analysis;
            html += `<div class="site-info-section" style="margin-top:10px;">
                <div class="section-title">不确定性分析 (蒙特卡洛)</div>
                <div class="info-grid" style="font-size:12px;">
                    <div class="info-item"><span class="info-label">抽样次数</span><span class="info-value">${ua.n_samples || 1000} 次</span></div>
                    <div class="info-item"><span class="info-label">变异系数</span><span class="info-value">${(ua.cv * 100 || 0).toFixed(1)}%</span></div>
                    <div class="info-item"><span class="info-label">收敛</span><span class="info-value">${ua.convergence?.converged ? '✅ 是' : '❌ 否'}</span></div>
                </div>
            </div>`;
        }
    }

    html += `<div class="site-info-section">
        <div class="section-title">水文变化趋势</div>
        <div class="chart-container">
            <canvas id="hydroChart"></canvas>
        </div>
        <div class="chart-legend">
            <span class="chart-legend-item"><span class="chart-legend-color" style="background:#4299e1;"></span>降雨量 (mm)</span>
            <span class="chart-legend-item"><span class="chart-legend-color" style="background:#38b2ac;"></span>径流量</span>
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

// ========== 搜索 ==========
function setupSearch() {
    const input = document.getElementById('searchInput');
    const results = document.getElementById('searchResults');
    const btn = document.getElementById('searchBtn');

    function performSearch() {
        const q = input.value.trim().toLowerCase();
        if (!q) {
            results.classList.remove('active');
            results.innerHTML = '';
            return;
        }

        const matched = appState.map.search(q);

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
            const siteId = parseInt(item.dataset.id);
            appState.map.selectSite(siteId);
            results.classList.remove('active');
            input.value = '';
        }
    });

    document.addEventListener('click', e => {
        if (!e.target.closest('.search-box')) {
            results.classList.remove('active');
        }
    });
}

// ========== 批量操作 ==========
async function handleRestoreAll() {
    if (!confirm('确认计算全部遗迹的功能复原？可能需要较长时间。')) return;
    showToast('正在计算功能复原...', 'info');
    try {
        const res = await fetch(`${API_BASE}/batch/restore`, { method: 'POST' });
        const result = await res.json();
        showToast(`功能复原任务已提交，异步计算中`, 'success');
        setTimeout(loadSupplyRanges, 2000);
    } catch (e) {
        showToast('计算失败', 'error');
    }
}

async function handleAssessAll() {
    if (!confirm('确认对全部遗迹进行可持续性评估？')) return;
    showToast('正在评估可持续性...', 'info');
    try {
        const res = await fetch(`${API_BASE}/batch/assess`, { method: 'POST' });
        const result = await res.json();
        showToast(`评估任务已提交，异步计算中`, 'success');
        setTimeout(loadStatistics, 2000);
    } catch (e) {
        showToast('评估失败', 'error');
    }
}

// ========== 事件绑定 ==========
function setupEventListeners() {
    document.getElementById('applyFilter')?.addEventListener('click', applyFilters);
    document.getElementById('resetFilter')?.addEventListener('click', resetFilters);

    document.getElementById('restoreAllBtn')?.addEventListener('click', handleRestoreAll);
    document.getElementById('assessAllBtn')?.addEventListener('click', handleAssessAll);

    document.getElementById('showSupplyRange')?.addEventListener('change', e => {
        appState.map.toggleSupplyRange(e.target.checked);
        if (e.target.checked && appState.supplyRanges.length === 0) {
            loadSupplyRanges();
        }
    });

    document.getElementById('showHexagon')?.addEventListener('change', e => {
        appState.map.toggleHexagon(e.target.checked);
    });

    document.getElementById('sizeByArea')?.addEventListener('change', e => {
        appState.map.setSizeByArea(e.target.checked);
    });

    document.getElementById('colorByStatus')?.addEventListener('change', e => {
        appState.map.setColorByStatus(e.target.checked);
    });

    document.getElementById('closePanel')?.addEventListener('click', () => {
        document.getElementById('panelContent').innerHTML = `
            <div class="empty-state">
                <p>在地图上点击遗迹以查看详细信息</p>
                <div class="hint-icon">🗺️</div>
            </div>`;
        appState.selectedSite = null;
        appState.map.setSelected(null);
        if (appState.benefitRenderer) appState.benefitRenderer.clearSelected();
        if (appState.climateRiskRenderer) appState.climateRiskRenderer.clearSelected();
    });

    document.getElementById('alertClose')?.addEventListener('click', () => {
        document.getElementById('alertBanner').style.display = 'none';
    });

    let resizeTimer;
    window.addEventListener('resize', () => {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(() => {
            if (appState.selectedSite) {
                handleSiteSelect(appState.selectedSite);
            }
            appState.map.invalidateSize();
        }, 200);
    });
}

// ========== 工具函数 ==========
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text || '';
    return div.innerHTML;
}

function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    if (!container) return;

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
    if (banner) {
        document.getElementById('alertText').textContent = message;
        banner.style.display = 'block';
    }
}

// ========== 暴露全局 ==========
window.app = {
    state: appState,
    map: null,
    init: initApp
};

// ========== 启动 ==========
document.addEventListener('DOMContentLoaded', () => {
    initApp();
    window.app.map = appState.map;
});
