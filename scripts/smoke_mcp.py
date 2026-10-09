#!/usr/bin/env python3
"""Live MCP smoke (read-only). Requires MCD_MCP_TOKEN. Never creates orders."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mcd_calorie_budget.mcp_client import McpClient, McpError  # noqa: E402
from mcd_calorie_budget.parsers import (  # noqa: E402
    parse_nutrition_response,
    parse_stores,
)


def main() -> int:
    if not os.environ.get("MCD_MCP_TOKEN"):
        token_path = Path.home() / ".config/mcd/mcp_token"
        if token_path.is_file():
            os.environ["MCD_MCP_TOKEN"] = token_path.read_text(encoding="utf-8").strip()
    client = McpClient()
    client.initialize()
    checks = []

    def check(name: str, fn):
        try:
            ok, detail = fn()
            checks.append({"tool": name, "pass": ok, "detail": detail})
            print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")
        except Exception as e:
            checks.append({"tool": name, "pass": False, "detail": str(e)})
            print(f"[FAIL] {name}: {e}")

    def now():
        r = client.call_tool("now-time-info")
        text = r["text"] or ""
        ok = (not r["isError"]) and (("data" in text.lower()) or ("时间" in text) or len(text) > 20)
        return ok, f"chars={len(text)}"

    def nutrition():
        r = client.call_tool("list-nutrition-foods")
        foods = parse_nutrition_response(r["text"])
        return len(foods) > 10, f"foods={len(foods)}"

    def calendar():
        r = client.call_tool("campaign-calendar")
        return (not r["isError"] and len(r["text"]) > 50), f"chars={len(r['text'])}"

    def coupons():
        r = client.call_tool("available-coupons")
        return (not r["isError"] and len(r["text"]) > 20), f"chars={len(r['text'])}"

    def stores():
        r = client.call_tool(
            "query-nearby-stores",
            {"beType": 1, "searchType": 2, "city": "上海", "keyword": "徐汇"},
        )
        stores = parse_stores(r["text"])
        return len(stores) >= 1, f"stores={len(stores)} first={(stores[0].get('storeName') if stores else None)}"

    check("now-time-info", now)
    check("list-nutrition-foods", nutrition)
    check("campaign-calendar", calendar)
    check("available-coupons", coupons)
    check("query-nearby-stores", stores)

    out = ROOT / "fixtures" / "smoke_last_result.json"
    # sanitize store names ok; no tokens
    out.write_text(json.dumps(checks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    return 0 if all(c["pass"] for c in checks) else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except McpError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(1)
