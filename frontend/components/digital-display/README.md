# Digital Display Component

数字化展示面板组件

## 功能特性

- 动态插入 Tab 到现有详情面板
- 照片上传区 + 重建方法选择
- 9步进度条 + 重建状态
- 3D模型查看器占位（伪3D旋转动画）
- VR热点列表
- 重建日志 accordion

## API

### 构造函数

```javascript
new DigitalExhibitPanel(options)
```

### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| options | Object | 配置选项 |

### 方法

| 方法 | 说明 |
|------|------|
| `init(sitePanelEl)` | 初始化面板 |
| `addTo(container)` | 添加到容器 |
| `remove()` | 移除面板 |
| `show()` | 显示面板 |
| `hide()` | 隐藏面板 |
| `updateData(data)` | 更新数据 |
| `loadSite(siteId)` | 加载遗址数据 |
| `updateProgress(status)` | 更新重建进度 |
| `bindEvents()` | 绑定事件 |
| `on(event, callback)` | 绑定事件 |
| `destroy()` | 销毁组件 |

### 事件

| 事件 | 说明 |
|------|------|
| `reconstructionComplete` | 重建完成时触发 |

## 示例

```javascript
const panel = new DigitalExhibitPanel();
panel.init(document.getElementById('detailPanel'));
panel.loadSite('site-001');
```
