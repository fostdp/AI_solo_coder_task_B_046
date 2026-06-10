# 古代水利工程遗迹系统 v2.0 改动说明与定位

## 概述

针对首版运行发现的4个核心问题进行升级改造，从**水力模型、AHP评估、前端性能、MQTT可靠性**四个维度全面提升系统鲁棒性。

---

## 一、水力计算模型：参数估计 + 蒙特卡洛不确定性分析

### 问题定位
**文件**: `backend/app/services/restoration_model.py`
**问题**: 当结构参数（坝高、渠长等）缺失或不完整时，水力计算公式出现数值发散，导致灌溉能力计算结果异常。

### 改动内容

#### 1.1 新增 ParameterEstimator 类（第2章参数估计器）
**定位**: 约第80-230行
- **功能**: 基于工程类型统计分布和朝代技术发展因子，对缺失参数进行智能估计
- **核心算法**:
  - 5类工程各5-6个参数的统计分布（均值、标准差、min、max）
  - 17个朝代技术发展因子（春秋0.70 → 清代1.05）
  - 参数可靠度评分（已知参数权重 × 类型匹配度 × 朝代因子）
- **输出**: 估计值、参数来源、可靠度评分、置信区间

#### 1.2 新增数值收敛保护
**定位**: `_safe_log`、`_safe_sqrt`、`_clamp` 方法
- 安全对数：避免输入 ≤ 0 时发散
- 安全平方根：输入钳位到非负
- 通用钳位：限制输出范围防止溢出

#### 1.3 新增蒙特卡洛不确定性分析
**定位**: `monte_carlo_analysis()` 方法（约第500-600行）
- **核心功能**:
  - 1000次参数抽样（正态分布）
  - 每次独立计算灌溉能力
  - 输出统计分布特征
- **输出指标**:
  - 均值、标准差、变异系数(CV)
  - 中位数、5/25/75/95分位数
  - 收敛性检验（对半比较法）
- **SRC敏感性分析**:
  - 标准化回归系数法
  - 识别对结果影响最大的参数
  - 按敏感度排序

#### 1.4 API 接口
- `POST /api/sites/{site_id}/monte-carlo` - 运行蒙特卡洛分析
- `GET /api/sites/{site_id}/parameter-estimation` - 获取参数估计结果
- `GET /api/restoration/supply-ranges/simplified` - 获取简化版灌溉区

#### 1.5 数据库字段
- `functional_restoration.parameter_estimation` (JSONB) - 参数估计结果
- `functional_restoration.uncertainty_analysis` (JSONB) - 不确定性分析结果

---

## 二、AHP评估：群决策 + 一致性检验

### 问题定位
**文件**: `backend/app/services/ahp_assessment.py`
**问题**: 单专家权重设置主观性强，当专家判断不一致时评分偏差大，缺乏一致性检验机制。

### 改动内容

#### 2.1 新增 ExpertOpinion 数据类
**定位**: 类定义部分
- 专家属性：ID、姓名、领域、权重、机构
- 专家判断矩阵：5×5 Saaty标度矩阵

#### 2.2 新增 AHPGroupDecision 群决策类（约第100-300行）
**5位默认专家**:
1. 水利工程专家 (权重0.25)
2. 考古学专家 (权重0.20)
3. 经济学专家 (权重0.20)
4. 环境学专家 (权重0.20)
5. 综合评估专家 (权重0.15)

**核心方法**:
- `build_pairwise_matrix()` - 构建Saaty 1-9标度判断矩阵
- `check_consistency()` - 一致性检验（CR、CI、RI）
  - CR < 0.1：一致性可接受
  - CR ≥ 0.1：一致性不足
- `correct_consistency_iterative()` - 迭代法一致性修正
  - 最多50轮迭代
  - 目标CR < 0.08
  - 自动调整最不一致的判断项
- `aggregate_experts_geometric()` - 几何平均法加权聚合
  - 各专家权重矩阵元素相乘后开n次方
  - 保留专家判断的相对比例关系
- `calculate_expert_disagreement()` - 专家分歧度计算
  - 4级：高度一致、基本一致、中等分歧、分歧较大
  - 基于权重向量标准差计算

#### 2.3 AHPSustainabilityAssessment 重构
**定位**: `assess_site()` 方法
- 新增 `use_group_decision` 参数（默认True）
- 评估详情包含：
  - 一致性比率(CR)
  - 是否经过修正
  - 迭代修正次数
  - 原始CR
  - 权重方法（单专家/群决策）
  - 参与专家数
  - 专家分歧度

#### 2.4 API 接口
- `GET /api/ahp/experts` - 获取专家列表
- `GET /api/ahp/group-weights` - 获取群决策聚合权重
- `POST /api/ahp/check-consistency` - 检验权重一致性

#### 2.5 数据库字段
- `sustainability_assessment.group_decision_info` (JSONB) - 群决策信息

---

## 三、前端灌溉区渲染：Canvas高性能渲染器

### 问题定位
**文件**: `frontend/js/supply-range-renderer.js`（新增）
**相关文件**: `frontend/js/app.js`, `frontend/index.html`
**问题**: 使用Leaflet GeoJSON图层渲染300个多边形时，DOM节点过多导致交互卡顿，缩放平移帧率低。

### 改动内容

#### 3.1 新增 SupplyRangeRenderer 类（约350行）
**文件**: `frontend/js/supply-range-renderer.js`

**核心技术**:
- **Canvas 2D 批量绘制**: 所有多边形在单个Canvas上绘制，无DOM开销
- **Douglas-Peucker多边形简化**: 动态降低多边形顶点数
- **LOD细节层次**: 根据缩放级别自动调整简化精度
  - zoom < 8：最大简化（tolerance = 0.01）
  - 8 ≤ zoom < 12：中等简化（tolerance = 0.003）
  - zoom ≥ 12：最小简化（tolerance = 0.001）
- **视口裁剪**: 只渲染可视区域内的多边形（上限300个）
  - 包围盒快速检测
  - 超出视口的多边形跳过绘制
- **射线法点在多边形内检测**: 点击交互精确命中
- **节流渲染**: 80ms节流，避免频繁重绘

**状态样式**:
- 默认态：浅蓝色填充 + 虚线边框
- Hover态：深色边框 + 不透明度提升
- Selected态：橙色高亮边框 + 更显著填充

#### 3.2 app.js 集成
**定位**: `initCanvasLayer()`、`loadSupplyRanges()`、`selectSite()`、复选框事件

- `appState.supplyRangeRenderer` - 渲染器实例
- `appState.supplyRanges` - 灌溉区数据缓存
- `appState.useHighPerformanceRenderer` - 高性能模式开关（默认开启）

#### 3.3 性能对比（理论值）
| 指标 | v1.0 (GeoJSON) | v2.0 (Canvas) | 提升 |
|------|---------------|--------------|------|
| 300多边形FPS | ~25-30 | ~55-60 | 2倍 |
| 内存占用 | 高（300个DOM） | 低（1个Canvas） | -80% |
| 缩放响应延迟 | 100-200ms | 20-50ms | -75% |

---

## 四、MQTT推送：持久会话 + 离线消息缓存

### 问题定位
**文件**: `backend/app/services/mqtt_service.py`
**问题**: 文物保护中心离线期间，告警消息直接丢失，无法保证消息可靠送达。

### 改动内容

#### 4.1 持久会话 (Persistent Session)
**定位**: `_init_client()` 方法
- `clean_session=False`：Broker保存客户端订阅状态和未确认消息
- 固定client_id：基于数据库名生成，保证重连后恢复同一会话
- 连接日志显示会话状态："持久会话已恢复" / "新会话"

#### 4.2 离线消息缓存
**新增数据结构**:
- `MessageStatus` 枚举：pending / publishing / published / failed / expired
- `MQTTMessage` 数据类：包含消息完整生命周期信息
  - id, topic, payload, qos, retain
  - status, created_at, published_at
  - retry_count, max_retries, ttl
  - mid（MQTT消息ID）
  - 成功/失败回调

**核心机制**:
- `_pending_messages`：待发送消息字典（内存队列）
- `_dead_letter_queue`：死信队列（重试失败的消息）
- `_flush_pending_messages()`：重连后自动补发所有待发送消息
- 消息过期检查：TTL超时转入死信队列

#### 4.3 指数退避重连
**定位**: `_schedule_reconnect()` 方法
- 基础延迟2秒，每次翻倍
- 最大延迟120秒
- 最大重试50次
- 随机抖动避免雪崩

#### 4.4 QoS与遗嘱消息
- QoS 1：至少一次送达，保证消息不丢
- 遗嘱消息(Will Message)：异常断连时自动发送offline状态
- 连接状态主题：`heritage/alert/status`
  - online：服务正常运行
  - offline：服务异常断开

#### 4.5 新增方法
| 方法 | 功能 |
|------|------|
| `get_message_status()` | 查询单条消息状态 |
| `get_pending_count()` | 获取待发送统计 |
| `get_dead_letter_messages()` | 获取死信队列 |
| `clear_dead_letter()` | 清空死信队列 |
| `subscribe()` | 订阅主题 |
| `register_connect_callback()` | 注册连接回调 |
| `get_connection_info()` | 获取连接信息 |
| `manual_reconnect()` | 手动触发重连 |

#### 4.6 API 接口
- `GET /api/mqtt/status` - MQTT连接状态
- `GET /api/mqtt/pending-count` - 待发送消息数
- `GET /api/mqtt/messages/{message_id}/status` - 单条消息状态
- `GET /api/mqtt/dead-letter` - 死信队列
- `DELETE /api/mqtt/dead-letter` - 清空死信
- `POST /api/mqtt/reconnect` - 手动重连

#### 4.7 数据库字段
- `alert_records.mqtt_message_id` (VARCHAR) - MQTT消息ID
- `alert_records.mqtt_status` (VARCHAR) - 消息状态

---

## 五、数据库升级

### 升级脚本
**文件**: `scripts/upgrade_v2.sql`

### 新增字段汇总
| 表 | 字段 | 类型 | 说明 |
|----|------|------|------|
| functional_restoration | parameter_estimation | JSONB | 参数估计结果 |
| functional_restoration | uncertainty_analysis | JSONB | 不确定性分析 |
| sustainability_assessment | group_decision_info | JSONB | 群决策信息 |
| alert_records | mqtt_message_id | VARCHAR(100) | MQTT消息ID |
| alert_records | mqtt_status | VARCHAR(20) | 消息状态 |

---

## 六、文件清单与改动统计

### 新增文件（2个）
1. `frontend/js/supply-range-renderer.js` - 高性能灌溉区渲染器（~350行）
2. `scripts/upgrade_v2.sql` - v2.0数据库升级脚本

### 核心改动文件（6个）

| 文件 | 改动类型 | 主要改动 |
|------|---------|---------|
| `backend/app/services/restoration_model.py` | 重大升级 | +ParameterEstimator, +Monte Carlo, +数值保护 |
| `backend/app/services/ahp_assessment.py` | 重大升级 | +群决策, +一致性检验, +迭代修正 |
| `backend/app/services/mqtt_service.py` | 重写 | +持久会话, +离线队列, +指数退避重连 |
| `backend/app/models/__init__.py` | 扩展 | 新增5个JSON字段 |
| `backend/app/main.py` | 扩展 | +13个新API端点 |
| `frontend/js/app.js` | 集成 | 集成SupplyRangeRenderer |

### 次要改动文件（2个）
- `frontend/index.html` - 添加脚本引用
- `frontend/css/style.css` - 渲染器样式

---

## 七、升级注意事项

1. **数据库升级**: 执行 `scripts/upgrade_v2.sql` 升级现有数据库
2. **数据重新计算**: 建议重新运行功能复原和评估，生成参数估计和群决策数据
3. **MQTT Broker**: 确保Broker支持持久会话（Mosquitto/EMQX等主流Broker均支持）
4. **向后兼容**: v2.0 API完全向下兼容v1.0，旧版前端可正常使用
5. **性能开关**: 前端可通过 `appState.useHighPerformanceRenderer = false` 回退到GeoJSON模式

---

## 版本信息

- **版本号**: v2.0.0
- **升级日期**: 2025年
- **升级类型**: 功能增强 + 性能优化 + 可靠性提升
