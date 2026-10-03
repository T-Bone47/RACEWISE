"""Lazy third-party module proxy.

Why this exists
---------------
Importing ``fastf1`` + ``pandas`` costs roughly 1.7-9 seconds depending on
disk warmth. The RACEWISE API only needs them when a request actually reads
telemetry, yet they were imported eagerly at module load, so the server could
not answer ``/api/health`` until every heavy scientific dependency had been
linked. That turned API cold start into the dominant startup cost.

``LazyModule`` behaves exactly like the real module for attribute access
(``pd.isna``, ``fastf1.get_session``, ...) but defers ``importlib.import_module``
until the first attribute is actually touched.

Determinism and epistemic integrity
-----------------------------------
This changes *when* a dependency is imported, never *what* it computes. The
same objects are produced, the same canonical schemas are produced, and the
same exceptions propagate. No analytical behaviour changes.
"""
from __future__ import annotations

import importlib
import threading
from types import ModuleType
from typing import Any

__all__ = ["LazyModule", "LazyInstance"]


class LazyModule:
    """A module proxy that imports the wrapped module on first attribute access.

    Thread-safe: the import happens under a lock exactly once, and the real
    module object is cached on the instance so subsequent lookups bypass the
    proxy entirely.
    """

    __slots__ = ("_name", "_module", "_lock")

    def __init__(self, name: str) -> None:
        # object.__setattr__ is not needed: __slots__ attributes are writable,
        # but we bypass __getattr__ recursion by writing directly.
        object.__setattr__(self, "_name", name)
        object.__setattr__(self, "_module", None)
        object.__setattr__(self, "_lock", threading.Lock())

    @property
    def _real(self) -> ModuleType:
        mod = object.__getattribute__(self, "_module")
        if mod is None:
            lock = object.__getattribute__(self, "_lock")
            with lock:
                mod = object.__getattribute__(self, "_module")
                if mod is None:
                    mod = importlib.import_module(object.__getattribute__(self, "_name"))
                    object.__setattr__(self, "_module", mod)
        return mod

    def __getattr__(self, item: str) -> Any:
        return getattr(self._real, item)

    def __repr__(self) -> str:
        mod = object.__getattribute__(self, "_module")
        state = "loaded" if mod is not None else "deferred"
        return f"<LazyModule {object.__getattribute__(self, '_name')!r} {state}>"

    def __bool__(self) -> bool:
        # A deferred module must not be falsy-by-accident; truthiness of the
        # real module is only meaningful once loaded.
        return True

    def __dir__(self) -> list[str]:
        return dir(self._real)


class LazyInstance:
    """Defers construction of a heavy object until first attribute access.

    Used for module-level singletons whose constructor pulls in expensive
    dependencies (e.g. ``FastF1Adapter(...)`` enables the FastF1 cache, which
    imports fastf1). The instance is created exactly once, under a lock, and
    cached, so it behaves as a normal singleton from the caller's perspective.
    """

    __slots__ = ("_factory", "_instance", "_lock")

    def __init__(self, factory: Any) -> None:
        object.__setattr__(self, "_factory", factory)
        object.__setattr__(self, "_instance", None)
        object.__setattr__(self, "_lock", threading.Lock())

    @property
    def _real(self) -> Any:
        inst = object.__getattribute__(self, "_instance")
        if inst is None:
            lock = object.__getattribute__(self, "_lock")
            with lock:
                inst = object.__getattribute__(self, "_instance")
                if inst is None:
                    inst = object.__getattribute__(self, "_factory")()
                    object.__setattr__(self, "_instance", inst)
        return inst

    def __getattr__(self, item: str) -> Any:
        return getattr(self._real, item)

    def __repr__(self) -> str:
        inst = object.__getattribute__(self, "_instance")
        state = "initialised" if inst is not None else "deferred"
        return f"<LazyInstance {state}>"