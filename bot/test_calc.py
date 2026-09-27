import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import calc


def test_tax_is_applied_to_profit_not_revenue():
    result = calc.calculate(price=1500, cost=400, shipping=30, advertising=50, tax=15)
    assert result["pre_tax_profit"] == 1020
    assert result["tax_amount"] == 153
    assert result["unit_profit"] == 867


def test_workload_limit_is_rejected():
    result = calc.calculate(price=1500, cost=400, sales=6, hours=30)
    assert result["total_hours"] == 180
    assert result["hours_violation"] is True
    assert result["feasible"] is False


def test_goal_hours_are_exposed():
    result = calc.calculate(price=1500, cost=400, goal=5000, hours=30)
    assert result["sales_to_goal"] == 5
    assert result["sales_to_goal"] * result["hours"] == 150
