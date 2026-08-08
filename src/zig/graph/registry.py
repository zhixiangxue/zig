from __future__ import annotations

from ..exceptions import UnsupportedBackendError

from .base import AbstractGraphClient


class BackendRegistry:
    _clients: dict[str, type[AbstractGraphClient]] = {}

    @classmethod
    def register(cls, name: str, client_cls: type[AbstractGraphClient]) -> None:
        cls._clients[name] = client_cls

    @classmethod
    def get(cls, name: str) -> type[AbstractGraphClient]:
        try:
            return cls._clients[name]
        except KeyError as exc:
            raise UnsupportedBackendError(f"Unsupported graph backend: {name!r}") from exc
