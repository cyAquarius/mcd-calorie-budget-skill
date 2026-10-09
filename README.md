# 控卡省钱点餐助手

> 麦当劳程序员节创意开发大赛（M-CODE）参赛作品 · 非官方产品

基于麦当劳中国 MCP（`https://mcp.mcd.cn`）的 **Agent Skill**：在热量上限和/或预算内推荐可点套餐，自动领取「麦麦省」优惠券、算价，并在你确认后创建订单（返回支付链接，不会静默下单）。

## 目标用户

- 想控卡、又不想自己翻营养表的人
- 学生 / 打工人：热量和预算都卡死，还想吃麦当劳
- 用 Cursor / Codex / WorkBuddy / Cherry Studio 等 MCP 客户端的开发者，希望 Agent 直接帮自己点餐决策

## 能做什么

1. 问清：热量上限（kcal）、可选金额上限（元）、城市/地址或附近门店、堂食/外带/外送
2. 拉营养数据，按热量筛餐品
3. 查附近门店与可售菜单、套餐明细
4. 查券 / 一键领麦麦省 / 算到手价
5. 给出 **2～3 个方案**，按「贴近热量目标 → 实付更低 → 蛋白质密度」排序
6. **你确认后**才调用 `create-order`，返回支付链接

> 输出仅供参考，不构成医疗或营养建议。餐品、价格、库存以官方 MCP 实时结果为准。

## 仓库结构

```text
.
├── README.md                 # 本文件（必须）
├── CONTEST_DECLARATION.md    # 参赛声明（必须，内容不可改）
├── MCP_INTEGRATION.md        # MCP 接入与工具说明（必须）
├── mcp-config.example.json   # 脱敏 MCP 配置示例
├── .env.example              # Token 环境变量占位
├── skill/mcd-calorie-budget/SKILL.md   # Agent Skill 正文
├── scripts/rank_combos.py    # 本地排序助手（不伪造 MCP 响应）
├── fixtures/sample_candidates.json     # 合成样例，仅测排序逻辑
└── examples/dialogue.md      # 示例对话
```

## 前置条件

1. 前往 [open.mcd.cn/mcp](https://open.mcd.cn/mcp) 用**手机号**登录并申请 MCP Token  
2. MCP Client 支持 **Streamable HTTP**  
3. 将 Token 放进环境变量，**不要写进仓库**

```bash
export MCD_MCP_TOKEN="你的真实Token"
```

## 安装 MCP（复制即可）

将 [`mcp-config.example.json`](./mcp-config.example.json) 拷到你的客户端配置，并把 `${MCD_MCP_TOKEN}` 换成真实 Token（或让客户端读环境变量）：

```json
{
  "mcpServers": {
    "mcd-mcp": {
      "type": "streamablehttp",
      "url": "https://mcp.mcd.cn",
      "headers": {
        "Authorization": "Bearer YOUR_MCP_TOKEN"
      }
    }
  }
}
```

各客户端接入说明见官方：[M-China/mcd-mcp-server](https://github.com/M-China/mcd-mcp-server)。

### 安装本 Skill

**Cursor / 兼容 Agent Skills 的客户端：**

```bash
# 任选其一：项目级或用户级
mkdir -p .cursor/skills
cp -R skill/mcd-calorie-budget .cursor/skills/

# 或
mkdir -p ~/.cursor/skills
cp -R skill/mcd-calorie-budget ~/.cursor/skills/
```

在对话里说「按控卡省钱点餐助手帮我点」或 `/mcd-calorie-budget`，Agent 会按 `SKILL.md` 走完整流程。

## 使用示例

用户：

> 中午想吃麦当劳，热量别超 650 kcal，预算 30 块以内，上海徐汇附近，外带。

Agent（摘要）：

1. `now-time-info` → 确认是否早餐窗  
2. `list-nutrition-foods` → 筛 ≤650 kcal  
3. `query-nearby-stores` → 选门店  
4. `query-meals` / `query-meal-detail` → 可组套餐  
5. `available-coupons` → `auto-bind-coupons` → `query-my-coupons` / `query-store-coupons`  
6. `calculate-price` → 给出 2～3 个方案（热量 / 实付 / 蛋白）  
7. 你回复「就第二个」→ `create-order` → **支付链接**（支付在你手机上完成）

更完整的对话见 [`examples/dialogue.md`](./examples/dialogue.md)。

## 本地排序脚本（可选）

不连 MCP 时，可用合成样例验证「控卡 + 省钱」排序逻辑（**不是真实菜单**）：

```bash
python3 scripts/rank_combos.py \
  --input fixtures/sample_candidates.json \
  --calorie-cap 650 \
  --budget 30 \
  --top 3
```

连上 MCP 后，把 `list-nutrition-foods` / `calculate-price` 得到的候选写成同样 JSON 结构再喂给脚本即可。

## 安全与合规

- 仓库内**无真实 Token**；只用 `${MCD_MCP_TOKEN}` / `YOUR_MCP_TOKEN` 占位  
- **禁止**在未确认时调用 `create-order`  
- 本项目不代表麦当劳官方背书；商标归权利人所有  
- 详见 [`CONTEST_DECLARATION.md`](./CONTEST_DECLARATION.md)

## 许可证说明

参赛作品代码以学习与比赛交流为目的开源。使用麦当劳 MCP 须遵守麦当劳中国《使用条款》与 MCP 服务规则。

## 作者

GitHub: [cyAquarius](https://github.com/cyAquarius)

