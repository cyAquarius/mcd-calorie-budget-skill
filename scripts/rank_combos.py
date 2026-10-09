#!/usr/bin/env python3
"""Rank McD calorie/budget combo candidates locally.

Does NOT call the McDonald's MCP. Feed JSON produced from real MCP tool
results (or the synthetic fixture) and get a stable ranking.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Candidate:
    id: str
    title: str
    items: list[str]
    calories_kcal: float
    protein_g: float
    list_price_cny: float
    discount_cny: float
    pay_cny: float
    delivery_fee_cny: float = 0.0

    @property
    def total_pay(self) -> float:
        return float(self.pay_cny) + float(self.delivery_fee_cny)

    def protein_per_100_kcal(self) -> float:
        if self.calories_kcal <= 0:
            return 0.0
        return (self.protein_g / self.calories_kcal) * 100.0

    def protein_per_yuan(self) -> float:
        pay = self.total_pay
        if pay <= 0:
            return 0.0
        return self.protein_g / pay


def parse_candidate(raw: dict[str, Any]) -> Candidate:
    required = [
        "id",
        "title",
        "calories_kcal",
        "protein_g",
        "pay_cny",
    ]
    missing = [k for k in required if k not in raw]
    if missing:
        raise ValueError(f"candidate missing fields: {missing}")
    return Candidate(
        id=str(raw["id"]),
        title=str(raw["title"]),
        items=[str(x) for x in raw.get("items", [])],
        calories_kcal=float(raw["calories_kcal"]),
        protein_g=float(raw["protein_g"]),
        list_price_cny=float(raw.get("list_price_cny", raw["pay_cny"])),
        discount_cny=float(raw.get("discount_cny", 0)),
        pay_cny=float(raw["pay_cny"]),
        delivery_fee_cny=float(raw.get("delivery_fee_cny", 0)),
    )


def rank_candidates(
    candidates: list[Candidate],
    *,
    calorie_cap: float,
    budget_cny: float | None,
    calorie_target: float | None = None,
) -> list[Candidate]:
    """Filter then sort: hit calorie cap, low pay, high protein density."""
    target = calorie_target if calorie_target is not None else calorie_cap
    filtered: list[Candidate] = []
    for c in candidates:
        if c.calories_kcal > calorie_cap:
            continue
        if budget_cny is not None and c.total_pay > budget_cny:
            continue
        filtered.append(c)

    def sort_key(c: Candidate) -> tuple:
        # closer to target is better → smaller abs diff first
        # lower pay better → smaller pay
        # higher protein density better → negate density
        return (
            abs(c.calories_kcal - target),
            c.total_pay,
            -c.protein_per_100_kcal(),
            -c.protein_g,
            c.id,
        )

    return sorted(filtered, key=sort_key)


def load_payload(path: Path) -> tuple[list[Candidate], float | None, float | None]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [parse_candidate(x) for x in data], None, None
    cands = [parse_candidate(x) for x in data.get("candidates", [])]
    return cands, data.get("calorie_cap"), data.get("budget_cny")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", "-i", required=True, type=Path, help="JSON file")
    parser.add_argument("--calorie-cap", type=float, default=None)
    parser.add_argument("--calorie-target", type=float, default=None)
    parser.add_argument("--budget", type=float, default=None, help="CNY pay cap")
    parser.add_argument("--top", type=int, default=3)
    parser.add_argument("--json", action="store_true", help="print JSON only")
    args = parser.parse_args(argv)

    candidates, file_cap, file_budget = load_payload(args.input)
    calorie_cap = args.calorie_cap if args.calorie_cap is not None else file_cap
    budget = args.budget if args.budget is not None else file_budget
    if calorie_cap is None:
        print("error: --calorie-cap required (or set calorie_cap in JSON)", file=sys.stderr)
        return 2

    ranked = rank_candidates(
        candidates,
        calorie_cap=float(calorie_cap),
        budget_cny=float(budget) if budget is not None else None,
        calorie_target=args.calorie_target,
    )
    top = ranked[: max(0, args.top)]

    if args.json:
        out = [
            {
                "rank": i + 1,
                "id": c.id,
                "title": c.title,
                "items": c.items,
                "calories_kcal": c.calories_kcal,
                "protein_g": c.protein_g,
                "pay_cny": c.total_pay,
                "protein_per_100_kcal": round(c.protein_per_100_kcal(), 2),
            }
            for i, c in enumerate(top)
        ]
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    if not top:
        print("无符合热量/预算约束的候选。")
        return 0

    print(f"calorie_cap={calorie_cap} budget={budget} → top {len(top)} / {len(ranked)} eligible")
    print(f"{'Rank':<5}{'ID':<4}{'kcal':>8}{'蛋白g':>8}{'实付¥':>8}  标题")
    for i, c in enumerate(top, 1):
        print(
            f"{i:<5}{c.id:<4}{c.calories_kcal:>8.0f}{c.protein_g:>8.1f}{c.total_pay:>8.2f}  {c.title}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
