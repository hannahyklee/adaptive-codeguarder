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
# Prints the sec_eval.py JSON result to stdout (last line).
set -e

CODEGUARDER_DIR="$1"
PROMPT_PATH="$2"
RESPONSE_PATH="$3"
MODEL_NAME="$4"
MODEL_KEY="$5"
BASE_URL="$6"

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
    uv run --python 3.10 python src/sec_eval.py --result_path "${RESPONSE_PATH}" | tail -1
)
