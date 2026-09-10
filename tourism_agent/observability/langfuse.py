from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Iterator

logger = logging.getLogger(__name__)


def _safe(value: Any, max_chars: int = 8000) -> Any:
    if isinstance(value, str):
        return value if len(value) <= max_chars else value[:max_chars] + "…"
    if isinstance(value, dict):
        return {str(key): _safe(item, max_chars) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(item, max_chars) for item in value[:50]]
    return value


class ObservationHandle:
    def __init__(self, observation: Any = None):
        self.observation = observation

    def update(self, **kwargs: Any) -> None:
        if self.observation is None:
            return
        try:
            sanitized = {key: _safe(value) for key, value in kwargs.items()}
            self.observation.update(**sanitized)
        except Exception as exc:
            logger.debug("Langfuse update skipped: %s", exc)


class NoOpObservability:
    enabled = False

    @contextmanager
    def span(self, name: str, as_type: str = "span", **kwargs: Any) -> Iterator[ObservationHandle]:
        yield ObservationHandle()

    def flush(self) -> None:
        return None


class LangfuseObservability:
    """Fail-open Langfuse v4 adapter; telemetry must never break a chat request."""

    def __init__(
        self,
        *,
        enabled: bool,
        public_key: str,
        secret_key: str,
        base_url: str,
        environment: str,
        sample_rate: float = 1.0,
    ):
        self.enabled = bool(enabled and public_key and secret_key)
        self.client = None
        if enabled and not self.enabled:
            logger.warning("Langfuse enabled but credentials are missing; tracing is disabled.")
        if self.enabled:
            try:
                from langfuse import Langfuse

                self.client = Langfuse(
                    public_key=public_key,
                    secret_key=secret_key,
                    base_url=base_url,
                    environment=environment,
                    sample_rate=max(0.0, min(float(sample_rate), 1.0)),
                )
            except Exception as exc:
                logger.warning("Langfuse initialization failed; tracing is disabled: %s", exc)
                self.enabled = False

    @contextmanager
    def span(self, name: str, as_type: str = "span", **kwargs: Any) -> Iterator[ObservationHandle]:
        if not self.enabled or self.client is None:
            yield ObservationHandle()
            return
        try:
            manager = self.client.start_as_current_observation(
                name=name,
                as_type=as_type,
                **{key: _safe(value) for key, value in kwargs.items()},
            )
        except Exception as exc:
            logger.warning("Langfuse span '%s' failed open: %s", name, exc)
            yield ObservationHandle()
            return
        body_failed = False
        try:
            with manager as observation:
                try:
                    yield ObservationHandle(observation)
                except BaseException:
                    body_failed = True
                    raise
        except BaseException as exc:
            if body_failed:
                raise
            logger.warning("Langfuse span '%s' failed open: %s", name, exc)

    def flush(self) -> None:
        if self.client is not None:
            try:
                self.client.flush()
            except Exception as exc:
                logger.debug("Langfuse flush skipped: %s", exc)
