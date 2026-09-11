# Vendored subset of Meta PurpleLlama's CybersecurityBenchmarks

This directory is a **trimmed copy** of the `CybersecurityBenchmarks/`
component of Meta's [PurpleLlama](https://github.com/meta-llama/PurpleLlama)
project (the CyberSecEval suite), used here only for its `benchmark/run.py`
harness, which this repo's `scripts/*.sh` invoke as
`python -m CybersecurityBenchmarks.benchmark.run --benchmark=instruct ...`
to query an LLM with a constructed prompt and record its response.

Licensed under the MIT License — see `LICENSE` in this directory (unchanged
from upstream).

## What was removed from the upstream copy

To keep this repository small and focused, the following were deleted from
the vendored copy (none of them are read by `benchmark/run.py`'s `instruct`
path, which takes its prompts from `--prompt-path` and writes to
`--response-path`, both supplied by this repo's own `scripts/*.sh`):

- `.git/` — a nested git repository that had been checked in whole; never
  commit a nested `.git` directory, it silently breaks cloning and hides
  provenance. If you need the full upstream history, clone
  [meta-llama/PurpleLlama](https://github.com/meta-llama/PurpleLlama)
  directly.
- `website/` — the project's Docusaurus documentation site.
- `datasets/` — CyberSecEval's own seed datasets for every benchmark
  variant (autocomplete, autonomous_uplift, canary_exploit, frr, interpreter,
  mitre, prompt_injection, spear_phishing, `third-party.txt`). This repo
  supplies its own prompts (see `../dataset/`), so none of this was needed.
- `scripts/` — upstream's own lint/test runner scripts.
- `__pycache__/` — build artifacts.

Everything under `benchmark/` is kept unmodified (including benchmark
variants this repo doesn't call, such as `mitre_benchmark.py`) since
`benchmark/run.py` imports all of them at module load time; only the
`instruct` variant is ever invoked here.
