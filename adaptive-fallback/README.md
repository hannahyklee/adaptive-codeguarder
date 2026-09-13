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

**Can filtering out retrieved examples only when they contradict the retrieved security rules improve CodeGuarder's ability to generate secure code?**

## Core files

- **`scripts/sample_toy_dataset.py`** — samples instances/scenario
  (Standard / Poisoning I / Poisoning II) from `../CodeGuarder/dataset` into
  `dataset/toy/`, for C / Python / Java. Reuses CodeGuarder's own
  `*_Def.json` files as the "Def" (always-keep-the-example) comparison arm.
- **`src/adaptive_judge.py`** — the judge: one LLM call per retrieved
  example, asking whether it's safe relative to the security knowledge for
  that instance. Fails closed. Verdicts cached on disk.
- **`src/defense_adaptive.py`** — builds the Adaptive-arm prompts: pulls the
  security knowledge straight out of the matching Def-arm prompt (so Def and
  Adaptive see identical knowledge), judges each retrieved example, and
  drops the ones the judge flags unsafe before calling `construct_prompt()`.
- **`scripts/run_{standard,poisoning_i,poisoning_ii}_adaptive.sh`** — builds
  the adaptive prompts, then queries the model under test and scores it with
  CodeGuarder's harness/detector, for all three arms (Ori, Def, Adaptive).
- **`scripts/RQ_Adaptive.sh`** — once all three scenarios have been run,
  prints average SR per scenario/arm plus **recovery %**.
- **`scripts/plot_results.py`** — SR / CodeBLEU / judge-fallback-rate plots
  across whichever scenarios have been run.

## Reproduce Results

```bash
# Setup (once)
cd ../CodeGuarder && uv sync --python 3.10
cd ../adaptive-fallback && ./scripts/init_env.sh
# Fill in a judge model in src/judge_config.py and a model-under-test in
# ../CodeGuarder/src/configs.py (both point at a local Ollama endpoint by default).

# Sample the toy dataset
uv run python scripts/sample_toy_dataset.py

# Run each scenario (<MODEL_KEY> can be any placeholder string for local Ollama)
./scripts/run_standard_adaptive.sh <MODEL_NAME> <MODEL_KEY> <BASE_URL>
./scripts/run_poisoning_i_adaptive.sh <MODEL_NAME> <MODEL_KEY> <BASE_URL>
./scripts/run_poisoning_ii_adaptive.sh <MODEL_NAME> <MODEL_KEY> <BASE_URL>

# Recovery-% summary (needs all three scenarios above) and plots
./scripts/RQ_Adaptive.sh <MODEL_NAME>
uv run python scripts/plot_results.py --model <MODEL_NAME>
```

`src/defense_adaptive.py --dry_run` exercises the prompt-construction
pipeline with a mock judge (no network calls) before spending real ones.
