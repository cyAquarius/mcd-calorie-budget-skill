#!/usr/bin/env python3
"""Minimal self-check for rank_combos (no third-party deps)."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "rank_combos.py"
FIXTURE = ROOT / "fixtures" / "sample_candidates.json"


def test_cli_fixture() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--input",
            str(FIXTURE),
            "--top",
            "3",
            "--json",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    rows = json.loads(proc.stdout)
    assert len(rows) == 3
    ids = [r["id"] for r in rows]
    # C over budget, D over calories → eligible A,B,E
    # target 650: B(640) closer than A(520) closer than E(480)?
    # abs: B=10, A=130, E=170 → B, A, E
    assert ids == ["B", "A", "E"], ids


def test_budget_filter() -> None:
    payload = {
        "calorie_cap": 700,
        "budget_cny": 25,
        "candidates": [
            {
                "id": "cheap",
                "title": "cheap",
                "calories_kcal": 500,
                "protein_g": 20,
                "pay_cny": 20,
            },
            {
                "id": "pricey",
                "title": "pricey",
                "calories_kcal": 500,
                "protein_g": 40,
                "pay_cny": 40,
            },
        ],
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(payload, f)
        path = f.name
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "-i", path, "--json", "--top", "5"],
        check=True,
        capture_output=True,
        text=True,
    )
    rows = json.loads(proc.stdout)
    assert [r["id"] for r in rows] == ["cheap"]


def main() -> int:
    test_cli_fixture()
    test_budget_filter()
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
