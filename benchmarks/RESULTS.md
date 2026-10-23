# Benchmark results — Wobble 1.3.0 self-diagnostics

Recorded on 2026-10-23 while implementing the 1.3.0 health subsystem.

| | |
|:---|:---|
| Host | x86_64 Linux sandbox (container), Python 3.11.2 (CPython) |
| Baseline | `main` @ `0085706` (Wobble 1.2.0) via `git worktree` |
| Current | `arena/0854cb5f-wobble` (Wobble 1.3.0) |
| Runner | `python3 benchmarks/bench.py --compare /tmp/wobble-baseline --iterations 9 --warmup 1` (baseline and current runs interleaved) |
| Metric | median cold-process wall time, 15 samples (phone timings are higher; ratios are the point) |

## Warm probe cache (repeat run — the normal case)

| Command | 1.2.0 | 1.3.0 | Change |
|:---|---:|---:|---:|
| `wob --version` | 19.4 ms | **13.0 ms** | 1.49× faster |
| `wob --help` | 35.3 ms | **32.5 ms** | 1.09× |
| `wob schema` | 38.2 ms | 40.0 ms | parity |
| `wob self status` | 42.1 ms | **36.8 ms** | 1.14× faster, ~10× more checks |
| `wob self status --json` | 42.6 ms | **37.6 ms** | 1.13× faster |
| `wob doctor --quick` | 48.7 ms | 51.4 ms | parity (0.95×, more checks) |
| `wob doctor --json` | 121.8 ms | **58.0 ms** | **2.10× faster** |
| `wob doctor --json --no-cache` | — (flag missing) | 128.1 ms | first-run cost, opt-in |
| `wob doctor --only wobble` | — (flag missing) | 46.2 ms | new: installation-only check, no tool probes |
| `installed: self status` | 43.5 ms | **36.4 ms** | 1.19× faster |
| `installed: self status --deep` | — (flag missing) | 71.7 ms | new: hashes + import smoke test |
| `installed: self verify` | 49.4 ms | **40.3 ms** | 1.23× faster |
| `installed: doctor --json` | 130.9 ms | **61.6 ms** | **2.13× faster** |

## Cold probe cache (first run on a new device)

`--cold-cache --iterations 5`: the probe cache is deleted before every sample.

| Command | 1.2.0 | 1.3.0 | Change |
|:---|---:|---:|---:|
| `wob --version` | 22.7 ms | **13.8 ms** | 1.65× faster |
| `wob --help` | 40.1 ms | **32.4 ms** | 1.24× faster |
| `wob schema` | 38.5 ms | 39.8 ms | parity |
| `wob self status` | 43.6 ms | **37.9 ms** | 1.15× faster |
| `wob self status --json` | 40.9 ms | **38.4 ms** | 1.06× faster |
| `wob doctor --quick` | 46.9 ms | 53.8 ms | 0.87× (adds installation health checks) |
| `wob doctor --json` | 137.3 ms | 138.9 ms | parity on the very first run, 2.2× on every run after |
| `installed: self status` | 46.5 ms | **37.9 ms** | 1.23× faster |
| `installed: self verify` | 46.7 ms | 48.7 ms | parity (within run-to-run noise) |

## Micro-benchmarks

Measured in-process after imports, so these isolate the subsystems from
interpreter startup:

| Operation | Time |
|:---|---:|
| `selfcheck.inspect()` — source checkout | ~0.2 ms |
| `selfcheck.inspect()` — installed runtime (16 checks) | ~2.8–3.5 ms |
| `selfcheck.inspect(deep=True)` — 59 files + 7 module imports | ~28 ms |
| `installer.verify()` — 59 files, 508 KB (serial path) | ~9 ms |
| `doctor.inspect_environment(quick=True)` | ~0.9 ms |
| `doctor.inspect_environment()` with warm probe cache | ~1.7 ms |
| Android property lookup, 1.2.0 (4 × `getprop`) | 4 subprocesses |
| Android property lookup, 1.3.0 (batched + cached) | 1 subprocess |

## Why it got faster

* `concurrent.futures` (which drags in `logging`, ~6 ms) is imported only when a
  verification or probe actually needs a thread pool, and small trees now hash
  serially because a pool costs more than the reads.
* `typing`, `json`, `hashlib`, `socket`, `tempfile`, and `platform` moved off the
  startup path (`wob --version` no longer pays for any of them).
* Tool version probes are cached in `~/.wobble/cache/probes.json`, keyed by the
  executable's inode fingerprint, so a warm `wob doctor` performs no subprocess
  probes at all.
* Android properties are read from a single batched `getprop` table instead of
  four separate calls.
* Shell completion scripts are imported only when they are installed or printed.

## Interpreting the numbers

* The sandbox is noisy (±10% between runs). Treat differences under ~10% as
  parity. The harness interleaves baseline/current samples on every iteration
  precisely so machine drift cannot be mistaken for a speed-up; run at least 9–15
  samples and compare medians.
* The first `wob doctor` after an install equals the old cost by design: it
  probes for real and writes the cache. Everything after that is ~2× faster.
* `wob self status` is both faster **and** substantially larger in scope than
  1.2.0, which only checked for a manifest, an app directory, and a launcher.
