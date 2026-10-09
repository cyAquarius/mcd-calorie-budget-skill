"""Stable ranking for calorie/budget meal candidates."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Candidate:
    id: str
    title: str
    items: list[str] = field(default_factory=list)
    calories_kcal: float = 0.0
    protein_g: float = 0.0
    list_price_cny: float = 0.0
    discount_cny: float = 0.0
    pay_cny: float = 0.0
    delivery_fee_cny: float = 0.0
    product_code: str | None = None
    coupon_id: str | None = None
    coupon_code: str | None = None
    round_list: list[dict[str, Any]] | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def total_pay(self) -> float:
        return float(self.pay_cny) + float(self.delivery_fee_cny)

    def protein_per_100_kcal(self) -> float:
        if self.calories_kcal <= 0:
            return 0.0
        return (self.protein_g / self.calories_kcal) * 100.0


def rank_candidates(
    candidates: list[Candidate],
    *,
    calorie_cap: float,
    budget_cny: float | None,
    calorie_target: float | None = None,
) -> list[Candidate]:
    target = calorie_target if calorie_target is not None else calorie_cap
    filtered: list[Candidate] = []
    for c in candidates:
        if c.calories_kcal > calorie_cap:
            continue
        if budget_cny is not None and c.total_pay > budget_cny:
            continue
        filtered.append(c)

    def sort_key(c: Candidate) -> tuple:
        return (
            abs(c.calories_kcal - target),
            c.total_pay,
            -c.protein_per_100_kcal(),
            -c.protein_g,
            c.id,
        )

    return sorted(filtered, key=sort_key)
