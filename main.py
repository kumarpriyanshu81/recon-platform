"""
recon-platform — modular reconnaissance orchestration framework.

Entry point.  Orchestrates the full pipeline:
  1.  Parse CLI arguments
  2.  Load plugins (public + private)
  3.  Enumerate subdomains
  4.  Probe live hosts
  5.  Categorise findings
  6.  Write output files
  7.  Fire post-output hooks & print summary
"""

from __future__ import annotations

import argparse
import sys
import textwrap
from pathlib import Path

from config import settings
from core.filters import ResultFilter
from core.logger import configure_root_logger, get_logger
from core.output import OutputWriter
from core.probe import HTTPProber
from core.subdomains import SubdomainEnumerator
from core.utils import sanitise_domain
from plugins.loader import PluginLoader, PluginRegistry

BANNER = """
  +-------------------------------------------------+
  |   R E C O N - P L A T F O R M                  |
  |   Reconnaissance Orchestration Framework        |
  +-------------------------------------------------+
"""


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="recon-platform",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=textwrap.dedent("""\
            Modular reconnaissance orchestration framework.

            Runs a full passive recon pipeline:
              subfinder -> httpx -> categorisation -> structured output
        """),
        epilog=textwrap.dedent("""\
            Examples:
              python main.py -d example.com
              python main.py -d example.com --output-dir ./runs/example
              python main.py -d example.com --skip-probe --verbose
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
        "--skip-enum",
        action="store_true",
        help="Skip subdomain enumeration (requires --subdomains-file)",
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
        help="Skip HTTP probing (only run enumeration)",
    )
    parser.add_argument(
        "--no-plugins",
        action="store_true",
        help="Disable plugin loading",
    )

    # Tool overrides
    parser.add_argument(
        "--subfinder-args",
        metavar="ARGS",
        default="",
        help="Additional arguments passed directly to subfinder",
    )
    parser.add_argument(
        "--httpx-args",
        metavar="ARGS",
        default="",
        help="Additional arguments passed directly to httpx",
    )

    # Logging
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable DEBUG logging",
    )

    return parser


def load_plugins(registry: PluginRegistry) -> None:
    loader = PluginLoader(registry)
    public_count = loader.load_directory(settings.PLUGINS_DIR)
    private_count = loader.load_directory(settings.PRIVATE_MODULES_DIR)
    log = get_logger(__name__)
    log.info(
        "Plugins loaded: %d public, %d private.",
        public_count, private_count,
    )


def load_subdomains_from_file(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"Subdomains file not found: {path}")
    lines = path.read_text(encoding="utf-8").splitlines()
    return [l.strip() for l in lines if l.strip()]


def print_summary(domain: str, subdomains: list, results: list, written: dict) -> None:
    log = get_logger(__name__)
    sep = "-" * 56
    print(f"\n{sep}")
    print(f"  SCAN SUMMARY  {domain}")
    print(sep)
    print(f"  Subdomains discovered : {len(subdomains)}")
    print(f"  Live hosts            : {len(results)}")

    login  = sum(1 for r in results if r.is_login)
    admin  = sum(1 for r in results if r.is_admin)
    api    = sum(1 for r in results if r.is_api)
    stag   = sum(1 for r in results if r.is_staging)

    print(f"  Login pages           : {login}")
    print(f"  Admin panels          : {admin}")
    print(f"  API endpoints         : {api}")
    print(f"  Staging environments  : {stag}")
    print(sep)
    print("  Output files:")
    for label, path in written.items():
        print(f"    {label:<18} -> {path}")
    print(f"{sep}\n")


def run(args: argparse.Namespace) -> int:
    log = get_logger(__name__)
    domain = sanitise_domain(args.domain)

    # ------------------------------------------------------------------
    # Plugin bootstrap
    # ------------------------------------------------------------------
    registry = PluginRegistry()
    if not args.no_plugins:
        load_plugins(registry)

    # ------------------------------------------------------------------
    # Subdomain enumeration
    # ------------------------------------------------------------------
    subdomains: list[str] = []

    registry.fire("pre_enum", domain)

    if args.subdomains_file:
        log.info("Loading subdomains from %s …", args.subdomains_file)
        try:
            subdomains = load_subdomains_from_file(args.subdomains_file)
        except FileNotFoundError as exc:
            log.error("%s", exc)
            return 1
    elif not args.skip_enum:
        extra = args.subfinder_args.split() if args.subfinder_args else []
        enumerator = SubdomainEnumerator(domain, extra_args=extra)
        subdomains = enumerator.run()
    else:
        log.warning("--skip-enum set without --subdomains-file; no hosts to probe.")

    registry.fire("post_enum", domain, subdomains)

    if not subdomains:
        log.warning("No subdomains found. The pipeline will continue with an empty list.")

    # ------------------------------------------------------------------
    # HTTP probing
    # ------------------------------------------------------------------
    results = []

    if not args.skip_probe and subdomains:
        registry.fire("pre_probe", subdomains)

        extra_httpx = args.httpx_args.split() if args.httpx_args else []
        prober = HTTPProber(subdomains, extra_args=extra_httpx)
        results = prober.run()

        registry.fire("post_probe", results)

    # ------------------------------------------------------------------
    # Categorisation
    # ------------------------------------------------------------------
    if results:
        rf = ResultFilter()
        rf.apply(results)
        registry.fire("post_filter", results)

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------
    writer = OutputWriter(domain, output_dir=args.output_dir)
    written = writer.write_all(subdomains, results)

    registry.fire("post_output", written)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print_summary(domain, subdomains, results, written)
    return 0


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    log_level = "DEBUG" if args.verbose else settings.LOG_LEVEL
    configure_root_logger(log_level)

    print(BANNER)

    sys.exit(run(args))


if __name__ == "__main__":
    main()
