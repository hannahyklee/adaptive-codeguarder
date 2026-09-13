#!/bin/bash
# Answers the research question: does the adaptive fallback recover most of
# the Standard-scenario security-rate ceiling even under poisoning, compared
# to CodeGuarder's always-keep-the-example Def arm?
#
# Reads the nine results/toy_<scenario>_<arm>_<MODEL_NAME>.json files
# (3 scenarios x {ori, def, adaptive}) produced by
# run_{standard,poisoning_i,poisoning_ii}_adaptive.sh, re-scores each with
# CodeGuarder's own (untouched) src/sec_eval.py, and prints:
#   1. Average SR per scenario/arm.
#   2. Recovery % = (arm_SR - Ori_SR) / (Standard_Def_SR - Standard_Ori_SR)
#      for the Def and Adaptive arms under each poisoning scenario -- how
#      much of the non-poisoned ceiling each arm recovers.
#
# Usage: RQ_Adaptive.sh <MODEL_NAME>
set -e

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

if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <MODEL_NAME>"
    exit 1
fi
MODEL_NAME="$1"

RESULTS_DIR="${PROJECT_ROOT}/results"
SCENARIOS="standard poisoning_i poisoning_ii"
ARMS="ori def adaptive"

RESULTS_JSON=$(mktemp)
AVG_TABLE=$(mktemp)
trap 'rm -f "${RESULTS_JSON}" "${AVG_TABLE}"' EXIT

for scenario in ${SCENARIOS}; do
    for arm in ${ARMS}; do
        RESPONSE_PATH="${RESULTS_DIR}/toy_${scenario}_${arm}_${MODEL_NAME}.json"
        SCORES_PATH="${RESPONSE_PATH%.json}_scores.json"
        if [ ! -f "${RESPONSE_PATH}" ]; then
            echo "Missing ${RESPONSE_PATH}."
            echo "Run scripts/run_${scenario}_adaptive.sh ${MODEL_NAME} <MODEL_KEY> <BASE_URL> first."
            exit 1
        fi
        # Reuse the scores saved by scripts/_query_and_score.sh at generation
        # time rather than recomputing: codebleu has genuine run-to-run
        # nondeterminism (see that script's comment), so re-scoring here would
        # silently give slightly different numbers than what was actually
        # produced and would waste the (slow) codebleu computation again.
        if [ -f "${SCORES_PATH}" ]; then
            ARM_JSON=$(cat "${SCORES_PATH}")
        else
            echo "No cached ${SCORES_PATH}; scoring now (fixing PYTHONHASHSEED for reproducibility)..." >&2
            ARM_JSON=$(cd "${CODEGUARDER_DIR}" && PYTHONHASHSEED=0 uv run --python 3.10 python src/sec_eval.py --result_path "${RESPONSE_PATH}" | tail -1)
            echo "${ARM_JSON}" > "${SCORES_PATH}"
        fi
        echo "{\"scenario\": \"${scenario}\", \"arm\": \"${arm}\", \"result\": ${ARM_JSON}}" >> "${RESULTS_JSON}"
    done
done

echo ""
echo "--- Average SR by scenario and arm (model=${MODEL_NAME}) ---"
printf "%-14s %-10s %-10s\n" "Scenario" "Arm" "Avg SR"
echo "----------------------------------------"
while read -r line; do
    scenario=$(echo "${line}" | jq -r '.scenario')
    arm=$(echo "${line}" | jq -r '.arm')
    avg_sr=$(echo "${line}" | jq -r '[.result[].pass_rate] | add / length')
    printf "%-14s %-10s %-10.2f\n" "${scenario}" "${arm}" "${avg_sr}"
    echo "${scenario} ${arm} ${avg_sr}" >> "${AVG_TABLE}"
done < "${RESULTS_JSON}"

STD_ORI=$(awk '$1=="standard" && $2=="ori" {print $3}' "${AVG_TABLE}")
STD_DEF=$(awk '$1=="standard" && $2=="def" {print $3}' "${AVG_TABLE}")
CEILING=$(awk -v def="${STD_DEF}" -v ori="${STD_ORI}" 'BEGIN{print def-ori}')

echo ""
echo "--- Recovery %  (share of the Standard Def-Ori ceiling of ${CEILING} SR points each arm recovers) ---"
printf "%-14s %-20s %-20s\n" "Scenario" "Def recovery" "Adaptive recovery"
echo "-------------------------------------------------------"
for scenario in poisoning_i poisoning_ii; do
    ORI=$(awk -v s="${scenario}" '$1==s && $2=="ori" {print $3}' "${AVG_TABLE}")
    DEF=$(awk -v s="${scenario}" '$1==s && $2=="def" {print $3}' "${AVG_TABLE}")
    ADAPTIVE=$(awk -v s="${scenario}" '$1==s && $2=="adaptive" {print $3}' "${AVG_TABLE}")
    DEF_RECOVERY=$(awk -v arm="${DEF}" -v ori="${ORI}" -v c="${CEILING}" 'BEGIN{ if (c==0) print "n/a"; else printf "%.2f", (arm-ori)/c*100 }')
    ADAPTIVE_RECOVERY=$(awk -v arm="${ADAPTIVE}" -v ori="${ORI}" -v c="${CEILING}" 'BEGIN{ if (c==0) print "n/a"; else printf "%.2f", (arm-ori)/c*100 }')
    printf "%-14s %-20s %-20s\n" "${scenario}" "${DEF_RECOVERY}%" "${ADAPTIVE_RECOVERY}%"
done

echo ""
echo "--- Script finished ---"
