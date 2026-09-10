from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import httpx

from tourism_agent.tools.base import ToolResult, ToolSpec


class GoongPlacesTool:
    """Vietnam place search using Goong Place Autocomplete + Place Detail."""

    def __init__(
        self,
        api_key: str,
        timeout_seconds: float = 10.0,
        base_url: str = "https://rsapi.goong.io",
        client: httpx.Client | None = None,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.client = client or httpx.Client(timeout=timeout_seconds)

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="map_location",
            description=(
                "Tìm địa điểm tại Việt Nam bằng Goong Places, trả tên, địa chỉ, tọa độ, "
                "place_id và link mở tọa độ trên bản đồ. Không cung cấp rating."
            ),
            parameters={
                "query": "string, tên hoặc địa chỉ đầy đủ của địa điểm tại Việt Nam",
                "limit": "integer từ 1 đến 5; mặc định 1 để giảm API requests",
            },
            available=bool(self.api_key),
        )

    def run(self, query: str, limit: int = 1, **_: Any) -> ToolResult:
        normalized_query = query.strip()
        if len(normalized_query) < 2:
            return ToolResult(
                self.spec.name,
                "Query địa điểm phải có ít nhất 2 ký tự.",
                success=False,
            )

        requested = max(1, min(int(limit), 5))
        session_token = str(uuid4())
        response = self.client.get(
            f"{self.base_url}/Place/AutoComplete",
            params={
                "api_key": self.api_key,
                "input": normalized_query,
                "limit": requested,
                "more_compound": "true",
                "sessiontoken": session_token,
            },
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("predictions"), list):
            return ToolResult(
                self.spec.name,
                "Goong trả về response không đúng định dạng mong đợi.",
                success=False,
            )
        if payload.get("status") not in (None, "OK"):
            return ToolResult(
                self.spec.name,
                f"Goong Places không thể tìm địa điểm (status={payload.get('status')}).",
                success=False,
            )

        places = [
            self._resolve_place(item, session_token)
            for item in payload["predictions"][:requested]
            if isinstance(item, dict)
        ]
        map_urls = [place["map_url"] for place in places if place.get("map_url")]
        sources = ["https://docs.goong.io/rest/place/"]
        sources.extend(url for url in map_urls if url not in sources)
        result_payload = {
            "provider": "goong",
            "query": normalized_query,
            "result_count": len(places),
            "places": places,
            "limitations": "Goong Place API không trả rating hoặc website trong response này.",
        }
        return ToolResult(
            self.spec.name,
            json.dumps(result_payload, ensure_ascii=False),
            sources=sources,
        )

    def _resolve_place(self, prediction: dict[str, Any], session_token: str) -> dict[str, Any]:
        place_id = prediction.get("place_id")
        detail: dict[str, Any] = {}
        detail_error = None
        if place_id:
            try:
                response = self.client.get(
                    f"{self.base_url}/Place/Detail",
                    params={
                        "api_key": self.api_key,
                        "place_id": place_id,
                        "sessiontoken": session_token,
                    },
                )
                response.raise_for_status()
                payload = response.json()
                if isinstance(payload, dict) and isinstance(payload.get("result"), dict):
                    detail = payload["result"]
                else:
                    detail_error = "Goong Place Detail trả về response không hợp lệ."
            except (httpx.HTTPError, ValueError, TypeError) as exc:
                detail_error = f"Không lấy được Place Detail: {type(exc).__name__}"

        location = detail.get("geometry", {}).get("location", {})
        lat = location.get("lat")
        lng = location.get("lng")
        map_url = self._map_url(lat, lng) if lat is not None and lng is not None else None
        structured = prediction.get("structured_formatting") or {}
        place = {
            "name": detail.get("name") or structured.get("main_text") or prediction.get("description"),
            "address": detail.get("formatted_address") or prediction.get("description"),
            "location": {"latitude": lat, "longitude": lng}
            if lat is not None and lng is not None
            else None,
            "place_id": place_id,
            "types": detail.get("types", []),
            "geo_uri": f"geo:{lat},{lng}" if lat is not None and lng is not None else None,
            "map_url": map_url,
        }
        if detail_error:
            place["warning"] = detail_error
        return place

    @staticmethod
    def _map_url(lat: Any, lng: Any) -> str:
        return f"https://www.openstreetmap.org/?mlat={lat}&mlon={lng}#map=17/{lat}/{lng}"

