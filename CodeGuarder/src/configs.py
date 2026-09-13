CHUNK_SIZE = 100
CHUNK_OVERLAP = 0
RC_TAG = "|<$RC$>|"
models_config = {
    "deepseek-chat": {
        "base_url": "https://api.deepseek.com",
        "key": "",
    },
    "gpt-4o": {
        "base_url": "",
        "key": "",
    },

    "qwen-local": {
        "base_url": "http://localhost:11434/v1",
        "key": "ollama",
        "model_name": "qwen2.5-coder:7b",
    },


}

