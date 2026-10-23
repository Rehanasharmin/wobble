# Wobble benchmarks

`bench.py` measures the latency a phone user actually feels: a **cold process**
for every command (`python -m wobble <command>` or the generated launcher),
including interpreter startup and imports. It can benchmark one checkout or two
side by side.

## Quick start

```bash
python3 benchmarks/bench.py                       # current tree
python3 benchmarks/bench.py --iterations 15 --json
python3 benchmarks/bench.py --cold-cache          # first-run doctor cost
python3 benchmarks/bench.py --compare ~/wobble-main   # baseline vs current
python3 benchmarks/bench.py --compare ~/wobble-main --fail-under 1.25
```

`--compare` needs a second checkout (a `git worktree` is ideal):

```bash
git worktree add /tmp/wobble-baseline <older-commit>
python3 benchmarks/bench.py --compare /tmp/wobble-baseline --iterations 15
```

## What is measured

| Group | Commands |
|:---|:---|
| Trivial fast paths | `wob --version`, `wob --help` |
| Introspection | `wob schema` |
| Self-health | `wob self status`, `wob self status --json` |
| Doctor | `wob doctor --quick`, `wob doctor --json`, `wob doctor --json --no-cache` |
| Installed runtime (launcher) | `self status`, `self status --deep`, `self verify`, `doctor --json` |

Installed-mode commands run through a launcher generated in a throwaway prefix,
so the benchmark exercises the same entry point as a real installation, without
touching your own `~/.local`.

## Method

* Every sample is a fresh interpreter; startup time is part of the result.
* `--warmup` runs are discarded, then `--iterations` samples are recorded.
* Reported value is the **median**; the JSON output includes `min`, `mean`,
  `p95`, `max`, and `stdev`.
* `--cold-cache` clears `~/.wobble/cache` before every run (warm-up included), so
  the measurement reflects "first doctor on a new device".
* Default (warm) mode lets the probe cache settle first. That is the realistic
  repeat-run cost and the main 1.3.0 optimization.
* Commands a baseline checkout does not support (unknown flags) are shown as
  `-` instead of aborting the run.
* `--fail-under FACTOR` turns the tool into a regression gate: it exits `1` if
  any command is slower than the baseline by more than `FACTOR` (for example
  `1.25` for a 25% budget).

## Files

* `bench.py` — the harness (standard library only).
* `RESULTS.md` — recorded results for the 1.3.0 self-diagnostics work, with
  hardware and Python versions.
