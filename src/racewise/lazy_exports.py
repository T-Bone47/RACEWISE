"""Lazy re-exports for package ``__init__`` modules (PEP 562).

Why
---
``racewise/data/__init__.py`` eagerly imported every adapter and the entire
historical ingestion stack. Importing *any* submodule - including
``racewise.data.fastf1_adapter`` - therefore executed the whole graph, dragging
in fastf1 + pandas (~1.7s warm, ~9s cold). That cost was paid on every API
cold start, CLI invocation and test collection.

How
---
Each export is declared as ``name -> "module.path"`` and resolved on first
attribute access. ``from racewise.data import FastF1Adapter`` still works
exactly as before; the difference is only *when* the module is imported.

This is purely an import-graph optimisation. It does not change any value,
schema, ordering or determinism of the analytical engine.
"""
from __future__ import annotations

import importlib
import threading
from typing import Any, Mapping, Sequence

__all__ = ["install_lazy_exports"]

_MISSING = object()


def install_lazy_exports(
    module_globals: Mapping[str, Any],
    exports: Mapping[str, str],
    all_names: Sequence[str] | None = None,
) -> None:
    """Install a PEP 562 ``__getattr__`` that lazily resolves ``exports``.

    Args:
        module_globals: the ``globals()`` of the calling ``__init__`` module.
        exports: mapping of exported attribute name -> source module path.
        all_names: names for ``__all__``; defaults to ``sorted(exports)``.
    """
    lock = threading.Lock()
    resolved: dict[str, Any] = {}

    names = tuple(all_names) if all_names is not None else tuple(sorted(exports))

    def __getattr__(name: str) -> Any:
        target = exports.get(name)
        if target is None:
            raise AttributeError(
                f"module {module_globals.get('__name__')!r} has no attribute {name!r}"
            )
        # Fast path: already resolved in this process.
        cached = resolved.get(name, _MISSING)
        if cached is not _MISSING:
            return cached
        with lock:
            cached = resolved.get(name, _MISSING)
            if cached is not _MISSING:
                return cached
            value = getattr(importlib.import_module(target), name)
            resolved[name] = value
            # Also bind into module globals so subsequent attribute access
            # bypasses this hook entirely.
            module_globals[name] = value
            return value

    def __dir__() -> list[str]:
        return sorted(set(module_globals) | set(names))

    module_globals["__getattr__"] = __getattr__
    module_globals["__dir__"] = __dir__
    module_globals["__all__"] = list(names)