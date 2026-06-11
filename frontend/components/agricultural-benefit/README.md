# Agricultural Benefit Component

农业受益区渲染组件

## 功能特性

- Canvas 批量绘制三级受益区（核心/辐射/边缘）
- 渐变填充与增产率颜色饱和度映射
- 视口裁剪、LOD简化、80ms debounce、DPR适配
- 网格空间索引（快速点击命中检测）
- 鼠标悬停 popup 提示

## API

### 构造函数

```javascript
new BenefitRenderer(map, options)
```

### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| map | L.Map | Leaflet 地图实例 |
| options | Object | 配置选项 |

### 方法

| 方法 | 说明 |
|------|------|
| `addTo(map)` | 添加到地图 |
| `remove()` | 从地图移除 |
| `show()` | 显示图层 |
| `hide()` | 隐藏图层 |
| `updateData(data)` | 更新数据 |
| `setBenefitZones(zones)` | 设置受益区数据 |
| `setSelected(siteId)` | 设置选中的遗址 |
| `clearSelected()` | 清除选中状态 |
| `on(event, callback)` | 绑定事件 |
| `destroy()` | 销毁组件 |

### 事件

| 事件 | 说明 |
|------|------|
| `click` | 点击受益区时触发 |
| `hover` | 鼠标悬停在受益区时触发 |

## 示例

```javascript
const renderer = new BenefitRenderer(map, {
  onClick: (hit) => {
    console.log('点击了:', hit.zone.site_name);
  }
});

renderer.setBenefitZones(zonesData);
renderer.show();
```
