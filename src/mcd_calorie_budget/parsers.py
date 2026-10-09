"""Parse McDonald's MCP tool responses (markdown envelope + JSON / nutrition DSL)."""

from __future__ import annotations

import json
import re
from typing import Any


def extract_api_json(text: str) -> dict[str, Any] | None:
    """Extract the API envelope JSON ({"success":...} or similar) from tool text."""
    if not text:
        return None
    for marker in ('{"success"', '{"code"', '{"data"'):
        idx = text.find(marker)
        if idx >= 0:
            try:
                obj, _ = json.JSONDecoder().raw_decode(text[idx:])
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                continue
    # last-resort: any top-level object
    idx = text.find("{")
    while idx >= 0:
        try:
            obj, _ = json.JSONDecoder().raw_decode(text[idx:])
            if isinstance(obj, dict) and ("data" in obj or "success" in obj):
                return obj
        except json.JSONDecodeError:
            pass
        idx = text.find("{", idx + 1)
    return None


def fen_to_yuan(value: Any) -> float | None:
    """MCP money fields are usually integer fen (分). Strings may already be yuan."""
    if value is None:
        return None
    if isinstance(value, str):
        s = value.strip().replace("¥", "").replace("元", "")
        if not s:
            return None
        try:
            f = float(s)
        except ValueError:
            return None
        # Heuristic: integers > 100 looking like fen in int fields; strings like "22.5" are yuan
        if "." in s:
            return f
        if f >= 100 and f == int(f):
            return f / 100.0
        return f
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    # integer fen
    if isinstance(value, int) or (isinstance(value, float) and n == int(n) and abs(n) >= 100):
        return n / 100.0
    return n


def parse_nutrition_dsl(data_field: str) -> list[dict[str, Any]]:
    """Parse list-nutrition-foods data DSL:

    [160]{productName,nutritionDescription,energyKj,energyKcal,...}:
      猪柳麦满分,null,1288,308,16,16,24,781,213
    """
    if not isinstance(data_field, str):
        return []
    header = re.search(r"\{([^}]+)\}:", data_field)
    if not header:
        return []
    columns = [c.strip() for c in header.group(1).split(",")]
    body = data_field[header.end() :]
    foods: list[dict[str, Any]] = []
    for line in body.splitlines():
        line = line.strip()
        if not line or line.startswith("["):
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < len(columns):
            # name may contain commas rarely; pad
            parts += [""] * (len(columns) - len(parts))
        if len(parts) > len(columns):
            # merge overflow into first field (name)
            overflow = len(parts) - len(columns)
            parts = [",".join(parts[: overflow + 1])] + parts[overflow + 1 :]
        row: dict[str, Any] = {}
        for col, raw in zip(columns, parts):
            if raw in ("null", "None", ""):
                row[col] = None
                continue
            try:
                if "." in raw:
                    row[col] = float(raw)
                else:
                    row[col] = int(raw)
            except ValueError:
                row[col] = raw
        if row.get("productName"):
            foods.append(row)
    return foods


def parse_nutrition_response(text: str) -> list[dict[str, Any]]:
    blob = extract_api_json(text)
    if not blob:
        return []
    data = blob.get("data")
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, str):
        return parse_nutrition_dsl(data)
    return []


def parse_stores(text: str) -> list[dict[str, Any]]:
    blob = extract_api_json(text)
    if not blob:
        return []
    data = blob.get("data")
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict) and isinstance(data.get("stores"), list):
        return [x for x in data["stores"] if isinstance(x, dict)]
    return []


def parse_meals(text: str) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Return (categories, meals_by_code)."""
    blob = extract_api_json(text)
    if not blob:
        return [], {}
    data = blob.get("data") or {}
    if not isinstance(data, dict):
        return [], {}
    categories = data.get("categories") or []
    meals = data.get("meals") or {}
    if not isinstance(meals, dict):
        meals = {}
    return list(categories) if isinstance(categories, list) else [], meals


def parse_meal_detail(text: str) -> dict[str, Any] | None:
    blob = extract_api_json(text)
    if not blob:
        return None
    data = blob.get("data")
    return data if isinstance(data, dict) else None


def default_round_list(detail: dict[str, Any]) -> list[dict[str, Any]]:
    """Build calculate-price roundList from meal-detail defaults (isDefault=1)."""
    rounds = detail.get("rounds") or []
    out: list[dict[str, Any]] = []
    for r in rounds:
        if not isinstance(r, dict):
            continue
        choices = r.get("choices") or []
        if isinstance(choices, dict):
            choices = [choices]
        defaults = [
            c
            for c in choices
            if isinstance(c, dict) and str(c.get("isDefault")) in ("1", "true", "True")
        ]
        if not defaults and choices:
            defaults = [choices[0]]
        combo = []
        for c in defaults:
            code = c.get("code")
            if not code:
                continue
            combo.append(
                {
                    "code": str(code),
                    "quantity": int(c.get("quantity") or r.get("quantity") or 1),
                }
            )
        if combo:
            out.append({"round": str(r.get("id") or r.get("name") or ""), "comboItemList": combo})
    return out


def parse_price(text: str) -> dict[str, Any] | None:
    blob = extract_api_json(text)
    if not blob:
        return None
    data = blob.get("data")
    if not isinstance(data, dict):
        return None
    return {
        "product_original_yuan": fen_to_yuan(data.get("productOriginalPrice")),
        "product_yuan": fen_to_yuan(data.get("productPrice")),
        "original_yuan": fen_to_yuan(data.get("originalPrice")),
        "discount_yuan": fen_to_yuan(data.get("discount")),
        "pay_yuan": fen_to_yuan(data.get("price")),
        "take_way_list": data.get("takeWayList") or [],
        "product_list": data.get("productList") or [],
        "enjoyed": data.get("enjoyed"),
        "enjoyable": data.get("enjoyable"),
        "raw": data,
    }


def parse_coupons(text: str) -> list[dict[str, Any]]:
    blob = extract_api_json(text)
    if blob:
        data = blob.get("data")
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        if isinstance(data, dict):
            for key in ("coupons", "list", "items"):
                if isinstance(data.get(key), list):
                    return [x for x in data[key] if isinstance(x, dict)]
    # markdown-only available-coupons: scrape titles
    titles = re.findall(r"优惠券标题：\s*(.+?)(?:\s*\\\\|\s*$)", text, re.M)
    statuses = re.findall(r"状态：\s*(.+?)(?:\s*\\\\|\s*$)", text, re.M)
    out = []
    for i, title in enumerate(titles):
        out.append(
            {
                "title": title.strip(),
                "status": statuses[i].strip() if i < len(statuses) else None,
            }
        )
    return out


def normalize_name(name: str) -> str:
    s = (name or "").strip().lower()
    for ch in (" ", "\u3000", "（", "）", "(", ")", "【", "】", "-", "_"):
        s = s.replace(ch, "")
    return s
