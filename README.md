# adaptive-codeguarder

- [`CodeGuarder/`](CodeGuarder) — a vendored copy of the CCS'25 artifact for
  ["Give LLMs a Security Course: Securing Retrieval-Augmented Code
  Generation via Knowledge Injection"](https://doi.org/10.1145/3719027.3765049)
  (Lin, Wang, Qin, Chen, and Mao). Trimmed of unused bulk (see
  `CodeGuarder/CybersecurityBenchmarks/VENDORED.md`) and given an
  alternative `uv`-based environment (`CodeGuarder/pyproject.toml`, so
  installing conda is never required) but otherwise unmodified — same
  scripts, same behavior, same package versions as the original artifact
  (data and code originally published at
  https://zenodo.org/records/16957113). Its original conda-based
  `environment.yml`/`scripts/init_env.sh` are left in place for anyone who
  wants to reproduce it exactly as published.
- [`adaptive-fallback/`](adaptive-fallback) — a new experiment built on top
  of it, asking whether dropping a retrieved code example when an LLM judge
  flags it as unsafe (instead of CodeGuarder's always-keep-the-example
  behavior) recovers more of the security-rate ceiling under CodeGuarder's
  own poisoning attacks. See its own README for what it does and how to run
  it.

## License

Source: Lin, Bo et al., "Give LLMs a Security Course" (CCS '25) artifact, https://zenodo.org/records/16957113, DOI 10.5281/zenodo.16957113. Listed under Zenodo with a CC BY 4.0 license.
