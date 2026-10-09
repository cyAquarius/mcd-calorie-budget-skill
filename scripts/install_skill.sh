#!/usr/bin/env bash
# 把控卡省钱 Skill 安装到目标项目的 .cursor/skills/
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="${1:-.}"
DEST="$TARGET/.cursor/skills/mcd-calorie-budget"
mkdir -p "$(dirname "$DEST")"
rm -rf "$DEST"
cp -R "$ROOT/skill/mcd-calorie-budget" "$DEST"
echo "已安装 Skill → $DEST"
echo "在对话里说：按控卡省钱点餐助手帮我点"
