import json

from tourism_agent.tools.budget import BudgetCalculatorTool


def test_budget_calculator_returns_deterministic_breakdown():
    result = BudgetCalculatorTool().run(
        destination="Đà Nẵng", days=3, travelers=2, style="budget", transport_vnd=1_000_000
    )
    payload = json.loads(result.content)

    assert result.success is True
    assert payload["nights"] == 2
    assert payload["estimated_total"] == 4_620_000
