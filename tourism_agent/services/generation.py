from __future__ import annotations

import json
import re
from collections.abc import Iterator
from typing import Any

from google import genai
from google.genai import types

from tourism_agent.domain.models import ChatMessage
from tourism_agent.observability import NoOpObservability


class ModelRouter:
    """Cheap deterministic routing; avoids spending an extra LLM call per answer."""

    COMPLEX_MARKERS = (
        "lịch trình", "kế hoạch", "so sánh", "ngân sách", "tối ưu", "nhiều ngày",
        "itinerary", "compare", "budget", "phân tích",
    )

    def __init__(self, fast_model: str, complex_model: str):
        self.fast_model = fast_model
        self.complex_model = complex_model

    def select(self, query: str) -> str:
        normalized = query.casefold()
        is_complex = len(query) > 280 or any(marker in normalized for marker in self.COMPLEX_MARKERS)
        return self.complex_model if is_complex else self.fast_model


class GeminiGenerationService:
    def __init__(self, api_key: str, fast_model: str, complex_model: str, observer=None):
        if not api_key:
            raise ValueError("GEMINI_API_KEY is required")
        self.client = genai.Client(api_key=api_key)
        self.router = ModelRouter(fast_model, complex_model)
        self.observer = observer or NoOpObservability()

    def complete(self, prompt: str, *, json_output: bool = False) -> str:
        model = self.router.fast_model
        with self.observer.span(
            "gemini.complete",
            as_type="generation",
            input=prompt,
            model=model,
            model_parameters={"temperature": 0.1, "json_output": json_output},
        ) as span:
            config = types.GenerateContentConfig(temperature=0.1)
            if json_output:
                config.response_mime_type = "application/json"
            response = self.client.models.generate_content(model=model, contents=prompt, config=config)
            text = (response.text or "").strip()
            span.update(output=text, usage_details=self._usage(response))
            return text

    def stream_answer(self, query: str, context: str, history: list[ChatMessage]) -> Iterator[str]:
        system_prompt = (
            "Bạn là trợ lý du lịch chuyên nghiệp, am hiểu du lịch Việt Nam. "
            "Trả lời thân thiện, rõ ràng và chính xác. Chỉ dùng dữ liệu trong CONTEXT; "
            "không suy đoán dữ kiện. Nếu dữ liệu không đủ, hãy nói rõ điều đó."
        )
        history_text = self._history_text(history)
        prompt = f"""LỊCH SỬ GẦN ĐÂY:
{history_text or '(không có)'}

CONTEXT:
{context}

QUY TẮC:
1. Chỉ dùng thông tin trong CONTEXT, không bịa thêm.
2. Trình bày rõ địa chỉ, giá hoặc giờ mở cửa nếu CONTEXT có.
3. Nếu CONTEXT không đủ, nói rõ giới hạn dữ liệu.

CÂU HỎI: {query}"""
        yield from self._stream_generation(query, prompt, system_prompt, "gemini.rag_answer")

    def stream_agent_answer(
        self,
        query: str,
        history: list[ChatMessage],
        goal: str,
        tool_results: list[dict],
    ) -> Iterator[str]:
        history_text = self._history_text(history)
        observations = json.dumps(tool_results, ensure_ascii=False, default=str)
        prompt = f"""MỤC TIÊU: {goal}

LỊCH SỬ GẦN ĐÂY:
{history_text or '(không có)'}

KẾT QUẢ TOOLS:
{observations or '[]'}

CÂU HỎI: {query}

Hãy trả lời bằng tiếng Việt, rõ ràng và hữu ích.
- Chỉ khẳng định dữ kiện dựa trên kết quả tools; nếu tool lỗi hoặc thiếu dữ liệu, nói rõ giới hạn.
- Với ngân sách, nhấn mạnh đây là ước tính.
- Nếu kết quả có sources, đặt link nguồn gần thông tin tương ứng.
- Nếu tourism knowledge có web_fallback, ưu tiên nội bộ cho kiến thức ổn định và web cho dữ liệu thời sự.
- Không âm thầm trộn hai nguồn mâu thuẫn; nêu rõ khác biệt, thời điểm và mức độ chưa chắc chắn.
- Không nhắc đến tên node, state hay quy trình nội bộ."""
        system = "Bạn là AI Agent tư vấn du lịch Việt Nam, biết tổng hợp nhiều công cụ."
        yield from self._stream_generation(query, prompt, system, "gemini.agent_answer")

    def _stream_generation(
        self,
        query: str,
        prompt: str,
        system_prompt: str,
        observation_name: str,
    ) -> Iterator[str]:
        model = self.router.select(query)
        parts: list[str] = []
        usage: dict[str, int] = {}
        with self.observer.span(
            observation_name,
            as_type="generation",
            input=prompt,
            model=model,
            model_parameters={"temperature": 0.15},
        ) as span:
            stream = self.client.models.generate_content_stream(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.15,
                ),
            )
            for chunk in stream:
                chunk_usage = self._usage(chunk)
                if chunk_usage:
                    usage = chunk_usage
                if chunk.text:
                    parts.append(chunk.text)
                    yield chunk.text
            span.update(output="".join(parts), usage_details=usage or None)

    @staticmethod
    def _history_text(history: list[ChatMessage]) -> str:
        return "\n".join(
            f"{'Người dùng' if item.role == 'user' else 'Trợ lý'}: {item.content[:600]}"
            for item in history[-6:]
        )

    @staticmethod
    def _usage(response: Any) -> dict[str, int]:
        metadata = getattr(response, "usage_metadata", None)
        if metadata is None:
            return {}
        values = {
            "input": getattr(metadata, "prompt_token_count", None),
            "output": getattr(metadata, "candidates_token_count", None),
            "total": getattr(metadata, "total_token_count", None),
            "cache_read_input_tokens": getattr(metadata, "cached_content_token_count", None),
            "reasoning": getattr(metadata, "thoughts_token_count", None),
        }
        return {key: int(value) for key, value in values.items() if value is not None}

    @staticmethod
    def extract_json(text: str) -> dict:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if not match:
                return {}
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                return {}
