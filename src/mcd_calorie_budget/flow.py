"""Core recommend flow: nutrition → store → meals → coupons → price → rank."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .mcp_client import McpClient, McpError
from .parsers import (
    default_round_list,
    extract_api_json,
    fen_to_yuan,
    meal_role,
    normalize_name,
    nutrition_match_kind,
    parse_addresses,
    parse_coupons,
    parse_meal_detail,
    parse_meals,
    parse_nutrition_response,
    parse_price,
    parse_stores,
    redact_address_line,
    redact_phone,
)
from .rank import Candidate, rank_candidates


LogFn = Callable[[str], None]


def _noop_log(msg: str) -> None:
    pass


@dataclass
class FlowResult:
    time_info: str = ""
    foods_matched: int = 0
    store: dict[str, Any] | None = None
    address: dict[str, Any] | None = None
    available_coupons: list[dict[str, Any]] = field(default_factory=list)
    store_coupons: list[dict[str, Any]] = field(default_factory=list)
    candidates: list[Candidate] = field(default_factory=list)
    ranked: list[Candidate] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    tool_log: list[dict[str, Any]] = field(default_factory=list)


class CalorieBudgetFlow:
    def __init__(self, client: McpClient, log: LogFn | None = None) -> None:
        self.client = client
        self.log = log or _noop_log

    def _tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        self.log(f"→ {name}")
        result = self.client.call_tool(name, arguments)
        entry = {
            "tool": name,
            "ok": not result["isError"],
            "chars": len(result.get("text") or ""),
        }
        self.tool_log_append(entry)
        if result["isError"]:
            raise McpError(f"工具 {name} 返回 isError: {(result.get('text') or '')[:200]}")
        return result

    def tool_log_append(self, entry: dict[str, Any]) -> None:
        # filled by run via mutable on result; keep local buffer
        if not hasattr(self, "_tool_log"):
            self._tool_log: list[dict[str, Any]] = []
        self._tool_log.append(entry)

    def run(
        self,
        *,
        calorie_cap: float,
        budget_cny: float | None = None,
        calorie_target: float | None = None,
        city: str = "上海",
        keyword: str = "",
        dining_mode: str = "takeout",  # dine_in | takeout | delivery
        be_type: int | None = None,  # 1 takeout/dine-in, 2 delivery, 5 DT
        order_type: int | None = None,
        store_code: str | None = None,
        address_id: str | None = None,
        auto_bind: bool = True,
        top: int = 3,
        max_meal_scan: int = 40,
        prefer_mains: bool = True,
    ) -> FlowResult:
        self._tool_log = []
        out = FlowResult()

        if dining_mode == "delivery":
            be_type = 2 if be_type is None else be_type
            order_type = 2 if order_type is None else order_type
        else:
            be_type = 1 if be_type is None else be_type
            order_type = 1 if order_type is None else order_type

        # 1) time
        t = self._tool("now-time-info")
        out.time_info = (t.get("text") or "")[:400]
        self.log("时间窗已获取")

        # 2) nutrition
        n = self._tool("list-nutrition-foods")
        foods = parse_nutrition_response(n["text"])
        under = [
            f
            for f in foods
            if _as_float(f.get("energyKcal")) is not None
            and _as_float(f.get("energyKcal")) <= calorie_cap
        ]
        nutrition_by_name = {
            normalize_name(str(f.get("productName"))): f for f in foods if f.get("productName")
        }
        out.foods_matched = len(under)
        self.log(f"营养表 {len(foods)} 条，≤{calorie_cap:.0f} kcal：{len(under)} 条")

        # 3) store (+ delivery address)
        address_id_resolved: str | None = None
        if dining_mode == "delivery":
            store, address_id_resolved, addr_notes = self._resolve_delivery_store(
                address_id=address_id, store_code=store_code
            )
            out.notes.extend(addr_notes)
            if address_id_resolved:
                # keep redacted address snapshot for CLI display
                out.address = {"addressId": address_id_resolved}
            if not store:
                out.tool_log = list(self._tool_log)
                return out
        elif store_code:
            store = {"storeCode": store_code, "storeName": store_code}
        else:
            st = self._tool(
                "query-nearby-stores",
                {
                    "beType": be_type,
                    "searchType": 2,
                    "city": city,
                    "keyword": keyword or city,
                },
            )
            stores = parse_stores(st["text"])
            open_stores = [s for s in stores if s.get("businessStatus") in (True, "true", 1, "1")]
            pick = (open_stores or stores)
            if not pick:
                out.notes.append("附近无可用门店，请换城市/关键词。")
                out.tool_log = list(self._tool_log)
                return out
            store = pick[0]
        out.store = store
        sc = str(store.get("storeCode"))
        be_code = store.get("beCode")
        self.log(f"门店：{store.get('storeName') or sc} ({sc})")

        # 4) meals
        meal_args: dict[str, Any] = {
            "storeCode": sc,
            "orderType": order_type,
            "beType": be_type,
        }
        if be_code and be_type != 1:
            meal_args["beCode"] = be_code
        mq = self._tool("query-meals", meal_args)
        categories, meals = parse_meals(mq["text"])
        self.log(f"可售餐品 {len(meals)} 个，分类 {len(categories)}")

        # Build candidate pool: prefer named combos / burgers with nutrition match
        scored: list[tuple[float, str, dict[str, Any]]] = []
        for code, meal in meals.items():
            name = str(meal.get("name") or "")
            price = fen_to_yuan(meal.get("currentPrice")) or fen_to_yuan(meal.get("originalPrice"))
            if price is None:
                continue
            if budget_cny is not None and price > budget_cny * 1.4:
                # loose prefilter; coupons may reduce
                continue
            nut = _match_nutrition(name, nutrition_by_name)
            kcal = _as_float(nut.get("energyKcal")) if nut else None
            protein = _as_float(nut.get("protein")) if nut else None
            role = meal_role(name)
            matched_product = str(nut.get("productName")) if nut else None
            match_kind = nutrition_match_kind(name, matched_product)
            # Prefer items with known kcal under cap, else combos/burgers for detail expand
            score = 0.0
            if prefer_mains and role in ("drink", "dessert"):
                # still allow later if mains empty; heavily deprioritize now
                score -= 80
            if kcal is not None:
                if kcal > calorie_cap:
                    continue
                score += 120 - abs(kcal - (calorie_target or calorie_cap)) / max(calorie_cap, 1)
            elif any(k in name for k in ("套餐", "三件套", "两件套")):
                score += 15  # unknown kcal combos: still try via detail
            if any(k in name for k in ("套餐", "三件套", "两件套")) and kcal is not None:
                score += 25
            if role == "main":
                score += 20
            if any(k in name for k in ("汉堡", "巨无霸", "板烧", "麦辣", "麦香", "安格斯")):
                score += 10
            if budget_cny is not None:
                score += max(0, 30 - abs(price - budget_cny * 0.7))
            scored.append(
                (
                    score,
                    code,
                    {
                        "name": name,
                        "price": price,
                        "kcal": kcal,
                        "protein": protein,
                        "nut": nut,
                        "role": role,
                        "match_kind": match_kind,
                    },
                )
            )

        scored.sort(key=lambda x: -x[0])
        if prefer_mains:
            mains = [x for x in scored if x[2].get("role") == "main"]
            if mains:
                pool = mains[:max_meal_scan]
            else:
                # fall back but warn — avoids recommending only zero-cal drinks
                pool = scored[:max_meal_scan]
                out.notes.append("未找到明显主食/套餐，结果可能含小食或饮品，请自行核对。")
        else:
            pool = scored[:max_meal_scan]
        if not pool:
            out.notes.append("菜单与热量约束无交集，请放宽 calorie_cap 或 budget。")
            out.tool_log = list(self._tool_log)
            return out

        # 5) coupons
        try:
            av = self._tool("available-coupons")
            out.available_coupons = parse_coupons(av["text"])
            self.log(f"可领麦麦省：{len(out.available_coupons)}")
        except McpError as e:
            out.notes.append(f"available-coupons 失败：{e}")

        if auto_bind and out.available_coupons:
            claimable = [
                c
                for c in out.available_coupons
                if (c.get("status") or "") not in ("已领取", "已领", "不可领")
            ]
            # even if markdown says 已领取, try once is ok; auto-bind is idempotent-ish
            try:
                self._tool("auto-bind-coupons")
                self.log("已尝试 auto-bind-coupons")
            except McpError as e:
                out.notes.append(f"auto-bind-coupons 失败：{e}")

        try:
            my = self._tool("query-my-coupons", {"page": "1", "pageSize": "50"})
            my_coupons = parse_coupons(my["text"])
            self.log(f"我的券：{len(my_coupons)}")
        except McpError as e:
            my_coupons = []
            out.notes.append(f"query-my-coupons 失败：{e}")

        coupon_args: dict[str, Any] = {
            "storeCode": sc,
            "orderType": order_type,
            "beType": be_type,
        }
        if be_code and be_type != 1:
            coupon_args["beCode"] = be_code
        try:
            scp = self._tool("query-store-coupons", coupon_args)
            out.store_coupons = parse_coupons(scp["text"])
            self.log(f"门店可用券：{len(out.store_coupons)}")
        except McpError as e:
            out.notes.append(f"query-store-coupons 失败：{e}")

        # 6) price top candidates
        candidates: list[Candidate] = []
        for idx, (_score, code, meta) in enumerate(pool[:18]):
            name = meta["name"]
            looks_combo = any(k in name for k in ("套餐", "三件套", "两件套", "开心乐园"))
            detail: dict[str, Any] = {}
            round_list = None
            if looks_combo or meta["kcal"] is None:
                detail_args = {
                    "storeCode": sc,
                    "orderType": order_type,
                    "beType": be_type,
                    "code": code,
                }
                if be_code and be_type != 1:
                    detail_args["beCode"] = be_code
                try:
                    detail_res = self._tool("query-meal-detail", detail_args)
                    detail = parse_meal_detail(detail_res["text"]) or {}
                except McpError:
                    detail = {}
                round_list = default_round_list(detail) if detail.get("rounds") else None

            items_payload: dict[str, Any] = {"productCode": code, "quantity": 1}
            if round_list:
                items_payload["roundList"] = round_list

            # estimate kcal from components if combo
            est_kcal, est_protein, item_names = _estimate_combo_nutrition(
                detail, nutrition_by_name, fallback_kcal=meta["kcal"], fallback_protein=meta["protein"], fallback_name=name
            )
            if est_kcal is not None and est_kcal > calorie_cap:
                continue

            # optional best coupon for this product
            coupon_id, coupon_code = _pick_coupon_for_product(out.store_coupons, code, name)
            if coupon_id:
                items_payload["couponId"] = coupon_id
            if coupon_code:
                items_payload["couponCode"] = coupon_code

            price_args: dict[str, Any] = {
                "storeCode": sc,
                "orderType": order_type,
                "beType": be_type,
                "items": [items_payload],
                "needTableware": False,
            }
            if be_code and be_type != 1:
                price_args["beCode"] = be_code
            try:
                price_res = self._tool("calculate-price", price_args)
                price = parse_price(price_res["text"])
            except McpError as e:
                out.notes.append(f"算价失败 {name}: {e}")
                continue
            if not price or price.get("pay_yuan") is None:
                continue

            match_kind = meta.get("match_kind") or "none"
            if looks_combo and match_kind in ("component_only", "partial", "none") and not (
                detail.get("rounds") and item_names and len(item_names) > 1
            ):
                out.notes.append(
                    f"「{name}」热量可能仅按单品口径估算，套餐真实热量可能更高。"
                )
            cand = Candidate(
                id=str(len(candidates) + 1),  # temporary; re-letter after rank
                title=name,
                items=item_names or [name],
                calories_kcal=float(est_kcal or 0),
                protein_g=float(est_protein or 0),
                list_price_cny=float(price.get("original_yuan") or price.get("product_original_yuan") or 0),
                discount_cny=float(price.get("discount_yuan") or 0),
                pay_cny=float(price["pay_yuan"]),
                product_code=code,
                coupon_id=coupon_id,
                coupon_code=coupon_code,
                round_list=round_list,
                extra={
                    "store_code": sc,
                    "be_type": be_type,
                    "order_type": order_type,
                    "be_code": be_code,
                    "take_way_list": price.get("take_way_list") or [],
                    "dining_mode": dining_mode,
                    "address_id": address_id_resolved,
                    "match_kind": match_kind,
                    "role": meta.get("role"),
                },
            )
            candidates.append(cand)
            if len(candidates) >= max(top * 3, 6):
                break

        out.candidates = candidates
        ranked = rank_candidates(
            candidates,
            calorie_cap=calorie_cap,
            budget_cny=budget_cny,
            calorie_target=calorie_target,
        )[:top]
        for i, c in enumerate(ranked):
            c.id = chr(ord("A") + i)
        out.ranked = ranked
        out.tool_log = list(self._tool_log)
        if not out.ranked:
            out.notes.append("无方案同时满足热量与预算；可放宽上限后重试。")
        return out

    def create_order(
        self,
        candidate: Candidate,
        *,
        take_way_code: str | None = None,
        need_tableware: bool = False,
    ) -> dict[str, Any]:
        """Create order for a ranked candidate. Caller must have user confirmation."""
        extra = candidate.extra or {}
        sc = str(extra.get("store_code") or "")
        be_type = int(extra.get("be_type") or 1)
        order_type = int(extra.get("order_type") or 1)
        be_code = extra.get("be_code")
        items_payload: dict[str, Any] = {
            "productCode": candidate.product_code,
            "quantity": 1,
        }
        if candidate.round_list:
            items_payload["roundList"] = candidate.round_list
        if candidate.coupon_id:
            items_payload["couponId"] = candidate.coupon_id
        if candidate.coupon_code:
            items_payload["couponCode"] = candidate.coupon_code

        # pick take way
        tw = take_way_code
        if not tw and order_type == 1:
            ways = extra.get("take_way_list") or []
            # prefer locker-out for takeout
            mode = extra.get("dining_mode") or "takeout"
            prefer = "locker-out" if mode == "takeout" else "eat-in"
            for w in ways:
                if isinstance(w, dict) and w.get("code") == prefer:
                    tw = prefer
                    break
            if not tw and ways and isinstance(ways[0], dict):
                tw = ways[0].get("code")

        args: dict[str, Any] = {
            "storeCode": sc,
            "orderType": order_type,
            "beType": be_type,
            "items": [items_payload],
            "needTableware": need_tableware,
        }
        if be_code and be_type != 1:
            args["beCode"] = be_code
        address_id = extra.get("address_id")
        if be_type == 2 and address_id:
            args["addressId"] = address_id
        if tw and order_type == 1:
            args["takeWayCode"] = tw

        res = self._tool("create-order", args)
        blob = extract_api_json(res["text"]) or {}
        return {"text": res["text"], "json": blob}


    def list_delivery_addresses(self) -> list[dict[str, Any]]:
        """Return redacted address summaries for CLI listing."""
        res = self._tool("delivery-query-addresses")
        raw = parse_addresses(res["text"])
        out = []
        for a in raw:
            out.append(
                {
                    "addressId": a.get("addressId"),
                    "contactName": a.get("contactName"),
                    "phone_redacted": redact_phone(a.get("phone")),
                    "address_redacted": redact_address_line(a.get("fullAddress"), keep_chars=18),
                    "fullAddress": a.get("fullAddress"),
                    "raw": a,
                }
            )
        return out

    def _resolve_delivery_store(
        self,
        *,
        address_id: str | None,
        store_code: str | None,
    ) -> tuple[dict[str, Any] | None, str | None, list[str]]:
        notes: list[str] = []
        addrs = self.list_delivery_addresses()
        if not addrs:
            notes.append(
                "账号暂无外送地址。请先在麦当劳 App 添加，或让 Agent 经用户确认后调用 delivery-create-address。"
            )
            return None, None, notes
        chosen = None
        if address_id:
            for a in addrs:
                if str(a.get("addressId")) == str(address_id):
                    chosen = a
                    break
            if not chosen:
                notes.append(f"找不到 addressId={address_id[-6:]}…，请用 addresses 子命令查看。")
                return None, None, notes
        else:
            chosen = addrs[0]
            if len(addrs) > 1:
                notes.append(
                    f"未指定 --address-id，默认使用第一条（共 {len(addrs)} 条）。"
                    "可用 `mcd-calorie-budget addresses` 查看后传入。"
                )
        aid = str(chosen.get("addressId"))
        self.log(
            f"外送地址：{chosen.get('address_redacted')} / {chosen.get('phone_redacted')}"
        )
        if store_code:
            # still need beCode from delivery-query-stores when possible
            st = self._tool(
                "delivery-query-stores",
                {"beType": 2, "addressId": aid},
            )
            stores = parse_stores(st["text"])
            match = next((s for s in stores if str(s.get("storeCode")) == str(store_code)), None)
            if match:
                return match, aid, notes
            notes.append("指定 storeCode 不在该地址可配送列表，仍按编码下单（可能失败）。")
            return {"storeCode": store_code, "storeName": store_code}, aid, notes

        st = self._tool("delivery-query-stores", {"beType": 2, "addressId": aid})
        stores = parse_stores(st["text"])
        open_stores = [s for s in stores if s.get("businessStatus") in (True, "true", 1, "1")]
        pick = open_stores or stores
        if not pick:
            notes.append("该地址暂无可配送门店（或已打烊）。")
            return None, aid, notes
        return pick[0], aid, notes


def _as_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _match_nutrition(name: str, nutrition_by_name: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    n = normalize_name(name)
    if n in nutrition_by_name:
        return nutrition_by_name[n]
    # substring soft match
    best = None
    best_len = 0
    for key, food in nutrition_by_name.items():
        if key and (key in n or n in key):
            if len(key) > best_len:
                best = food
                best_len = len(key)
    return best


def _estimate_combo_nutrition(
    detail: dict[str, Any],
    nutrition_by_name: dict[str, dict[str, Any]],
    *,
    fallback_kcal: float | None,
    fallback_protein: float | None,
    fallback_name: str,
) -> tuple[float | None, float | None, list[str]]:
    rounds = detail.get("rounds") or []
    names: list[str] = []
    kcal = 0.0
    protein = 0.0
    found = 0
    for r in rounds:
        choices = r.get("choices") or []
        defaults = [
            c
            for c in choices
            if isinstance(c, dict) and str(c.get("isDefault")) in ("1", "true", "True")
        ]
        if not defaults and choices:
            defaults = [choices[0]]
        for c in defaults:
            cname = str(c.get("name") or "")
            names.append(cname)
            nut = _match_nutrition(cname, nutrition_by_name)
            if nut:
                k = _as_float(nut.get("energyKcal"))
                p = _as_float(nut.get("protein"))
                if k is not None:
                    kcal += k
                    found += 1
                if p is not None:
                    protein += p
    if found:
        return kcal, protein, names or [fallback_name]
    return fallback_kcal, fallback_protein, names or [fallback_name]


def _pick_coupon_for_product(
    store_coupons: list[dict[str, Any]], product_code: str, product_name: str
) -> tuple[str | None, str | None]:
    for c in store_coupons:
        products = c.get("products") or []
        for p in products:
            if not isinstance(p, dict):
                continue
            if str(p.get("productCode")) == str(product_code):
                return (
                    str(c["couponId"]) if c.get("couponId") else None,
                    str(c["couponCode"]) if c.get("couponCode") else None,
                )
            pname = str(p.get("productName") or "")
            if pname and (pname in product_name or product_name in pname):
                return (
                    str(c["couponId"]) if c.get("couponId") else None,
                    str(c["couponCode"]) if c.get("couponCode") else None,
                )
    return None, None
