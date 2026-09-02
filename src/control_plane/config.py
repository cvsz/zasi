"""Fail-closed, immutable control-plane configuration."""

from dataclasses import dataclass, field
import hashlib
import hmac
import os
import secrets
from pathlib import Path
from typing import Mapping, Optional, Tuple
from urllib.parse import urlsplit


class ConfigurationError(ValueError):
    """Raised when a profile cannot be started safely."""


def _derive_api_key_digest(api_key: str, salt: bytes) -> bytes:
    """Derive a memory-hard verifier for a bootstrap API key."""
    return hashlib.scrypt(
        api_key.encode("utf-8"),
        salt=salt,
        n=2**14,
        r=8,
        p=1,
        dklen=32,
    )


@dataclass(frozen=True)
class Settings:
    profile: str
    host: str
    port: int
    cors_origins: Tuple[str, ...]
    api_key_digest: bytes = field(repr=False, compare=False)
    api_key_salt: bytes = field(repr=False, compare=False)
    database_path: str
    max_body_bytes: int
    auth_rate_limit: int = 10
    auth_rate_window_seconds: int = 60
    request_rate_limit: int = 120
    request_rate_window_seconds: int = 60
    event_retention: int = 10_000
    artifact_directory: str = ""
    database_backend: str = "sqlite"
    database_url: Optional[str] = None
    redis_url: Optional[str] = field(default=None, repr=False, compare=False)
    secret_provider: str = "environment"
    backup_policy: str = "local"
    external_egress_enabled: bool = False
    research_execution_enabled: bool = False
    physical_actuation_enabled: bool = False
    egress_allowed_hosts: Tuple[str, ...] = ()
    api_prefix: str = "/api/v2"

    @classmethod
    def from_mapping(cls, mapping: Optional[Mapping[str, str]] = None) -> "Settings":
        source = dict(os.environ if mapping is None else mapping)
        profile = source.get("ZASI_PROFILE", "local").strip().lower()
        if profile not in {"local", "staging", "production"}:
            raise ConfigurationError("ZASI_PROFILE must be local, staging, or production")

        raw_api_key = source.get("ZASI_API_KEY", "")
        if not raw_api_key or not raw_api_key.strip():
            raise ConfigurationError("ZASI_API_KEY is required; insecure defaults are disabled")
        api_key_salt = secrets.token_bytes(16)
        api_key_digest = _derive_api_key_digest(raw_api_key, api_key_salt)

        origins_value = source.get("ZASI_CORS_ORIGINS")
        if origins_value is None and profile == "local":
            origins = ("http://localhost:5173", "http://127.0.0.1:5173")
        else:
            origins = tuple(
                item.strip()
                for item in (origins_value or "").split(",")
                if item.strip()
            )
        if not origins or "*" in origins:
            raise ConfigurationError("ZASI_CORS_ORIGINS must be an explicit non-wildcard allowlist")
        for origin in origins:
            try:
                parsed_origin = urlsplit(origin)
                parsed_port = parsed_origin.port
            except ValueError as exc:
                raise ConfigurationError("ZASI_CORS_ORIGINS contains an invalid origin") from exc
            if (
                parsed_origin.scheme not in {"http", "https"}
                or not parsed_origin.netloc
                or parsed_origin.path not in {"", "/"}
                or parsed_origin.query
                or parsed_origin.fragment
                or parsed_origin.username is not None
                or parsed_origin.password is not None
                or parsed_port is not None and not 1 <= parsed_port <= 65535
                or any(ord(char) < 0x20 or char.isspace() for char in origin)
            ):
                raise ConfigurationError("ZASI_CORS_ORIGINS contains an invalid origin")

        host = source.get("ZASI_HOST", "127.0.0.1").strip()
        if not host:
            raise ConfigurationError("ZASI_HOST must not be empty")
        if profile in {"staging", "production"} and host in {"0.0.0.0", "::"}:
            if source.get("ZASI_ALLOW_PUBLIC_BIND", "").strip().lower() != "yes":
                raise ConfigurationError("public bind requires explicit ZASI_ALLOW_PUBLIC_BIND=yes")

        try:
            port = int(source.get("ZASI_PORT", "8080"))
        except ValueError as exc:
            raise ConfigurationError("ZASI_PORT must be an integer") from exc
        if not 1 <= port <= 65535:
            raise ConfigurationError("ZASI_PORT must be between 1 and 65535")

        try:
            max_body_bytes = int(source.get("ZASI_MAX_BODY", str(1 * 1024 * 1024)))
        except ValueError as exc:
            raise ConfigurationError("ZASI_MAX_BODY must be an integer") from exc
        if not 1 <= max_body_bytes <= 16 * 1024 * 1024:
            raise ConfigurationError("ZASI_MAX_BODY must be between 1 byte and 16 MiB")

        def bounded_int(name: str, default: str, minimum: int, maximum: int) -> int:
            try:
                value = int(source.get(name, default))
            except ValueError as exc:
                raise ConfigurationError(f"{name} must be an integer") from exc
            if not minimum <= value <= maximum:
                raise ConfigurationError(f"{name} is outside the safe bound")
            return value

        auth_rate_limit = bounded_int("ZASI_AUTH_RATE_LIMIT", "10", 1, 10_000)
        auth_rate_window_seconds = bounded_int(
            "ZASI_AUTH_RATE_WINDOW", "60", 1, 86_400
        )
        request_rate_limit = bounded_int("ZASI_REQUEST_RATE_LIMIT", "120", 1, 1_000_000)
        request_rate_window_seconds = bounded_int(
            "ZASI_REQUEST_RATE_WINDOW", "60", 1, 86_400
        )
        event_retention = bounded_int("ZASI_EVENT_RETENTION", "10000", 1, 10_000_000)

        default_database = Path(__file__).resolve().parents[2] / "data" / "zasi_control_plane.db"
        database_path = source.get("ZASI_DATABASE_PATH", str(default_database)).strip()
        if not database_path:
            raise ConfigurationError("ZASI_DATABASE_PATH must not be empty")

        database_backend = source.get("ZASI_DATABASE_BACKEND", "sqlite").strip().lower()
        if database_backend not in {"sqlite", "postgresql"}:
            raise ConfigurationError("ZASI_DATABASE_BACKEND must be sqlite or postgresql")
        database_url = source.get("ZASI_DATABASE_URL", "").strip() or None
        redis_url = source.get("ZASI_REDIS_URL", "").strip() or None
        if redis_url:
            try:
                parsed_redis = urlsplit(redis_url)
                parsed_redis_port = parsed_redis.port
            except ValueError as exc:
                raise ConfigurationError("ZASI_REDIS_URL contains an invalid URL") from exc
            if (
                parsed_redis.scheme not in {"redis", "rediss"}
                or not parsed_redis.hostname
                or parsed_redis.path not in {"", "/", "/0"}
                or parsed_redis.query
                or parsed_redis.fragment
                or parsed_redis_port is not None
                and not 1 <= parsed_redis_port <= 65535
            ):
                raise ConfigurationError("ZASI_REDIS_URL must be a redis:// or rediss:// URL")
        secret_provider = source.get("ZASI_SECRET_PROVIDER", "environment").strip().lower()
        backup_policy = source.get("ZASI_BACKUP_POLICY", "local").strip().lower()
        if profile in {"staging", "production"}:
            if database_backend != "postgresql" or not database_url:
                raise ConfigurationError(
                    "staging and production require an explicit PostgreSQL database URL"
                )
            if not database_url.startswith(("postgresql://", "postgres://")):
                raise ConfigurationError("ZASI_DATABASE_URL must use a PostgreSQL scheme")
            if not redis_url:
                raise ConfigurationError(
                    "staging and production require an explicit Redis URL"
                )
            if not urlsplit(redis_url).password:
                raise ConfigurationError(
                    "staging and production require an authenticated Redis URL"
                )
            if secret_provider in {"", "environment"}:
                raise ConfigurationError(
                    "staging and production require an external secret provider"
                )
            if backup_policy in {"", "none", "local"}:
                raise ConfigurationError(
                    "staging and production require a managed backup policy"
                )

        default_artifact_directory = str(
            Path(database_path).resolve().parent / "artifacts"
        )
        artifact_directory = source.get(
            "ZASI_ARTIFACT_DIRECTORY", default_artifact_directory
        ).strip()
        if not artifact_directory:
            raise ConfigurationError("ZASI_ARTIFACT_DIRECTORY must not be empty")

        external_egress_enabled = source.get(
            "ZASI_ENABLE_EXTERNAL_EGRESS", "no"
        ).strip().lower() == "yes"
        egress_allowed_hosts = tuple(
            item.strip().lower()
            for item in source.get("ZASI_EGRESS_ALLOWED_HOSTS", "").split(",")
            if item.strip()
        )
        if external_egress_enabled and not egress_allowed_hosts:
            raise ConfigurationError(
                "external egress requires ZASI_EGRESS_ALLOWED_HOSTS"
            )
        research_execution_enabled = source.get(
            "ZASI_ENABLE_RESEARCH_EXECUTION", "no"
        ).strip().lower() == "yes"
        if research_execution_enabled and not source.get("ZASI_RESEARCH_SANDBOX", "").strip():
            raise ConfigurationError(
                "research execution requires an explicit sandbox capability"
            )
        if source.get("ZASI_ENABLE_PHYSICAL_ACTUATION", "no").strip().lower() == "yes":
            raise ConfigurationError(
                "physical actuation is disabled in the reference control plane"
            )

        return cls(
            profile=profile,
            host=host,
            port=port,
            cors_origins=origins,
            api_key_digest=api_key_digest,
            api_key_salt=api_key_salt,
            database_path=database_path,
            max_body_bytes=max_body_bytes,
            auth_rate_limit=auth_rate_limit,
            auth_rate_window_seconds=auth_rate_window_seconds,
            request_rate_limit=request_rate_limit,
            request_rate_window_seconds=request_rate_window_seconds,
            event_retention=event_retention,
            artifact_directory=artifact_directory,
            database_backend=database_backend,
            database_url=database_url,
            redis_url=redis_url,
            secret_provider=secret_provider,
            backup_policy=backup_policy,
            external_egress_enabled=external_egress_enabled,
            research_execution_enabled=research_execution_enabled,
            physical_actuation_enabled=False,
            egress_allowed_hosts=egress_allowed_hosts,
        )

    def api_key_matches(self, candidate: str) -> bool:
        """Compare a supplied bootstrap key without retaining its plaintext."""
        if not isinstance(candidate, str) or not candidate:
            return False
        candidate_digest = _derive_api_key_digest(candidate, self.api_key_salt)
        return hmac.compare_digest(candidate_digest, self.api_key_digest)
