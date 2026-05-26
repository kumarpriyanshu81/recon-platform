"""
Dynamic plugin loader — public and private plugin support.

============================================================
Public vs Private Plugin Model
============================================================

PUBLIC plugins  →  plugins/
    - Committed to version control
    - Generic, reusable, shareable
    - Must contain no proprietary methodology

PRIVATE plugins →  private_modules/
    - Excluded from version control (.gitignore)
    - Proprietary detection logic, custom scoring, internal workflows
    - Loaded at runtime exactly like public plugins — no config required
    - Drop any .py file into private_modules/ and it is picked up automatically

Both directories are scanned in order. Private plugins load after public
ones, so they can safely override or augment public behaviour.

============================================================
Plugin Contract
============================================================

Every plugin file must expose a top-level `register(registry)` function
that attaches hooks to the provided PluginRegistry.

    # my_plugin.py
    from plugins.loader import PluginRegistry

    def register(registry: PluginRegistry) -> None:
        registry.on("post_probe", _my_hook)

    def _my_hook(results):
        ...

============================================================
Supported Hook Events
============================================================

    pre_enum(domain: str)
    post_enum(domain: str, subdomains: list[str])
    pre_probe(hosts: list[str])
    post_probe(results: list[HostResult])
    post_filter(results: list[HostResult])
    post_output(written_paths: dict[str, Path])

Hooks are called in registration order. Return values are collected
but not threaded back into the pipeline — plugins mutate in place.
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
    Central event bus that plugins register hooks against.

    Plugins call `registry.on(event, fn)` inside their `register()` function.
    The orchestrator calls `registry.fire(event, *args)` at each pipeline stage.
    """

    VALID_EVENTS = frozenset({
        "pre_enum",
        "post_enum",
        "pre_probe",
        "post_probe",
        "post_filter",
        "post_output",
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
                f"Unknown event '{event}'. "
                f"Valid events: {sorted(self.VALID_EVENTS)}"
            )
        self._hooks[event].append(fn)
        log.debug("Hook registered: event=%s fn=%s", event, fn.__qualname__)

    # ------------------------------------------------------------------
    # Orchestrator interface
    # ------------------------------------------------------------------

    def fire(self, event: str, *args: Any, **kwargs: Any) -> list[Any]:
        """
        Invoke all hooks registered for *event* in registration order.
        Exceptions in individual hooks are caught and logged so one
        failing plugin never aborts the pipeline.
        """
        return_values = []
        for fn in self._hooks.get(event, []):
            try:
                rv = fn(*args, **kwargs)
                return_values.append(rv)
            except Exception as exc:  # noqa: BLE001
                log.error(
                    "Hook %s raised an exception (event=%s): %s",
                    fn.__qualname__, event, exc,
                )
        return return_values

    @property
    def loaded_plugins(self) -> list[str]:
        return list(self._loaded_plugins)


class PluginLoader:
    """
    Discovers and loads plugin modules from a directory.

    Any .py file whose name does not start with '_' and is not 'loader.py'
    is treated as a plugin candidate. The file is imported and its
    `register(registry)` function is called if present.

    Usage::

        registry = PluginRegistry()
        loader = PluginLoader(registry)
        loader.load_directory(settings.PLUGINS_DIR)          # public
        loader.load_directory(settings.PRIVATE_MODULES_DIR)  # private
    """

    def __init__(self, registry: PluginRegistry) -> None:
        self.registry = registry

    def load_directory(self, directory: Path) -> int:
        """
        Load all plugins found in *directory*.
        Returns the count of successfully registered plugins.
        Missing directories are silently skipped.
        """
        if not directory.exists():
            log.debug("Plugin directory not found, skipping: %s", directory)
            return 0

        loaded = 0
        for plugin_file in sorted(directory.glob("*.py")):
            if plugin_file.name.startswith("_") or plugin_file.name == "loader.py":
                continue
            if self._load_file(plugin_file):
                loaded += 1
        return loaded

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _load_file(self, path: Path) -> bool:
        """Import *path* as a module and call its register() function."""
        module_name = f"_plugin_{path.stem}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, path)
            if spec is None or spec.loader is None:
                log.warning("Could not create module spec for %s", path)
                return False

            module: ModuleType = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)  # type: ignore[attr-defined]

            if not (hasattr(module, "register") and callable(module.register)):
                log.warning(
                    "Plugin %s has no register() function — skipped.", path.name
                )
                return False

            module.register(self.registry)
            self.registry._loaded_plugins.append(path.name)
            log.info("Loaded plugin: %s", path.name)

        except Exception as exc:  # noqa: BLE001
            log.error("Failed to load plugin %s: %s", path.name, exc)
            return False

        return True
