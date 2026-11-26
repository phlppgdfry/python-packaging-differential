#!/usr/bin/env bash
# Fetch uv at the pinned commit, build the uv target, install the pinned Python packages, run.
set -euo pipefail
cd "$(dirname "$0")"

UV_REF=$(python3 -c 'import json; print(json.load(open("pins.json"))["uv"])')
PACKAGING=$(python3 -c 'import json; print(json.load(open("pins.json"))["packaging"])')
POETRY_CORE=$(python3 -c 'import json; print(json.load(open("pins.json"))["poetry-core"])')

if [ "$(git -C .cache/uv rev-parse HEAD 2>/dev/null || true)" != "$UV_REF" ]; then
  rm -rf .cache/uv && git init -q .cache/uv
  git -C .cache/uv fetch -q --depth 1 https://github.com/astral-sh/uv.git "$UV_REF"
  git -C .cache/uv checkout -q FETCH_HEAD
fi
cargo build -q --release --manifest-path targets/uv/Cargo.toml

[ -x .venv/bin/python ] || uv venv -q -p 3.12 .venv
uv pip install -q -p .venv "packaging==$PACKAGING" "poetry-core==$POETRY_CORE"

.venv/bin/python run.py
