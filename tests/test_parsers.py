from mcd_calorie_budget.parsers import parse_nutrition_dsl, fen_to_yuan, extract_api_json
from mcd_calorie_budget.rank import Candidate, rank_candidates


def test_nutrition_dsl():
    raw = """[3]{productName,nutritionDescription,energyKj,energyKcal,protein,fat,carbohydrate,sodium,calcium}:
  猪柳麦满分,null,1288,308,16,16,24,781,213
  中薯条,null,1210,289,4,12,38,165,18
  可乐中杯,null,200,48,0,0,12,10,0
"""
    foods = parse_nutrition_dsl(raw)
    assert len(foods) == 3
    assert foods[0]["productName"] == "猪柳麦满分"
    assert foods[0]["energyKcal"] == 308
    assert foods[1]["protein"] == 4


def test_fen_to_yuan():
    assert fen_to_yuan(2250) == 22.5
    assert fen_to_yuan("22.5") == 22.5
    assert fen_to_yuan("33.5") == 33.5


def test_extract_api_json():
    text = '前言\n{"success":true,"code":200,"data":[{"a":1}]}\n后记'
    blob = extract_api_json(text)
    assert blob and blob["code"] == 200


def test_rank():
    cands = [
        Candidate(id="A", title="a", calories_kcal=600, protein_g=20, pay_cny=28),
        Candidate(id="B", title="b", calories_kcal=640, protein_g=30, pay_cny=25),
        Candidate(id="C", title="c", calories_kcal=700, protein_g=40, pay_cny=20),
    ]
    ranked = rank_candidates(cands, calorie_cap=650, budget_cny=30, calorie_target=650)
    assert [c.id for c in ranked] == ["B", "A"]
