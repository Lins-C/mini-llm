# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
from __future__ import annotations

import asyncio
import os
import socket
from pathlib import Path

import uvicorn


def listener(family: socket.AddressFamily, address: str, port: int) -> socket.socket:
    sock = socket.socket(family, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if family == socket.AF_INET6:
        # Separate IPv4 and IPv6 sockets make the behavior consistent on macOS.
        sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
    sock.bind((address, port))
    sock.listen(2048)
    sock.setblocking(False)
    return sock


async def serve() -> None:
    root = Path.cwd()
    port = int(os.getenv("PUBLIC_PORT", "8443"))
    sockets = [
        listener(socket.AF_INET, "0.0.0.0", port),
        listener(socket.AF_INET6, "::", port),
    ]
    config = uvicorn.Config(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        ssl_keyfile=str(root / ".certs" / "server.key"),
        ssl_certfile=str(root / ".certs" / "server.crt"),
    )
    server = uvicorn.Server(config)
    try:
        await server.serve(sockets=sockets)
    finally:
        for sock in sockets:
            sock.close()


if __name__ == "__main__":
    asyncio.run(serve())
