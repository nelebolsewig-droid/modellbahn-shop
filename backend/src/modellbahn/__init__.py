"""Modellbahn-Shop backend: a modular monolith (API process + outbox worker)."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("modellbahn")
except PackageNotFoundError:  # pragma: no cover - only when running from an uninstalled tree
    __version__ = "0.0.0"
