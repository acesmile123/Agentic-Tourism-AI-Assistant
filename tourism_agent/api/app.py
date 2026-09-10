from __future__ import annotations

import asyncio
import json
import logging
import queue
import threading
import time
from uuid import uuid4
from collections.abc import Callable
from contextlib import asynccontextmanager

import jwt
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from tourism_agent.api.schemas import ChatRequest, MessageResponse, SessionCreateResponse, SessionInfo
from tourism_agent.application.container import Container, build_container
from tourism_agent.core.config import Settings, get_settings
from tourism_agent.core.logging import configure_logging

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    container_factory: Callable[[Settings], Container] = build_container,
) -> FastAPI:
    app_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        configure_logging(app_settings.log_level)
        app.state.container = container_factory(app_settings)
        try:
            yield
        finally:
            observer = getattr(app.state.container, "observer", None)
            if observer is not None:
                observer.flush()

    app = FastAPI(title=app_settings.app_name, version="5.0.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def production_guardrails(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid4())
        started = time.perf_counter()
        path = request.url.path

        if app_settings.auth_enabled and path not in {"/health/live", "/health/ready", "/docs", "/openapi.json"}:
            authorization = request.headers.get("authorization", "")
            if not authorization.startswith("Bearer "):
                return JSONResponse({"detail": "Authentication required"}, status_code=401)
            try:
                claims = jwt.decode(
                    authorization.removeprefix("Bearer "),
                    app_settings.jwt_secret,
                    algorithms=[app_settings.jwt_algorithm],
                    audience=app_settings.jwt_audience,
                )
                request.state.principal = str(claims.get("sub", "anonymous"))
            except jwt.PyJWTError:
                return JSONResponse({"detail": "Invalid or expired access token"}, status_code=401)

        if path == "/chat" and app_settings.rate_limit_enabled:
            forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
            remote = request.client.host if request.client else "unknown"
            identity = getattr(request.state, "principal", None) or (
                forwarded if app_settings.trusted_proxy_headers and forwarded else remote
            )
            limiter = getattr(getattr(request.app.state, "container", None), "rate_limiter", None)
            if limiter is not None and not limiter.allow_request(
                "chat", identity, app_settings.rate_limit_requests, app_settings.rate_limit_window_seconds
            ):
                return JSONResponse(
                    {"detail": "Too many requests. Please try again shortly."},
                    status_code=429,
                    headers={"Retry-After": str(app_settings.rate_limit_window_seconds)},
                )

        response = await call_next(request)
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "http_request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response

    def container(request: Request) -> Container:
        return request.app.state.container

    @app.get("/")
    def root():
        return {"status": "ok", "service": app_settings.app_name, "version": "5.0.0"}

    @app.get("/health/live")
    def live():
        return {"status": "ok"}

    @app.get("/health/ready")
    def ready(request: Request):
        current = container(request)
        checks = {
            "redis": current.redis.ping(),
            "postgres": current.sessions.ping() if hasattr(current.sessions, "ping") else True,
            "mcp": current.agent.tools.ping() if hasattr(current.agent.tools, "ping") else True,
            "observability": bool(getattr(current.observer, "enabled", False)),
        }
        required = {key: value for key, value in checks.items() if key != "observability"}
        if not all(required.values()):
            raise HTTPException(status_code=503, detail={"status": "degraded", **checks})
        return {"status": "ok", **checks}

    @app.post("/sessions", response_model=SessionCreateResponse, status_code=201)
    def create_session(request: Request):
        session = container(request).sessions.create()
        return SessionCreateResponse(session_id=session.id, created_at=session.created_at)

    @app.get("/sessions", response_model=list[SessionInfo])
    def list_sessions(request: Request):
        return [SessionInfo(
            session_id=item.id,
            title=item.title,
            created_at=item.created_at,
            updated_at=item.updated_at,
            message_count=item.message_count,
        ) for item in container(request).sessions.list()]

    @app.get("/sessions/{session_id}/messages", response_model=list[MessageResponse])
    def get_messages(session_id: str, request: Request):
        try:
            return container(request).sessions.all_messages(session_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Session không tồn tại") from None

    @app.delete("/sessions/{session_id}")
    def delete_session(session_id: str, request: Request):
        if not container(request).sessions.delete(session_id):
            raise HTTPException(status_code=404, detail="Session không tồn tại")
        return {"deleted": session_id}

    @app.post("/chat")
    async def chat(payload: ChatRequest, request: Request):
        current = container(request)
        session = current.sessions.get_or_create(payload.session_id)
        history = current.sessions.recent_history(session.id)
        token_queue: queue.Queue = queue.Queue()
        done = object()

        def produce() -> None:
            try:
                stream = (
                    current.agent.stream_events(payload.query, history, session_id=session.id)
                    if hasattr(current.agent, "stream_events")
                    else current.agent.stream(payload.query, history, session_id=session.id)
                )
                for item in stream:
                    token_queue.put(item)
            except Exception as exc:
                logger.exception("RAG stream failed")
                token_queue.put(exc)
            finally:
                token_queue.put(done)

        threading.Thread(target=produce, daemon=True).start()

        async def event_stream():
            parts: list[str] = []
            failed = False
            while True:
                item = await asyncio.to_thread(token_queue.get)
                if item is done:
                    break
                if isinstance(item, Exception):
                    failed = True
                    body = {"error": "Không thể tạo câu trả lời lúc này", "done": True}
                    yield f"data: {json.dumps(body, ensure_ascii=False)}\n\n"
                    break
                if isinstance(item, dict) and item.get("type") == "activity":
                    body = {
                        "event": "activity",
                        "activity": {
                            "id": str(item.get("id", "activity")),
                            "label": str(item.get("label", "Đang xử lý")),
                            "status": str(item.get("status", "running")),
                        },
                        "done": False,
                    }
                    yield f"data: {json.dumps(body, ensure_ascii=False)}\n\n"
                    continue
                if isinstance(item, dict):
                    item = item.get("token", "")
                parts.append(str(item))
                body = {"token": str(item), "done": False}
                yield f"data: {json.dumps(body, ensure_ascii=False)}\n\n"

            if failed:
                return
            updated = await asyncio.to_thread(
                current.sessions.save_exchange, session.id, payload.query, "".join(parts)
            )
            body = {
                "token": "",
                "done": True,
                "session_id": session.id,
                "title": updated.title,
            }
            yield f"data: {json.dumps(body, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    return app
