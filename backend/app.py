"""Authoritative governed ZASI API application.

This module intentionally exposes only the first safe vertical slice. Legacy
routes remain available only as explicit read-only or retired compatibility
responses; they are not imported into this application.
"""

from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import asyncio
import hashlib
import json
import os
from typing import Any, AsyncGenerator, AsyncIterator, Dict, FrozenSet, Iterator, Optional, Sequence, Union

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from backend.compatibility import COMPATIBILITY_ROUTES
from backend.frontend_assets import frontend_dist_path
from backend.readiness import probe as readiness_probe
from src.control_plane.config import ConfigurationError, Settings
from src.control_plane.briefing import BriefingAggregator
from src.control_plane.contracts import IntentCreateRequest, RiskTier
from src.control_plane.connectors import ConnectorRegistry
from src.control_plane.execution import ActionBroker, ToolDefinition, ToolRegistry
from src.control_plane.events import OutboxDispatcher
from src.control_plane.identity import hash_token, issue_id, issue_token, optional_bearer
from src.control_plane.policy import PolicyEngine
from src.control_plane.redis_runtime import RedisRuntime
from src.control_plane.storage import (
    CURRENT_SCHEMA_VERSION,
    ConflictError,
    ControlPlaneStore,
    NotFoundError,
    ScopeViolation,
    _prepare_private_directory,
)


class SessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_key: SecretStr = Field(min_length=1, max_length=4096)


class ToolCallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_id: str = Field(min_length=2, max_length=128, pattern=r"^[a-z][a-z0-9_.-]+$")
    requested_risk_tier: RiskTier
    payload: Dict[str, Any] = Field(default_factory=dict)


class ApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    digest: str = Field(min_length=8, max_length=128, pattern=r"^sha256:[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=2000)


class MemoryCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=16_384)
    scope: str = Field(default="workspace", pattern=r"^(workspace|project)$")
    memory_type: str = Field(
        default="conversation",
        pattern=r"^(core|working|conversation|episodic|semantic|project|tool|audit)$",
    )
    project_id: Optional[str] = Field(default=None, min_length=1, max_length=256)
    source_ref: str = Field(default="", max_length=512)
    provenance: Dict[str, Any] = Field(default_factory=dict)
    trust: str = Field(
        default="operator",
        pattern=r"^(operator|verified_local|verified_external|inferred|unverified)$",
    )
    last_verified_at: Optional[str] = None
    fresh_until: Optional[str] = None


class BriefingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sources: list[str] = Field(default_factory=list, max_length=32)


class GoalCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=256)
    description: str = Field(default="", max_length=4096)
    priority: int = Field(default=50, ge=0, le=100)
    due_at: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TaskCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=256)
    instruction: str = Field(min_length=1, max_length=16_384)
    idempotency_key: str = Field(min_length=1, max_length=256)
    priority: int = Field(default=50, ge=0, le=100)
    not_before: Optional[str] = None
    max_attempts: int = Field(default=3, ge=1, le=10)
    depends_on: list[str] = Field(default_factory=list, max_length=64)


class TaskClaimRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    worker_id: str = Field(min_length=1, max_length=128)
    lease_seconds: int = Field(default=60, ge=1, le=3600)


class TaskCompleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    worker_id: str = Field(min_length=1, max_length=128)
    lease_token: SecretStr = Field(min_length=1, max_length=512)
    result: Dict[str, Any] = Field(default_factory=dict)


class ScheduleCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=1, max_length=128)
    kind: str = Field(pattern=r"^(once|interval)$")
    next_run_at: str = Field(min_length=1, max_length=64)
    idempotency_key: str = Field(min_length=1, max_length=256)
    interval_seconds: Optional[int] = Field(default=None, ge=1, le=31_536_000)
    misfire_policy: str = Field(default="skip", pattern=r"^(skip|run_once)$")


class ScheduleClaimRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    worker_id: str = Field(min_length=1, max_length=128)
    lease_seconds: int = Field(default=60, ge=1, le=3600)


class TaskRunCompleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    worker_id: str = Field(min_length=1, max_length=128)
    lease_token: SecretStr = Field(min_length=1, max_length=512)
    status: str = Field(pattern=r"^(succeeded|failed|cancelled)$")
    result: Dict[str, Any] = Field(default_factory=dict)
    error: Dict[str, Any] = Field(default_factory=dict)


class ActionReconcileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: str = Field(pattern=r"^(retry|succeeded|failed|cancelled)$")
    reason: str = Field(min_length=1, max_length=2000)
    result: Dict[str, Any] = Field(default_factory=dict)


class DevicePairRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_label: str = Field(min_length=1, max_length=128)


class DeviceApproveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    challenge: SecretStr = Field(min_length=1, max_length=512)


class SequenceStepRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_id: str = Field(min_length=2, max_length=128, pattern=r"^[a-z][a-z0-9_.-]+$")
    risk_tier: RiskTier
    payload: Dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list, max_length=16)


class SequenceCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    steps: list[SequenceStepRequest] = Field(min_length=1, max_length=64)


class SequenceApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    digest: str = Field(min_length=8, max_length=128, pattern=r"^sha256:[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=2000)


class EvidenceSupersedeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=2000)
    status: str = Field(pattern=r"^(verified|rejected|unknown|unavailable|simulated|research_only)$")
    result: Dict[str, Any] = Field(default_factory=dict)


class ArtifactAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: str = Field(min_length=4, max_length=128)
    analysis_kind: str = Field(default="default", min_length=1, max_length=64)


class VisionAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: str = Field(min_length=4, max_length=128)
    analysis_kind: str = Field(default="default", min_length=1, max_length=64)


class MCPRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jsonrpc: str = Field(pattern=r"^2\.0$")
    id: Union[int, str, None] = None
    method: str = Field(min_length=1, max_length=128)
    params: Dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True)
class AuthContext:
    session_id: str
    tenant_id: str
    principal_id: str
    device_id: Optional[str]
    scopes: FrozenSet[str]


class _RequestBodyTooLarge(Exception):
    """Raised before an oversized streamed body can be buffered."""


def _error(
    status_code: int,
    code: str,
    message: str,
    request_id: Optional[str] = None,
    retryable: bool = False,
    details: Optional[Dict[str, Any]] = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": request_id,
                "retryable": retryable,
                "details": details or {},
            }
        },
    )


def _context_from_request(request: Request) -> AuthContext:
    token = optional_bearer(request.headers.get("Authorization"))
    if token is None:
        raise HTTPException(
            status_code=401,
            detail={"code": "AUTH_REQUIRED", "message": "Authentication is required."},
        )
    session = request.app.state.store.authenticate_session(token)
    if session is None:
        raise HTTPException(
            status_code=401,
            detail={"code": "AUTH_REQUIRED", "message": "Authentication is required."},
        )
    try:
        raw_scopes = json.loads(session.get("scope_json") or "[]")
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=401,
            detail={"code": "AUTH_REQUIRED", "message": "Session scope is invalid."},
        )
    if not isinstance(raw_scopes, list) or not all(
        isinstance(scope, str) for scope in raw_scopes
    ):
        raise HTTPException(
            status_code=401,
            detail={"code": "AUTH_REQUIRED", "message": "Session scope is invalid."},
        )
    scopes = frozenset(raw_scopes)
    return AuthContext(
        session_id=session["id"],
        tenant_id=session["tenant_id"],
        principal_id=session["principal_id"],
        device_id=session["device_id"],
        scopes=scopes,
    )


def _session_is_active(
    store: ControlPlaneStore,
    token: Optional[str],
    context: AuthContext,
) -> bool:
    """Revalidate the session and its authorization snapshot for live streams."""
    if token is None:
        return False
    session = store.authenticate_session(token)
    if session is None:
        return False
    try:
        raw_scopes = json.loads(session.get("scope_json") or "[]")
    except (TypeError, ValueError, json.JSONDecodeError):
        return False
    if not isinstance(raw_scopes, list) or not all(
        isinstance(scope, str) for scope in raw_scopes
    ):
        return False
    scopes = frozenset(raw_scopes)
    return (
        session.get("id") == context.session_id
        and session.get("tenant_id") == context.tenant_id
        and session.get("principal_id") == context.principal_id
        and session.get("device_id") == context.device_id
        and scopes == context.scopes
    )


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "")


def _scope_digest(context: AuthContext) -> str:
    scope_material = json.dumps(
        {
            "tenant_id": context.tenant_id,
            "principal_id": context.principal_id,
            "scopes": sorted(context.scopes),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return "sha256:" + hashlib.sha256(scope_material.encode("utf-8")).hexdigest()


async def _read_body_limited(request: Request, limit: int) -> bytes:
    """Read and cache an ASGI body while enforcing the limit per chunk."""
    cached = getattr(request, "_body", None)
    if cached is not None:
        return cached
    chunks = []
    total = 0
    while True:
        message = await request._receive()  # Starlette's Request.body() uses this receive hook.
        if message["type"] == "http.disconnect":
            break
        if message["type"] != "http.request":
            continue
        chunk = message.get("body", b"")
        total += len(chunk)
        if total > limit:
            raise _RequestBodyTooLarge
        chunks.append(chunk)
        if not message.get("more_body", False):
            break
    body = b"".join(chunks)
    request._body = body
    return body


def _safe_validation_errors(errors: Sequence[Any]) -> list[Dict[str, Any]]:
    """Keep validation diagnostics useful without echoing submitted values."""
    safe_errors = []
    for error in errors:
        location = error.get("loc", ())
        if not isinstance(location, (list, tuple)):
            location = (location,)
        safe_errors.append(
            {
                "type": str(error.get("type", "validation_error")),
                "loc": [str(item) for item in location],
                "message": str(error.get("msg", "Request validation failed.")),
            }
        )
    return safe_errors


def _side_effect_for_risk(risk_tier: str) -> str:
    if risk_tier in {"R0", "R1"}:
        return "none"
    if risk_tier in {"R2", "R3", "R4"}:
        return "local" if risk_tier == "R2" else "external"
    return "physical"


def _idempotency_key(request: Request, message: str) -> str:
    value = request.headers.get("Idempotency-Key", "").strip()
    if not value or len(value) > 256 or any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        raise HTTPException(
            status_code=400,
            detail={"code": "IDEMPOTENCY_REQUIRED", "message": message},
        )
    return value


def _canonical_timestamp(value: Optional[str], field_name: str) -> Optional[str]:
    """Match repository timestamp normalization during idempotency replay."""
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat()


def _maintain_events_once(
    store: ControlPlaneStore,
    retain_latest: int,
    tenant_id: Optional[str] = "local",
) -> None:
    """Deliver the durable event stream before applying event retention."""
    report = OutboxDispatcher(store).dispatch_once(limit=100)
    if report.retried:
        raise ConflictError("outbox delivery is pending")
    tenant_ids = [tenant_id] if tenant_id is not None else store.list_tenant_ids()
    for current_tenant_id in tenant_ids:
        store.prune_events(current_tenant_id, retain_latest)


def create_app(
    settings: Optional[Settings] = None,
    store: Optional[ControlPlaneStore] = None,
) -> FastAPI:
    settings = settings or Settings.from_mapping()
    if store is None:
        if settings.database_backend == "postgresql":
            from src.control_plane.postgres_storage import PostgresControlPlaneStore

            if not settings.database_url:
                raise ConfigurationError("PostgreSQL profiles require ZASI_DATABASE_URL")
            store = PostgresControlPlaneStore(settings.database_url)
        else:
            store = ControlPlaneStore(settings.database_path)
    redis_runtime = RedisRuntime(settings.redis_url) if settings.redis_url else None
    registry = ToolRegistry()
    connector_registry = ConnectorRegistry()

    def system_status(_payload: Dict[str, Any]) -> Dict[str, Any]:
        store.latest_sequence("local")
        return {
            "service": "zasi-control-plane",
            "status": "ready",
            "profile": settings.profile,
            "legacy_catalog_claim": False,
        }

    registry.register(
        ToolDefinition(
            tool_id="registry.system.status",
            version="1.0.0",
            risk_tier="R0",
            required_scopes=frozenset({"workspace:read"}),
            handler=system_status,
            evidence_status="verified",
            disclosure="Local control-plane readiness observation; no legacy subsystem availability claim.",
            evidence_method_ref="procedure.control-plane.readiness.v1",
        )
    )
    policy = PolicyEngine(registry.capabilities())
    broker = ActionBroker(store=store, registry=registry, policy=policy)

    def require_scope(context: AuthContext, scope: str, message: str) -> None:
        if scope not in context.scopes:
            raise HTTPException(
                status_code=403,
                detail={"code": "POLICY_DENIED", "message": message},
            )

    async def event_retention_maintenance(application: FastAPI) -> None:
        """Apply the configured event retention without blocking request handling."""
        while True:
            await asyncio.sleep(60)
            try:
                _maintain_events_once(
                    application.state.store,
                    settings.event_retention,
                    tenant_id=None,
                )
            except (ConflictError, RuntimeError):
                # A failed outbox delivery deliberately defers pruning until a
                # later maintenance cycle can retry it.
                continue

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        application.state.store.initialize()
        application.state.store.create_tenant("local")
        application.state.store.create_principal("local-operator", "local")
        for definition in application.state.registry.definitions():
            application.state.store.upsert_capability(definition.manifest())
        artifact_directory = _prepare_private_directory(settings.artifact_directory)
        application.state.artifact_directory = artifact_directory
        maintenance_task = asyncio.create_task(event_retention_maintenance(application))
        try:
            yield
        finally:
            maintenance_task.cancel()
            await asyncio.gather(maintenance_task, return_exceptions=True)
            if redis_runtime is not None:
                redis_runtime.close()
            application.state.store.close()

    app = FastAPI(
        title="ZASI Governed Control Plane",
        version="1.0.0-control-plane",
        openapi_url=None,
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.store = store
    app.state.registry = registry
    app.state.connector_registry = connector_registry
    app.state.broker = broker
    app.state.redis_runtime = redis_runtime

    def authoritative_openapi() -> Dict[str, Any]:
        if app.openapi_schema is not None:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=(
                "Authenticated ZASI control-plane API. Capability and evidence "
                "claims are profile-scoped and require server-side provenance."
            ),
            routes=app.routes,
        )
        schema.setdefault("components", {}).setdefault("securitySchemes", {})[
            "BearerAuth"
        ] = {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "opaque-session-token",
            "description": "Short-lived server-issued session token.",
        }
        for path, operations in schema.get("paths", {}).items():
            if path.startswith("/api/"):
                for method, operation in operations.items():
                    if isinstance(operation, dict):
                        operation["security"] = (
                            []
                            if path == "/api/v2/sessions" and method == "post"
                            else [{"BearerAuth": []}]
                        )
        app.openapi_schema = schema
        return schema

    app.openapi = authoritative_openapi  # type: ignore[method-assign]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Idempotency-Key",
            "X-ZASI-Event-Cursor",
        ],
        expose_headers=["X-Request-ID", "X-ZASI-Event-Cursor"],
    )

    @app.middleware("http")
    async def security_middleware(request: Request, call_next):
        request.state.request_id = issue_id("req")
        content_length = request.headers.get("content-length")
        body = None
        if content_length:
            try:
                too_large = int(content_length) > settings.max_body_bytes
            except ValueError:
                too_large = True
            if too_large:
                return _error(
                    413,
                    "REQUEST_TOO_LARGE",
                    "Request body exceeds the configured limit.",
                    _request_id(request),
                )
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            try:
                body = await _read_body_limited(request, settings.max_body_bytes)
            except _RequestBodyTooLarge:
                return _error(
                    413,
                    "REQUEST_TOO_LARGE",
                    "Request body exceeds the configured limit.",
                    _request_id(request),
                )
        if (
            request.method in {"POST", "PUT", "PATCH"}
            and request.url.path.startswith("/api/v2/")
            and body
        ):
            media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            if request.url.path.startswith("/api/v2/artifacts"):
                allowed_upload_types = {
                    "application/octet-stream",
                    "application/step",
                    "model/step",
                    "model/stl",
                    "image/png",
                    "image/jpeg",
                    "audio/wav",
                    "audio/mpeg",
                    "text/plain",
                }
                if media_type not in allowed_upload_types:
                    return _error(
                        415,
                        "UNSUPPORTED_MEDIA_TYPE",
                        "Artifact content type is not supported.",
                        _request_id(request),
                    )
            elif media_type != "application/json":
                return _error(
                    415,
                    "UNSUPPORTED_MEDIA_TYPE",
                    "JSON content type is required.",
                    _request_id(request),
                )
        if request.url.path.startswith("/api/") and request.url.path not in {
            "/health/live",
            "/health/ready",
        }:
            remote = request.client.host if request.client is not None else "unknown"
            subject_prefix = "auth" if request.url.path == "/api/v2/sessions" else "request"
            try:
                if subject_prefix == "auth":
                    rate_limit_args = (
                        "local",
                        f"{subject_prefix}:ip:{remote}",
                        settings.auth_rate_limit,
                        settings.auth_rate_window_seconds,
                    )
                else:
                    rate_limit_args = (
                        "local",
                        f"{subject_prefix}:ip:{remote}",
                        settings.request_rate_limit,
                        settings.request_rate_window_seconds,
                    )
                limiter = request.app.state.redis_runtime
                if limiter is None:
                    allowed, retry_after = request.app.state.store.consume_rate_limit(
                        *rate_limit_args
                    )
                else:
                    allowed, retry_after = limiter.consume_rate_limit(*rate_limit_args)
            except RuntimeError:
                allowed, retry_after = False, 1
            if not allowed:
                response = _error(
                    429,
                    "RATE_LIMITED",
                    "Request rate limit exceeded.",
                    _request_id(request),
                    True,
                    {"retry_after_seconds": retry_after},
                )
                response.headers["Retry-After"] = str(max(1, retry_after))
                return response
        response = await call_next(request)
        response.headers["X-Request-ID"] = _request_id(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
        )
        if not request.url.path.startswith("/api/") and request.url.path not in {
            "/health/live",
            "/health/ready",
        }:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; connect-src 'self'; img-src 'self' data:; "
                "style-src 'self'; script-src 'self'; "
                "base-uri 'none'; frame-ancestors 'none'"
            )
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        detail: Dict[str, Any] = exc.detail if isinstance(exc.detail, dict) else {}
        return _error(
            exc.status_code,
            detail.get("code", "HTTP_ERROR"),
            detail.get("message", "Request failed."),
            _request_id(request),
            bool(detail.get("retryable", False)),
            detail.get("details", {}),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        errors = exc.errors()
        malformed_json = any(
            str(error.get("type", "")).lower() in {"json_invalid", "value_error.jsondecode"}
            for error in errors
        )
        return _error(
            400 if malformed_json else 422,
            "MALFORMED_JSON" if malformed_json else "VALIDATION_ERROR",
            "Malformed JSON request body." if malformed_json else "Request validation failed.",
            _request_id(request),
            False,
            {"errors": _safe_validation_errors(errors)},
        )

    @app.get("/health/live")
    async def liveness():
        return {"status": "alive"}

    @app.get("/api/v2/openapi.json", include_in_schema=False)
    async def openapi_document(context: AuthContext = Depends(_context_from_request)):
        require_scope(context, "workspace:read", "API schema visibility is not permitted.")
        return app.openapi()

    @app.get("/health/ready")
    async def readiness(request: Request):
        readiness_state = readiness_probe(
            request.app.state.store,
            settings,
            registry,
            request.app.state.redis_runtime,
        )
        if readiness_state["status"] != "ready":
            return _error(
                503,
                "NOT_READY",
                "Control-plane dependencies are unavailable.",
                _request_id(request),
                True,
                {"checks": readiness_state["checks"]},
            )
        return readiness_state

    @app.post("/api/v2/sessions", status_code=201)
    async def create_session(payload: SessionRequest, request: Request):
        if not settings.api_key_matches(payload.api_key.get_secret_value()):
            raise HTTPException(
                status_code=401,
                detail={"code": "AUTH_REQUIRED", "message": "Authentication is required."},
            )
        access_token = issue_token()
        session_id = issue_id("ses")
        expires_at = datetime.now(timezone.utc) + timedelta(hours=8)
        request.app.state.store.create_session(
            session_id=session_id,
            tenant_id="local",
            principal_id="local-operator",
            device_id=None,
            token_hash=hash_token(access_token),
            expires_at=expires_at,
            scopes=[
                "workspace:read",
                "workspace:write",
                "intent:create",
                "plan:create",
                "approval:write",
                "audit:read",
                "device:pair",
                "device:revoke",
                "evidence:read",
                "evidence:write",
                "analysis:write",
                "run:cancel",
                "run:reconcile",
                "sequence:write",
            ],
        )
        return {
            "session_id": session_id,
            "access_token": access_token,
            "token_type": "Bearer",
            "tenant_id": "local",
            "principal_id": "local-operator",
            "scopes": [
                "approval:write",
                "audit:read",
                "device:pair",
                "device:revoke",
                "evidence:read",
                "evidence:write",
                "analysis:write",
                "intent:create",
                "plan:create",
                "run:cancel",
                "run:reconcile",
                "sequence:write",
                "workspace:read",
                "workspace:write",
            ],
            "expires_at": expires_at.isoformat(),
        }

    @app.get("/api/v2/sessions/current")
    async def current_session(context: AuthContext = Depends(_context_from_request)):
        return {
            "session_id": context.session_id,
            "tenant_id": context.tenant_id,
            "principal_id": context.principal_id,
            "device_id": context.device_id,
            "scopes": sorted(context.scopes),
        }

    @app.post("/api/v2/sessions/revoke")
    async def revoke_current_session(
        request: Request, context: AuthContext = Depends(_context_from_request)
    ):
        try:
            request.app.state.store.get_session(context.session_id, context.tenant_id)
            request.app.state.store.revoke_session(context.session_id)
        except (NotFoundError, ScopeViolation):
            raise HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": "Session not found."},
            )
        return {"session_id": context.session_id, "status": "revoked"}

    async def start_device_pairing(
        payload: DevicePairRequest,
        request: Request,
        context: AuthContext,
    ) -> Dict[str, Any]:
        require_scope(context, "device:pair", "Device pairing is not permitted.")
        idempotency_key = _idempotency_key(
            request, "Idempotency-Key is required for device pairing."
        )
        challenge = issue_token()
        challenge_id = issue_id("pch")
        device_id = issue_id("dev")
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
        try:
            record = request.app.state.store.create_pairing_challenge(
                challenge_id=challenge_id,
                device_id=device_id,
                tenant_id=context.tenant_id,
                principal_id=context.principal_id,
                device_label=payload.device_label,
                challenge_hash=hash_token(challenge),
                expires_at=expires_at,
                idempotency_key=idempotency_key,
            )
        except ConflictError as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "PAIRING_CONFLICT", "message": str(exc)},
            ) from exc
        return {
            **record,
            "challenge": challenge,
            "disclosure": "One-time pairing value; it expires and is not an API credential.",
        }

    @app.post("/api/v2/devices", status_code=201)
    async def pair_device(
        payload: DevicePairRequest,
        request: Request,
        context: AuthContext = Depends(_context_from_request),
    ):
        return await start_device_pairing(payload, request, context)

    @app.post("/api/v2/mobile/pair", status_code=201)
    async def pair_mobile_device(
        payload: DevicePairRequest,
        request: Request,
        context: AuthContext = Depends(_context_from_request),
    ):
        return await start_device_pairing(payload, request, context)

    @app.post("/api/v2/mobile/{device_id}/approve")
    async def approve_mobile_device(
        device_id: str,
        payload: DeviceApproveRequest,
        request: Request,
        context: AuthContext = Depends(_context_from_request),
    ):
        require_scope(context, "device:pair", "Device pairing is not permitted.")
        idempotency_key = _idempotency_key(
            request, "Idempotency-Key is required for device approval."
        )
        try:
            return request.app.state.store.approve_pairing_challenge(
                device_id=device_id,
                tenant_id=context.tenant_id,
                principal_id=context.principal_id,
                challenge=payload.challenge.get_secret_value(),
                enrollment_hash=hash_token(f"{device_id}:{payload.challenge.get_secret_value()}"),
                idempotency_key=idempotency_key,
            )
        except NotFoundError:
            raise HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": "Pairing challenge not found."},
            )
        except ConflictError as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "PAIRING_CONFLICT", "message": str(exc)},
            )

    @app.get("/api/v2/devices")
    async def list_devices(
        context: AuthContext = Depends(_context_from_request),
        limit: int = Query(default=100, ge=1, le=1000),
    ):
        require_scope(context, "workspace:read", "Device visibility is not permitted.")
        return {"tenant_id": context.tenant_id, "devices": app.state.store.list_devices(context.tenant_id, limit)}

    @app.post("/api/v2/devices/{device_id}/revoke")
    async def revoke_device(
        device_id: str,
        request: Request,
        context: AuthContext = Depends(_context_from_request),
    ):
        require_scope(context, "device:revoke", "Device revocation is not permitted.")
        idempotency_key = _idempotency_key(
            request, "Idempotency-Key is required for device revocation."
        )
        try:
            return request.app.state.store.revoke_device(
                device_id,
                context.tenant_id,
                context.principal_id,
                idempotency_key=idempotency_key,
            )
        except NotFoundError:
            raise HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": "Device not found."},
            )
        except ConflictError as exc:
            message = str(exc)
            code = (
                "IDEMPOTENCY_CONFLICT"
                if "idempotency" in message
                else "DEVICE_CONFLICT"
            )
            raise HTTPException(
                status_code=409,
                detail={"code": code, "message": message},
            )

    @app.get("/api/v2/devices/{device_id}/telemetry")
    async def device_telemetry(
        device_id: str,
        request: Request,
        context: AuthContext = Depends(_context_from_request),
    ):
        require_scope(context, "workspace:read", "Device telemetry is not permitted.")
        try:
            device = request.app.state.store.get_device(device_id, context.tenant_id)
        except NotFoundError:
            raise HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": "Device not found."},
            )
        return {
            "device_id": device_id,
            "status": "unavailable",
            "evidence_state": "unavailable",
            "device": device,
            "observed_at": None,
            "fresh_until": None,
            "disclosure": "No physical device telemetry adapter is enabled in the reference profile.",
        }

    @app.get("/api/v2/approvals")
    async def list_approvals(context: AuthContext = Depends(_context_from_request)):
        if "audit:read" not in context.scopes:
            raise HTTPException(
                status_code=403,
                detail={"code": "POLICY_DENIED", "message": "Approval visibility is not permitted."},
            )
        return {
            "approvals": app.state.store.list_approvals(context.tenant_id),
            "tenant_id": context.tenant_id,
        }

    @app.post("/api/v2/approvals/{approval_id}/revoke")
    async def revoke_approval(
        approval_id: str,
        request: Request,
        context: AuthContext = Depends(_context_from_request),
    ):
        if "approval:write" not in context.scopes:
            raise HTTPException(
                status_code=403,
                detail={"code": "POLICY_DENIED", "message": "Approval revocation is not permitted."},
            )
        try:
            return request.app.state.store.revoke_approval(
                approval_id, context.tenant_id, context.principal_id
            )
        except (NotFoundError, ScopeViolation):
            raise HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": "Approval not found."},
            )
        except ConflictError as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "APPROVAL_CONFLICT", "message": str(exc)},
            )

    @app.get("/api/v2/audit")
    async def audit_records(
        context: AuthContext = Depends(_context_from_request),
        limit: int = Query(default=100, ge=1, le=1000),
        after: Optional[str] = Query(default=None, max_length=64),
    ):
        if "audit:read" not in context.scopes:
            raise HTTPException(
                status_code=403,
                detail={"code": "POLICY_DENIED", "message": "Audit visibility is not permitted."},
            )
        try:
            records = app.state.store.list_audit(context.tenant_id, limit=limit, after=after)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail={"code": "INVALID_CURSOR", "message": str(exc)},
            ) from exc
        return {
            "records": records,
            "tenant_id": context.tenant_id,
            "next_cursor": app.state.store.audit_cursor(records[-1]) if records else None,
        }

    @app.get("/api/v2/evidence/{evidence_id}")
    async def evidence_record(
        evidence_id: str,
        context: AuthContext = Depends(_context_from_request),
    ):
        if "evidence:read" not in context.scopes:
            raise HTTPException(
                status_code=403,
                detail={"code": "POLICY_DENIED", "message": "Evidence visibility is not permitted."},
            )
        try:
            return app.state.store.get_evidence(evidence_id, context.tenant_id)
        except (NotFoundError, ScopeViolation):
            raise HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": "Evidence not found."},
            )

    @app.post("/api/v2/evidence/{evidence_id}/supersede", status_code=201)
    async def supersede_evidence(
        evidence_id: str,
        payload: EvidenceSupersedeRequest,
        request: Request,
        context: AuthContext = Depends(_context_from_request),
    ):
        require_scope(context, "evidence:write", "Evidence correction is not permitted.")
        if payload.status == "verified":
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "VERIFICATION_NOT_AVAILABLE",
                    "message": "The reference profile cannot promote operator input to verified evidence.",
                },
            )
        try:
            previous = request.app.state.store.get_evidence(
                evidence_id, context.tenant_id
            )
        except NotFoundError:
            raise HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": "Evidence not found."},
            )
        replacement_id = issue_id("ev")
        provenance = {
            "adapter_id": "operator-correction",
            "adapter_version": "1.0.0",
            "origin": "local",
            "method_ref": "procedure.operator-correction.v1",
            "input_digest": "sha256:" + hashlib.sha256(
                json.dumps(previous["result"], sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
            "disclosure": f"Operator correction: {payload.reason}",
        }
        return request.app.state.store.create_evidence(
            evidence_id=replacement_id,
            tenant_id=context.tenant_id,
            principal_id=context.principal_id,
            kind=previous["kind"],
            status=payload.status,
            provenance=provenance,
            result=payload.result,
            artifact_ref=previous.get("artifact_ref"),
            supersedes=evidence_id,
        )

    @app.post("/api/v2/memory", status_code=201)
    async def create_memory(
        payload: MemoryCreateRequest,
        request: Request,
        context: AuthContext = Depends(_context_from_request),
    ):
        if "workspace:write" not in context.scopes:
            raise HTTPException(
                status_code=403,
                detail={"code": "POLICY_DENIED", "message": "Memory writes are not permitted for this session."},
            )
        if payload.scope == "project" and not payload.project_id:
            raise HTTPException(
                status_code=422,
                detail={"code": "VALIDATION_ERROR", "message": "Project memory requires project_id."},
            )
        if payload.memory_type == "project" and not payload.project_id:
            raise HTTPException(
                status_code=422,
                detail={"code": "VALIDATION_ERROR", "message": "Project memory requires project_id."},
            )
        try:
            return request.app.state.store.create_memory(
                memory_id=issue_id("mem"),
                tenant_id=context.tenant_id,
                principal_id=context.principal_id,
                content=payload.content,
                scope=payload.scope,
                memory_type=payload.memory_type,
                project_id=payload.project_id,
                source_ref=payload.source_ref,
                provenance=payload.provenance,
                trust=payload.trust,
                last_verified_at=payload.last_verified_at,
                fresh_until=payload.fresh_until,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": "VALIDATION_ERROR", "message": str(exc)},
            )

    @app.get("/api/v2/memory/search")
    async def search_memory(
        query: str = Query(default="", max_length=256),
        limit: int = Query(default=50, ge=1, le=100),
        project_id: Optional[str] = Query(default=None, min_length=1, max_length=256),
        memory_type: Optional[str] = Query(default=None, max_length=32),
        include_stale: bool = Query(default=False),
        context: AuthContext = Depends(_context_from_request),
    ):
        if "workspace:read" not in context.scopes:
            raise HTTPException(
                status_code=403,
                detail={"code": "POLICY_DENIED", "message": "Memory visibility is not permitted."},
            )
        try:
            items = app.state.store.search_memory(
                context.tenant_id,
                query,
                limit,
                project_id=project_id,
                memory_type=memory_type,
                include_stale=include_stale,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": "VALIDATION_ERROR", "message": str(exc)},
            )
        return {"items": items, "tenant_id": context.tenant_id}

    @app.delete("/api/v2/memory/{memory_id}")
    async def delete_memory(
        memory_id: str,
        request: Request,
        context: AuthContext = Depends(_context_from_request),
    ):
        if "workspace:write" not in context.scopes:
            raise HTTPException(
                status_code=403,
                detail={"code": "POLICY_DENIED", "message": "Memory deletion is not permitted."},
            )
        try:
            return request.app.state.store.delete_memory(
                memory_id, context.tenant_id, context.principal_id
            )
        except (NotFoundError, ScopeViolation):
            raise HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": "Memory item not found."},
            )

    @app.post("/api/v2/goals", status_code=201)
    async def create_goal(
        payload: GoalCreateRequest,
        request: Request,
        context: AuthContext = Depends(_context_from_request),
    ):
        require_scope(context, "workspace:write", "Goal writes are not permitted.")
        try:
            return request.app.state.store.create_goal(
                goal_id=issue_id("goal"),
                tenant_id=context.tenant_id,
                principal_id=context.principal_id,
                title=payload.title,
                description=payload.description,
                priority=payload.priority,
                due_at=payload.due_at,
                metadata=payload.metadata,
            )
        except (NotFoundError, ScopeViolation):
            raise HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": "Goal owner was not found."},
            )
        except ConflictError as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "GOAL_CONFLICT", "message": str(exc)},
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": "VALIDATION_ERROR", "message": str(exc)},
            )

    @app.get("/api/v2/goals")
    async def list_goals(
        status: Optional[str] = Query(default=None, max_length=32),
        limit: int = Query(default=100, ge=1, le=1000),
        context: AuthContext = Depends(_context_from_request),
    ):
        require_scope(context, "workspace:read", "Goal visibility is not permitted.")
        try:
            goals = app.state.store.list_goals(context.tenant_id, status=status, limit=limit)
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": "VALIDATION_ERROR", "message": str(exc)},
            )
        return {"tenant_id": context.tenant_id, "goals": goals}

    @app.get("/api/v2/goals/{goal_id}")
    async def get_goal(
        goal_id: str,
        context: AuthContext = Depends(_context_from_request),
    ):
        require_scope(context, "workspace:read", "Goal visibility is not permitted.")
        try:
            return app.state.store.get_goal(goal_id, context.tenant_id)
        except (NotFoundError, ScopeViolation):
            raise HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": "Goal not found."},
            )

    @app.post("/api/v2/goals/{goal_id}/tasks", status_code=201)
    async def create_task(
        goal_id: str,
        payload: TaskCreateRequest,
        request: Request,
        context: AuthContext = Depends(_context_from_request),
    ):
        require_scope(context, "workspace:write", "Task writes are not permitted.")
        def replay_task_if_matching() -> Optional[JSONResponse]:
            canonical_not_before = _canonical_timestamp(payload.not_before, "not_before")
            existing = request.app.state.store.get_task_by_idempotency(
                context.tenant_id, payload.idempotency_key
            )
            if existing is None:
                return None
            if (
                existing["goal_id"] != goal_id
                or existing["title"] != payload.title
                or existing["instruction"] != payload.instruction
                or existing["priority"] != payload.priority
                or existing["not_before"] != canonical_not_before
                or existing["max_attempts"] != payload.max_attempts
                or existing["dependencies"] != sorted(payload.depends_on)
            ):
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "IDEMPOTENCY_CONFLICT",
                        "message": "Idempotency key is bound to different task input.",
                    },
                )
            return JSONResponse(status_code=200, content=existing)

        try:
            replay = replay_task_if_matching()
            if replay is not None:
                return replay
            return request.app.state.store.create_task(
                task_id=issue_id("task"),
                goal_id=goal_id,
                tenant_id=context.tenant_id,
                principal_id=context.principal_id,
                title=payload.title,
                instruction=payload.instruction,
                idempotency_key=payload.idempotency_key,
                priority=payload.priority,
                not_before=payload.not_before,
                max_attempts=payload.max_attempts,
                depends_on=payload.depends_on,
            )
        except (NotFoundError, ScopeViolation):
            raise HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": "Goal or dependency not found."},
            )
        except ConflictError as exc:
            replay = replay_task_if_matching()
            if replay is not None:
                return replay
            raise HTTPException(
                status_code=409,
                detail={"code": "TASK_CONFLICT", "message": str(exc)},
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": "VALIDATION_ERROR", "message": str(exc)},
            )

    @app.get("/api/v2/goals/{goal_id}/tasks")
    async def list_tasks(
        goal_id: str,
        limit: int = Query(default=100, ge=1, le=1000),
        context: AuthContext = Depends(_context_from_request),
    ):
        require_scope(context, "workspace:read", "Task visibility is not permitted.")
        try:
            tasks = app.state.store.list_tasks(goal_id, context.tenant_id, limit=limit)
        except (NotFoundError, ScopeViolation):
            raise HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": "Goal not found."},
            )
        return {"tenant_id": context.tenant_id, "goal_id": goal_id, "tasks": tasks}

    @app.post("/api/v2/goals/{goal_id}/schedules", status_code=201)
    async def create_schedule(
        goal_id: str,
        payload: ScheduleCreateRequest,
        request: Request,
        context: AuthContext = Depends(_context_from_request),
    ):
        require_scope(context, "workspace:write", "Schedule writes are not permitted.")
        def replay_schedule_if_matching() -> Optional[JSONResponse]:
            canonical_next_run_at = _canonical_timestamp(
                payload.next_run_at, "next_run_at"
            )
            existing = request.app.state.store.get_schedule_by_idempotency(
                context.tenant_id, payload.idempotency_key
            )
            if existing is None:
                return None
            if (
                existing["task_id"] != payload.task_id
                or existing["kind"] != payload.kind
                or existing["next_run_at"] != canonical_next_run_at
                or existing["interval_seconds"] != payload.interval_seconds
                or existing["misfire_policy"] != payload.misfire_policy
            ):
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "IDEMPOTENCY_CONFLICT",
                        "message": "Idempotency key is bound to different schedule input.",
                    },
                )
            existing_task = request.app.state.store.get_task(
                existing["task_id"], context.tenant_id
            )
            if existing_task["goal_id"] != goal_id:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "IDEMPOTENCY_CONFLICT",
                        "message": "Idempotency key is bound to a different goal.",
                    },
                )
            return JSONResponse(status_code=200, content=existing)

        try:
            replay = replay_schedule_if_matching()
            if replay is not None:
                return replay
            task = request.app.state.store.get_task(payload.task_id, context.tenant_id)
            if task["goal_id"] != goal_id:
                raise ConflictError("scheduled task belongs to another goal")
            return request.app.state.store.create_schedule(
                schedule_id=issue_id("sch"),
                tenant_id=context.tenant_id,
                principal_id=context.principal_id,
                task_id=payload.task_id,
                kind=payload.kind,
                next_run_at=payload.next_run_at,
                idempotency_key=payload.idempotency_key,
                interval_seconds=payload.interval_seconds,
                misfire_policy=payload.misfire_policy,
            )
        except (NotFoundError, ScopeViolation):
            raise HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": "Goal or task not found."},
            )
        except ConflictError as exc:
            replay = replay_schedule_if_matching()
            if replay is not None:
                return replay
            raise HTTPException(
                status_code=409,
                detail={"code": "SCHEDULE_CONFLICT", "message": str(exc)},
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": "VALIDATION_ERROR", "message": str(exc)},
            )

    @app.get("/api/v2/goals/{goal_id}/schedules")
    async def list_goal_schedules(
        goal_id: str,
        limit: int = Query(default=100, ge=1, le=1000),
        context: AuthContext = Depends(_context_from_request),
    ):
        require_scope(context, "workspace:read", "Schedule visibility is not permitted.")
        try:
            schedules = app.state.store.list_schedules(
                context.tenant_id, goal_id=goal_id, limit=limit
            )
        except (NotFoundError, ScopeViolation):
            raise HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": "Goal not found."},
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": "VALIDATION_ERROR", "message": str(exc)},
            )
        return {"tenant_id": context.tenant_id, "goal_id": goal_id, "schedules": schedules}

    @app.get("/api/v2/schedules/{schedule_id}")
    async def get_schedule(
        schedule_id: str,
        context: AuthContext = Depends(_context_from_request),
    ):
        require_scope(context, "workspace:read", "Schedule visibility is not permitted.")
        try:
            return app.state.store.get_schedule(schedule_id, context.tenant_id)
        except (NotFoundError, ScopeViolation):
            raise HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": "Schedule not found."},
            )

    @app.post("/api/v2/schedules/{schedule_id}/cancel")
    async def cancel_schedule(
        schedule_id: str,
        request: Request,
        context: AuthContext = Depends(_context_from_request),
    ):
        require_scope(context, "workspace:write", "Schedule cancellation is not permitted.")
        idempotency_key = _idempotency_key(
            request, "Idempotency-Key is required for schedule cancellation."
        )
        try:
            return request.app.state.store.cancel_schedule(
                schedule_id=schedule_id,
                tenant_id=context.tenant_id,
                principal_id=context.principal_id,
                idempotency_key=idempotency_key,
            )
        except (NotFoundError, ScopeViolation):
            raise HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": "Schedule not found."},
            )
        except ConflictError as exc:
            message = str(exc)
            code = (
                "IDEMPOTENCY_CONFLICT"
                if "idempotency" in message
                else "SCHEDULE_CONFLICT"
            )
            raise HTTPException(
                status_code=409,
                detail={"code": code, "message": message},
            )

    @app.post("/api/v2/schedules/{schedule_id}/claim")
    async def claim_schedule(
        schedule_id: str,
        payload: ScheduleClaimRequest,
        request: Request,
        context: AuthContext = Depends(_context_from_request),
    ):
        require_scope(context, "workspace:write", "Schedule execution is not permitted.")
        try:
            claimed = request.app.state.store.claim_due_schedule(
                schedule_id=schedule_id,
                tenant_id=context.tenant_id,
                worker_id=payload.worker_id,
                lease_seconds=payload.lease_seconds,
            )
        except (NotFoundError, ScopeViolation):
            raise HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": "Schedule not found."},
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": "VALIDATION_ERROR", "message": str(exc)},
            )
        if claimed is None:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "SCHEDULE_NOT_CLAIMABLE",
                    "message": "Schedule is not due, is blocked, or already has an occurrence in progress.",
                },
            )
        return claimed

    @app.post("/api/v2/task-runs/{run_id}/claim")
    async def claim_task_run(
        run_id: str,
        payload: ScheduleClaimRequest,
        request: Request,
        context: AuthContext = Depends(_context_from_request),
    ):
        require_scope(context, "workspace:write", "Task-run execution is not permitted.")
        try:
            claimed = request.app.state.store.claim_task_run(
                run_id=run_id,
                tenant_id=context.tenant_id,
                worker_id=payload.worker_id,
                lease_seconds=payload.lease_seconds,
            )
        except (NotFoundError, ScopeViolation):
            raise HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": "Task run not found."},
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": "VALIDATION_ERROR", "message": str(exc)},
            )
        if claimed is None:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "TASK_RUN_NOT_CLAIMABLE",
                    "message": "Task run is not retryable or its lease is still active.",
                },
            )
        return claimed

    @app.post("/api/v2/task-runs/{run_id}/complete")
    async def complete_task_run(
        run_id: str,
        payload: TaskRunCompleteRequest,
        request: Request,
        context: AuthContext = Depends(_context_from_request),
    ):
        require_scope(context, "workspace:write", "Task-run execution is not permitted.")
        try:
            return request.app.state.store.complete_task_run(
                run_id=run_id,
                tenant_id=context.tenant_id,
                worker_id=payload.worker_id,
                lease_token=payload.lease_token.get_secret_value(),
                status=payload.status,
                result=payload.result,
                error=payload.error,
            )
        except (NotFoundError, ScopeViolation):
            raise HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": "Task run not found."},
            )
        except ConflictError as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "TASK_RUN_CONFLICT", "message": str(exc)},
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": "VALIDATION_ERROR", "message": str(exc)},
            )

    @app.get("/api/v2/tasks/{task_id}/runs")
    async def list_task_runs(
        task_id: str,
        limit: int = Query(default=100, ge=1, le=1000),
        context: AuthContext = Depends(_context_from_request),
    ):
        require_scope(context, "workspace:read", "Task-run visibility is not permitted.")
        try:
            runs = app.state.store.list_task_runs(task_id, context.tenant_id, limit=limit)
        except (NotFoundError, ScopeViolation):
            raise HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": "Task not found."},
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": "VALIDATION_ERROR", "message": str(exc)},
            )
        return {"tenant_id": context.tenant_id, "task_id": task_id, "runs": runs}

    @app.get("/api/v2/task-runs/{run_id}")
    async def get_task_run(
        run_id: str,
        context: AuthContext = Depends(_context_from_request),
    ):
        require_scope(context, "workspace:read", "Task-run visibility is not permitted.")
        try:
            return app.state.store.get_task_run(run_id, context.tenant_id)
        except (NotFoundError, ScopeViolation):
            raise HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": "Task run not found."},
            )

    @app.post("/api/v2/tasks/{task_id}/claim")
    async def claim_task(
        task_id: str,
        payload: TaskClaimRequest,
        request: Request,
        context: AuthContext = Depends(_context_from_request),
    ):
        require_scope(context, "workspace:write", "Task execution is not permitted.")
        try:
            task = request.app.state.store.claim_due_task(
                task_id=task_id,
                tenant_id=context.tenant_id,
                worker_id=payload.worker_id,
                lease_seconds=payload.lease_seconds,
            )
        except (NotFoundError, ScopeViolation):
            raise HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": "Task not found."},
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": "VALIDATION_ERROR", "message": str(exc)},
            )
        if task is None:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "TASK_NOT_CLAIMABLE",
                    "message": "Task is not due, is blocked by dependencies, or has no attempts left.",
                },
            )
        return task

    @app.post("/api/v2/tasks/{task_id}/complete")
    async def complete_task(
        task_id: str,
        payload: TaskCompleteRequest,
        request: Request,
        context: AuthContext = Depends(_context_from_request),
    ):
        require_scope(context, "workspace:write", "Task execution is not permitted.")
        try:
            return request.app.state.store.complete_task(
                task_id=task_id,
                tenant_id=context.tenant_id,
                worker_id=payload.worker_id,
                lease_token=payload.lease_token.get_secret_value(),
                result=payload.result,
            )
        except (NotFoundError, ScopeViolation):
            raise HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": "Task not found."},
            )
        except ConflictError as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "TASK_CONFLICT", "message": str(exc)},
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": "VALIDATION_ERROR", "message": str(exc)},
            )

    @app.post("/api/v2/briefings", status_code=201)
    async def create_briefing(
        payload: BriefingRequest,
        request: Request,
        context: AuthContext = Depends(_context_from_request),
    ):
        require_scope(context, "workspace:read", "Briefing visibility is not permitted.")
        briefing_id = issue_id("brf")
        content = BriefingAggregator(
            request.app.state.store,
            request.app.state.connector_registry,
        ).build(
            tenant_id=context.tenant_id,
            principal_id=context.principal_id,
            sources=payload.sources or None,
        )
        content["brief_id"] = briefing_id
        return request.app.state.store.create_briefing(
            briefing_id=briefing_id,
            tenant_id=context.tenant_id,
            principal_id=context.principal_id,
            content=content,
        )

    @app.get("/api/v2/briefings/{briefing_id}")
    async def get_briefing(
        briefing_id: str,
        context: AuthContext = Depends(_context_from_request),
    ):
        require_scope(context, "workspace:read", "Briefing visibility is not permitted.")
        try:
            return app.state.store.get_briefing(briefing_id, context.tenant_id)
        except (NotFoundError, ScopeViolation):
            raise HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": "Briefing not found."},
            )

    @app.post("/api/v2/artifacts", status_code=201)
    async def upload_artifact(
        request: Request,
        context: AuthContext = Depends(_context_from_request),
    ):
        require_scope(context, "analysis:write", "Artifact upload is not permitted.")
        raw = await request.body()
        if not raw:
            raise HTTPException(
                status_code=400,
                detail={"code": "EMPTY_ARTIFACT", "message": "Artifact body is empty."},
            )
        media_type = request.headers.get("content-type", "application/octet-stream").split(";", 1)[0].strip().lower()
        allowed_media_types = {
            "application/octet-stream",
            "application/step",
            "model/step",
            "model/stl",
            "image/png",
            "image/jpeg",
            "audio/wav",
            "audio/mpeg",
            "text/plain",
        }
        if media_type not in allowed_media_types:
            raise HTTPException(
                status_code=415,
                detail={"code": "UNSUPPORTED_ARTIFACT_TYPE", "message": "Artifact media type is not supported."},
            )
        digest = "sha256:" + hashlib.sha256(raw).hexdigest()
        artifact_id = issue_id("art")
        artifact_directory = request.app.state.artifact_directory
        artifact_path = os.path.join(artifact_directory, f"{artifact_id}.bin")
        temp_path = f"{artifact_path}.tmp"
        try:
            flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(temp_path, flags, 0o600)
            try:
                with os.fdopen(descriptor, "wb") as artifact_file:
                    descriptor = -1
                    artifact_file.write(raw)
            finally:
                if descriptor != -1:
                    os.close(descriptor)
            os.replace(temp_path, artifact_path)
            os.chmod(artifact_path, 0o600)
            record = request.app.state.store.create_artifact(
                artifact_id=artifact_id,
                tenant_id=context.tenant_id,
                principal_id=context.principal_id,
                digest=digest,
                media_type=media_type,
                size_bytes=len(raw),
                metadata={"storage": "quarantine", "content_ref": artifact_id},
                storage_ref=artifact_id,
            )
        except FileExistsError:
            raise HTTPException(
                status_code=409,
                detail={"code": "ARTIFACT_CONFLICT", "message": "Artifact upload could not be allocated."},
            )
        except Exception:
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass
            try:
                os.unlink(artifact_path)
            except FileNotFoundError:
                pass
            raise
        return record

    @app.get("/api/v2/artifacts/{artifact_id}")
    async def get_artifact(
        artifact_id: str,
        context: AuthContext = Depends(_context_from_request),
    ):
        require_scope(context, "evidence:read", "Artifact visibility is not permitted.")
        try:
            return app.state.store.get_artifact(artifact_id, context.tenant_id)
        except (NotFoundError, ScopeViolation):
            raise HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": "Artifact not found."},
            )

    @app.post("/api/v2/cad/analyze", status_code=201)
    async def analyze_cad(
        payload: ArtifactAnalysisRequest,
        request: Request,
        context: AuthContext = Depends(_context_from_request),
    ):
        require_scope(context, "analysis:write", "CAD analysis is not permitted.")
        try:
            artifact = request.app.state.store.get_artifact(
                payload.artifact_id, context.tenant_id
            )
        except NotFoundError:
            raise HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": "Artifact not found."},
            )
        evidence_id = issue_id("ev")
        evidence = request.app.state.store.create_evidence(
            evidence_id=evidence_id,
            tenant_id=context.tenant_id,
            principal_id=context.principal_id,
            kind="calculation",
            status="unavailable",
            provenance={
                "adapter_id": "cad-parser",
                "adapter_version": "unavailable",
                "origin": "local",
                "input_digest": artifact["digest"],
                "method_ref": "procedure.cad.parse-and-analyze.v1",
                "disclosure": "No supported CAD parser or solver is enabled in the reference profile.",
            },
            result={
                "analysis_kind": payload.analysis_kind,
                "parser_status": "unavailable",
                "geometry_status": "not_analyzed",
                "stress_status": "not_analyzed",
            },
            artifact_ref=payload.artifact_id,
        )
        return {"analysis_id": evidence_id, "evidence": evidence}

    @app.get("/api/v2/cad/{analysis_id}")
    async def get_cad_analysis(
        analysis_id: str,
        context: AuthContext = Depends(_context_from_request),
    ):
        require_scope(context, "evidence:read", "CAD evidence visibility is not permitted.")
        try:
            return app.state.store.get_evidence(analysis_id, context.tenant_id)
        except NotFoundError:
            raise HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": "CAD analysis not found."},
            )

    @app.post("/api/v2/vision/analyze", status_code=201)
    async def analyze_vision(
        payload: VisionAnalysisRequest,
        request: Request,
        context: AuthContext = Depends(_context_from_request),
    ):
        require_scope(context, "analysis:write", "Vision analysis is not permitted.")
        try:
            artifact = request.app.state.store.get_artifact(
                payload.artifact_id, context.tenant_id
            )
        except NotFoundError:
            raise HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": "Artifact not found."},
            )
        evidence_id = issue_id("ev")
        evidence = request.app.state.store.create_evidence(
            evidence_id=evidence_id,
            tenant_id=context.tenant_id,
            principal_id=context.principal_id,
            kind="observation",
            status="unavailable",
            provenance={
                "adapter_id": "vision-analyzer",
                "adapter_version": "unavailable",
                "origin": "local",
                "input_digest": artifact["digest"],
                "method_ref": "procedure.vision.analyze.v1",
                "disclosure": "No vision model adapter is enabled; confidence and labels are unavailable.",
            },
            result={
                "analysis_kind": payload.analysis_kind,
                "labels": [],
                "confidence": None,
                "status": "unavailable",
            },
            artifact_ref=payload.artifact_id,
        )
        return {"analysis_id": evidence_id, "evidence": evidence}

    @app.get("/api/v2/connectors")
    async def connectors(context: AuthContext = Depends(_context_from_request)):
        require_scope(context, "workspace:read", "Connector visibility is not permitted.")
        return {
            "tenant_id": context.tenant_id,
            "connectors": [
                status.as_dict()
                for status in app.state.connector_registry.statuses()
            ] + [
                {
                    "connector_id": "egress.default",
                    "status": "disabled" if not settings.external_egress_enabled else "configured",
                    "egress": "brokered",
                    "disclosure": "No external connector is enabled in the reference profile."
                    if not settings.external_egress_enabled
                    else "External calls require an allowlisted broker and durable action.",
                }
            ],
        }

    @app.post("/api/v2/connectors/{connector_id}/authorize")
    async def authorize_connector(
        connector_id: str,
        context: AuthContext = Depends(_context_from_request),
    ):
        require_scope(context, "workspace:write", "Connector authorization is not permitted.")
        raise HTTPException(
            status_code=503,
            detail={
                "code": "CAPABILITY_DISABLED",
                "message": "Connector authorization is disabled in the reference profile.",
                "details": {"connector_id": connector_id, "tenant_id": context.tenant_id},
                "retryable": False,
            },
        )

    @app.post("/api/v2/webhooks")
    async def register_webhook(
        context: AuthContext = Depends(_context_from_request),
    ):
        require_scope(context, "workspace:write", "Webhook registration is not permitted.")
        raise HTTPException(
            status_code=503,
            detail={
                "code": "CAPABILITY_DISABLED",
                "message": "Webhook registration is disabled until an egress policy is configured.",
                "details": {"tenant_id": context.tenant_id},
            },
        )

    @app.post("/api/v2/mcp")
    async def governed_mcp(
        payload: MCPRequest,
        request: Request,
        context: AuthContext = Depends(_context_from_request),
    ):
        require_scope(context, "workspace:read", "MCP access is not permitted.")
        if payload.method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": payload.id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "zasi-governed-control-plane", "version": "1.0.0"},
                    "disclosure": "MCP discovery and calls are governed by the ZASI broker.",
                },
            }
        if payload.method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": payload.id,
                "result": {
                    "tools": [
                        {
                            **definition.manifest(),
                            "name": definition.tool_id,
                            "description": definition.disclosure,
                            "inputSchema": {
                                "type": "object",
                                "additionalProperties": True,
                                "x-zasi-schema-ref": definition.input_schema_ref,
                            },
                        }
                        for definition in request.app.state.registry.definitions()
                    ]
                },
            }
        if payload.method != "tools/call":
            return JSONResponse(
                status_code=200,
                content={
                    "jsonrpc": "2.0",
                    "id": payload.id,
                    "error": {"code": -32601, "message": "Method not found"},
                },
            )
        name = payload.params.get("name")
        arguments = payload.params.get("arguments", {})
        if not isinstance(name, str) or not isinstance(arguments, dict):
            return JSONResponse(
                status_code=200,
                content={
                    "jsonrpc": "2.0",
                    "id": payload.id,
                    "error": {"code": -32602, "message": "Typed tool name and arguments are required"},
                },
            )
        definition = request.app.state.registry.get(name)
        if definition is None:
            return JSONResponse(
                status_code=200,
                content={
                    "jsonrpc": "2.0",
                    "id": payload.id,
                    "error": {"code": -32003, "message": "Capability unavailable"},
                },
            )
        if definition.risk_tier not in {"R0", "R1"}:
            return JSONResponse(
                status_code=200,
                content={
                    "jsonrpc": "2.0",
                    "id": payload.id,
                    "error": {"code": -32004, "message": "Risk-bearing MCP calls require a plan"},
                },
            )
        idempotency_key = request.headers.get("Idempotency-Key", "").strip()
        if not idempotency_key or len(idempotency_key) > 256 or any(
            ord(char) < 0x20 or ord(char) == 0x7F for char in idempotency_key
        ):
            return JSONResponse(
                status_code=400,
                content={
                    "jsonrpc": "2.0",
                    "id": payload.id,
                    "error": {"code": -32001, "message": "Idempotency-Key is required"},
                },
            )
        try:
            result = request.app.state.broker.execute(
                tenant_id=context.tenant_id,
                principal_id=context.principal_id,
                tool_id=name,
                payload=arguments,
                requested_risk_tier=definition.risk_tier,
                principal_scopes=context.scopes,
                idempotency_key=idempotency_key,
            )
        except ConflictError:
            return JSONResponse(
                status_code=409,
                content={
                    "jsonrpc": "2.0",
                    "id": payload.id,
                    "error": {"code": -32002, "message": "Idempotency key conflict"},
                },
            )
        if result.status == "denied":
            return JSONResponse(
                status_code=403,
                content={
                    "jsonrpc": "2.0",
                    "id": payload.id,
                    "error": {"code": -32005, "message": "Policy denied tool call"},
                },
            )
        return {
            "jsonrpc": "2.0",
            "id": payload.id,
            "result": {
                "status": result.status,
                "run_id": result.run_id,
                "action_id": result.action_id,
                "evidence": result.evidence,
            },
        }

    @app.post("/api/v2/intents", status_code=201)
    async def create_intent(
        payload: IntentCreateRequest,
        request: Request,
        context: AuthContext = Depends(_context_from_request),
    ):
        if "intent:create" not in context.scopes:
            raise HTTPException(
                status_code=403,
                detail={"code": "POLICY_DENIED", "message": "Intent creation is not permitted."},
            )
        intent_id = issue_id("int")
        record = request.app.state.store.create_intent(
            intent_id=intent_id,
            tenant_id=context.tenant_id,
            principal_id=context.principal_id,
            source_kind=payload.source_kind,
            source_text=payload.source_text,
            goal_json=payload.goal.model_dump_json(),
            requested_mode=payload.requested_mode,
            requested_risk_tier=payload.requested_risk_tier,
        )
        return record

    def sequence_validation_errors(
        steps: list[Dict[str, Any]], context: AuthContext
    ) -> list[str]:
        errors: list[str] = []
        known_step_ids = set()
        for index, step in enumerate(steps):
            step_id = step.get("step_id")
            if not isinstance(step_id, str) or step_id in known_step_ids:
                errors.append(f"step.{index}.id.invalid")
            for dependency in step.get("depends_on", []):
                if dependency not in known_step_ids:
                    errors.append(f"step.{index}.dependency.invalid")
            if isinstance(step_id, str):
                known_step_ids.add(step_id)
            tool_id = step.get("tool_id")
            risk_tier = step.get("risk_tier")
            definition = app.state.registry.get(tool_id) if isinstance(tool_id, str) else None
            if definition is None:
                errors.append(f"step.{index}.capability.unavailable")
                continue
            if step.get("tool_version") != definition.version:
                errors.append(f"step.{index}.capability.version_mismatch")
            decision = policy.evaluate(
                capability_id=tool_id,
                requested_risk_tier=risk_tier,
                principal_scopes=context.scopes,
            )
            if decision.decision == "deny":
                errors.extend(f"step.{index}.{reason}" for reason in decision.reasons)
        return sorted(set(errors))

    @app.post("/api/v2/sequences", status_code=201)
    async def create_sequence(
        payload: SequenceCreateRequest,
        request: Request,
        context: AuthContext = Depends(_context_from_request),
    ):
        require_scope(context, "sequence:write", "Sequence creation is not permitted.")
        steps: list[Dict[str, Any]] = []
        generated_step_ids = [issue_id("stp") for _ in payload.steps]
        client_refs = {f"step-{index}": step_id for index, step_id in enumerate(generated_step_ids)}
        for index, item in enumerate(payload.steps):
            definition = request.app.state.registry.get(item.tool_id)
            steps.append(
                {
                    "step_id": generated_step_ids[index],
                    "tool_id": item.tool_id,
                    "tool_version": definition.version if definition is not None else None,
                    "risk_tier": item.risk_tier,
                    "payload": item.payload,
                    "depends_on": [client_refs.get(ref, ref) for ref in item.depends_on],
                    "side_effect": _side_effect_for_risk(
                        definition.risk_tier if definition is not None else item.risk_tier
                    ),
                }
            )
        canonical_steps = json.dumps(steps, sort_keys=True, separators=(",", ":"))
        digest = "sha256:" + hashlib.sha256(canonical_steps.encode("utf-8")).hexdigest()
        return request.app.state.store.create_sequence(
            sequence_id=issue_id("seq"),
            tenant_id=context.tenant_id,
            principal_id=context.principal_id,
            name=payload.name,
            steps_json=canonical_steps,
            digest=digest,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        )

    @app.get("/api/v2/sequences/{sequence_id}")
    async def get_sequence(
        sequence_id: str,
        request: Request,
        context: AuthContext = Depends(_context_from_request),
    ):
        require_scope(context, "workspace:read", "Sequence visibility is not permitted.")
        try:
            return request.app.state.store.get_sequence(sequence_id, context.tenant_id)
        except NotFoundError:
            raise HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": "Sequence not found."},
            )

    @app.post("/api/v2/sequences/{sequence_id}/validate")
    async def validate_sequence(
        sequence_id: str,
        request: Request,
        context: AuthContext = Depends(_context_from_request),
    ):
        require_scope(context, "sequence:write", "Sequence validation is not permitted.")
        try:
            sequence = request.app.state.store.get_sequence(sequence_id, context.tenant_id)
        except NotFoundError:
            raise HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": "Sequence not found."},
            )
        errors = sequence_validation_errors(sequence["steps"], context)
        if errors:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "SEQUENCE_INVALID",
                    "message": "Sequence validation failed.",
                    "details": {"reasons": errors},
                },
            )
        try:
            return request.app.state.store.transition_sequence(
                sequence_id, context.tenant_id, context.principal_id, "validated"
            )
        except ConflictError as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "SEQUENCE_STATE_CONFLICT", "message": str(exc)},
            )

    @app.post("/api/v2/sequences/{sequence_id}/approve", status_code=201)
    async def approve_sequence(
        sequence_id: str,
        payload: SequenceApprovalRequest,
        request: Request,
        context: AuthContext = Depends(_context_from_request),
    ):
        require_scope(context, "approval:write", "Sequence approval is not permitted.")
        try:
            sequence = request.app.state.store.get_sequence(sequence_id, context.tenant_id)
        except NotFoundError:
            raise HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": "Sequence not found."},
            )
        if payload.digest != sequence["digest"]:
            raise HTTPException(
                status_code=409,
                detail={"code": "SEQUENCE_DIGEST_MISMATCH", "message": "Approval is bound to a different sequence revision."},
            )
        if any(step["risk_tier"] not in {"R0", "R1"} for step in sequence["steps"]):
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "CAPABILITY_DISABLED",
                    "message": "Risk-bearing sequence execution is disabled in the reference profile.",
                    "details": {"reason": payload.reason},
                },
            )
        raise HTTPException(
            status_code=409,
            detail={
                "code": "APPROVAL_NOT_REQUIRED",
                "message": "The enabled reference sequence steps do not require approval.",
            },
        )

    @app.post("/api/v2/sequences/{sequence_id}/run")
    async def run_sequence(
        sequence_id: str,
        request: Request,
        context: AuthContext = Depends(_context_from_request),
    ):
        require_scope(context, "sequence:write", "Sequence execution is not permitted.")
        idempotency_key = _idempotency_key(
            request, "Idempotency-Key is required for sequence runs."
        )
        try:
            sequence = request.app.state.store.get_sequence(sequence_id, context.tenant_id)
        except NotFoundError:
            raise HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": "Sequence not found."},
            )
        try:
            existing_run = request.app.state.store.get_sequence_run_by_idempotency(
                sequence_id,
                context.tenant_id,
                sequence["revision"],
                idempotency_key,
            )
        except ConflictError as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "IDEMPOTENCY_CONFLICT", "message": str(exc)},
            ) from exc
        if existing_run is not None:
            return existing_run
        if sequence["status"] not in {"validated", "approved"}:
            raise HTTPException(
                status_code=409,
                detail={"code": "SEQUENCE_STATE_CONFLICT", "message": "Sequence must be validated before execution."},
            )
        if sequence["expires_at"] and datetime.fromisoformat(sequence["expires_at"]) <= datetime.now(timezone.utc):
            raise HTTPException(
                status_code=409,
                detail={"code": "SEQUENCE_EXPIRED", "message": "Sequence revision has expired."},
            )
        for step in sequence["steps"]:
            definition = request.app.state.registry.get(step.get("tool_id"))
            if definition is None:
                raise HTTPException(
                    status_code=503,
                    detail={
                        "code": "CAPABILITY_DISABLED",
                        "message": "A sequence capability is unavailable.",
                    },
                )
            if step.get("tool_version") != definition.version:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "CAPABILITY_VERSION_MISMATCH",
                        "message": "A sequence capability changed after validation.",
                    },
                )
            if step["risk_tier"] not in {"R0", "R1"}:
                raise HTTPException(
                    status_code=503,
                    detail={"code": "CAPABILITY_DISABLED", "message": "Risk-bearing sequence execution is disabled."},
                )
        try:
            started = request.app.state.store.start_sequence_run(
                sequence_run_id=issue_id("srun"),
                sequence_id=sequence_id,
                tenant_id=context.tenant_id,
                principal_id=context.principal_id,
                revision=sequence["revision"],
                idempotency_key=idempotency_key,
            )
        except ConflictError as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "IDEMPOTENCY_CONFLICT", "message": str(exc)},
            )
        if not started["created"]:
            return started["run"]
        try:
            request.app.state.store.transition_sequence(
                sequence_id, context.tenant_id, context.principal_id, "executing"
            )
            step_results = []
            for index, step in enumerate(sequence["steps"]):
                result = request.app.state.broker.execute(
                    tenant_id=context.tenant_id,
                    principal_id=context.principal_id,
                    tool_id=step["tool_id"],
                    payload=step.get("payload", {}),
                    requested_risk_tier=step["risk_tier"],
                    principal_scopes=context.scopes,
                    idempotency_key=f"{idempotency_key}:step:{index}",
                )
                step_results.append(
                    {
                        "step_id": step["step_id"],
                        "status": result.status,
                        "run_id": result.run_id,
                        "action_id": result.action_id,
                        "evidence": result.evidence,
                        "reasons": list(result.reasons),
                    }
                )
                if result.status != "succeeded":
                    raise RuntimeError("sequence step did not succeed")
            final_status = "completed"
            result_payload = {"steps": step_results, "disclosure": "Sequence steps used the governed broker."}
            request.app.state.store.transition_sequence(
                sequence_id, context.tenant_id, context.principal_id, "completed"
            )
        except Exception:
            final_status = "failed"
            result_payload = {"status": "failed", "disclosure": "A sequence step failed; internal exception details are withheld."}
            try:
                request.app.state.store.transition_sequence(
                    sequence_id, context.tenant_id, context.principal_id, "failed"
                )
            except ConflictError:
                pass
        return request.app.state.store.complete_sequence_run(
            started["run"]["sequence_run_id"],
            context.tenant_id,
            context.principal_id,
            final_status,
            result_payload,
        )

    @app.get("/api/v2/sequences/{sequence_id}/events")
    async def sequence_events(
        sequence_id: str,
        context: AuthContext = Depends(_context_from_request),
        after: Optional[int] = Query(default=None, ge=0),
        limit: int = Query(default=100, ge=1, le=1000),
    ):
        require_scope(context, "workspace:read", "Sequence event visibility is not permitted.")
        after = 0 if after is None else after
        try:
            app.state.store.get_sequence(sequence_id, context.tenant_id)
            event_items = app.state.store.list_sequence_events(
                sequence_id, context.tenant_id, after=after, limit=limit
            )
        except NotFoundError:
            raise HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": "Sequence not found."},
            )
        def sequence_event_stream() -> Iterator[str]:
            for item in event_items:
                yield (
                    f"event: {item['type']}\n"
                    f"id: {item['sequence']}\n"
                    f"data: {json.dumps(item, sort_keys=True, separators=(',', ':'))}\n\n"
                )
            yield "event: stream.end\ndata: {}\n\n"
        return StreamingResponse(
            sequence_event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/api/v2/intents/{intent_id}/plan", status_code=201)
    async def create_plan(
        intent_id: str,
        request: Request,
        context: AuthContext = Depends(_context_from_request),
    ):
        if "plan:create" not in context.scopes:
            raise HTTPException(
                status_code=403,
                detail={"code": "POLICY_DENIED", "message": "Plan creation is not permitted."},
            )
        try:
            intent = request.app.state.store.get_intent(intent_id, context.tenant_id)
        except (NotFoundError, ScopeViolation):
            raise HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": "Intent not found."},
            )
        requested_tool_id = intent["goal"]["object"]
        if requested_tool_id == "system.status":
            requested_tool_id = "registry.system.status"
        definition = request.app.state.registry.get(requested_tool_id)
        decision = policy.evaluate(
            capability_id=requested_tool_id,
            requested_risk_tier=intent["requested_risk_tier"],
            principal_scopes=context.scopes,
        )
        if decision.decision not in {"allow", "allow_with_approval"}:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "POLICY_DENIED",
                    "message": "The requested plan is not permitted.",
                    "details": {"reasons": decision.reasons},
                },
            )
        if definition is None:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "CAPABILITY_UNAVAILABLE",
                    "message": "The requested capability is unavailable.",
                },
            )
        plan_risk = definition.risk_tier
        step = {
            "step_id": issue_id("stp"),
            "kind": "read" if plan_risk == "R0" else "compute" if plan_risk == "R1" else "external_write",
            "tool_id": definition.tool_id,
            "tool_version": definition.version,
            "input_ref": None,
            "risk_tier": plan_risk,
            "side_effect": _side_effect_for_risk(plan_risk),
            "preconditions": ["session.active", "tenant.scope"],
            "rollback": "not_applicable",
        }
        steps = [step]
        canonical_steps = json.dumps(steps, sort_keys=True, separators=(",", ":"))
        digest = "sha256:" + hashlib.sha256(canonical_steps.encode("utf-8")).hexdigest()
        scope_digest = _scope_digest(context)
        plan_id = issue_id("pln")
        plan_status = "awaiting_approval" if decision.decision == "allow_with_approval" else "draft"
        return request.app.state.store.create_plan(
            plan_id=plan_id,
            tenant_id=context.tenant_id,
            principal_id=context.principal_id,
            intent_id=intent_id,
            digest=digest,
            steps_json=canonical_steps,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            scope_digest=scope_digest,
            status=plan_status,
        )

    @app.get("/api/v2/intents/{intent_id}/plan")
    async def get_intent_plan_not_allowed(
        context: AuthContext = Depends(_context_from_request),
    ):
        require_scope(context, "workspace:read", "Plan visibility is not permitted.")
        response = _error(
            405,
            "METHOD_NOT_ALLOWED",
            "Plan generation requires POST; plans are read through /api/v2/plans/{plan_id}.",
        )
        response.headers["Allow"] = "POST"
        return response

    @app.get("/api/v2/plans/{plan_id}")
    async def get_plan(
        plan_id: str,
        request: Request,
        context: AuthContext = Depends(_context_from_request),
    ):
        require_scope(context, "workspace:read", "Plan visibility is not permitted.")
        try:
            return request.app.state.store.get_plan(plan_id, context.tenant_id)
        except (NotFoundError, ScopeViolation):
            raise HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": "Plan not found."},
            )

    @app.post("/api/v2/plans/{plan_id}/approve", status_code=201)
    async def approve_plan(
        plan_id: str,
        payload: ApprovalRequest,
        request: Request,
        context: AuthContext = Depends(_context_from_request),
    ):
        if "approval:write" not in context.scopes:
            raise HTTPException(
                status_code=403,
                detail={"code": "POLICY_DENIED", "message": "Approval is not permitted."},
            )
        try:
            plan = request.app.state.store.get_plan(plan_id, context.tenant_id)
        except (NotFoundError, ScopeViolation):
            raise HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": "Plan not found."},
            )
        if len(plan["steps"]) != 1:
            raise HTTPException(
                status_code=409,
                detail={"code": "PLAN_INTEGRITY_ERROR", "message": "Plan shape is unsupported."},
            )
        step = plan["steps"][0]
        if step["risk_tier"] in {"R0", "R1"}:
            raise HTTPException(
                status_code=409,
                detail={"code": "APPROVAL_NOT_REQUIRED", "message": "This plan does not require approval."},
            )
        if payload.digest != plan["digest"]:
            raise HTTPException(
                status_code=409,
                detail={"code": "PLAN_DIGEST_MISMATCH", "message": "Approval is bound to a different plan digest."},
            )
        try:
            approval = request.app.state.store.approve_plan(
                approval_id=issue_id("apr"),
                plan_id=plan_id,
                tenant_id=context.tenant_id,
                approver_id=context.principal_id,
                digest=payload.digest,
                scope_digest=plan["scope_digest"],
                required_capability=step["tool_id"],
                risk_tier=step["risk_tier"],
                reason=payload.reason,
                expires_at=datetime.fromisoformat(plan["expires_at"]),
            )
        except ConflictError as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "APPROVAL_CONFLICT", "message": str(exc)},
            )
        return approval

    @app.post("/api/v2/plans/{plan_id}/run")
    async def run_plan(
        plan_id: str,
        request: Request,
        context: AuthContext = Depends(_context_from_request),
    ):
        idempotency_key = _idempotency_key(
            request, "Idempotency-Key is required for plan runs."
        )
        try:
            plan = request.app.state.store.get_plan(plan_id, context.tenant_id)
        except (NotFoundError, ScopeViolation):
            raise HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": "Plan not found."},
            )
        existing_run = request.app.state.store.get_run_by_idempotency(
            context.tenant_id, idempotency_key
        )
        if existing_run is not None:
            if existing_run.get("plan_id") != plan_id:
                raise HTTPException(
                    status_code=409,
                    detail={"code": "IDEMPOTENCY_CONFLICT", "message": "Idempotency key is bound to another plan."},
                )
            return {
                "status": existing_run["status"],
                "decision": "allow",
                "run_id": existing_run["run_id"],
                "action_id": existing_run["action_id"],
                "evidence": existing_run["evidence"],
                "reasons": ["idempotency.replay"],
            }
        if datetime.fromisoformat(plan["expires_at"]) <= datetime.now(timezone.utc):
            if plan["status"] not in {"expired", "completed", "failed"}:
                try:
                    request.app.state.store.transition_plan(
                        plan_id, context.tenant_id, context.principal_id, "expired"
                    )
                except ConflictError:
                    pass
            raise HTTPException(
                status_code=409,
                detail={"code": "PLAN_EXPIRED", "message": "Plan approval window expired."},
            )
        canonical_steps = json.dumps(
            plan["steps"], sort_keys=True, separators=(",", ":")
        )
        expected_digest = "sha256:" + hashlib.sha256(
            canonical_steps.encode("utf-8")
        ).hexdigest()
        if (
            expected_digest != plan["digest"]
            or len(plan["steps"]) != 1
            or plan["scope_digest"] != _scope_digest(context)
        ):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "PLAN_SCOPE_OR_INTEGRITY_ERROR",
                    "message": "Plan integrity verification failed.",
                },
            )
        step = plan["steps"][0]
        definition = request.app.state.registry.get(step["tool_id"])
        if definition is None:
            raise HTTPException(
                status_code=409,
                detail={"code": "CAPABILITY_UNAVAILABLE", "message": "Plan capability is unavailable."},
            )
        if step.get("tool_version") != definition.version:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "CAPABILITY_VERSION_MISMATCH",
                    "message": "Plan capability changed after plan creation.",
                },
            )
        decision = policy.evaluate(
            capability_id=definition.tool_id,
            requested_risk_tier=step["risk_tier"],
            principal_scopes=context.scopes,
        )
        if decision.decision == "deny":
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "POLICY_DENIED",
                    "message": "The plan run is not permitted.",
                    "details": {"reasons": list(decision.reasons)},
                },
            )
        requires_approval = decision.required_approvals > 0
        approved = False
        if requires_approval:
            if plan["status"] != "approved" or not request.app.state.store.has_valid_approval(
                plan_id,
                context.tenant_id,
                plan["digest"],
                plan["scope_digest"],
            ):
                raise HTTPException(
                    status_code=409,
                    detail={"code": "APPROVAL_REQUIRED", "message": "An unexpired approval for this exact plan is required."},
                )
            approved = True
        elif plan["status"] not in {"draft", "approved"}:
            raise HTTPException(
                status_code=409,
                detail={"code": "PLAN_STATE_CONFLICT", "message": "Plan is not runnable in its current state."},
            )
        try:
            request.app.state.store.transition_plan(
                plan_id, context.tenant_id, context.principal_id, "executing"
            )
        except ConflictError as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "PLAN_STATE_CONFLICT", "message": str(exc)},
            )
        result = request.app.state.broker.execute(
            tenant_id=context.tenant_id,
            principal_id=context.principal_id,
            tool_id=step["tool_id"],
            payload={},
            requested_risk_tier=step["risk_tier"],
            principal_scopes=context.scopes,
            idempotency_key=idempotency_key,
            approved=approved,
            plan_id=plan_id,
        )
        if result.status == "denied":
            try:
                request.app.state.store.transition_plan(
                    plan_id, context.tenant_id, context.principal_id, "failed"
                )
            except ConflictError:
                pass
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "POLICY_DENIED",
                    "message": "The plan run is not permitted.",
                    "details": {"reasons": list(result.reasons)},
                },
            )
        try:
            request.app.state.store.transition_plan(
                plan_id,
                context.tenant_id,
                context.principal_id,
                "completed" if result.status == "succeeded" else "failed",
            )
        except ConflictError:
            # The run is durable even if a concurrent status transition won.
            pass
        response_body = {
            "status": result.status,
            "decision": result.decision,
            "run_id": result.run_id,
            "action_id": result.action_id,
            "evidence": result.evidence,
            "reasons": list(result.reasons),
        }
        if result.status == "waiting_approval":
            return JSONResponse(status_code=202, content=response_body)
        return response_body

    @app.get("/api/v2/capabilities")
    async def capabilities(context: AuthContext = Depends(_context_from_request)):
        require_scope(context, "workspace:read", "Capability visibility is not permitted.")
        registered = []
        for definition in app.state.registry.definitions():
            manifest = definition.manifest()
            registered.append(
                {
                    **manifest,
                    "implementation_state": "implemented" if definition.availability == "enabled" else definition.availability,
                    "runtime_state": "ready" if definition.availability == "enabled" else "simulated" if definition.availability == "simulation" else "offline",
                    "evidence_state": (
                        "locally_verified"
                        if definition.evidence_status == "verified"
                        else definition.evidence_status
                    ),
                    "allowed_risk_tiers": [definition.risk_tier] if definition.availability == "enabled" else [],
                    "last_verified_at": None,
                    "evidence_refs": [],
                    "operator_disclosure": definition.disclosure,
                }
            )
        return {
            "capabilities": registered,
            "tenant_id": context.tenant_id,
            "profile": settings.profile,
        }

    @app.post("/api/v2/tools/preview")
    async def preview_tool(
        payload: ToolCallRequest,
        context: AuthContext = Depends(_context_from_request),
    ):
        decision = app.state.broker.preview(
            tool_id=payload.tool_id,
            requested_risk_tier=payload.requested_risk_tier,
            principal_scopes=context.scopes,
        )
        return {
            "tool_id": payload.tool_id,
            "decision": decision.decision,
            "risk_tier": decision.risk_tier,
            "reasons": list(decision.reasons),
            "required_approvals": decision.required_approvals,
            "policy_version": decision.policy_version,
        }

    @app.post("/api/v2/tools/call")
    async def call_tool(
        payload: ToolCallRequest,
        request: Request,
        context: AuthContext = Depends(_context_from_request),
    ):
        idempotency_key = _idempotency_key(
            request, "Idempotency-Key is required for tool calls."
        )
        definition = app.state.registry.get(payload.tool_id)
        if definition is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "CAPABILITY_UNAVAILABLE", "message": "The requested capability is unavailable."},
            )
        if definition.risk_tier not in {"R0", "R1"}:
            raise HTTPException(
                status_code=409,
                detail={"code": "PLAN_REQUIRED", "message": "Risk-bearing tools must be submitted through an immutable plan."},
            )
        try:
            result = app.state.broker.execute(
                tenant_id=context.tenant_id,
                principal_id=context.principal_id,
                tool_id=payload.tool_id,
                payload=payload.payload,
                requested_risk_tier=payload.requested_risk_tier,
                principal_scopes=context.scopes,
                idempotency_key=idempotency_key,
            )
        except ConflictError as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "IDEMPOTENCY_CONFLICT", "message": str(exc)},
            )
        if result.status == "denied":
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "POLICY_DENIED",
                    "message": "The requested tool call is not permitted.",
                    "details": {"reasons": list(result.reasons)},
                },
            )
        if result.status == "waiting_approval":
            return JSONResponse(
                status_code=202,
                content={
                    "status": result.status,
                    "decision": result.decision,
                    "run_id": result.run_id,
                    "action_id": result.action_id,
                    "evidence": result.evidence,
                    "reasons": list(result.reasons),
                },
            )
        return {
            "status": result.status,
            "decision": result.decision,
            "run_id": result.run_id,
            "action_id": result.action_id,
            "evidence": result.evidence,
            "reasons": list(result.reasons),
        }

    @app.get("/api/v2/runs/{run_id}")
    async def get_run(
        run_id: str,
        request: Request,
        context: AuthContext = Depends(_context_from_request),
    ):
        require_scope(context, "workspace:read", "Run visibility is not permitted.")
        try:
            return request.app.state.store.get_run(run_id, context.tenant_id)
        except (NotFoundError, ScopeViolation):
            raise HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": "Run not found."},
            )

    @app.post("/api/v2/runs/{run_id}/reconcile")
    async def reconcile_run(
        run_id: str,
        payload: ActionReconcileRequest,
        context: AuthContext = Depends(_context_from_request),
    ):
        require_scope(context, "run:reconcile", "Run reconciliation is not permitted.")
        try:
            return app.state.store.reconcile_action(
                run_id=run_id,
                tenant_id=context.tenant_id,
                principal_id=context.principal_id,
                outcome=payload.outcome,
                reason=payload.reason,
                result=payload.result,
            )
        except (NotFoundError, ScopeViolation):
            raise HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": "Run not found."},
            )
        except ConflictError as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "RUN_RECONCILIATION_CONFLICT", "message": str(exc)},
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": "VALIDATION_ERROR", "message": str(exc)},
            )

    @app.post("/api/v2/runs/{run_id}/cancel")
    async def cancel_run(
        run_id: str,
        request: Request,
        context: AuthContext = Depends(_context_from_request),
    ):
        require_scope(context, "run:cancel", "Run cancellation is not permitted.")
        idempotency_key = _idempotency_key(
            request, "Idempotency-Key is required for cancellation."
        )
        try:
            return request.app.state.store.cancel_run(
                run_id,
                context.tenant_id,
                context.principal_id,
                idempotency_key=idempotency_key,
            )
        except NotFoundError:
            raise HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": "Run not found."},
            )
        except ConflictError as exc:
            message = str(exc)
            code = (
                "IDEMPOTENCY_CONFLICT"
                if "idempotency" in message
                else "RUN_STATE_CONFLICT"
            )
            raise HTTPException(
                status_code=409,
                detail={"code": code, "message": message},
            )

    @app.get("/api/v2/snapshot")
    async def snapshot(
        request: Request,
        context: AuthContext = Depends(_context_from_request),
    ):
        require_scope(context, "workspace:read", "Snapshot visibility is not permitted.")
        return {
            "tenant_id": context.tenant_id,
            "schema_version": CURRENT_SCHEMA_VERSION,
            "cursor": request.app.state.store.latest_sequence(context.tenant_id),
            "capabilities": {
                "database": "ready",
                "external_egress": "configured" if settings.external_egress_enabled else "disabled",
                "research_execution": "configured" if settings.research_execution_enabled else "disabled",
                "physical_actuation": "disabled",
            },
            "disclosure": "Snapshot is authoritative for control-plane state only; it is not subsystem availability evidence.",
        }

    @app.get("/api/v2/events")
    async def events(
        request: Request,
        after: Optional[int] = Query(default=None, ge=0),
        limit: int = Query(default=100, ge=1, le=1000),
        follow: bool = Query(default=False),
        x_zasi_event_cursor: Optional[str] = Header(default=None),
        last_event_id: Optional[str] = Header(default=None),
        context: AuthContext = Depends(_context_from_request),
    ):
        require_scope(context, "workspace:read", "Event visibility is not permitted.")
        query_after = after
        after = 0 if after is None else after
        last_after: Optional[int] = None
        if last_event_id is not None:
            try:
                last_after = int(last_event_id)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail={"code": "INVALID_CURSOR", "message": "The event cursor is invalid."},
                )
            if query_after is not None and query_after != last_after:
                raise HTTPException(
                    status_code=400,
                    detail={"code": "CURSOR_MISMATCH", "message": "Query and Last-Event-ID cursors do not match."},
                )
            after = last_after
        if x_zasi_event_cursor is not None:
            try:
                header_after = int(x_zasi_event_cursor)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "code": "INVALID_CURSOR",
                        "message": "The event cursor is invalid.",
                    },
                )
            if header_after < 0 or (
                query_after is not None and query_after != header_after
            ) or (last_after is not None and last_after != header_after):
                raise HTTPException(
                    status_code=400,
                    detail={
                        "code": "CURSOR_MISMATCH",
                        "message": "Query and header cursors do not match.",
                    },
                )
            after = header_after
        try:
            requires_resync = request.app.state.store.cursor_requires_resync(
                context.tenant_id, after
            )
            event_items = request.app.state.store.list_events(
                context.tenant_id, after=after, limit=limit
            )
            latest = request.app.state.store.latest_sequence(context.tenant_id)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail={"code": "INVALID_CURSOR", "message": "The event cursor is invalid."},
            )

        next_cursor = event_items[-1]["sequence"] if event_items else after
        stream_token = optional_bearer(request.headers.get("Authorization"))

        def format_event(item: Dict[str, Any]) -> str:
            return (
                f"event: {item['type']}\n"
                f"id: {item['sequence']}\n"
                f"data: {json.dumps(item, sort_keys=True, separators=(',', ':'))}\n\n"
            )

        def event_stream() -> Iterator[str]:
            if requires_resync:
                yield (
                    "event: resync.required\n"
                    "data: "
                    + json.dumps(
                        {
                            "required": True,
                            "snapshot_ref": "/api/v2/snapshot",
                            "from_cursor": after,
                            "latest_cursor": latest,
                        },
                        sort_keys=True,
                    )
                    + "\n\n"
                )
                yield (
                    "event: stream.end\n"
                    f"data: {json.dumps({'next_cursor': latest, 'resync_required': True})}\n\n"
                )
                return
            for item in event_items:
                yield format_event(item)
            yield (
                "event: stream.end\n"
                f"data: {json.dumps({'next_cursor': next_cursor, 'resync_required': False})}\n\n"
            )

        async def live_event_stream() -> AsyncGenerator[str, None]:
            cursor = after
            if requires_resync:
                yield (
                    "event: resync.required\n"
                    "data: "
                    + json.dumps(
                        {
                            "required": True,
                            "snapshot_ref": "/api/v2/snapshot",
                            "from_cursor": after,
                            "latest_cursor": latest,
                        },
                        sort_keys=True,
                    )
                    + "\n\n"
                )
                return
            while True:
                if await request.is_disconnected():
                    return
                if not _session_is_active(
                    request.app.state.store,
                    stream_token,
                    context,
                ):
                    yield (
                        "event: stream.end\n"
                        + "data: "
                        + json.dumps(
                            {
                                "next_cursor": cursor,
                                "resync_required": False,
                                "reason": "session_revoked_or_expired",
                            },
                            sort_keys=True,
                        )
                        + "\n\n"
                    )
                    return
                items = request.app.state.store.list_events(
                    context.tenant_id, after=cursor, limit=limit
                )
                if items:
                    for item in items:
                        cursor = item["sequence"]
                        yield format_event(item)
                else:
                    yield ": keepalive\n\n"
                await asyncio.sleep(1)

        return StreamingResponse(
            live_event_stream() if follow else event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "X-ZASI-Event-Cursor": str(latest if requires_resync else next_cursor),
            },
        )

    @app.get("/api/status")
    async def compatibility_status(context: AuthContext = Depends(_context_from_request)):
        require_scope(context, "workspace:read", "Compatibility status visibility is not permitted.")
        definitions = app.state.registry.definitions()
        implemented = sum(1 for item in definitions if item.availability == "enabled")
        simulated = sum(1 for item in definitions if item.availability == "simulation")
        research_only = sum(1 for item in definitions if item.availability == "research_only")
        disabled = sum(1 for item in definitions if item.availability == "disabled")
        return {
            "status": "READY",
            "claim_basis": "authoritative-control-plane-registry",
            "tenant_id": context.tenant_id,
            "capabilities": {
                "implemented": implemented,
                "simulated": simulated,
                "research_only": research_only,
                "disabled": disabled,
            },
            "compatibility_routes": COMPATIBILITY_ROUTES,
            "disclosure": "This compatibility response does not claim that the legacy catalog is live.",
        }

    @app.get("/api/telemetry")
    async def compatibility_telemetry(context: AuthContext = Depends(_context_from_request)):
        require_scope(context, "workspace:read", "Compatibility telemetry visibility is not permitted.")
        return {
            "status": "unavailable",
            "evidence_state": "unavailable",
            "profile": settings.profile,
            "tenant_id": context.tenant_id,
            "disclosure": "Host telemetry is not exposed by this compatibility surface.",
        }

    @app.get("/api/tick")
    async def retired_tick():
        return _error(410, "ROUTE_RETIRED", "State changes through GET are retired.")

    @app.get("/api/execute/{key}")
    async def retired_execute(key: str):
        return _error(410, "ROUTE_RETIRED", "Direct execution routes are retired.")

    @app.post("/api/mutate")
    async def retired_mutate():
        return _error(410, "ROUTE_RETIRED", "Direct mutation routes are retired.")

    @app.post("/api/rsi/upgrade")
    async def retired_rsi():
        return _error(410, "CAPABILITY_DISABLED", "Runtime hot swap is disabled.")

    @app.post("/api/mcp")
    async def retired_mcp():
        return _error(410, "ROUTE_RETIRED", "MCP calls must use the governed broker.")

    frontend_dist = str(frontend_dist_path())
    if os.path.isdir(os.path.join(frontend_dist, "assets")):
        app.mount(
            "/assets",
            StaticFiles(directory=os.path.join(frontend_dist, "assets")),
            name="frontend-assets",
        )

    @app.get("/", include_in_schema=False)
    async def frontend_root():
        index_path = os.path.join(frontend_dist, "index.html")
        if not os.path.isfile(index_path):
            return _error(503, "UI_BUILD_REQUIRED", "The bundled cockpit has not been built.")
        return FileResponse(index_path, media_type="text/html")

    @app.get("/{frontend_path:path}", include_in_schema=False)
    async def frontend_fallback(frontend_path: str):
        # Only the built SPA entry point is eligible for fallback. No arbitrary
        # filesystem path is accepted from the URL.
        if frontend_path.startswith("api/") or frontend_path.startswith("health/"):
            raise HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": "Route not found."},
            )
        index_path = os.path.join(frontend_dist, "index.html")
        if not os.path.isfile(index_path):
            return _error(404, "NOT_FOUND", "Route not found.")
        return FileResponse(index_path, media_type="text/html")

    return app


def run() -> None:
    import uvicorn

    settings = Settings.from_mapping()
    uvicorn.run(
        "backend.app:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        log_level="info",
    )


if __name__ == "__main__":
    run()
