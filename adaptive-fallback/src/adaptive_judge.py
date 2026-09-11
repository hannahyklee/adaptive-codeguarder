"""LLM judge for the adaptive-fallback experiment.

Given a retrieved code example and the same security-knowledge entries
CodeGuarder already selected for a query, asks an LLM whether copying or
closely adapting that example would risk reintroducing one of the flagged
vulnerabilities. `defense_adaptive.py` uses the verdict to decide whether to
keep the example in the prompt (CodeGuarder's current always-keep behavior)
or drop it and rely on the security-knowledge text alone for that instance.

Caches verdicts on disk (keyed by a hash of the example + knowledge + model,
mirroring the `calculate_md5`-keyed caching already used in
../CodeGuarder/src/Defense_Standard.py) so re-running an experiment doesn't
re-spend API/compute budget on unchanged inputs.
"""

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List

from openai import OpenAI

from configs import models_config

CACHE_DIR = Path(__file__).resolve().parent.parent / "cache" / "judge"

PROMPT_TEMPLATE = """You are a secure-code reviewer. A code-generation assistant is about to be \
shown the {language} example function below as a reference for a task, \
alongside the security guidance listed after it.

Decide: would copying or closely adapting this example risk reintroducing \
one of the vulnerabilities described in the guidance? Judge the example on \
its own merits -- the guidance may describe issues unrelated to it, in \
which case the example is safe.

### Example function
```{language}
{example_code}
```

### Security guidance retrieved for this task
{knowledge_block}

Respond with exactly two lines and nothing else:
VERDICT: safe|unsafe
RATIONALE: <one sentence>
"""


@dataclass
class JudgeResult:
    verdict: str  # "safe" or "unsafe"
    rationale: str


def _cache_key(example_code: str, security_knowledge: List[str], language: str, model: str) -> str:
    payload = json.dumps(
        {"code": example_code, "knowledge": security_knowledge, "language": language, "model": model},
        sort_keys=True,
    )
    return hashlib.md5(payload.encode("utf-8")).hexdigest()


def _cache_path(key: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{key}.json"


def _parse_verdict(text: str) -> JudgeResult:
    # Fail closed: if the model's response doesn't parse, treat the example
    # as unsafe (drop it) rather than silently keeping a potentially bad one.
    verdict = "unsafe"
    rationale = text.strip()[:500] or "(unparseable judge response)"
    for line in text.splitlines():
        line = line.strip()
        if line.upper().startswith("VERDICT:"):
            value = line.split(":", 1)[1].strip().lower()
            if value.startswith("safe"):
                verdict = "safe"
            elif value.startswith("unsafe"):
                verdict = "unsafe"
        elif line.upper().startswith("RATIONALE:"):
            rationale = line.split(":", 1)[1].strip()
    return JudgeResult(verdict=verdict, rationale=rationale)


def judge_example(
    example_code: str,
    security_knowledge: List[str],
    language: str,
    model: str = "judge-local",
    use_cache: bool = True,
) -> JudgeResult:
    """Ask the judge model whether `example_code` is safe to keep as a
    reference example, given the retrieved `security_knowledge` (a list of
    the same JSON-stringified root-cause entries CodeGuarder injects into
    the generation prompt) for this instance.
    """
    key = _cache_key(example_code, security_knowledge, language, model)
    cache_file = _cache_path(key)
    if use_cache and cache_file.exists():
        return JudgeResult(**json.loads(cache_file.read_text(encoding="utf-8")))

    if model not in models_config:
        raise ValueError(
            f"Unknown judge model '{model}'; add an entry for it to src/configs.py's models_config."
        )
    model_info = models_config[model]
    model_name = model_info.get("model_name") or model
    if not model_name:
        raise ValueError(
            f"models_config['{model}'] has no model_name set -- fill in src/configs.py first."
        )

    client = OpenAI(api_key=model_info.get("key") or "not-needed", base_url=model_info["base_url"])
    knowledge_block = "\n---\n".join(security_knowledge) if security_knowledge else "(none retrieved)"
    prompt = PROMPT_TEMPLATE.format(language=language, example_code=example_code, knowledge_block=knowledge_block)

    response = client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
    )
    result = _parse_verdict(response.choices[0].message.content or "")

    if use_cache:
        cache_file.write_text(json.dumps(asdict(result)), encoding="utf-8")
    return result


def judge_example_dry_run(example_code: str, security_knowledge: List[str], language: str) -> JudgeResult:
    """Deterministic stand-in for `judge_example` that makes no network
    calls, for exercising the rest of the pipeline (defense_adaptive.py's
    prompt construction, logging, output shape) before a judge model is
    configured.
    """
    # Deterministic on content, not random, so re-running is reproducible.
    verdict = "unsafe" if int(hashlib.md5(example_code.encode("utf-8")).hexdigest(), 16) % 2 == 0 else "safe"
    return JudgeResult(verdict=verdict, rationale="dry_run: no real judge call was made")
