import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading

from robot_agent.goal_analysis import GoalAnalyzer
from robot_agent.store import Store


def test_analysis_and_clarification_use_independent_system_prompts(tmp_path):
    requests = []
    responses = [
        {
            "interpreted_intent": "把被指代的箱子放入被指代的容器",
            "entities": [{"ref": "target", "type": "box", "status": "unresolved"}],
            "relations": [],
            "constraints": [],
            "completion_criteria": ["目标箱子位于目标容器内部"],
            "ambiguities": ["箱子不明确", "容器不明确"],
            "missing_information": ["目标箱子", "目标容器"],
            "assumptions": [],
            "grounding_requests": [],
            "clarification_requests": ["确认目标箱子和容器"],
        },
        {
            "questions": [
                {
                    "field": "target_object",
                    "question": "你指的是哪个箱子？",
                    "reason": "存在多个可能目标",
                }
            ]
        },
    ]

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers["Content-Length"])
            requests.append(json.loads(self.rfile.read(length)))
            content = json.dumps(responses[len(requests) - 1], ensure_ascii=False)
            body = json.dumps(
                {
                    "id": f"response-{len(requests)}",
                    "model": "test-model",
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {"content": content, "refusal": None},
                        }
                    ],
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    store = Store(tmp_path)
    try:
        result = GoalAnalyzer(
            store,
            {
                "endpoint": f"http://127.0.0.1:{server.server_port}",
                "model": "test-model",
            },
        ).analyze("把那个箱子放到里面")
        assert result.goal_context.original_input == "把那个箱子放到里面"
        assert result.goal_context.disposition == "needs_clarification"
        assert result.questions[0]["question"] == "你指的是哪个箱子？"
        assert len(requests) == 2
        assert requests[0]["messages"][0]["content"] != requests[1]["messages"][0]["content"]
        assert "Analyze the user's robot goal" in requests[0]["messages"][0]["content"]
        assert "Generate concise clarification questions" in requests[1]["messages"][0]["content"]
        assert not store.list("tasks")
        records = sorted(store.list("model_responses"), key=lambda x: x["created_at"])
        assert [x["method"] for x in records] == [
            "goal_analysis",
            "goal_clarification",
        ]
    finally:
        store.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_grounding_request_does_not_ask_user(tmp_path):
    class Handler(BaseHTTPRequestHandler):
        calls = 0

        def do_POST(self):
            type(self).calls += 1
            length = int(self.headers["Content-Length"])
            self.rfile.read(length)
            content = json.dumps(
                {
                    "interpreted_intent": "找到红色杯子",
                    "entities": [],
                    "relations": [],
                    "constraints": [],
                    "completion_criteria": ["红色杯子已定位"],
                    "ambiguities": [],
                    "missing_information": ["杯子位置"],
                    "assumptions": [],
                    "grounding_requests": ["使用相机检测红色杯子"],
                    "clarification_requests": [],
                },
                ensure_ascii=False,
            )
            body = json.dumps(
                {
                    "id": "response-grounding",
                    "model": "test-model",
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {"content": content, "refusal": None},
                        }
                    ],
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    store = Store(tmp_path)
    try:
        result = GoalAnalyzer(
            store,
            {
                "endpoint": f"http://127.0.0.1:{server.server_port}",
                "model": "test-model",
            },
        ).analyze("找到红色杯子")
        assert result.goal_context.disposition == "needs_grounding"
        assert result.questions == ()
        assert Handler.calls == 1
    finally:
        store.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
