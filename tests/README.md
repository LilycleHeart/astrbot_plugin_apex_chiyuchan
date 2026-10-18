# Offline RP regression tests

With the plugin's requirements installed, run from the repository root:

```sh
python -m unittest discover -s tests -v
```

These tests use temporary SQLite files and stub the AstrBot host and upstream
responses. They execute both real command/LLM handler bodies without calling an
API, LLM, live account, or launching a browser. HTML tests use the real template.
They do not execute the legacy network-dependent scripts under `scripts/`.

For command latency changes, run only the focused regressions from `tests/`:

```sh
python -m unittest -v test_latency test_rp_window.DatabaseTests.test_command_and_llm_share_window_and_persistence
```

These checks cover concurrent LFG refreshes and ordering in command/tool results,
browser context scale isolation and reuse, concurrent upstream requests, cached
predator changes, and usable Steam counts when chart downloads fail.
Windows Python also needs `tzdata` for the existing season timezone code.

For the direct public profile loader, run only its request-contract and browser
fallback checks from the repository root:

```sh
python -m unittest discover -s tests -p test_latency.py -k ProfileTests -v
```

The normal profile path uses `beautifulsoup4` from `requirements.txt` and does not
start a browser. Browser extraction remains available when the public bootstrap
changes or a direct request fails.

For inventory completeness changes, run the focused checks only:

```sh
python -m unittest discover -s tests -p test_latency.py -k inventory -v
```

They check modern level/prestige cards, encoded global/platform rank positions,
career tracker scope, shared browser fallback parsing, complete media collection,
and the five-image card display limit.

`[ChiyuTiming]` logs cover all 13 slash commands and their aliases. `ready` measures
handler entry to result preparation; `total` includes platform send completion,
and `delivery` is the time between those points. The platform acknowledgement
does not measure when the user's QQ client displays the message.

Coverage includes rolling cutoff, multiple gains/losses, more than 12 samples,
unchanged samples, expired gains, incomplete history, long gaps, the 6-hour
estimate boundary, UID/platform isolation, season resets, absent metadata,
local legacy timestamps, single-row/append-only migration and restart persistence,
missing-season estimates without backfill, intervening season changes,
simultaneous snapshots, concise labels, and command/LLM display parity.
