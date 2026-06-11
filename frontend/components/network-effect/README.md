# Network Effect Component

网络效应图层组件

## 功能特性

- 基于 Leaflet GeoJSON + Canvas 叠加渲染
- 节点按 role 着色与动画（核心枢纽脉冲）
- 边按 connection_strength 映射线宽与线型
- 关键节点高亮光晕效果
- 右键菜单切换显示模式
- 节点中心性弹窗卡片

## API

### 构造函数

```javascript
new NetworkLayer(options)
```

### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| options | Object | 配置选项 |

### 方法

| 方法 | 说明 |
|------|------|
| `addTo(map)` | 添加到地图 |
| `remove()` | 从地图移除 |
| `show()` | 显示图层 |
| `hide()` | 隐藏图层 |
| `updateData(geojson)` | 更新网络数据 |
| `setNetworkData(geojson)` | 设置网络数据 |
| `loadNetwork(region)` | 加载指定区域的网络数据 |
| `highlightCriticalNodes()` | 高亮关键节点 |
| `setShowEdges(show)` | 设置是否显示连线 |
| `setCriticalOnly(only)` | 设置只看关键节点 |
| `setCoreOnly(only)` | 设置只看核心枢纽 |
| `showNodePopup(siteId, latlng, props)` | 显示节点弹窗 |
| `on(event, callback)` | 绑定事件 |

### 事件

| 事件 | 说明 |
|------|------|
| `nodeClick` | 点击节点时触发 |

## 示例

```javascript
const networkLayer = new NetworkLayer({
  nodeStyles: {
    core_hub: { color: '#e53e3e', size: 20 }
  }
});

networkLayer.addTo(map);
networkLayer.loadNetwork('jiangnan');
networkLayer.show();
```
