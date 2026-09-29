#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

export MODEL_ENDPOINT="${MODEL_ENDPOINT:-http://127.0.0.1:8000/v1/chat/completions}"
export MODEL_NAME="${MODEL_NAME:-Qwen/Qwen3.8-27B}"

echo "GPTmoment for robot portable physical-agent runtime"
echo "UI:    http://$(hostname -I 2>/dev/null | awk '{print $1}'):${PORT:-3030}"
echo "Model: ${MODEL_NAME} @ ${MODEL_ENDPOINT}"
exec python3 gptmoment.py --host 0.0.0.0 --port "${PORT:-3030}"
