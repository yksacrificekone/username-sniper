"""CLI entry point: `python -m kxne_sniper check|snipe ...`"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from rich.console import Console

from .config import Config
from .engine import SniperEngine
from .notify import Notifier
from .ui import Dashboard

console = Console()


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="kxne-sniper",
        description="Kxne Sniper — multithreaded username availability sniper",
    )
    parser.add_argument("--config", default="config.json", help="config file (default: config.json)")
    parser.add_argument("--threads", type=int, default=0, help="override connection pool size")
    parser.add_argument("--proxies", default=None, help="override proxies file")
    sub = parser.add_subparsers(dest="mode", required=True)

    check = sub.add_parser("check", help="check a list of usernames")
    check.add_argument("--usernames", default="usernames.txt", help="file with one username per line")
    check.add_argument("--output", default="available.txt", help="where available usernames are written")

    snipe = sub.add_parser("snipe", help="snipe a single username")
    snipe.add_argument("username", help="username to snipe")
    snipe.add_argument("--interval", type=float, default=0.0,
                       help="poll interval in seconds (0 = use config.json)")

    return parser.parse_args(argv)


def load_names(path: str) -> list[str]:
    p = Path(path)
    if not p.exists():
        return []
    return [
        line.strip()
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


async def amain(args: argparse.Namespace) -> int:
    cfg = Config(args.config)
    if args.threads:
        cfg.data["network"]["connections"] = args.threads
    if args.proxies:
        cfg.data["network"]["proxy_file"] = args.proxies

    notifier = Notifier(cfg)

    def active_getter() -> int:
        return cfg.get("network", "connections", 200) - engine.sem._value if engine.sem else 0

    engine = None
    with Dashboard(active_getter=active_getter) as ui:
        engine = SniperEngine(cfg, ui, notifier)
        await engine.start()
        try:
            if args.mode == "check":
                names = load_names(args.usernames)
                if not names:
                    console.print(f"[red]No usernames found in {args.usernames}[/]")
                    return 1
                await engine.run_checker(names, args.output)
            else:
                interval = args.interval or float(cfg.get("sniper", "interval", 0.35))
                await engine.run_sniper(args.username, interval)
            await asyncio.sleep(1.2)  # let the final state render
        except KeyboardInterrupt:
            engine.stats.add_event("Aborted by user", "yellow")
            ui.refresh(engine.stats)
        finally:
            await engine.close()

    # summary after the live view closes
    s = engine.stats
    console.print(f"\n[bold cyan]KXNE SNIPER — summary[/]  "
                  f"[dim]({s.mode}, {int(s.elapsed())}s)[/]")
    console.print(f"  checks: [white]{s.total_checks:,}[/]  "
                  f"available: [green]{s.available:,}[/]  "
                  f"taken: [red]{s.taken:,}[/]  "
                  f"errors: {s.errors:,}  "
                  f"rate-limited: [yellow]{s.rate_limited:,}[/]  "
                  f"claims won: [bold green]{s.claims_success}[/]")
    return 0


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        return asyncio.run(amain(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
