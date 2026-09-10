from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

import httpx

from tourism_agent.tools.base import ToolResult, ToolSpec


class WeatherTool:
    def __init__(self, api_key: str, timeout_seconds: float = 10.0, client: httpx.Client | None = None):
        self.api_key = api_key
        self.client = client or httpx.Client(timeout=timeout_seconds)

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="weather",
            description="Tra cứu thời tiết hiện tại hoặc dự báo 5 ngày cho một địa điểm.",
            parameters={
                "location": "string, địa điểm cần tra cứu",
                "forecast": "boolean, true nếu người dùng hỏi tương lai/dự báo",
            },
            available=bool(self.api_key),
        )

    def run(self, location: str, forecast: bool = False, **_: Any) -> ToolResult:
        geo = self.client.get(
            "https://api.openweathermap.org/geo/1.0/direct",
            params={"q": location, "limit": 1, "appid": self.api_key},
        )
        geo.raise_for_status()
        matches = geo.json()
        if not matches:
            return ToolResult(self.spec.name, f"Không tìm thấy địa điểm: {location}", success=False)
        place = matches[0]
        params = {
            "lat": place["lat"], "lon": place["lon"], "appid": self.api_key,
            "units": "metric", "lang": "vi",
        }
        endpoint = "forecast" if forecast else "weather"
        response = self.client.get(f"https://api.openweathermap.org/data/2.5/{endpoint}", params=params)
        response.raise_for_status()
        data = response.json()
        resolved = f"{place.get('name', location)}, {place.get('country', '')}".strip(", ")
        if forecast:
            content = self._format_forecast(resolved, data)
        else:
            weather = (data.get("weather") or [{}])[0]
            main = data.get("main", {})
            content = json.dumps({
                "location": resolved,
                "condition": weather.get("description"),
                "temperature_c": main.get("temp"),
                "feels_like_c": main.get("feels_like"),
                "humidity_percent": main.get("humidity"),
                "wind_m_s": data.get("wind", {}).get("speed"),
            }, ensure_ascii=False)
        return ToolResult(self.spec.name, content, sources=["https://openweathermap.org/"])

    @staticmethod
    def _format_forecast(location: str, data: dict) -> str:
        days: dict[str, list[dict]] = defaultdict(list)
        for item in data.get("list", []):
            days[item.get("dt_txt", "")[:10]].append(item)
        summary = []
        for date, items in list(days.items())[:5]:
            temperatures = [item.get("main", {}).get("temp") for item in items]
            temperatures = [value for value in temperatures if value is not None]
            descriptions = [(item.get("weather") or [{}])[0].get("description") for item in items]
            summary.append({
                "date": date,
                "min_c": min(temperatures) if temperatures else None,
                "max_c": max(temperatures) if temperatures else None,
                "conditions": list(dict.fromkeys(value for value in descriptions if value)),
            })
        return json.dumps({"location": location, "forecast": summary}, ensure_ascii=False)

