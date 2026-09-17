"""Local request-boundary tests, not evidence of model answer quality."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import uuid
import httpx
import pytest
from robot_agent_observer.model_test import make_server
from robot_agent.store import Store


def test_gateway_rejects_unauthorized_and_invalid_requests(tmp_path):
    server = make_server(tmp_path, {'endpoint':'https://example.invalid/chat/completions',
                                  'model':'qwen3.8-max','token_env':'UI_TEST_MISSING_KEY'}, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(base_url=f'http://127.0.0.1:{server.server_port}', trust_env=False) as client:
            config = client.get('/model-test/config').json()
            assert config['ready'] is False
            assert 'endpoint' not in config
            assert client.post('/model-test/run', json={}).status_code == 403
            headers = {'X-Model-Test-Token':config['csrf']}
            assert client.post('/model-test/run', headers=headers, json={'id':str(uuid.uuid4()),'question':' '}).status_code == 400
            assert client.post('/semantic-test/context', headers=headers,
                               json={'analysis_response_id': str(uuid.uuid4())}).status_code == 400
            assert client.get('/model-test/config', headers={'Host':'attacker.example'}).status_code == 403
            assert client.post('/model-test/run', headers={**headers,'Origin':'https://attacker.example'}, json={}).status_code == 403
            assert client.post('/api/v1/tasks', headers=headers, json={}).status_code == 405
            assert client.get('/model-test/history').json() == {'items':[]}
    finally:
        server.shutdown();server.server_close();thread.join()


@pytest.mark.parametrize('ask_clarification', [False, True])
def test_gateway_runs_semantic_analysis_and_returns_grounding(monkeypatch, tmp_path,
                                                               ask_clarification):
    payload = {
        'interpreted_intent': '导航到厨房并定位热水壶',
        'entities': [
            {'id': 'destination', 'type': 'location', 'name': '厨房'},
            {'id': 'target', 'type': 'object', 'name': '热水壶'},
        ],
        'relations': [{'subject': 'target', 'predicate': 'expected_in',
                       'object': 'destination'}],
        'constraints': ['先到达厨房再搜索'],
        'completion_criteria': ['热水壶已定位'],
        'ambiguities': [],
        'missing_information': ['热水壶当前位置'],
        'assumptions': [],
        'grounding_requests': ['使用相机搜索热水壶'],
        'clarification_requests': ['确认热水壶的外观'] if ask_clarification else [],
    }
    questions = {'questions': [{
        'field': 'target_appearance',
        'question': '热水壶是什么颜色？',
        'reason': '便于缩小搜索范围',
    }]}

    plan = {
        'steps': [
            {'id': 'inspect', 'skill': 'vision.inspect', 'args': {}},
            {'id': 'verify', 'skill': 'goal.verify', 'args': {}, 'deps': ['inspect']},
        ],
        'verification': 'verify',
    }

    class Upstream(BaseHTTPRequestHandler):
        calls = 0

        def do_POST(self):
            type(self).calls += 1
            size = int(self.headers['Content-Length'])
            self.rfile.read(size)
            body = json.dumps({
                'id': f'model-response-{type(self).calls}',
                'model': 'qwen3.8-max',
                'choices': [{
                    'finish_reason': 'stop',
                    'message': {'content': json.dumps(
                        payload if type(self).calls == 1 else
                        questions if ask_clarification and type(self).calls == 2 else plan,
                        ensure_ascii=False,
                    ),
                                'refusal': None},
                }],
            }).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            return

    upstream = ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
    upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    upstream_thread.start()
    monkeypatch.setenv('SEMANTIC_TEST_KEY', 'test-only-token')
    setup_store = Store(tmp_path)
    setup_store.put('skills', 'vision.inspect', {
        'name': 'vision.inspect', 'input_schema': {}, 'output_schema': {}
    })
    setup_store.put('skills', 'goal.verify', {
        'name': 'goal.verify', 'input_schema': {}, 'output_schema': {},
        'verifier': True,
    })
    setup_store.close()
    server = make_server(
        tmp_path,
        {'endpoint': f'http://127.0.0.1:{upstream.server_port}',
         'model': 'qwen3.8-max', 'token_env': 'SEMANTIC_TEST_KEY'},
        port=0,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(base_url=f'http://127.0.0.1:{server.server_port}',
                          trust_env=False) as client:
            config = client.get('/model-test/config').json()
            response = client.post(
                '/semantic-test/analyze',
                headers={'X-Model-Test-Token': config['csrf']},
                json={'goal': '到厨房去找热水壶', 'conversation': []},
            )
            assert response.status_code == 200
            result = response.json()
            assert result['status'] == ('needs_clarification' if ask_clarification
                                        else 'needs_grounding')
            assert result['questions'] == (questions['questions'] if ask_clarification
                                           else [])
            assert result['goal_context']['original_input'] == '到厨房去找热水壶'
            assert result['goal_context']['grounding_requests'] == ['使用相机搜索热水壶']
            context = client.post(
                '/semantic-test/context',
                headers={'X-Model-Test-Token': config['csrf']},
                json={'analysis_response_id': result['analysis_response_id'],
                      'robot_id': 'g1'},
            )
            assert context.status_code == 200
            preview = context.json()
            assert [item['id'] for item in preview['fragments']] == [
                'goal', 'capabilities'
            ]
            assert preview['fragments'][0]['content']['clarification_requests'] == (
                payload['clarification_requests']
            )
            assert preview['messages'][1]['role'] == 'user'
            assert preview['allocation']['included'] == ['goal', 'capabilities']
            planned = client.post(
                '/semantic-test/plan',
                headers={'X-Model-Test-Token': config['csrf']},
                json={'context_request_id': preview['request_id']},
            )
            assert planned.status_code == 200
            planned_body = planned.json()
            assert planned_body['plan'] == plan
            assert planned_body['request_id'] == preview['request_id']
            assert planned_body['context_manifest_id']
            assert Upstream.calls == (3 if ask_clarification else 2)
    finally:
        server.shutdown();server.server_close();thread.join()
        upstream.shutdown();upstream.server_close();upstream_thread.join()
