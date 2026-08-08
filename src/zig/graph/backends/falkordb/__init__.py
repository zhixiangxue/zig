from __future__ import annotations

from .client import FalkorDBClient
from ...registry import BackendRegistry

BackendRegistry.register("falkordb", FalkorDBClient)

__all__ = ["FalkorDBClient"]
