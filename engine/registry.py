"""
engine/registry.py
Strategy discovery and registration.

Two ways a strategy joins the engine:

  1. Decorator   — apply @register to a BaseStrategy subclass.
  2. Auto-import — call discover() to import every module in the strategies/
                   package; any @register'd class inside is collected.

The registry stores classes, not instances, so the host app controls when and
with what parameters strategies are built.
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
from typing import Type

from engine.strategy import BaseStrategy

logger = logging.getLogger(__name__)

# name -> strategy class
_REGISTRY: dict[str, Type[BaseStrategy]] = {}


def register(cls: Type[BaseStrategy]) -> Type[BaseStrategy]:
    """Class decorator that adds a strategy to the global registry."""
    if not (isinstance(cls, type) and issubclass(cls, BaseStrategy)):
        raise TypeError(f"@register expects a BaseStrategy subclass, got {cls!r}")
    key = cls.name or cls.__name__
    if key in _REGISTRY and _REGISTRY[key] is not cls:
        raise ValueError(f"Duplicate strategy name {key!r} "
                         f"({_REGISTRY[key].__module__} vs {cls.__module__})")
    _REGISTRY[key] = cls
    logger.debug("Registered strategy %s", key)
    return cls


def get_registry() -> dict[str, Type[BaseStrategy]]:
    """Return a copy of the current name -> class map."""
    return dict(_REGISTRY)


def clear() -> None:
    """Drop all registrations (mainly for tests)."""
    _REGISTRY.clear()


def discover(package: str = "strategies") -> dict[str, Type[BaseStrategy]]:
    """
    Import every module under `package` so that decorators run and populate
    the registry. Returns the registry afterwards.

    A strategy author just drops a new file into strategies/ — no wiring,
    no edits to the engine. This is the whole plug-in mechanism.
    """
    try:
        pkg = importlib.import_module(package)
    except ModuleNotFoundError:
        logger.warning("Strategy package %r not found — nothing to discover.", package)
        return get_registry()

    for mod in pkgutil.iter_modules(pkg.__path__):
        if mod.name.startswith("_"):
            continue  # skip private / helper modules
        full = f"{package}.{mod.name}"
        try:
            importlib.import_module(full)
        except Exception as exc:  # one bad strategy must not sink the rest
            logger.error("Failed to import strategy module %s: %s", full, exc)

    logger.info("Discovered %d strategy(ies): %s",
                len(_REGISTRY), ", ".join(sorted(_REGISTRY)) or "none")
    return get_registry()
