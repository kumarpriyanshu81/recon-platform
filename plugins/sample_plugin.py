"""
Sample plugin — demonstrates the recon-platform plugin interface.

This file is safe to commit and serves as documentation-by-example.
Copy it to private_modules/ and customise for proprietary heuristics.

Hook reference
--------------
pre_enum(domain: str)
post_enum(domain: str, subdomains: list[str]) -> list[str] | None
pre_probe(hosts: list[str])
post_probe(results: list[HostResult]) -> list[HostResult] | None
post_filter(results: list[HostResult])
post_output(written_paths: dict[str, Path])
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from core.logger import get_logger

if TYPE_CHECKING:
    from core.probe import HostResult
    from plugins.loader import PluginRegistry

log = get_logger(__name__)

PLUGIN_NAME = "sample_plugin"
PLUGIN_VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# Hook implementations
# ---------------------------------------------------------------------------

def on_post_enum(domain: str, subdomains: list[str]) -> None:
    """
    Fired after subdomain enumeration completes.

    Example use-cases in a private plugin:
    - Filter out out-of-scope subdomains.
    - Append subdomains from a custom wordlist bruteforce.
    - Push the list to an internal asset inventory API.
    """
    log.debug(
        "[%s] post_enum hook: %d subdomains for %s",
        PLUGIN_NAME, len(subdomains), domain,
    )


def on_post_probe(results: list[HostResult]) -> None:
    """
    Fired after HTTP probing.

    Example use-cases in a private plugin:
    - Flag hosts running specific technology stacks.
    - Correlate results with a known-vulnerable version database.
    - Send a Slack/webhook notification for high-interest targets.
    """
    interesting = [r for r in results if r.status_code in (200, 301, 302)]
    log.debug(
        "[%s] post_probe hook: %d/%d hosts returned 2xx/3xx.",
        PLUGIN_NAME, len(interesting), len(results),
    )


def on_post_output(written_paths: dict[str, Path]) -> None:
    """
    Fired after all output files are written.

    Example use-cases in a private plugin:
    - Upload results to an S3 bucket.
    - Sync to a Notion/Confluence page.
    - Trigger a downstream pipeline step.
    """
    log.debug(
        "[%s] post_output hook: %d files written.",
        PLUGIN_NAME, len(written_paths),
    )


# ---------------------------------------------------------------------------
# Plugin entry point — REQUIRED
# ---------------------------------------------------------------------------

def register(registry: PluginRegistry) -> None:
    """
    Called by the plugin loader at startup.
    Attach hooks to the registry here.
    """
    registry.on("post_enum", on_post_enum)
    registry.on("post_probe", on_post_probe)
    registry.on("post_output", on_post_output)
    log.debug("Sample plugin registered (v%s).", PLUGIN_VERSION)
