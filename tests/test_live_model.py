import json
import os
from pathlib import Path

import httpx
import pytest


@pytest.mark.live_model
def test_actual_model_answers_independently_checkable_question():
    if os.environ.get("RUN_LIVE_MODEL_TESTS") != "1":
        pytest.skip("set RUN_LIVE_MODEL_TESTS=1 to call the actual model")

    config_path = Path(
        os.environ.get("ROBOT_AGENT_MODEL_CONFIG", ".runtime/model-config.json")
    )
    config = json.loads(config_path.read_text())
    token_env = config["token_env"]
    token = os.environ.get(token_env)
    if not token:
        pytest.fail(f"required model token environment variable is missing: {token_env}")

    payload = {
        "model": config["model"],
        "messages": [
            {
                "role": "system",
                "content": '只返回 JSON 对象，格式为 {"answer":整数}。',
            },
            {
                "role": "user",
                "content": "仓库中有37个零件箱，每箱29个零件。装配用了428个零件，还剩多少个？",
            },
        ],
        "response_format": {"type": "json_object"},
    }
    with httpx.Client(
        timeout=config.get("timeout", 60), follow_redirects=False, trust_env=False
    ) as client:
        response = client.post(
            config["endpoint"],
            json=payload,
            headers={"Authorization": "Bearer " + token},
        )
    response.raise_for_status()
    body = response.json()
    assert body["model"] == "qwen3.8-max"
    choice = body["choices"][0]
    assert choice["finish_reason"] == "stop"
    answer = json.loads(choice["message"]["content"])
    assert answer == {"answer": 645}
