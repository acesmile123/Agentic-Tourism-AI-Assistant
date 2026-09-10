from __future__ import annotations

import json
import math
from typing import Any

from tourism_agent.tools.base import ToolResult, ToolSpec


class BudgetCalculatorTool:
    PRESETS = {
        "budget": {"room": 400_000, "food": 220_000, "local": 100_000, "activities": 150_000},
        "mid_range": {"room": 900_000, "food": 450_000, "local": 250_000, "activities": 350_000},
        "premium": {"room": 2_500_000, "food": 900_000, "local": 600_000, "activities": 900_000},
    }

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="budget_calculator",
            description="Ước tính ngân sách chuyến đi bằng VND theo số ngày, số người và phong cách.",
            parameters={
                "destination": "string",
                "days": "integer >= 1",
                "travelers": "integer >= 1",
                "style": "budget, mid_range hoặc premium",
                "transport_vnd": "number, tổng chi phí di chuyển khứ hồi nếu biết",
            },
        )

    def run(
        self,
        destination: str,
        days: int,
        travelers: int = 1,
        style: str = "mid_range",
        transport_vnd: float = 0,
        **_: Any,
    ) -> ToolResult:
        days = max(1, int(days))
        travelers = max(1, int(travelers))
        preset = self.PRESETS.get(style, self.PRESETS["mid_range"])
        rooms = math.ceil(travelers / 2)
        nights = max(0, days - 1)
        accommodation = preset["room"] * rooms * nights
        food = preset["food"] * travelers * days
        local = preset["local"] * travelers * days
        activities = preset["activities"] * travelers * days
        total = accommodation + food + local + activities + max(0, float(transport_vnd))
        payload = {
            "destination": destination,
            "days": days,
            "nights": nights,
            "travelers": travelers,
            "style": style if style in self.PRESETS else "mid_range",
            "currency": "VND",
            "breakdown": {
                "accommodation": accommodation,
                "food": food,
                "local_transport": local,
                "activities": activities,
                "round_trip_transport": max(0, float(transport_vnd)),
            },
            "estimated_total": total,
            "disclaimer": "Ước tính tham khảo; giá thực tế phụ thuộc thời điểm và nhà cung cấp.",
        }
        return ToolResult(self.spec.name, json.dumps(payload, ensure_ascii=False))

