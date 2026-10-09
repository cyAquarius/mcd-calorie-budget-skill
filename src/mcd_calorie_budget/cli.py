#!/usr/bin/env python3
"""CLI: 控卡省钱点餐助手 (McDonald's China MCP)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running without install: python -m mcd_calorie_budget from src/
_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from mcd_calorie_budget.flow import CalorieBudgetFlow
from mcd_calorie_budget.mcp_client import McpClient, McpError


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mcd-calorie-budget",
        description="控卡省钱点餐助手：热量/预算筛选 → 领券算价 → 可选确认下单",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    smoke = sub.add_parser("smoke", help="只读冒烟：now-time / nutrition / calendar / available-coupons")
    smoke.add_argument("--json", action="store_true")

    rec = sub.add_parser("recommend", help="完整推荐流程（默认不算价失败就跳过；不下单）")
    rec.add_argument("--calorie-cap", type=float, required=True, help="本餐热量上限 kcal")
    rec.add_argument("--budget", type=float, default=None, help="实付预算（元）")
    rec.add_argument("--calorie-target", type=float, default=None, help="热量目标，默认=cap")
    rec.add_argument("--city", default="上海")
    rec.add_argument("--keyword", default="", help="附近搜索关键词，如 徐汇 / 地标")
    rec.add_argument(
        "--mode",
        choices=("takeout", "dine_in", "delivery"),
        default="takeout",
        help="就餐方式（delivery 需账号已有地址，本 CLI 先支持 takeout/dine_in）",
    )
    rec.add_argument("--store-code", default=None, help="指定门店编码，跳过附近搜索")
    rec.add_argument("--no-auto-bind", action="store_true", help="不调用 auto-bind-coupons")
    rec.add_argument("--top", type=int, default=3)
    rec.add_argument("--json", action="store_true")
    rec.add_argument("-q", "--quiet", action="store_true")

    order = sub.add_parser("order", help="对上次/指定方案下单（必须 --confirm）")
    order.add_argument("--from-json", type=Path, required=True, help="recommend --json 输出文件")
    order.add_argument("--pick", default="A", help="方案字母，如 A/B/C")
    order.add_argument(
        "--confirm",
        action="store_true",
        help="明确确认创建真实订单（会返回支付链接）",
    )
    order.add_argument("--take-way", default=None, help="eat-in / locker-out 等")
    order.add_argument("--json", action="store_true")

    return p


def cmd_smoke(args: argparse.Namespace) -> int:
    client = McpClient()
    client.initialize()
    tools = [
        ("now-time-info", {}),
        ("list-nutrition-foods", {}),
        ("campaign-calendar", {}),
        ("available-coupons", {}),
    ]
    rows = []
    for name, a in tools:
        try:
            r = client.call_tool(name, a)
            ok = not r["isError"] and bool(r.get("text"))
            rows.append({"tool": name, "pass": ok, "chars": len(r.get("text") or "")})
            status = "PASS" if ok else "FAIL"
            print(f"[{status}] {name} ({len(r.get('text') or '')} chars)")
        except McpError as e:
            rows.append({"tool": name, "pass": False, "error": str(e)})
            print(f"[FAIL] {name}: {e}")
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0 if all(r.get("pass") for r in rows) else 1


def cmd_recommend(args: argparse.Namespace) -> int:
    if args.mode == "delivery":
        print(
            "当前 CLI 的 recommend 主路径为到店自取/外带 (beType=1)。"
            "外送请用 Agent Skill + delivery-* 工具，或后续版本。",
            file=sys.stderr,
        )
        return 2

    client = McpClient()
    log = (lambda m: None) if args.quiet else (lambda m: print(m, file=sys.stderr))
    flow = CalorieBudgetFlow(client, log=log)
    try:
        result = flow.run(
            calorie_cap=args.calorie_cap,
            budget_cny=args.budget,
            calorie_target=args.calorie_target,
            city=args.city,
            keyword=args.keyword,
            dining_mode=args.mode,
            be_type=1,
            order_type=1,
            store_code=args.store_code,
            auto_bind=not args.no_auto_bind,
            top=args.top,
        )
    except McpError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    payload = {
        "store": {
            "storeCode": (result.store or {}).get("storeCode"),
            "storeName": (result.store or {}).get("storeName"),
            "address": (result.store or {}).get("address"),
        },
        "nutrition_under_cap": result.foods_matched,
        "available_coupons": [
            {"title": c.get("title"), "status": c.get("status")} for c in result.available_coupons[:10]
        ],
        "store_coupons": [
            {
                "title": c.get("title"),
                "couponId": _redact_id(c.get("couponId")),
                "products": [
                    {"productCode": p.get("productCode"), "productName": p.get("productName")}
                    for p in (c.get("products") or [])[:5]
                    if isinstance(p, dict)
                ],
            }
            for c in result.store_coupons[:10]
        ],
        "options": [
            {
                "id": c.id,
                "title": c.title,
                "items": c.items,
                "calories_kcal": c.calories_kcal,
                "protein_g": c.protein_g,
                "list_price_cny": c.list_price_cny,
                "discount_cny": c.discount_cny,
                "pay_cny": c.pay_cny,
                "product_code": c.product_code,
                "has_coupon": bool(c.coupon_id),
                # keep fields needed for order; coupon ids kept for order path but not printed in table
                "_order": {
                    "product_code": c.product_code,
                    "coupon_id": c.coupon_id,
                    "coupon_code": c.coupon_code,
                    "round_list": c.round_list,
                    "extra": c.extra,
                    "title": c.title,
                    "items": c.items,
                    "calories_kcal": c.calories_kcal,
                    "protein_g": c.protein_g,
                    "pay_cny": c.pay_cny,
                    "list_price_cny": c.list_price_cny,
                    "discount_cny": c.discount_cny,
                },
            }
            for c in result.ranked
        ],
        "notes": result.notes,
        "tools": result.tool_log,
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    store = result.store or {}
    print(f"门店：{store.get('storeName')}  code={store.get('storeCode')}")
    if store.get("address"):
        print(f"地址：{_sanitize_address(store.get('address'))}")
    print(
        f"约束：calorie_cap={args.calorie_cap} kcal"
        + (f"  budget=¥{args.budget}" if args.budget is not None else "")
    )
    print(f"营养表中 ≤cap 单品：{result.foods_matched}")
    if result.available_coupons:
        print(f"麦麦省可领/列表：{len(result.available_coupons)}（详见 MCP）")
    if result.store_coupons:
        print(f"本店可用券：{len(result.store_coupons)}")
    if not result.ranked:
        print("无符合条件的方案。")
        for n in result.notes:
            print(f"- {n}")
        return 0

    print()
    print(f"{'方案':<4}{'热量':>8}{'蛋白g':>8}{'原价':>8}{'优惠':>8}{'实付':>8}  内容")
    for c in result.ranked:
        print(
            f"{c.id:<4}{c.calories_kcal:>8.0f}{c.protein_g:>8.1f}"
            f"{c.list_price_cny:>8.2f}{c.discount_cny:>8.2f}{c.pay_cny:>8.2f}  {c.title}"
        )
        if c.items and c.items != [c.title]:
            print(f"     组成：{' + '.join(c.items)}")
    print()
    print("未加 --confirm 不会创建订单。若要下单：")
    print("  1) 先 recommend --json > /tmp/plan.json")
    print("  2) python -m mcd_calorie_budget order --from-json /tmp/plan.json --pick A --confirm")
    for n in result.notes:
        print(f"note: {n}")
    return 0


def cmd_order(args: argparse.Namespace) -> int:
    if not args.confirm:
        print(
            "拒绝下单：缺少 --confirm。请仅在用户明确确认某一方案后使用。",
            file=sys.stderr,
        )
        return 2
    data = json.loads(args.from_json.read_text(encoding="utf-8"))
    options = data.get("options") or []
    pick = None
    for o in options:
        if str(o.get("id")).upper() == str(args.pick).upper():
            pick = o
            break
    if not pick:
        print(f"找不到方案 {args.pick}", file=sys.stderr)
        return 1
    order_blob = pick.get("_order") or {}
    from mcd_calorie_budget.rank import Candidate

    cand = Candidate(
        id=str(pick.get("id")),
        title=str(order_blob.get("title") or pick.get("title")),
        items=list(order_blob.get("items") or pick.get("items") or []),
        calories_kcal=float(order_blob.get("calories_kcal") or 0),
        protein_g=float(order_blob.get("protein_g") or 0),
        list_price_cny=float(order_blob.get("list_price_cny") or 0),
        discount_cny=float(order_blob.get("discount_cny") or 0),
        pay_cny=float(order_blob.get("pay_cny") or pick.get("pay_cny") or 0),
        product_code=order_blob.get("product_code") or pick.get("product_code"),
        coupon_id=order_blob.get("coupon_id"),
        coupon_code=order_blob.get("coupon_code"),
        round_list=order_blob.get("round_list"),
        extra=order_blob.get("extra") or {},
    )
    client = McpClient()
    flow = CalorieBudgetFlow(client, log=lambda m: print(m, file=sys.stderr))
    try:
        result = flow.create_order(cand, take_way_code=args.take_way)
    except McpError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    # sanitize: don't dump full personal payloads loudly
    blob = result.get("json") or {}
    data_field = blob.get("data") if isinstance(blob, dict) else None
    summary = {
        "success": blob.get("success") if isinstance(blob, dict) else None,
        "message": blob.get("message") if isinstance(blob, dict) else None,
        "order_keys": list(data_field.keys()) if isinstance(data_field, dict) else None,
    }
    # try extract pay url without printing phones
    if isinstance(data_field, dict):
        for k in ("payUrl", "pay_url", "paymentUrl", "cashierUrl", "url"):
            if data_field.get(k):
                summary["pay_url"] = data_field.get(k)
                break
        if data_field.get("orderId") or data_field.get("orderCode"):
            summary["order_id"] = data_field.get("orderId") or data_field.get("orderCode")

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print("订单创建结果（摘要）：")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        print("请在手机上打开支付链接完成支付；本工具不会代付。")
    return 0


def _redact_id(v: object) -> str | None:
    if v is None:
        return None
    s = str(v)
    if len(s) <= 8:
        return "***"
    return f"{s[:4]}…{s[-4:]}"


def _sanitize_address(addr: object) -> str:
    s = str(addr or "")
    # keep street-level but avoid dumping phone-like digits runs in notes
    return s


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.cmd == "smoke":
            return cmd_smoke(args)
        if args.cmd == "recommend":
            return cmd_recommend(args)
        if args.cmd == "order":
            return cmd_order(args)
    except McpError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    parser.error(f"unknown cmd {args.cmd}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
