"""Adaptive-fallback prompt builder: CodeGuarder's own defense
(../CodeGuarder/src/Defense_Standard.py, Defense_Poisoning_I.py,
Defense_Poisoning_II.py) always keeps every retrieved example function
verbatim in the prompt and appends security-knowledge advisory text next to
it. This script does the same sub-task retrieval and root-cause selection,
reusing CodeGuarder's own retrieval code unmodified, but adds one new
decision point: each retrieved example is first shown to an LLM judge
(adaptive_judge.judge_example) alongside the same security knowledge
CodeGuarder would inject, and is dropped from the prompt -- rather than kept
next to a warning -- when the judge calls it unsafe. `construct_prompt()`
itself (also reused, unmodified) never changes; only the list of examples
passed into it does.

The three scenarios (standard / poisoning_i / poisoning_ii) share the exact
same logic in CodeGuarder -- Defense_Standard.py, Defense_Poisoning_I.py and
Defense_Poisoning_II.py differ only in default file paths -- so this script
is intentionally a single generic implementation selected with --scenario,
rather than three near-duplicate files.

Usage (from this project's root, after `uv sync`):
    uv run python src/defense_adaptive.py --scenario standard \
        --judge_model judge-local
"""

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import List

from tqdm import tqdm

import adaptive_judge

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CODEGUARDER_SRC = REPO_ROOT / "CodeGuarder" / "src"
sys.path.insert(0, str(CODEGUARDER_SRC))

# Reused, unmodified, from CodeGuarder's own defense scripts. The three
# Defense_*.py files define identical copies of these helpers; Defense_Standard
# is picked as the one canonical source to import them from.
from Defense_Standard import (  # noqa: E402
    build_vector_database,
    construct_prompt,
    find_root_causes,
    load_local_model,
)
from utils import remove_duplicates_preserve_order  # noqa: E402
from langchain_community.vectorstores import FAISS  # noqa: E402

SCENARIOS = {
    "standard": dict(
        ori_file="standard_ori.json",
        instruction_file="standard_instruction.json",
        broken_file="standard_broken_instruct.json",
    ),
    "poisoning_i": dict(
        ori_file="poisoning_i_ori.json",
        instruction_file="poisoning_i_instruction.json",
        broken_file="poisoning_i_broken_instruct.json",
    ),
    "poisoning_ii": dict(
        ori_file="poisoning_ii_ori.json",
        instruction_file="poisoning_ii_instruction.json",
        broken_file="poisoning_ii_broken_instruct.json",
    ),
}


def load(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_prompt_to_queries(broken_instructions):
    mapping = {item["test_case_prompt"]: item["broken_instructions"] for item in broken_instructions}
    mapping.update(
        {item["test_case_prompt"].split("\n")[0]: item["broken_instructions"] for item in broken_instructions}
    )
    return mapping


def select_examples(
    similar_codes: List[str],
    final_root_causes: List[str],
    language: str,
    judge_model: str,
    dry_run: bool,
):
    """Judge each retrieved example against the same security knowledge
    CodeGuarder would inject; keep only the ones judged safe. Returns the
    filtered example list plus a log entry per example for auditability.
    """
    kept, log = [], []
    for code in similar_codes:
        if dry_run:
            result = adaptive_judge.judge_example_dry_run(code, final_root_causes, language)
        else:
            result = adaptive_judge.judge_example(code, final_root_causes, language, model=judge_model)
        log.append({"verdict": result.verdict, "rationale": result.rationale})
        if result.verdict == "safe":
            kept.append(code)
    return kept, log


def main(args):
    scenario = SCENARIOS[args.scenario]
    dataset_dir = Path(args.dataset_dir)

    root_causes = load(Path(args.root_cause_path))
    instructions = load(dataset_dir / scenario["instruction_file"])
    poisoned_instructions = load(dataset_dir / scenario["ori_file"])
    broken_instructions = load(dataset_dir / scenario["broken_file"])
    prompt_to_queries = build_prompt_to_queries(broken_instructions)

    # Index by prompt_id rather than relying on list position: the toy
    # dataset is a filtered subset, so (unlike CodeGuarder's own full-scale
    # files) row index no longer equals prompt_id.
    poisoned_by_id = {x["prompt_id"]: x for x in poisoned_instructions}

    _, embed_model = load_local_model(args.embed_model_path)
    vector_db_path = Path(args.vector_db_path)
    if vector_db_path.exists():
        print("Loading security-knowledge vector db from local cache...")
        vector_db = FAISS.load_local(str(vector_db_path), embed_model.encode, allow_dangerous_deserialization=True)
    else:
        vector_db = build_vector_database(root_causes, embed_model)
        vector_db_path.parent.mkdir(parents=True, exist_ok=True)
        vector_db.save_local(str(vector_db_path))

    new_items = []
    for cur_response in tqdm(instructions, desc=f"Building adaptive prompts ({args.scenario})"):
        prompt_id = cur_response["prompt_id"]
        if prompt_id not in poisoned_by_id:
            continue
        cur_inst = poisoned_by_id[prompt_id]
        assert cur_inst["line_text"] == cur_response["line_text"]

        ori_prompt = cur_inst["ori_prompt"]
        if ori_prompt not in prompt_to_queries:
            raise ValueError(f"No broken-instruction query found for prompt_id={prompt_id}")
        broken_queries = prompt_to_queries[ori_prompt]

        cur_sim_root_causes = []
        for cur_query_dict in broken_queries:
            sub_task_query = cur_query_dict["description"]
            similar_docs = find_root_causes(vector_db, sub_task_query, top_k=5)
            cur_sim_root_causes.append((sub_task_query, [doc.page_content for doc in similar_docs]))

        final_root_causes = []
        for i in range(args.root_cause_per_module):
            final_root_causes.extend([x[1][i] for x in cur_sim_root_causes])
        final_root_causes = remove_duplicates_preserve_order(final_root_causes)

        filtered_codes, judge_log = select_examples(
            cur_inst["similar_codes"], final_root_causes, cur_response["language"], args.judge_model, args.dry_run
        )

        new_item = deepcopy(cur_inst)
        new_item["test_case_prompt"] = construct_prompt(final_root_causes, ori_prompt.split("\n")[0], filtered_codes)
        new_item["adaptive_kept_examples"] = len(filtered_codes)
        new_item["adaptive_total_examples"] = len(cur_inst["similar_codes"])
        new_item["adaptive_judge_log"] = judge_log
        new_items.append(new_item)

    Path(args.output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output_path, "w", encoding="utf-8") as f:
        json.dump(new_items, f, indent=2)

    dropped_all = sum(1 for x in new_items if x["adaptive_kept_examples"] == 0 and x["adaptive_total_examples"] > 0)
    print(
        f"Wrote {len(new_items)} adaptive prompts to {args.output_path} "
        f"({dropped_all} instances fell back to security-knowledge-only, no example kept)"
    )


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scenario", required=True, choices=sorted(SCENARIOS), help="Which scenario's toy slice to build prompts for")
    parser.add_argument("--dataset_dir", default="./dataset/toy", help="Directory with this project's sampled toy dataset")
    parser.add_argument("--root_cause_path", default="../CodeGuarder/dataset/Root_Causes.json", help="Path to CodeGuarder's security knowledge base")
    parser.add_argument("--embed_model_path", default="jinaai/jina-embeddings-v3", help="Embedding model (matches CodeGuarder's)")
    parser.add_argument("--vector_db_path", default=None, help="Where to cache the FAISS index (default: ./embeddings/, separate from CodeGuarder's own cache)")
    parser.add_argument("--judge_model", default="judge-local", help="Key into src/configs.py's models_config")
    parser.add_argument("--root_cause_per_module", type=int, default=2, help="Root causes per sub-task (matches CodeGuarder's default)")
    parser.add_argument("--output_path", default=None, help="Where to write the constructed prompts (default: ./dataset/toy/<scenario>_adaptive.json)")
    parser.add_argument("--dry_run", action="store_true", help="Use a deterministic mock judge instead of calling a real model, to sanity-check the pipeline shape")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.vector_db_path is None:
        args.vector_db_path = f"./embeddings/kng_rc_{Path(args.embed_model_path).name}.faiss"
    if args.output_path is None:
        args.output_path = f"./dataset/toy/{args.scenario}_adaptive.json"
    main(args)
