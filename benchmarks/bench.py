#!/usr/bin/env python3
"""Wobble performance benchmark.

Measures cold-process CLI latency (the metric a phone user actually feels) and
can compare two checkouts side by side, for example a branch against ``main``:

    python3 benchmarks/bench.py                          # current tree
    python3 benchmarks/bench.py --iterations 15 --json   # machine readable
    python3 benchmarks/bench.py --compare /tmp/wobble-main

Each command runs in a fresh interpreter so import and startup cost is included.
The ``installed *`` commands are measured through a generated launcher in a
throwaway prefix, which is how Wobble is used after ``sh install.sh``.

Design notes:
* ``--warm-cache`` (default) lets the probe cache settle before timing, which is
  what a second ``wob doctor`` on the same device looks like.
* ``--cold-cache`` clears ``~/.wobble/cache`` before every iteration so the
  benchmark also captures the first-run cost.
* Every measurement is a full process, so results are comparable across
  implementations that change their own internals.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _percentile(values, fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round(fraction * (len(ordered) - 1)))))
    return ordered[index]


def summarize(samples_ms) -> dict:
    """Return robust summary statistics for a list of millisecond samples."""
    samples = [float(value) for value in samples_ms]
    if not samples:
        return {"n": 0}
    return {
        "n": len(samples),
        "min": round(min(samples), 2),
        "median": round(statistics.median(samples), 2),
        "mean": round(statistics.fmean(samples), 2),
        "p95": round(_percentile(samples, 0.95), 2),
        "max": round(max(samples), 2),
        "stdev": round(statistics.pstdev(samples), 2) if len(samples) > 1 else 0.0,
    }


def run_once(cmd, env, cwd, timeout=180) -> float:
    started = time.perf_counter()
    result = subprocess.run(cmd, env=env, cwd=str(cwd), capture_output=True, text=True,
                            timeout=timeout)
    elapsed = (time.perf_counter() - started) * 1000.0
    if result.returncode not in (0, 1):
        raise RuntimeError(
            f"command failed with exit {result.returncode}: {' '.join(map(str, cmd))}\n"
            f"{result.stderr[-600:]}"
        )
    return elapsed


def measure_paired(items, iterations: int, warmup: int) -> dict:
    """Measure several implementations of the same command in an interleaved way.

    Running all baseline samples first and all current samples afterwards lets
    machine drift (thermal throttling, noisy neighbours) masquerade as a
    speed-up. Alternating the order on every iteration turns that drift into
    paired noise instead. ``items`` is a list of dicts with ``label``, ``cmd``,
    ``cwd``, ``env``, and an optional ``before`` callable.
    """
    samples = {item["label"]: [] for item in items}
    unsupported = {}

    def one(item):
        before = item.get("before")
        if before:
            before()
        return run_once(item["cmd"], item["env"], item["cwd"])

    for _ in range(warmup):
        for item in items:
            if item["label"] in unsupported:
                continue
            try:
                one(item)
            except RuntimeError as exc:
                unsupported[item["label"]] = str(exc).splitlines()[0][:160]

    for index in range(iterations):
        order = items if index % 2 == 0 else list(reversed(items))
        for item in order:
            label = item["label"]
            if label in unsupported:
                continue
            try:
                samples[label].append(one(item))
            except RuntimeError as exc:
                unsupported[label] = str(exc).splitlines()[0][:160]

    results = {}
    for item in items:
        label = item["label"]
        if label in unsupported:
            results[label] = {"n": 0, "unsupported": unsupported[label]}
        else:
            results[label] = summarize(samples[label])
    return results


# ---------------------------------------------------------------------------
# Environment / installations
# ---------------------------------------------------------------------------
def base_env() -> dict:
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.pop("WOBBLE_INSTALL_DIR", None)
    env.pop("WOBBLE_BIN_DIR", None)
    env.pop("WOBBLE_NO_CACHE", None)
    env["NO_COLOR"] = "1"
    env["TERM"] = "dumb"
    return env


class Target:
    """A checkout of Wobble, optionally installed into a throwaway prefix."""

    def __init__(self, tree: Path, label: str, cold_cache: bool = False):
        self.tree = Path(tree).resolve()
        self.label = label
        self.cold_cache = cold_cache
        self.tmp = Path(tempfile.mkdtemp(prefix=f"wobble_bench_{label}_"))
        self.home = self.tmp / "home"
        self.home.mkdir(parents=True)
        self.root = self.tmp / "root"
        self.bin = self.tmp / "bin"
        self.installed = False
        self.install_error = None

    # -- lifecycle ------------------------------------------------------
    def install(self) -> None:
        env = base_env()
        env["HOME"] = str(self.home)
        env.pop("WOBBLE_INSTALL_DIR", None)
        try:
            result = subprocess.run(
                [sys.executable, "-m", "wobble", "self", "install",
                 "--root", str(self.root), "--bin", str(self.bin),
                 "--no-path", "--no-completion"],
                env=env, cwd=str(self.tree), capture_output=True, text=True, timeout=180,
            )
            self.installed = result.returncode == 0 and (self.bin / "wob").is_file()
            if not self.installed:
                self.install_error = (result.stdout + result.stderr)[-400:]
        except Exception as exc:  # pragma: no cover - environment failure
            self.install_error = str(exc)

    def cleanup(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- commands -------------------------------------------------------
    def env(self) -> dict:
        env = base_env()
        env["HOME"] = str(self.home)
        if self.installed:
            env["WOBBLE_INSTALL_DIR"] = str(self.root)
            env["WOBBLE_BIN_DIR"] = str(self.bin)
            env["PATH"] = f"{self.bin}:{env.get('PATH', '')}"
        return env

    def python_cmd(self, *args) -> list:
        return [sys.executable, "-m", "wobble", *args]

    def launcher_cmd(self, *args) -> list:
        return [str(self.bin / "wob"), *args]

    def prepare_cache(self) -> None:
        """Warm (or clear) the probe cache so runs are comparable."""
        cache_dir = self.home / ".wobble" / "cache"
        shutil.rmtree(cache_dir, ignore_errors=True)
        if self.cold_cache:
            return
        env = self.env()
        subprocess.run(self.python_cmd("doctor", "--json"), env=env,
                       cwd=str(self.tree), capture_output=True, text=True, timeout=180)

    def before_iteration(self) -> None:
        if self.cold_cache:
            shutil.rmtree(self.home / ".wobble" / "cache", ignore_errors=True)

    def suite(self) -> list:
        items = [
            ("wob --version", self.python_cmd("--version"), self.tree),
            ("wob --help", self.python_cmd("--help"), self.tree),
            ("wob schema", self.python_cmd("schema"), self.tree),
            ("wob self status", self.python_cmd("self", "status"), self.tree),
            ("wob self status --json", self.python_cmd("--json", "self", "status"), self.tree),
            ("wob doctor --quick", self.python_cmd("doctor", "--quick"), self.tree),
            ("wob doctor --json", self.python_cmd("--json", "doctor"), self.tree),
            ("wob doctor --json --no-cache", self.python_cmd("--json", "doctor", "--no-cache"),
             self.tree),
            ("wob doctor --only wobble", self.python_cmd("doctor", "--only", "wobble"), self.tree),
        ]
        if self.installed:
            items.extend([
                ("installed: self status", self.launcher_cmd("self", "status"), self.tree),
                ("installed: self status --deep", self.launcher_cmd("self", "status", "--deep"),
                 self.tree),
                ("installed: self verify", self.launcher_cmd("self", "verify"), self.tree),
                ("installed: doctor --json", self.launcher_cmd("--json", "doctor"), self.tree),
            ])
        return items


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def render_table(results: dict, labels: list, baseline: str = None) -> str:
    """Render a fixed-width comparison table."""
    commands = list(results[labels[0]].keys())
    header = f"{'command':<34}" + "".join(f"{label:>14}" for label in labels)
    if baseline and len(labels) > 1:
        header += f"{'speedup':>12}"
    lines = [header, "-" * len(header)]
    for command in commands:
        row = f"{command:<34}"
        for label in labels:
            stats = results[label].get(command, {})
            if stats.get("median") is not None and not stats.get("unsupported"):
                row += f"{stats['median']:>13.1f}ms"
            else:
                row += f"{'-':>14}"
        if baseline and len(labels) > 1:
            base = results[baseline].get(command, {}).get("median")
            current = results[labels[-1]].get(command, {}).get("median")
            if base and current:
                speedup = base / current
                row += f"{speedup:>11.2f}x"
        lines.append(row)
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark Wobble CLI latency",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Design notes:")[0].strip(),
    )
    parser.add_argument("--iterations", type=int, default=8,
                        help="Measured runs per command (default 8)")
    parser.add_argument("--warmup", type=int, default=2,
                        help="Discarded warm-up runs per command (default 2)")
    parser.add_argument("--compare", metavar="DIR",
                        help="Second checkout to benchmark and compare against")
    parser.add_argument("--tree", default=str(REPO), help="Checkout to benchmark")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of a table")
    parser.add_argument("--cold-cache", action="store_true",
                        help="Clear the probe cache before every iteration")
    parser.add_argument("--no-install", action="store_true",
                        help="Skip installed-mode commands")
    parser.add_argument("--fail-under", type=float, default=None, metavar="FACTOR",
                        help="Exit 1 when the current tree is slower than --compare by this factor")
    args = parser.parse_args(argv)

    if args.tree and not (Path(args.tree) / "wobble" / "cli.py").is_file():
        parser.error(f"{args.tree} does not look like a Wobble checkout")

    targets = [Target(Path(args.tree), "current", cold_cache=args.cold_cache)]
    if args.compare:
        if not (Path(args.compare) / "wobble" / "cli.py").is_file():
            parser.error(f"{args.compare} does not look like a Wobble checkout")
        targets.insert(0, Target(Path(args.compare), "baseline", cold_cache=args.cold_cache))

    results = {}
    meta = {}
    try:
        for target in targets:
            if not args.no_install:
                target.install()
            target.prepare_cache()
            results[target.label] = {}

        suites = {target.label: target.suite() for target in targets}
        command_order = []
        for target in targets:
            for name, _cmd, _cwd in suites[target.label]:
                if name not in command_order:
                    command_order.append(name)

        for name in command_order:
            items = []
            for target in targets:
                entry = next((item for item in suites[target.label] if item[0] == name), None)
                if not entry:
                    continue
                _name, cmd, cwd = entry
                items.append({
                    "label": target.label,
                    "cmd": cmd,
                    "cwd": cwd,
                    "env": target.env(),
                    "before": target.before_iteration if target.cold_cache else None,
                })
            measured = measure_paired(items, args.iterations, args.warmup)
            for item in items:
                results[item["label"]][name] = measured[item["label"]]

        for target in targets:
            meta[target.label] = {
                "tree": str(target.tree),
                "installed": target.installed,
                "install_error": target.install_error,
                "python": platform.python_version(),
                "platform": platform.platform(),
                "iterations": args.iterations,
                "warmup": args.warmup,
                "cold_cache": args.cold_cache,
            }
    finally:
        for target in targets:
            target.cleanup()

    labels = [target.label for target in targets]
    if args.json:
        print(json.dumps({"results": results, "meta": meta}, indent=2))
    else:
        print()
        print(f"Wobble benchmark  |  python {platform.python_version()}  |  "
              f"{platform.machine()}  |  {args.iterations} runs, "
              f"{'cold' if args.cold_cache else 'warm'} probe cache")
        print()
        print(render_table(results, labels, baseline="baseline" if args.compare else None))
        print()
        print("Values are median cold-process wall time (lower is better).")
        print()

    if args.fail_under is not None and args.compare:
        baseline_results = results.get("baseline", {})
        current_results = results.get("current", {})
        regressions = []
        for command, stats in current_results.items():
            base = baseline_results.get(command, {}).get("median")
            if not base:
                continue
            if stats["median"] > base * args.fail_under:
                regressions.append((command, stats["median"], base))
        if regressions:
            print(f"Performance regression: {len(regressions)} command(s) slower than "
                  f"{args.fail_under:.2f}x the baseline:", file=sys.stderr)
            for command, current, base in regressions:
                print(f"  {command}: {current:.1f} ms vs {base:.1f} ms", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
