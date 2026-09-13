"""Plots SR / CodeBLEU / judge fallback-rate across the three arms (Ori, Def,
Adaptive) and whichever scenarios (standard / poisoning_i / poisoning_ii)
have been run so far.

Reads two kinds of on-disk artifacts:
  - results/toy_<scenario>_<arm>_<model>.json (from scripts/run_*_adaptive.sh)
    -- re-scored here via CodeGuarder's own (untouched) src/sec_eval.py,
    exactly like scripts/RQ_Adaptive.sh does, to get SR/CodeBLEU per language.
  - dataset/toy/<scenario>_adaptive.json (from src/defense_adaptive.py)
    -- read directly (no subprocess needed) for the judge's per-instance
    adaptive_kept_examples / adaptive_total_examples fields, to compute the
    fallback rate (share of instances where the judge dropped every
    retrieved example) per language.
    
Usage (from this project's root, after `uv sync`):
    uv run python scripts/plot_results.py --model qwen2.5-coder:7b
"""

import argparse
import json
import os
import statistics
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CODEGUARDER_DIR = PROJECT_ROOT.parent / "CodeGuarder"

SCENARIOS = ["standard", "poisoning_i", "poisoning_ii"]
ARMS = ["ori", "def", "adaptive"]
ARM_COLORS = {"ori": "#9e9e9e", "def": "#4c72b0", "adaptive": "#c44e52"}
ARM_LABELS = {"ori": "Ori", "def": "Def", "adaptive": "Adaptive"}


def sec_eval(result_path: Path):
    """Returns the per-language {sr, code_bleu, ...} dict for an already-
    generated response file. Prefers the *_scores.json saved by
    scripts/_query_and_score.sh at generation time; only falls back to
    calling CodeGuarder's own sec_eval.py (in its own uv environment) if
    that cache is missing, since codebleu has genuine run-to-run
    nondeterminism (see scripts/_query_and_score.sh's comment) -- recomputing
    would silently give different numbers than what generation actually
    produced, and wastes the (slow) codebleu computation again.
    """
    scores_path = result_path.with_name(result_path.stem + "_scores.json")
    if scores_path.exists():
        return json.loads(scores_path.read_text())

    print(f"  (no cached {scores_path.name}; scoring now with PYTHONHASHSEED=0)", file=sys.stderr)
    env = {**os.environ, "PYTHONHASHSEED": "0"}
    proc = subprocess.run(
        ["uv", "run", "--python", "3.10", "python", "src/sec_eval.py", "--result_path", str(result_path)],
        cwd=str(CODEGUARDER_DIR),
        capture_output=True,
        text=True,
        env=env,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"sec_eval.py failed on {result_path}:\n{proc.stderr}")
    last_line = proc.stdout.strip().splitlines()[-1]
    result = json.loads(last_line)
    scores_path.write_text(json.dumps(result))
    return result


def collect_sr_codebleu(model: str):
    """Returns {scenario: {arm: {language: {"pass_rate":..., "code_bleu":...}}}},
    only for (scenario, arm) pairs whose result file actually exists.
    """
    data = defaultdict(dict)
    for scenario in SCENARIOS:
        for arm in ARMS:
            result_path = PROJECT_ROOT / "results" / f"toy_{scenario}_{arm}_{model}.json"
            if not result_path.exists():
                continue
            print(f"Scoring {scenario}/{arm}...", file=sys.stderr)
            data[scenario][arm] = sec_eval(result_path)
    return data


def collect_codebleu_stdev(model: str, scenarios_present):
    """Returns {scenario: {arm: {language: stdev}}} of the per-item
    code_bleu_score values, read from the *_filled.json companion file
    sec_eval.py always writes (the aggregate sec_eval() returns is only the
    per-language mean -- this recovers the spread behind that mean, e.g. to
    plot as error bars). Items missing a code_bleu_score (codebleu raised
    internally, rare) are skipped rather than treated as 0.
    """
    data = defaultdict(dict)
    for scenario in scenarios_present:
        for arm in ARMS:
            filled_path = PROJECT_ROOT / "results" / f"toy_{scenario}_{arm}_{model}_filled.json"
            if not filled_path.exists():
                continue
            items = json.loads(filled_path.read_text())
            by_lang = defaultdict(list)
            for item in items:
                score = item.get("code_bleu_score")
                if score is not None:
                    by_lang[item["language"]].append(score)
            data[scenario][arm] = {
                lang: statistics.stdev(scores) if len(scores) > 1 else 0.0
                for lang, scores in by_lang.items()
            }
    return data


def collect_sr_wilson_errors(sr_data):
    """Returns {scenario: {arm: {language: (lower_gap, upper_gap)}}} -- the
    distance from pass_rate down to the Wilson lower bound and up to the
    Wilson upper bound, in percentage points, ready to use as asymmetric
    matplotlib yerr.
    """
    data = defaultdict(dict)
    for scenario, arms in sr_data.items():
        for arm, langs in arms.items():
            by_lang = {}
            for lang, stats in langs.items():
                total = stats.get("total_count", 0)
                vulnerable = stats.get("vulnerable_suggestion_count", 0)
                successes = total - vulnerable
                lower, upper = wilson_interval(successes, total)
                pass_rate = stats.get("pass_rate", 0.0)
                by_lang[lang] = (max(0.0, pass_rate - lower * 100), max(0.0, upper * 100 - pass_rate))
            data[scenario][arm] = by_lang
    return data


def collect_judge_fallback_rates(scenarios_present):
    """Returns {scenario: {language: {"instances":n, "fell_back":n}}} by
    reading the adaptive prompt-construction output directly (no subprocess
    needed -- these fields are written by src/defense_adaptive.py itself).
    """
    data = {}
    for scenario in scenarios_present:
        path = PROJECT_ROOT / "dataset" / "toy" / f"{scenario}_adaptive.json"
        if not path.exists():
            continue
        items = json.loads(path.read_text())
        by_lang = defaultdict(lambda: {"instances": 0, "fell_back": 0})
        for item in items:
            lang = item["language"]
            by_lang[lang]["instances"] += 1
            if item["adaptive_total_examples"] > 0 and item["adaptive_kept_examples"] == 0:
                by_lang[lang]["fell_back"] += 1
        data[scenario] = dict(by_lang)
    return data


def all_languages(sr_data):
    langs = set()
    for scenario in sr_data.values():
        for arm in scenario.values():
            langs.update(arm.keys())
    return sorted(langs)


def wilson_interval(successes: int, n: int, z: float = 1.96):
    """95% Wilson score interval for a binomial proportion, returned as
    (lower, upper) fractions in [0, 1]. The right choice for a rate like SR
    (each instance is a secure/insecure Bernoulli trial) -- unlike a raw
    stdev of the 0/1 outcomes (which is ~fixed by p(1-p) and barely differs
    across arms), this actually shrinks with sample size and widens near
    p=0 or p=1, so it reflects how much a given SR estimate could plausibly
    move with more instances.
    """
    if n == 0:
        return (0.0, 0.0)
    phat = successes / n
    denom = 1 + z * z / n
    center = (phat + z * z / (2 * n)) / denom
    margin = z * ((phat * (1 - phat) / n + z * z / (4 * n * n)) ** 0.5) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


def plot_metric_by_scenario(sr_data, metric_key, ylabel, title, out_path, err_data=None, err_label=""):
    """err_data, if given: {scenario: {arm: {language: stdev_or_(lower,upper)}}}.
    Each entry can be a single number (symmetric error bar) or a (lower_gap,
    upper_gap) tuple (asymmetric, e.g. from a Wilson interval) -- both are
    normalized into matplotlib's expected yerr shape.
    """
    scenarios_present = [s for s in SCENARIOS if s in sr_data]
    if not scenarios_present:
        print(f"No data to plot for {title}; skipping.", file=sys.stderr)
        return
    langs = all_languages(sr_data)

    fig, axes = plt.subplots(1, len(scenarios_present), figsize=(5 * len(scenarios_present), 4.5), squeeze=False)
    axes = axes[0]

    for ax, scenario in zip(axes, scenarios_present):
        x = range(len(langs))
        width = 0.25
        for i, arm in enumerate(ARMS):
            arm_data = sr_data[scenario].get(arm, {})
            values = [arm_data.get(lang, {}).get(metric_key, float("nan")) for lang in langs]
            offsets = [xi + (i - 1) * width for xi in x]
            yerr = None
            if err_data is not None:
                raw = [err_data.get(scenario, {}).get(arm, {}).get(lang, 0.0) for lang in langs]
                if raw and isinstance(raw[0], tuple):
                    yerr = [[e[0] for e in raw], [e[1] for e in raw]]
                else:
                    yerr = raw
            ax.bar(
                offsets, values, width=width, label=ARM_LABELS[arm], color=ARM_COLORS[arm],
                yerr=yerr, capsize=3, ecolor="black", error_kw={"alpha": 0.6, "linewidth": 1},
            )
        ax.set_xticks(list(x))
        ax.set_xticklabels(langs)
        ax.set_title(scenario)
        ax.set_ylabel(ylabel)
        ax.grid(axis="y", alpha=0.3)

    axes[0].legend()
    fig.suptitle(title + (f"  ({err_label})" if err_label else ""))
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"Wrote {out_path}")


def plot_fallback_rates(fallback_data, out_path):
    scenarios_present = [s for s in SCENARIOS if s in fallback_data]
    if not scenarios_present:
        print("No judge fallback data to plot; skipping.", file=sys.stderr)
        return
    langs = sorted({lang for s in fallback_data.values() for lang in s})

    fig, ax = plt.subplots(figsize=(6 + len(langs), 4.5))
    x = range(len(langs))
    width = 0.8 / len(scenarios_present)
    colors = plt.cm.Set2.colors

    for i, scenario in enumerate(scenarios_present):
        rates = []
        for lang in langs:
            stats = fallback_data[scenario].get(lang)
            rate = 100 * stats["fell_back"] / stats["instances"] if stats and stats["instances"] else float("nan")
            rates.append(rate)
        offsets = [xi + (i - (len(scenarios_present) - 1) / 2) * width for xi in x]
        ax.bar(offsets, rates, width=width, label=scenario, color=colors[i % len(colors)])

    ax.set_xticks(list(x))
    ax.set_xticklabels(langs)
    ax.set_ylabel("Fallback rate (%) -- judge dropped every retrieved example")
    ax.set_title("Judge fallback rate by language and scenario")
    ax.grid(axis="y", alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"Wrote {out_path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", required=True, help="MODEL_NAME used in results/toy_<scenario>_<arm>_<model>.json filenames")
    parser.add_argument("--out_dir", default="./plots", help="Where to write PNG plots")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    sr_data = collect_sr_codebleu(args.model)
    if not sr_data:
        print("No result files found for any scenario/arm -- nothing to plot.", file=sys.stderr)
        sys.exit(1)

    fallback_data = collect_judge_fallback_rates(list(sr_data.keys()))

    # Error bars (Wilson interval for SR, stdev for CodeBLEU) are implemented
    # above (collect_sr_wilson_errors, collect_codebleu_stdev) but left off
    # by default for now, while this is still a toy-scale (~25-40
    # instances/language) sample -- pass err_data=... / err_label=... back in
    # to plot_metric_by_scenario below once instance counts are large enough
    # that the bars are worth showing.
    plot_metric_by_scenario(sr_data, "pass_rate", "Security Rate (%)", f"Security Rate by arm and language ({args.model})", out_dir / "sr_by_arm_language.png")
    plot_metric_by_scenario(sr_data, "code_bleu", "CodeBLEU", f"CodeBLEU by arm and language ({args.model})", out_dir / "codebleu_by_arm_language.png")
    plot_fallback_rates(fallback_data, out_dir / "judge_fallback_rate.png")


if __name__ == "__main__":
    main()
