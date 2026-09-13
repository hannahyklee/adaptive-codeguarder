#!/bin/bash
# Internal helper, not meant to be run directly: queries the model under
# test on a prompt file via CodeGuarder's own CyberSecEval harness
# (CybersecurityBenchmarks.benchmark.run), then scores the responses with
# CodeGuarder's own insecure-code detector (src/sec_eval.py). Both steps run
# unmodified, inside CodeGuarder's own uv environment (see CodeGuarder/pyproject.toml
# -- a non-conda alternative to environment.yml, added so this whole project
# never requires installing conda).
#
# Usage: _query_and_score.sh <CODEGUARDER_DIR> <PROMPT_PATH> <RESPONSE_PATH> <MODEL_NAME> <MODEL_KEY> <BASE_URL>
# Prints the sec_eval.py JSON result to stdout (last line), and also persists
# it to <RESPONSE_PATH sans .json>_scores.json -- codebleu's own data-flow
# matching has genuine run-to-run nondeterminism (observed: ~13% of items'
# CodeBLEU score drift slightly between identical re-runs, traced to Python's
# per-process hash randomization affecting its internal graph construction),
# so PYTHONHASHSEED=0 pins that away, and persisting the result means nothing
# downstream (scripts/RQ_Adaptive.sh, scripts/plot_results.py) needs to
# recompute -- and re-invoking sec_eval.py is otherwise the only way to get
# these numbers again, since the harness itself never saves them.
set -e

CODEGUARDER_DIR="$1"
PROMPT_PATH="$2"
RESPONSE_PATH="$3"
MODEL_NAME="$4"
MODEL_KEY="$5"
BASE_URL="$6"
SCORES_PATH="${RESPONSE_PATH%.json}_scores.json"

LLM_TEST_STRING="OPENAI::${MODEL_NAME}::${MODEL_KEY}::${BASE_URL}"

(
    cd "${CODEGUARDER_DIR}"
    uv run --python 3.10 python -m CybersecurityBenchmarks.benchmark.run \
        --benchmark=instruct \
        --prompt-path="${PROMPT_PATH}" \
        --response-path="${RESPONSE_PATH}" \
        --llm-under-test="${LLM_TEST_STRING}"
) >&2

(
    cd "${CODEGUARDER_DIR}"
    PYTHONHASHSEED=0 uv run --python 3.10 python src/sec_eval.py --result_path "${RESPONSE_PATH}" | tail -1
) | tee "${SCORES_PATH}"
