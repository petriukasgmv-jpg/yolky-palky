import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import memory


def test_budget_intents():
    assert memory.parse_natural_memory_intent(
        "запомни мой бюджет 300 евро"
    ) == ("set_budget", 300)
    assert memory.parse_natural_memory_intent(
        "какой мой бюджет?"
    ) == ("get_budget", None)


def test_goal_intents():
    assert memory.parse_natural_memory_intent(
        "сохрани цель 5000"
    ) == ("set_goal", 5000)
    assert memory.parse_natural_memory_intent(
        "какая моя цель?"
    ) == ("get_goal", None)


def test_unrelated_text_is_not_memory_intent():
    assert memory.parse_natural_memory_intent(
        "посчитай прибыль от стола"
    ) is None
