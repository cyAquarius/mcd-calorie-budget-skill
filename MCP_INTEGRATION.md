# MCP 集成说明

## MCP Server

| 项 | 值 |
|---|---|
| Server | 麦当劳中国官方托管 MCP |
| URL | `https://mcp.mcd.cn` |
| 协议 | Streamable HTTP |
| 鉴权 | `Authorization: Bearer <MCP_TOKEN>` |
| Token 申请 | [https://open.mcd.cn/mcp](https://open.mcd.cn/mcp) |
| 限流 | 每 Token 约 600 次/分钟（超限 HTTP 429） |

本项目配置示例见 [`mcp-config.example.json`](./mcp-config.example.json)，Token 仅通过环境变量或客户端本地配置注入，**不入库**。

## 实际使用的 Tools

按控卡省钱点餐主链路：

| Tool | 用途 |
|---|---|
| `now-time-info` | 判断当前时段（是否早餐等），避免推荐不可售品 |
| `list-nutrition-foods` | 拉营养表，按能量 (kcal) 等过滤候选 |
| `query-nearby-stores` | 堂食/外带：按地址查附近门店 |
| `delivery-query-addresses` | 外送：查已有收货地址 |
| `delivery-query-stores` | 外送：按地址查可配送门店 |
| `delivery-create-address` | 无地址时引导新增（需用户确认信息） |
| `query-meals` | 当前门店可售菜单 |
| `query-meal-detail` | 套餐组成与可替换项 |
| `available-coupons` | 可领的麦麦省券列表 |
| `auto-bind-coupons` | 一键领取当前可领麦麦省券 |
| `query-my-coupons` | 账户已有券 |
| `query-store-coupons` | 当前门店可用券 |
| `calculate-price` | 商品 + 券 → 优惠额与实付 |
| `create-order` | **仅用户确认后**创建订单，返回支付链接 |
| `query-order` / `cancel-order` | 下单后查进度或取消（按需） |

非主链路但可扩展：`campaign-calendar`（活动日历）、`query-my-account`（积分）——本 Skill 默认不强制使用。

## 调用流程

```text
用户诉求（热量 / 预算 / 地址 / 就餐方式）
        │
        ▼
  now-time-info
        │
        ▼
 list-nutrition-foods  ──过滤──► 热量合规候选
        │
        ├─ 堂食/外带 ─► query-nearby-stores
        └─ 外送 ─► delivery-query-addresses / delivery-query-stores
        │
        ▼
 query-meals → query-meal-detail  ──► 可组 2～3 个方案
        │
        ▼
 available-coupons → auto-bind-coupons（有券可领时）
        │
        ▼
 query-my-coupons / query-store-coupons
        │
        ▼
 calculate-price（每个方案）
        │
        ▼
 展示排序结果（热量贴近 → 实付低 → 蛋白密度高）
        │
        ▼
 用户明确确认某一方案
        │
        ▼
 create-order → 支付链接（用户自行支付）
```

详细 Agent 行为约束见 [`skill/mcd-calorie-budget/SKILL.md`](./skill/mcd-calorie-budget/SKILL.md)。

## 业务价值

| 痛点 | Skill 做法 |
|---|---|
| 控卡靠猜、营养表难翻 | 用 `list-nutrition-foods` 硬约束热量 |
| 优惠券散落、忘记领 | `available-coupons` + `auto-bind-coupons` 自动领再用 |
| 算到手价麻烦 | `calculate-price` 对比多方案实付 |
| 怕 Agent 乱下单 | **必须口头确认**才 `create-order` |
| 时段错点（早餐/正餐） | `now-time-info` + 门店可售校验 |

一句话：**在热量和预算双约束下，用官方 MCP 完成「筛品 → 领券 → 算价 → 确认下单」闭环。**

## 错误处理建议

| 情况 | 处理 |
|---|---|
| 401 | Token 无效/过期，提示用户去 open.mcd.cn 重新申请 |
| 429 | 降低调用频率，合并查询 |
| 无门店 / 无菜 | 换地址或就餐方式，向用户说明 |
| 热量无解 | 放宽上限，或拆成「主食 + 饮品」轻量组合并标明风险 |
| 算价失败 | 去掉券重试，并提示可能已过期 |

## 可运行 CLI

本仓库 `src/mcd_calorie_budget` 实现同一主链路的命令行客户端：

| 命令 | 对应 Tools |
|---|---|
| `python -m mcd_calorie_budget smoke` | `now-time-info` / `list-nutrition-foods` / `campaign-calendar` / `available-coupons` |
| `python -m mcd_calorie_budget addresses` | `delivery-query-addresses`（输出脱敏） |
| `python -m mcd_calorie_budget recommend ...` | 堂食/外带：`query-nearby-stores` → … → `calculate-price` |
| `python -m mcd_calorie_budget recommend --mode delivery ...` | `delivery-query-addresses` → `delivery-query-stores` → … → `calculate-price`（`beType=2` / `orderType=2`） |
| `python -m mcd_calorie_budget order --confirm` | `create-order`（强制显式确认；外送带 `addressId`） |

### CLI 实现细节（与竞品踩坑对齐）

1. **营养 DSL**：`list-nutrition-foods` 的 `data` 不是 JSON，按 `[N]{cols}:` + 行解析。
2. **主食优先**：默认降权纯饮品/甜品，避免「无糖可乐」因低卡刷成推荐第一名；可用 `--allow-sides` 关闭。
3. **套餐热量警告**：套餐名若只能匹配到单品营养行，会在 notes 标明「可能仅单品口径」。
4. **Token**：环境变量 `MCD_MCP_TOKEN`，或文件 `~/.config/mcd/mcp_token` / `MCD_MCP_TOKEN_FILE`；日志不打印完整 Token。

