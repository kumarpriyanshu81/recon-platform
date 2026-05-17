"""
Shared utility helpers used across core modules and plugins.
"""

import shutil
import subprocess
from pathlib import Path
from typing import Optional

from core.logger import get_logger

log = get_logger(__name__)


def require_tool(binary: str) -> str:
    """
    Verify that *binary* is available on PATH.

    Returns the resolved absolute path on success.
    Raises FileNotFoundError with a helpful message on failure.
    """
    resolved = shutil.which(binary)
    if resolved is None:
        raise FileNotFoundError(
            f"Required tool '{binary}' was not found on PATH. "
            f"Install it and ensure it is executable."
        )
    return resolved


def run_command(
    cmd: list[str],
    *,
    capture: bool = True,
    timeout: Optional[int] = None,
    cwd: Optional[Path] = None,
    stdin_input: Optional[str] = None,
) -> subprocess.CompletedProcess:
    """
    Execute *cmd* as a subprocess with uniform error handling.

    Args:
        cmd:         Command + arguments list (never pass a raw string).
        capture:     Whether to capture stdout/stderr (default True).
        timeout:     Optional wall-clock timeout in seconds.
        cwd:         Working directory for the child process.
        stdin_input: Optional string piped to the process's stdin.

    Returns:
        CompletedProcess with .stdout / .stderr as decoded strings.

    Raises:
        subprocess.TimeoutExpired: if *timeout* is exceeded.
    """
    log.debug("Executing: %s", " ".join(cmd))
    return subprocess.run(
        cmd,
        input=stdin_input,
        capture_output=capture,
        text=True,
        timeout=timeout,
        cwd=cwd,
        check=False,  # callers decide how to handle non-zero exits
    )


def ensure_dir(path: Path) -> Path:
    """Create *path* (and parents) if it does not exist; return *path*."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def sanitise_domain(domain: str) -> str:
    """
    Strip common URL prefixes so callers can pass either a bare domain
    or a full URL without breaking tool invocations.
    """
    for prefix in ("https://", "http://", "//"):
        if domain.startswith(prefix):
            domain = domain[len(prefix):]
    return domain.rstrip("/").lower()


def deduplicate(items: list[str]) -> list[str]:
    """Return *items* with duplicates removed, order preserved."""
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
