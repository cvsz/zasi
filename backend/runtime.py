"""Authoritative production launcher with atomic network-port ownership.

The launcher reserves the configured listen socket before Uvicorn starts and
hands that exact socket to the server. This makes duplicate runtime ownership a
fail-closed startup error instead of relying on a second control plane to notice
the conflict after initialization.
"""

from __future__ import annotations

import errno
import socket
from typing import Final

import uvicorn

from src.control_plane.config import Settings


DEFAULT_BACKLOG: Final[int] = 2048


class RuntimeOwnershipError(RuntimeError):
    """Raised when the authoritative runtime cannot own its configured socket."""


def _address_family(host: str) -> socket.AddressFamily:
    """Resolve the configured host to one deterministic stream-socket family."""
    try:
        infos = socket.getaddrinfo(
            host,
            None,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
    except socket.gaierror as exc:
        raise RuntimeOwnershipError(f"cannot resolve runtime host {host!r}") from exc

    for family, socktype, protocol, _canonname, _sockaddr in infos:
        if socktype == socket.SOCK_STREAM and protocol in {0, socket.IPPROTO_TCP}:
            if family in {socket.AF_INET, socket.AF_INET6}:
                return family
    raise RuntimeOwnershipError(f"runtime host {host!r} has no TCP address")


def bind_runtime_socket(host: str, port: int, *, backlog: int = DEFAULT_BACKLOG) -> socket.socket:
    """Atomically reserve and listen on the authoritative runtime endpoint."""
    family = _address_family(host)
    listener = socket.socket(family, socket.SOCK_STREAM)
    try:
        if family == socket.AF_INET6 and host == "::":
            # Match the conventional public-bind behavior while keeping a single
            # owned listener. Platforms without dual-stack support remain IPv6-only.
            try:
                listener.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
            except OSError:
                pass
        listener.bind((host, port))
        listener.listen(backlog)
        listener.setblocking(False)
        return listener
    except OSError as exc:
        listener.close()
        if exc.errno == errno.EADDRINUSE:
            raise RuntimeOwnershipError(
                f"runtime endpoint {host}:{port} is already owned; refusing duplicate control plane"
            ) from exc
        raise RuntimeOwnershipError(
            f"cannot own runtime endpoint {host}:{port}: {exc.strerror or exc}"
        ) from exc


def serve(settings: Settings | None = None) -> None:
    """Run the authoritative ASGI app on the exact socket reserved above."""
    effective = settings or Settings.from_mapping()
    listener = bind_runtime_socket(effective.host, effective.port)
    try:
        config = uvicorn.Config(
            "backend.app:create_app",
            factory=True,
            host=effective.host,
            port=effective.port,
            log_level="info",
        )
        server = uvicorn.Server(config)
        server.run(sockets=[listener])
    finally:
        listener.close()


def main() -> int:
    try:
        serve()
    except RuntimeOwnershipError as exc:
        print(f"ZASI runtime ownership error: {exc}")
        return 78
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
