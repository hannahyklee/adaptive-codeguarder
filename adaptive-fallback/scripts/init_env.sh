#!/bin/bash

# Sets up this project's own environment (separate from ../CodeGuarder's
# conda environment). Pins the same Python version as CodeGuarder for
# compatibility with its reused torch/transformers/faiss versions.
PYTHON_VERSION="3.10"

# --- 1. Check if uv is installed ---
if ! command -v uv &> /dev/null
then
    echo "uv is not found. Install it first: https://docs.astral.sh/uv/getting-started/installation/"
    echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

# --- 2. Check if jq is installed ---
# Used by scripts/RQ_Adaptive.sh to parse JSON output.
if ! command -v jq &> /dev/null
then
    echo "jq is not found. Please install it using your system's package manager."
    echo "For Debian/Ubuntu: sudo apt-get install jq"
    echo "For Fedora/CentOS: sudo yum install jq"
    echo "For macOS (with Homebrew): brew install jq"
    exit 1
fi

# --- 3. Ensure the pinned Python version is available to uv ---
echo "Ensuring Python ${PYTHON_VERSION} is available..."
uv python install "${PYTHON_VERSION}"

# --- 4. Sync the environment from pyproject.toml / uv.lock ---
echo "Syncing dependencies with uv..."
uv sync --python "${PYTHON_VERSION}"
if [ $? -ne 0 ]; then
    echo "Failed to sync the environment. Exiting."
    exit 1
fi

echo "Environment setup complete!"
echo "Run this project's scripts with: uv run python <script>.py"
echo ""
echo "Note: ../CodeGuarder still needs its own conda environment set up"
echo "separately (see ../CodeGuarder/scripts/init_env.sh) -- scripts/run_*_adaptive.sh"
echo "invoke both environments."
