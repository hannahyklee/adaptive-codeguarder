"""Build a small, reproducible toy slice of the CyberSecEval-derived
CodeGuarder dataset for the adaptive-fallback experiment.

`Instruction.json`, `Standard.json` / `Standard_Def.json`,
`Poisoning_I.json` / `Poisoning_I_Def.json`, and
`Poisoning_II.json` / `Poisoning_II_Def.json` are all keyed by the same
`prompt_id` (0..1915). This script:

1. Picks, per scenario, up to `--n_per_scenario` prompt_ids whose language is
   in `--languages`, sampled with a fixed seed so the toy set is
   reproducible.
2. Writes matching filtered slices of the instruction file, the "Ori"
   (baseline RACG, no security knowledge) file, and the "Def" (CodeGuarder,
   always-keep-the-example) file that ships with the original artifact —
   reusing the paper authors' own precomputed Def prompts as the comparison
   arm rather than rebuilding them.
3. Writes a matching slice of `Broken_instruct.json` (the sub-task
   decompositions), matched by `test_case_prompt` text rather than index,
   since that's how `Defense_*.py`'s `prompt_to_queries` lookup works.

`Root_Causes.json` (the security knowledge base) is left untouched — it's
retrieval-time knowledge, not a per-instance file, so there's nothing to
sample out of it.

Reads from ../CodeGuarder/dataset (left untouched) and writes into this
project's own ./dataset/toy, so the vendored CodeGuarder/ copy never needs
to be modified.

Usage (from this project's root):
    uv run python scripts/sample_toy_dataset.py \
        --dataset_dir ../CodeGuarder/dataset --out_dir ./dataset/toy \
        --languages c python java --n_per_scenario 100 --seed 42
"""

import argparse
import json
import random
from collections import Counter
from pathlib import Path

SCENARIOS = {
    "standard": ("Standard.json", "Standard_Def.json"),
    "poisoning_i": ("Poisoning_I.json", "Poisoning_I_Def.json"),
    "poisoning_ii": ("Poisoning_II.json", "Poisoning_II_Def.json"),
}


def load(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def dump(path: Path, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def index_by_prompt_id(items):
    # Standard.json / Standard_Def.json ship with no "prompt_id" field at
    # all (unlike Poisoning_I/II's files and Instruction.json); their row
    # order is verified to exactly match Instruction.json's prompt_id-sorted
    # order, so row index doubles as prompt_id in that case.
    return {item.get("prompt_id", idx): item for idx, item in enumerate(items)}


def sample_scenario(scenario, ori_name, def_name, dataset_dir, instruction_by_id,
                     broken, languages, n_per_scenario, seed):
    ori = load(dataset_dir / ori_name)
    deff = load(dataset_dir / def_name)
    ori_by_id = index_by_prompt_id(ori)
    def_by_id = index_by_prompt_id(deff)

    eligible = sorted(
        pid for pid, item in instruction_by_id.items()
        if item["language"] in languages and pid in ori_by_id and pid in def_by_id
    )
    rng = random.Random(f"{seed}-{scenario}")
    n = min(n_per_scenario, len(eligible))
    sample_ids = sorted(rng.sample(eligible, n))

    def subset(by_id):
        # Stamp prompt_id onto every sampled item (even for Standard.json /
        # Standard_Def.json, which don't carry the field natively) so
        # downstream consumers can always key off item["prompt_id"].
        items = []
        for pid in sample_ids:
            item = dict(by_id[pid])
            item["prompt_id"] = pid
            items.append(item)
        return items

    sample_prompts = {instruction_by_id[pid]["test_case_prompt"] for pid in sample_ids}
    broken_subset = [b for b in broken if b["test_case_prompt"] in sample_prompts]

    lang_counts = Counter(instruction_by_id[pid]["language"] for pid in sample_ids)
    print(f"[{scenario}] sampled {n}/{len(eligible)} eligible instances "
          f"-> {dict(lang_counts)}; {len(broken_subset)} broken_instruct entries matched")

    return {
        f"{scenario}_instruction.json": subset(instruction_by_id),
        f"{scenario}_ori.json": subset(ori_by_id),
        f"{scenario}_def.json": subset(def_by_id),
        f"{scenario}_broken_instruct.json": broken_subset,
    }


def main(dataset_dir: str, out_dir: str, languages, n_per_scenario: int, seed: int):
    dataset_dir = Path(dataset_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    instruction = load(dataset_dir / "Instruction.json")
    instruction_by_id = {x["prompt_id"]: x for x in instruction}
    broken = load(dataset_dir / "Broken_instruct.json")

    for scenario, (ori_name, def_name) in SCENARIOS.items():
        outputs = sample_scenario(
            scenario, ori_name, def_name, dataset_dir, instruction_by_id,
            broken, set(languages), n_per_scenario, seed,
        )
        for filename, data in outputs.items():
            dump(out_dir / filename, data)

    print(f"\nWrote toy dataset slices to {out_dir}/")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset_dir", default="../CodeGuarder/dataset", help="Directory containing the full (untouched) CodeGuarder dataset files")
    parser.add_argument("--out_dir", default="./dataset/toy", help="Where to write the sampled toy dataset")
    parser.add_argument("--languages", nargs="+", default=["c", "python", "java"], help="Languages to keep")
    parser.add_argument("--n_per_scenario", type=int, default=100, help="Max instances to sample per scenario")
    parser.add_argument("--seed", type=int, default=42, help="Sampling seed, for reproducibility")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    main(args.dataset_dir, args.out_dir, args.languages, args.n_per_scenario, args.seed)
