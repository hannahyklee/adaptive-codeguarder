#!/bin/bash
# Runs all three arms (Ori / Def / Adaptive) for the Standard scenario on
# this project's toy dataset slice, using the model under test given on the
# command line, and writes
# results/toy_standard_{ori,def,adaptive}_<MODEL_NAME>.json.
#
# Usage: run_standard_adaptive.sh <MODEL_NAME> <MODEL_KEY> <BASE_URL>
# Optional env vars:
#   JUDGE_MODEL (default: judge-local, from src/judge_config.py)
#   DATASET_DIR (default: ./dataset/toy; e.g. ./dataset/test_5 for a quick smoke test)
set -e

SCENARIO="standard"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "${SCRIPT_DIR}")"
CODEGUARDER_DIR="$(cd "${PROJECT_ROOT}/../CodeGuarder" && pwd)"

command_exists () { command -v "$1" >/dev/null 2>&1; }
for cmd in jq uv; do
    if ! command_exists "$cmd"; then
        echo "'${cmd}' is not found; it's required to run this script."
        exit 1
    fi
done

if [ "$#" -ne 3 ]; then
    echo "Usage: $0 <MODEL_NAME> <MODEL_KEY> <BASE_URL>"
    exit 1
fi
MODEL_NAME="$1"
MODEL_KEY="$2"
BASE_URL="$3"
JUDGE_MODEL="${JUDGE_MODEL:-judge-local}"

DATASET_DIR="${DATASET_DIR:-${PROJECT_ROOT}/dataset/toy}"
RESULTS_DIR="${PROJECT_ROOT}/results"
mkdir -p "${RESULTS_DIR}"

echo "--- Step 1: Building adaptive-fallback prompts (this project's uv env) ---"
(
    cd "${PROJECT_ROOT}"
    uv run python src/defense_adaptive.py \
        --scenario "${SCENARIO}" \
        --dataset_dir "${DATASET_DIR}" \
        --judge_model "${JUDGE_MODEL}" \
        --output_path "${DATASET_DIR}/${SCENARIO}_adaptive.json"
)

echo ""
echo "--- Step 2: Querying + scoring all three arms (CodeGuarder's uv env) ---"

TEMP_FILE=$(mktemp)
for arm in ori def adaptive; do
    echo "  Arm: ${arm}"
    PROMPT_PATH="${DATASET_DIR}/${SCENARIO}_${arm}.json"
    RESPONSE_PATH="${RESULTS_DIR}/toy_${SCENARIO}_${arm}_${MODEL_NAME}.json"
    ARM_JSON=$("${SCRIPT_DIR}/_query_and_score.sh" "${CODEGUARDER_DIR}" "${PROMPT_PATH}" "${RESPONSE_PATH}" "${MODEL_NAME}" "${MODEL_KEY}" "${BASE_URL}")
    if ! echo "${ARM_JSON}" | jq -e . >/dev/null 2>&1; then
        echo "Error: arm '${arm}' did not produce valid JSON output: ${ARM_JSON}"
        exit 1
    fi
    echo "{\"arm\": \"${arm}\", \"result\": ${ARM_JSON}}" >> "${TEMP_FILE}"
done

echo ""
echo "--- Final Results (${SCENARIO}, model=${MODEL_NAME}) ---"
echo ""
printf "%-10s %-10s %-10s %-10s\n" "Arm" "Language" "SR" "CodeBLEU"
echo "---------------------------------------------"
while read -r line; do
    arm=$(echo "$line" | jq -r '.arm')
    for lang in $(echo "$line" | jq -r '.result | keys | .[]'); do
        sr=$(echo "$line" | jq -r ".result.${lang}.pass_rate")
        bleu=$(echo "$line" | jq -r ".result.${lang}.code_bleu")
        printf "%-10s %-10s %-10.2f %-10.2f\n" "$arm" "$lang" "$sr" "$bleu"
    done
done < "${TEMP_FILE}"
rm "${TEMP_FILE}"

echo ""
echo "Run scripts/RQ_Adaptive.sh ${MODEL_NAME} to compute the recovery-% summary across all three scenarios."
