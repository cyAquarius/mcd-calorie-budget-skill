# 🍔 控卡省钱点餐助手

[![M-CODE](https://img.shields.io/badge/M--CODE-参赛作品-FFC72C?style=flat-square)](https://github.com/M-China/mcd-developer-innovation-challenge)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)](./pyproject.toml)
[![MCP](https://img.shields.io/badge/MCP-mcp.mcd.cn-000?style=flat-square)](https://mcp.mcd.cn)
[![License](https://img.shields.io/badge/license-学习交流-lightgrey?style=flat-square)](#许可证说明)

> 麦当劳程序员节创意开发大赛（M-CODE）参赛作品 · **非官方** · 数据全部来自官方 MCP 实时查询

**热量卡死 + 预算卡死 → 自动领「麦麦省」→ 算到手价 → 你点头才下单。**

适合：控卡又不想自己翻营养表、学生/打工人要卡预算、以及想把麦当劳 MCP 接到 Cursor / Codex / WorkBuddy 的开发者。

<p align="center">
  <img src="docs/demo-recommend.png" alt="CLI 推荐演示（脱敏）" width="900" />
</p>

## 目录

- [和「只推荐」有什么不一样](#和只推荐有什么不一样)
- [30 秒上手](#30-秒上手)
- [真实 CLI 输出](#真实-cli-输出)
- [安装 Skill / MCP](#安装-skill--mcp)
- [Agent 对话示例](#agent-对话示例)
- [仓库结构](#仓库结构)
- [安全与合规](#安全与合规)
- [许可证 / 作者](#许可证说明)

## 和「只推荐」有什么不一样

| 能力 | 本项目 |
|---|---|
| 双约束 | 热量上限 **且** 金额预算同时卡死 |
| 省钱闭环 | `available-coupons` → `auto-bind-coupons` → `calculate-price` 出**实付** |
| 可下单 | 确认后 `create-order`，返回支付链接；**无 `--confirm` 绝不下单** |
| 堂食 / 外带 / 外送 | 附近门店 + `delivery-*` 地址链路 |
| 可运行 | 零第三方依赖 Python CLI + Agent `SKILL.md` |

输出仅供参考，不构成医疗或营养建议。价格/库存以 MCP 实时结果为准。

## 30 秒上手

1. 在 [open.mcd.cn/mcp](https://open.mcd.cn/mcp) 用手机号申请 MCP Token  
2. 本地配置（二选一，**不要提交进仓**）：

```bash
export MCD_MCP_TOKEN="你的Token"
# 或：mkdir -p ~/.config/mcd && umask 077 && printf '%s' '你的Token' > ~/.config/mcd/mcp_token
```

3. 跑起来：

```bash
git clone https://github.com/cyAquarius/mcd-calorie-budget-skill.git
cd mcd-calorie-budget-skill
pip install -e .          # 可选；也可 PYTHONPATH=src python3 -m mcd_calorie_budget ...

mcd-calorie-budget smoke  # 只读冒烟
mcd-calorie-budget recommend \
  --calorie-cap 650 --budget 35 \
  --city 上海 --keyword 徐汇 --top 3
```

外送：

```bash
mcd-calorie-budget addresses
mcd-calorie-budget recommend \
  --mode delivery --address-id <完整addressId> \
  --calorie-cap 650 --budget 40 --top 3
```

确认下单（真实订单 + 支付链接）：

```bash
mcd-calorie-budget recommend ... --json > /tmp/plan.json
mcd-calorie-budget order --from-json /tmp/plan.json --pick A --confirm
```

一键把 Skill 拷进当前项目（Cursor 等）：

```bash
bash scripts/install_skill.sh
# 或：bash scripts/install_skill.sh /path/to/your/project
```

## 真实 CLI 输出

上海徐汇附近、`calorie_cap=650`、`budget=35`（门店名保留，地址已缩写；实机 2026-10-09）：

```text
======== 控卡省钱点餐 · 推荐结果 ========
数据来源：麦当劳中国 MCP 实时 · 营养表 160 条 · ≤cap 156 · 本店可用券 9

模式：takeout
门店：麦当劳上海徐汇绿地缤纷城餐厅  code=1450384
地址：东安路××号绿地缤纷城B1…
约束：calorie_cap=650 kcal  budget=¥35

方案    热量   蛋白g    原价    优惠    实付  内容
A      513    27.0   26.50    6.62   19.88  巨无霸
B      495    26.0   35.00    8.75   26.25  牛气满满套餐
       组成：培根蔬萃双层牛堡 + 小杯玉米杯 + 无糖可口可乐中杯
C      485    24.0   22.50    5.62   16.88  麦辣鸡腿汉堡

未加 --confirm 不会创建订单。
```

默认优先汉堡/套餐，避免「低卡可乐」刷榜；需要配餐饮品可加 `--allow-sides`。

## 安装 Skill / MCP

### MCP 客户端

把 [`mcp-config.example.json`](./mcp-config.example.json) 拷到客户端，替换 `YOUR_MCP_TOKEN`。官方说明：[M-China/mcd-mcp-server](https://github.com/M-China/mcd-mcp-server)。

### Agent Skill

```bash
bash scripts/install_skill.sh
# 等价于：mkdir -p .cursor/skills && cp -R skill/mcd-calorie-budget .cursor/skills/
```

对话里说「按控卡省钱点餐助手帮我点」，Agent 按 [`skill/mcd-calorie-budget/SKILL.md`](./skill/mcd-calorie-budget/SKILL.md) 走完整流程。工具清单与时序见 [`MCP_INTEGRATION.md`](./MCP_INTEGRATION.md)。

## Agent 对话示例

> 中午想吃麦当劳，热量别超 650 kcal，预算 30 块以内，上海徐汇附近，外带。

Agent：`now-time-info` → `list-nutrition-foods` → `query-nearby-stores` → `query-meals` → 领券算价 → 展示 2～3 方案 → **你确认后再** `create-order`。

外送改走 `delivery-query-addresses` → `delivery-query-stores`。完整话术见 [`examples/dialogue.md`](./examples/dialogue.md)。

本地排序（不连网，可选）：

```bash
python3 scripts/rank_combos.py \
  --input fixtures/sample_candidates.json \
  --calorie-cap 650 --budget 30 --top 3
```

## 仓库结构

```text
.
├── README.md
├── CONTEST_DECLARATION.md   # 参赛声明（内容不可改）
├── MCP_INTEGRATION.md
├── workbuddy.md             # WorkBuddy 导出位（诚实占位）
├── mcp-config.example.json
├── docs/demo-recommend.png
├── src/mcd_calorie_budget/  # 零依赖 CLI → mcp.mcd.cn
├── skill/mcd-calorie-budget/SKILL.md
├── scripts/install_skill.sh
├── fixtures/sample_candidates.json
└── examples/dialogue.md
```

## 安全与合规

- 仓库内**无真实 Token**；只用环境变量 / `~/.config/mcd/mcp_token` / `YOUR_MCP_TOKEN` 占位  
- **禁止**未确认调用 `create-order`（CLI 必须 `--confirm`）  
- 外送地址列表默认脱敏电话与门牌  
- 本项目不代表麦当劳官方背书；商标归权利人所有  
- 详见 [`CONTEST_DECLARATION.md`](./CONTEST_DECLARATION.md)

## 许可证说明

参赛作品以学习与比赛交流为目的开源。使用麦当劳 MCP 须遵守麦当劳中国《使用条款》与 MCP 服务规则。

## 作者

GitHub: [cyAquarius](https://github.com/cyAquarius)

---

⭐ **如果有用，欢迎 Star** —— M-CODE 按公开 Star 排前 100。  
仓库：[cyAquarius/mcd-calorie-budget-skill](https://github.com/cyAquarius/mcd-calorie-budget-skill)
