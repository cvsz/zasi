"""Policy-controlled outbound HTTP with dual-stack SSRF defenses."""

from dataclasses import dataclass
import http.client
import ipaddress
import json
import socket
import ssl
import time
from typing import Callable, FrozenSet, List, Optional, Tuple
from urllib.parse import SplitResult, urljoin, urlsplit


class EgressDenied(PermissionError):
    """Raised when an outbound destination violates the egress policy."""


class EgressRequestFailed(RuntimeError):
    """Raised when a permitted outbound request fails."""


Resolver = Callable[[str, int], List[Tuple[int, int, int, str, tuple]]]


@dataclass(frozen=True)
class EgressPolicy:
    allowed_hosts: FrozenSet[str]
    allowed_schemes: FrozenSet[str] = frozenset({"https"})
    allow_redirects: bool = False
    max_payload_bytes: int = 256 * 1024
    max_response_bytes: int = 1024 * 1024
    connect_timeout_sec: float = 5.0
    total_timeout_sec: float = 10.0


@dataclass(frozen=True)
class ResolvedDestination:
    url: str
    scheme: str
    hostname: str
    port: int
    request_target: str
    addresses: Tuple[Tuple[int, tuple], ...]


@dataclass(frozen=True)
class EgressResponse:
    status_code: int
    headers: Tuple[Tuple[str, str], ...]
    body: bytes


def _default_resolver(hostname: str, port: int):
    return socket.getaddrinfo(
        hostname,
        port,
        type=socket.SOCK_STREAM,
    )


def _secure_tls_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return context


def _remaining_timeout(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise EgressRequestFailed("outbound request exceeded total timeout")
    return remaining


def _host_allowed(hostname: str, allowed_hosts: FrozenSet[str]) -> bool:
    normalized = hostname.rstrip(".").lower()
    for candidate in allowed_hosts:
        rule = candidate.rstrip(".").lower()
        if rule.startswith("."):
            if normalized.endswith(rule) and normalized != rule[1:]:
                return True
        elif normalized == rule:
            return True
    return False


def _public_ip(address: str) -> ipaddress.IPv4Address:
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError as exc:
        raise EgressDenied("destination resolved to an invalid address") from exc
    if (
        not parsed.is_global
        or parsed.is_loopback
        or parsed.is_link_local
        or parsed.is_multicast
        or parsed.is_reserved
        or parsed.is_unspecified
    ):
        raise EgressDenied("destination resolved to a non-public address")
    return parsed


def _parts(url: str, policy: EgressPolicy) -> Tuple[SplitResult, str, int]:
    if not isinstance(url, str) or len(url) > 2048:
        raise EgressDenied("destination URL is invalid")
    try:
        parsed = urlsplit(url)
        hostname = (parsed.hostname or "").rstrip(".").lower()
        port = parsed.port
    except ValueError as exc:
        raise EgressDenied("destination URL is invalid") from exc
    if parsed.scheme.lower() not in policy.allowed_schemes:
        raise EgressDenied("destination scheme is not allowed")
    if not hostname or parsed.username is not None or parsed.password is not None:
        raise EgressDenied("destination URL contains forbidden authority data")
    if not _host_allowed(hostname, policy.allowed_hosts):
        raise EgressDenied("destination host is not allowlisted")
    if port is None:
        port = 443 if parsed.scheme.lower() == "https" else 80
    if not 1 <= port <= 65535:
        raise EgressDenied("destination port is invalid")
    if parsed.fragment:
        raise EgressDenied("destination fragments are not sent to the server")
    return parsed, hostname, port


def validate_destination(
    url: str,
    policy: EgressPolicy,
    resolver: Optional[Resolver] = None,
) -> ResolvedDestination:
    parsed, hostname, port = _parts(url, policy)
    resolve = resolver or _default_resolver
    try:
        records = resolve(hostname, port)
    except Exception as exc:
        raise EgressDenied("destination DNS resolution failed") from exc
    addresses = []
    for record in records:
        if len(record) != 5:
            continue
        family, _socktype, _protocol, _canonname, sockaddr = record
        if family not in (socket.AF_INET, socket.AF_INET6):
            continue
        if not sockaddr:
            continue
        _public_ip(sockaddr[0])
        addresses.append((family, sockaddr))
    if not addresses:
        raise EgressDenied("destination has no permitted public address")
    request_target = parsed.path or "/"
    if parsed.query:
        request_target += "?" + parsed.query
    return ResolvedDestination(
        url=url,
        scheme=parsed.scheme.lower(),
        hostname=hostname,
        port=port,
        request_target=request_target,
        addresses=tuple(addresses),
    )


def validate_redirect(
    current_url: str,
    location: str,
    policy: EgressPolicy,
    resolver: Optional[Resolver] = None,
) -> ResolvedDestination:
    if not policy.allow_redirects:
        raise EgressDenied("redirects are disabled by egress policy")
    if not isinstance(location, str) or len(location) > 2048:
        raise EgressDenied("redirect location is invalid")
    return validate_destination(urljoin(current_url, location), policy, resolver=resolver)


class EgressBroker:
    """Send bounded JSON requests using the exact addresses validated above."""

    def __init__(self, policy: EgressPolicy, resolver: Optional[Resolver] = None):
        self.policy = policy
        self.resolver = resolver

    def post_json(self, url: str, payload: dict, idempotency_key: str) -> EgressResponse:
        if not idempotency_key or len(idempotency_key) > 256:
            raise EgressDenied("idempotency key is required")
        body = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        if len(body) > self.policy.max_payload_bytes:
            raise EgressDenied("outbound payload exceeds policy limit")
        deadline = time.monotonic() + self.policy.total_timeout_sec
        destination = validate_destination(url, self.policy, resolver=self.resolver)
        sock = self._connect(destination, deadline=deadline)
        try:
            sock.settimeout(_remaining_timeout(deadline))
            host_header = destination.hostname
            if destination.port not in (80, 443):
                host_header = f"{host_header}:{destination.port}"
            request = (
                f"POST {destination.request_target} HTTP/1.1\r\n"
                f"Host: {host_header}\r\n"
                "Content-Type: application/json\r\n"
                f"Content-Length: {len(body)}\r\n"
                f"Idempotency-Key: {idempotency_key}\r\n"
                "Connection: close\r\n\r\n"
            ).encode("ascii") + body
            sock.sendall(request)
            sock.settimeout(_remaining_timeout(deadline))
            response = http.client.HTTPResponse(sock)
            response.begin()
            if response.status in {301, 302, 303, 307, 308}:
                raise EgressDenied("redirect response is not followed")
            content_length = response.getheader("Content-Length")
            if content_length is not None:
                try:
                    if int(content_length) > self.policy.max_response_bytes:
                        raise EgressRequestFailed("outbound response exceeds policy limit")
                except ValueError as exc:
                    raise EgressRequestFailed("outbound response length is invalid") from exc
            response_body = self._read_response_body(
                response,
                sock,
                deadline,
            )
            if len(response_body) > self.policy.max_response_bytes:
                raise EgressRequestFailed("outbound response exceeds policy limit")
            if response.status >= 400:
                raise EgressRequestFailed(f"outbound response status {response.status}")
            return EgressResponse(
                status_code=response.status,
                headers=tuple(
                    (key.lower(), value)
                    for key, value in response.getheaders()
                ),
                body=response_body,
            )
        finally:
            sock.close()

    def _read_response_body(self, response, sock, deadline: float) -> bytes:
        chunks = []
        total = 0
        remaining = self.policy.max_response_bytes + 1
        while remaining > 0:
            sock.settimeout(_remaining_timeout(deadline))
            chunk = response.read(min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > self.policy.max_response_bytes:
                raise EgressRequestFailed("outbound response exceeds policy limit")
            remaining -= len(chunk)
        return b"".join(chunks)

    def _connect(self, destination: ResolvedDestination, deadline: float):
        last_error = None
        allowed_addresses = {sockaddr[0] for _family, sockaddr in destination.addresses}
        for family, sockaddr in destination.addresses:
            sock = socket.socket(family, socket.SOCK_STREAM)
            try:
                sock.settimeout(
                    min(self.policy.connect_timeout_sec, _remaining_timeout(deadline))
                )
                sock.connect(sockaddr)
                peer = sock.getpeername()
                peer_address = peer[0] if isinstance(peer, tuple) and peer else ""
                _public_ip(peer_address)
                if peer_address not in allowed_addresses:
                    raise EgressDenied("connected peer was not in the validated address set")
                if destination.scheme == "https":
                    context = _secure_tls_context()
                    sock.settimeout(_remaining_timeout(deadline))
                    sock = context.wrap_socket(
                        sock,
                        server_hostname=destination.hostname,
                    )
                return sock
            except EgressDenied:
                try:
                    sock.close()
                except Exception:
                    pass
                raise
            except EgressRequestFailed:
                try:
                    sock.close()
                except Exception:
                    pass
                raise
            except Exception as exc:
                last_error = exc
                try:
                    sock.close()
                except Exception:
                    pass
        raise EgressRequestFailed("unable to connect to permitted destination") from last_error
