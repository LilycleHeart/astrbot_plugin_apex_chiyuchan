# Offline RP regression tests

With the plugin's requirements installed, run from the repository root:

```sh
python -m unittest discover -s tests -v
```

These tests use temporary SQLite files and stub the AstrBot host and upstream
responses. They execute both real command/LLM handler bodies without calling an
API, LLM, live account, or launching a browser. HTML tests use the real template.
They do not execute the legacy network-dependent scripts under `scripts/`.

Coverage includes rolling cutoff, multiple gains/losses, more than 12 samples,
unchanged samples, expired gains, incomplete history, long gaps, the 6-hour
estimate boundary, UID/platform isolation, season resets, absent metadata,
local legacy timestamps, migration/restart persistence, simultaneous snapshots,
and command/LLM display parity.
