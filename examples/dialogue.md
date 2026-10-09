# 示例对话（摘要）

用户：中午想吃麦当劳，热量别超 650 kcal，预算 35 以内，上海徐汇附近，外带。

助手：

1. 已查当前时间（非早餐窗）→ 按正餐推荐  
2. 营养表筛出 ≤650 kcal 单品约 150+  
3. 附近门店：徐汇某餐厅（营业中）  
4. 已尝试领取麦麦省，并拉取本店可用券  
5. 算价后推荐：

| 方案 | 内容 | 热量 | 实付 |
|---|---|---:|---:|
| A | 巨无霸 | ~513 | ~¥20 |
| B | 牛气满满套餐 | ~495 | ~¥26 |
| C | 麦辣鸡腿汉堡 | ~485 | ~¥17 |

回复方案字母即可下单；未确认前不会创建订单。

---

等价 CLI：

```bash
export MCD_MCP_TOKEN=...
PYTHONPATH=src python3 -m mcd_calorie_budget recommend \
  --calorie-cap 650 --budget 35 --city 上海 --keyword 徐汇
```

---

用户：送到家，热量 600 以内，预算 40。

助手：

1. `delivery-query-addresses` → 列出脱敏地址供确认  
2. `delivery-query-stores` → 选可配送且营业中的门店  
3. 领券算价后给出 2～3 个方案（含配送场景下的实付）  
4. 确认后 `create-order`（带 addressId）→ 支付链接

等价 CLI：

```bash
mcd-calorie-budget addresses
mcd-calorie-budget recommend --mode delivery --address-id ... --calorie-cap 600 --budget 40
```
