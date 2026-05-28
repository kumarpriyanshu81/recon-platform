"""
recon-platform — modular reconnaissance orchestration framework.

Pipeline stages:
  [ENUM]   Subdomain enumeration via subfinder
  [PROBE]  HTTP probing via httpx-toolkit (chunked, with retry pass)
  [FILTER] Categorisation + priority scoring
  [OUTPUT] Structured file output + JSON report
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
import time
from pathlib import Path

from config import settings
from core.filters import ResultFilter
from core.logger import configure_root_logger, get_logger
from core.output import OutputWriter
from core.probe import HTTPProber
from core.subdomains import SubdomainEnumerator
from core.utils import ensure_dir, sanitise_domain
from plugins.loader import PluginLoader, PluginRegistry

BANNER = """
  +-------------------------------------------------+
  |   R E C O N - P L A T F O R M                  |
  |   Reconnaissance Orchestration Framework        |
  +-------------------------------------------------+
"""

_STATE_PREFIX = ".state_"


# ---------------------------------------------------------------------------
# Resumable scan state
# ---------------------------------------------------------------------------

def _state_path(domain: str, output_dir: Path) -> Path:
    return output_dir / f"{_STATE_PREFIX}{domain}.json"


def _save_state(domain: str, subdomains: list[str], output_dir: Path) -> None:
    """Persist subdomain list so a scan can be resumed after interruption."""
    path = _state_path(domain, output_dir)
    path.write_text(
        json.dumps({"domain": domain, "subdomains": subdomains}, indent=2),
        encoding="utf-8",
    )
    get_logger(__name__).debug("[ENUM] State saved -> %s", path)


def _load_state(domain: str, output_dir: Path) -> list[str] | None:
    """Load a previously saved subdomain list. Returns None if absent or corrupt."""
    path = _state_path(domain, output_dir)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        subdomains = data.get("subdomains")
        if not isinstance(subdomains, list):
            raise ValueError("'subdomains' key missing or not a list")
        return subdomains
    except (json.JSONDecodeError, ValueError) as exc:
        get_logger(__name__).warning(
            "[ENUM] State file corrupt (%s) — running full enumeration.", exc
        )
        return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="recon-platform",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=textwrap.dedent("""\
            Modular reconnaissance orchestration framework.

            Pipeline:
              [ENUM] subfinder -> [PROBE] httpx-toolkit -> [FILTER] categorise -> [OUTPUT] files
        """),
        epilog=textwrap.dedent("""\
            Examples:
              python main.py -d example.com
              python main.py -d example.com --output-dir ./runs/2024-05-01
              python main.py -d example.com --resume
              python main.py -d example.com --subdomains-file subs.txt
              python main.py -d example.com --chunk-size 250 --httpx-args "-t 100"
        """),
    )

    # Required
    parser.add_argument(
        "-d", "--domain",
        required=True,
        metavar="DOMAIN",
        help="Target domain (e.g. example.com)",
    )

    # Output
    parser.add_argument(
        "--output-dir",
        metavar="DIR",
        type=Path,
        default=None,
        help="Directory for output files (default: output/)",
    )

    # Pipeline control
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Reload subdomains from last saved state, skip re-enumeration",
    )
    parser.add_argument(
        "--skip-enum",
        action="store_true",
        help="Skip subfinder (requires --subdomains-file)",
    )
    parser.add_argument(
        "--subdomains-file",
        metavar="FILE",
        type=Path,
        default=None,
        help="Load subdomains from a file instead of running subfinder",
    )
    parser.add_argument(
        "--skip-probe",
        action="store_true",
        help="Enumeration only — skip HTTP probing",
    )
    parser.add_argument(
        "--no-plugins",
        action="store_true",
        help="Disable all plugin loading",
    )

    # Enumeration
    parser.add_argument(
        "--enum-timeout",
        metavar="SEC",
        type=int,
        default=None,
        help=(
            f"subfinder wall-clock timeout in seconds "
            f"(default: {settings.SUBFINDER_TIMEOUT}). "
            f"On timeout, partial results collected before the cutoff are "
            f"preserved and the pipeline continues."
        ),
    )

    # Probing
    parser.add_argument(
        "--chunk-size",
        metavar="N",
        type=int,
        default=None,
        help=f"Hosts per httpx batch (default: {settings.HTTPX_CHUNK_SIZE})",
    )

    # Tool pass-through
    parser.add_argument(
        "--subfinder-args",
        metavar="ARGS",
        default="",
        help="Extra arguments forwarded verbatim to subfinder",
    )
    parser.add_argument(
        "--httpx-args",
        metavar="ARGS",
        default="",
        help="Extra arguments forwarded verbatim to httpx-toolkit",
    )

    # Verbosity
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable DEBUG logging",
    )

    return parser


# ---------------------------------------------------------------------------
# Plugin bootstrap
# ---------------------------------------------------------------------------

def _load_plugins(registry: PluginRegistry) -> None:
    loader   = PluginLoader(registry)
    public   = loader.load_directory(settings.PLUGINS_DIR)
    private  = loader.load_directory(settings.PRIVATE_MODULES_DIR)
    get_logger(__name__).info(
        "Plugins: %d public, %d private loaded.", public, private
    )


# ---------------------------------------------------------------------------
# Subdomain file loader
# ---------------------------------------------------------------------------

def _load_subdomains_from_file(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"Subdomains file not found: {path}")
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


# ---------------------------------------------------------------------------
# Console summary
# ---------------------------------------------------------------------------

def _print_summary(
    domain: str,
    subdomains: list,
    results: list,
    written: dict,
    elapsed: float,
) -> None:
    live_rate = (len(results) / len(subdomains) * 100) if subdomains else 0.0
    minutes, seconds = divmod(int(elapsed), 60)
    duration = f"{minutes}m {seconds}s" if minutes else f"{seconds}s"

    high    = sum(1 for r in results if r.score == settings.SCORE_HIGH)
    medium  = sum(1 for r in results if r.score == settings.SCORE_MEDIUM)
    low     = sum(1 for r in results if r.score == settings.SCORE_LOW)
    logins  = sum(1 for r in results if r.is_login)
    admins  = sum(1 for r in results if r.is_admin)
    apis    = sum(1 for r in results if r.is_api)
    staging = sum(1 for r in results if r.is_staging)

    sep = "-" * 56
    print(f"\n{sep}")
    print(f"  SCAN SUMMARY  {domain}")
    print(sep)
    print(f"  Duration              : {duration}")
    print(f"  Subdomains discovered : {len(subdomains)}")
    print(f"  Live hosts            : {len(results)}  ({live_rate:.1f}%)")
    print(f"  Login pages           : {logins}")
    print(f"  Admin panels          : {admins}")
    print(f"  API endpoints         : {apis}")
    print(f"  Staging environments  : {staging}")
    if high or medium or low:
        print(sep)
        print(f"  High priority findings   : {high}")
        print(f"  Medium priority findings : {medium}")
        print(f"  Low priority findings    : {low}")
    print(sep)
    for key, label in (
        ("high_priority",   "high_priority"),
        ("medium_priority", "medium_priority"),
        ("low_priority",    "low_priority"),
        ("results_json",    "report (json)"),
    ):
        if key in written:
            print(f"  {label:<18} -> {written[key]}")
    print(f"{sep}\n")


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def run(args: argparse.Namespace) -> int:
    log        = get_logger(__name__)
    start_time = time.monotonic()
    domain     = sanitise_domain(args.domain)
    output_dir = ensure_dir(args.output_dir or settings.OUTPUT_DIR)

    # --- Plugins ---
    registry = PluginRegistry()
    if not args.no_plugins:
        _load_plugins(registry)

    # --- [ENUM] Subdomain enumeration ---
    subdomains: list[str] = []
    registry.fire("pre_enum", domain)

    if args.resume:
        saved = _load_state(domain, output_dir)
        if saved:
            subdomains = saved
            log.info("[ENUM] Resumed: %d subdomains from saved state.", len(subdomains))
        else:
            log.warning("[ENUM] No saved state for '%s' — running full enumeration.", domain)

    if not subdomains:
        if args.subdomains_file:
            log.info("[ENUM] Loading from file: %s", args.subdomains_file)
            try:
                subdomains = _load_subdomains_from_file(args.subdomains_file)
            except FileNotFoundError as exc:
                log.error("[ENUM] %s", exc)
                return 1
        elif not args.skip_enum:
            extra        = args.subfinder_args.split() if args.subfinder_args else []
            enum_timeout = args.enum_timeout or settings.SUBFINDER_TIMEOUT
            subdomains   = SubdomainEnumerator(
                domain, timeout=enum_timeout, extra_args=extra
            ).run()
        else:
            log.warning("[ENUM] --skip-enum set without --subdomains-file.")

    registry.fire("post_enum", domain, subdomains)

    if not subdomains:
        log.warning("[ENUM] No subdomains found — probe stage will be skipped.")
    else:
        _save_state(domain, subdomains, output_dir)

    # --- [PROBE] HTTP probing ---
    results: list = []

    if not args.skip_probe and subdomains:
        registry.fire("pre_probe", subdomains)

        chunk_size  = args.chunk_size or settings.HTTPX_CHUNK_SIZE
        extra_httpx = args.httpx_args.split() if args.httpx_args else []

        prober  = HTTPProber(subdomains, chunk_size=chunk_size, extra_args=extra_httpx)
        results = prober.run()

        registry.fire("post_probe", results)
    elif args.skip_probe:
        log.info("[PROBE] Skipped (--skip-probe).")

    # --- [FILTER] Categorisation + scoring ---
    if results:
        log.info("[FILTER] Classifying %d hosts ...", len(results))
        ResultFilter().apply(results)
        registry.fire("post_filter", results)
    else:
        log.info("[FILTER] No results to classify.")

    # --- [OUTPUT] Write files ---
    elapsed = time.monotonic() - start_time
    writer  = OutputWriter(domain, output_dir=output_dir)
    written = writer.write_all(subdomains, results, duration_seconds=elapsed)

    registry.fire("post_output", written)

    _print_summary(domain, subdomains, results, written, elapsed)
    return 0


def main() -> None:
    parser = build_arg_parser()
    args   = parser.parse_args()

    configure_root_logger("DEBUG" if args.verbose else settings.LOG_LEVEL)
    print(BANNER)
    sys.exit(run(args))


if __name__ == "__main__":
    main()
