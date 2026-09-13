# Adaptive Fallback for CodeGuarder

A small experiment built on top of [CodeGuarder](../CodeGuarder) (CCS'25,
["Give LLMs a Security Course: Securing Retrieval-Augmented Code Generation
via Knowledge Injection"](https://doi.org/10.1145/3719027.3765049)).

## The question

CodeGuarder's defense always keeps every retrieved example function verbatim
in the generation prompt and appends security-knowledge advisory text next
to it. The paper's own failure-case analysis (§7.6) shows the LLM sometimes
copies a bad pattern from the retrieved example even when the correct
warning sits right next to it.

**Can an adaptive fallback — keep the retrieved example only when an LLM
judge calls it safe relative to the retrieved security knowledge, and rely
on the security knowledge alone otherwise — recover most of the
Standard-scenario security-rate ceiling even under CodeGuarder's own
Poisoning I / Poisoning II attacks, instead of always keeping the
example?**

## How it fits together

This directory never modifies `../CodeGuarder` — it reuses it. Concretely:

- **`scripts/sample_toy_dataset.py`** reads `../CodeGuarder/dataset` (left
  untouched) and writes a small, reproducible, language-filtered slice into
  `dataset/toy/`: up to 100 instances per scenario (Standard / Poisoning I /
  Poisoning II), for C / Python / Java. It reuses CodeGuarder's own
  `Standard_Def.json` / `Poisoning_I_Def.json` / `Poisoning_II_Def.json` as
  the "Def" (always-keep-the-example) comparison arm, rather than
  regenerating them.
- **`src/adaptive_judge.py`** is the one new decision point: one LLM call
  per retrieved example, asking whether it's safe relative to the security
  knowledge already retrieved for that instance. Fails closed (unparseable
  response → treated as unsafe → dropped). Verdicts are cached on disk.
- **`src/defense_adaptive.py`** does the same sub-task retrieval and
  root-cause selection CodeGuarder's own `Defense_Standard.py` /
  `Defense_Poisoning_I.py` / `Defense_Poisoning_II.py` do — imported
  directly from `../CodeGuarder/src` rather than reimplemented — then builds
  the prompt from only the examples the judge kept.
  `../CodeGuarder/src/Defense_Standard.py`'s `construct_prompt()` itself is
  reused unmodified; only the list of examples handed to it changes.
- **`scripts/run_{standard,poisoning_i,poisoning_ii}_adaptive.sh`** build
  the adaptive prompts (this project's own `uv` environment), then query the
  model under test and score it with CodeGuarder's own CyberSecEval harness
  and insecure-code detector (`../CodeGuarder`'s own separate `uv`
  environment) for all three arms — Ori, Def, Adaptive.
- **`scripts/RQ_Adaptive.sh`** prints average SR per scenario/arm and a
  **recovery %**: how much of the Standard scenario's Def−Ori gap each arm
  (Def, Adaptive) recovers under each poisoning scenario. That number is the
  direct answer to the research question above.

## Setup

Two separate `uv` environments are involved (no conda needed):

1. `../CodeGuarder` needs its own environment:
   ```bash
   cd ../CodeGuarder && uv sync --python 3.10
   ```
   This uses `CodeGuarder/pyproject.toml`, a non-conda alternative to the
   original artifact's `environment.yml` (added so this whole project never
   requires installing conda) — same pinned package versions, minus a
   handful of Linux+CUDA-only packages (`nvidia-*`, `triton`) that aren't
   needed off Linux/GPU machines. The original artifact's own
   `environment.yml`/`scripts/init_env.sh` (conda-based) are left in place
   too, if you'd rather reproduce it exactly that way.
2. This project needs its own environment:
   ```bash
   ./scripts/init_env.sh
   ```

Then fill in a judge model in `src/judge_config.py` (a local Ollama model is
the default assumption — e.g. `ollama pull codellama:13b`, then set
`model_name` to that tag). This is unrelated to which model is under test:
the model actually being evaluated is passed as CLI args to the
`run_*_adaptive.sh` scripts, exactly the way `../CodeGuarder`'s own
`run_*.sh` scripts take `<MODEL_NAME> <MODEL_KEY> <BASE_URL>` (see
[`../CodeGuarder/CybersecurityBenchmarks/benchmark/llm.py`](../CodeGuarder/CybersecurityBenchmarks/benchmark/llm.py)'s
`create()`, which only ever wraps a generic OpenAI-compatible client — the
same mechanism the paper used to point at local Ollama models).

## Running it

```bash
# 1. Sample the toy dataset (only needs stdlib -- no environment required).
python3 scripts/sample_toy_dataset.py

# 2. Run all three arms for each scenario against your model under test.
#    <MODEL_KEY> can be any placeholder string for a local Ollama model.
./scripts/run_standard_adaptive.sh <MODEL_NAME> <MODEL_KEY> <BASE_URL>
./scripts/run_poisoning_i_adaptive.sh <MODEL_NAME> <MODEL_KEY> <BASE_URL>
./scripts/run_poisoning_ii_adaptive.sh <MODEL_NAME> <MODEL_KEY> <BASE_URL>

# 3. See the recovery-% answer.
./scripts/RQ_Adaptive.sh <MODEL_NAME>
```

Before spending real judge/model calls, `src/defense_adaptive.py --dry_run`
exercises the whole prompt-construction pipeline with a deterministic mock
judge (no network calls), to check the plumbing end-to-end first.

## A note on validity

The paper's own §7.8 validates its automated pipeline (root-cause
extraction, query decomposition) against manual review by three people. This
experiment's judge deserves the same scrutiny at its own toy scale — before
trusting a full run's numbers, spot-check ~20 entries from a result file's
`adaptive_judge_log` against the actual example code the judge saw, the same
way the paper did.

## Attribution

This directory's code is new. It depends on and reuses
[`../CodeGuarder`](../CodeGuarder) (see that directory for its own
provenance and licensing) and, through it, CodeShield and CyberSecEval (both
MIT-licensed, Meta) — see `../CodeGuarder/CodeShield/LICENSE` and
`../CodeGuarder/CybersecurityBenchmarks/LICENSE`.
