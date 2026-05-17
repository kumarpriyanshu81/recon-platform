"""
Dynamic plugin loader.

Discovers and loads plugin modules from two locations:
  1. plugins/         — public plugins committed to the repository.
  2. private_modules/ — proprietary plugins excluded from version control.

Plugins must define a top-level `register(registry: PluginRegistry)` function
that attaches hooks to the provided registry.  This keeps the public loader
interface stable while allowing private plugins to hook into any pipeline stage.

Example plugin skeleton::

    # plugins/my_plugin.py
    from plugins.loader import PluginRegistry

    def register(registry: PluginRegistry) -> None:
        registry.on("post_probe", my_hook)

    def my_hook(results):
        ...
        return results
"""

from __future__ import annotations

import importlib.util
import sys
from collections import defaultdict
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

from core.logger import get_logger

log = get_logger(__name__)

HookFn = Callable[..., Any]


class PluginRegistry:
    """
    Central registry that plugins attach hooks to.

    Supported hook events
    ---------------------
    pre_enum        Called before subdomain enumeration.   args: (domain,)
    post_enum       Called after enumeration.              args: (domain, subdomains)
    pre_probe       Called before HTTP probing.            args: (hosts,)
    post_probe      Called after probing.                  args: (results,)
    post_filter     Called after categorisation.           args: (results,)
    post_output     Called after all files are written.    args: (written_paths,)
    """

    VALID_EVENTS = frozenset({
        "pre_enum", "post_enum",
        "pre_probe", "post_probe",
        "post_filter", "post_output",
    })

    def __init__(self) -> None:
        self._hooks: dict[str, list[HookFn]] = defaultdict(list)
        self._loaded_plugins: list[str] = []

    # ------------------------------------------------------------------
    # Plugin authoring interface
    # ------------------------------------------------------------------

    def on(self, event: str, fn: HookFn) -> None:
        """Register *fn* as a hook for *event*."""
        if event not in self.VALID_EVENTS:
            raise ValueError(
                f"Unknown event '{event}'. Valid events: {sorted(self.VALID_EVENTS)}"
            )
        self._hooks[event].append(fn)
        log.debug("Hook registered: event=%s fn=%s", event, fn.__qualname__)

    # ------------------------------------------------------------------
    # Orchestrator interface
    # ------------------------------------------------------------------

    def fire(self, event: str, *args: Any, **kwargs: Any) -> list[Any]:
        """
        Invoke all hooks registered for *event*.
        Returns a list of return values from each hook.
        """
        results = []
        for fn in self._hooks.get(event, []):
            try:
                rv = fn(*args, **kwargs)
                results.append(rv)
            except Exception as exc:  # noqa: BLE001
                log.error("Hook %s raised an error: %s", fn.__qualname__, exc)
        return results

    @property
    def loaded_plugins(self) -> list[str]:
        return list(self._loaded_plugins)


class PluginLoader:
    """
    Discovers and loads plugin files from one or more directories.

    Each Python file (except __init__.py and loader.py) is imported and
    its `register(registry)` function is called if present.
    """

    def __init__(self, registry: PluginRegistry) -> None:
        self.registry = registry

    def load_directory(self, directory: Path) -> int:
        """
        Load all plugins from *directory*.
        Returns the number of successfully loaded plugins.
        """
        if not directory.exists():
            log.debug("Plugin directory does not exist, skipping: %s", directory)
            return 0

        loaded = 0
        for plugin_file in sorted(directory.glob("*.py")):
            if plugin_file.name.startswith("_") or plugin_file.name == "loader.py":
                continue
            if self._load_file(plugin_file):
                loaded += 1
        return loaded

    def _load_file(self, path: Path) -> bool:
        module_name = f"_plugin_{path.stem}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, path)
            if spec is None or spec.loader is None:
                log.warning("Could not create module spec for %s", path)
                return False

            module: ModuleType = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)  # type: ignore[attr-defined]

            if hasattr(module, "register") and callable(module.register):
                module.register(self.registry)
                self.registry._loaded_plugins.append(path.name)
                log.info("Loaded plugin: %s", path.name)
            else:
                log.warning(
                    "Plugin %s has no register() function — skipped.", path.name
                )
                return False

        except Exception as exc:  # noqa: BLE001
            log.error("Failed to load plugin %s: %s", path.name, exc)
            return False

        return True
