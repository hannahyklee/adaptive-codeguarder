"""Model configuration for this project's own LLM calls (the adaptive judge,
and whatever backend defense_adaptive.py's --judge_model points at).

Kept separate from ../CodeGuarder/src/configs.py on purpose, and deliberately
named differently (not `configs.py`), so it can never collide with or shadow
CodeGuarder's own `configs` module if both directories end up on sys.path.
Fill in *this* file instead of touching the vendored copy.
"""

models_config = {
    # Fill in with a local Ollama model, e.g. after `ollama pull codellama:13b`.
    # Ollama exposes an OpenAI-compatible endpoint at this base_url; "key" can
    # be any non-empty string since Ollama doesn't check it.
    "judge-local": {
        "base_url": "http://localhost:11434/v1",
        "key": "ollama",
        "model_name": "qwen2.5-coder:7b",
    },
}
