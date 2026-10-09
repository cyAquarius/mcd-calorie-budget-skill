# WorkBuddy 对话上下文

本文件用于麦当劳程序员节与 WorkBuddy 联动奖励核验（排行榜前 100 且提交本文件可领 WorkBuddy 积分）。

## 当前状态

本仓库主体是用本机 Python CLI + Agent Skill 直连 `https://mcp.mcd.cn` 开发与联调的，**尚未在 WorkBuddy 客户端内完成可导出的开发会话**，因此这里先保留说明，而不是伪造对话记录。

## 若要参加 WorkBuddy 专项奖励

1. 打开 [WorkBuddy](https://www.workbuddy.cn/)，配置自定义 MCP（见仓库 `mcp-config.example.json`，把 `YOUR_MCP_TOKEN` 换成真实 Token）。
2. 在 WorkBuddy 中按 `skill/mcd-calorie-budget/SKILL.md` 走一遍：热量/预算 → 门店 → 领券算价 →（可选）确认下单。
3. 按 WorkBuddy 文档导出对话上下文，**整份替换本文件内容**后推送到公开仓库。

未参加 WorkBuddy 专项奖励时，可忽略本文件；不影响 M-CODE 主赛报名与 Star 排名。
