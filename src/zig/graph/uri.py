from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import unquote, urlparse

from ..exceptions import InvalidGraphURIError


@dataclass(frozen=True)
class ParsedGraphURI:
    backend: str
    host: str
    port: int | None
    graph: str
    username: str | None = None
    password: str | None = None


def parse_graph_uri(uri: str) -> ParsedGraphURI:
    parsed = urlparse(uri)
    if not parsed.scheme:
        raise InvalidGraphURIError("Graph URI must include a backend scheme, e.g. falkordb://localhost:6379/programs")
    if not parsed.hostname:
        raise InvalidGraphURIError("Graph URI must include a host")

    graph = parsed.path.lstrip("/")
    if not graph:
        raise InvalidGraphURIError("Graph URI must include a graph name path, e.g. /programs")
    if "/" in graph:
        raise InvalidGraphURIError("Graph URI path must contain exactly one graph name")

    return ParsedGraphURI(
        backend=parsed.scheme,
        host=parsed.hostname,
        port=parsed.port,
        graph=unquote(graph),
        username=unquote(parsed.username) if parsed.username else None,
        password=unquote(parsed.password) if parsed.password else None,
    )
