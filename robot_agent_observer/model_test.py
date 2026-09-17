"""Opt-in local QA gateway; the standalone observer remains read-only."""
import argparse
import json
import os
from pathlib import Path
import secrets
import sqlite3
import threading
import time
import uuid

from robot_agent.model_call import ModelCaller
from robot_agent.model_transport import ModelCallError
from robot_agent.context_builder import ContextBuilder
from robot_agent.context_models import ContextRequest, GoalContext
from robot_agent.goal_analysis import GoalAnalyzer
from robot_agent.planner import Planner
from robot_agent.store import Store
from .server import make_server as observer_server


def make_server(root, config, port=8767, static=None):
    caller = ModelCaller(config)
    if caller.config.model != 'qwen3.8-max':
        raise ValueError('UI QA requires qwen3.8-max')
    if not caller.config.token_env:
        raise ValueError('UI QA requires token_env')
    directory = Path(root)
    directory.mkdir(parents=True, exist_ok=True)
    database = directory / 'model-tests.sqlite'
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE IF NOT EXISTS tests (id TEXT PRIMARY KEY, created REAL, data TEXT)')
    os.chmod(database, 0o600)
    token = secrets.token_urlsafe(32)
    lock = threading.Lock()
    server = observer_server(root, port=port, static=static)
    parent = server.RequestHandlerClass

    def save(record):
        with sqlite3.connect(database) as db:
            db.execute('INSERT OR REPLACE INTO tests VALUES (?,?,?)',
                       (record['id'], record['created_at'], json.dumps(record, ensure_ascii=False)))

    def semantic_goal(value):
        if not isinstance(value, dict):
            raise ValueError()
        raw = value.get('original_input')
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError()
        analysis = {key: item for key, item in value.items()
                    if key not in {'original_input', 'disposition'}}
        return GoalContext.from_analysis(raw, analysis)

    def analyzed_goal(store, response_id):
        response_id = str(uuid.UUID(response_id))
        record = store.get('model_responses', response_id)
        if (not record or record.get('method') != 'goal_analysis'
                or record.get('status') != 'validated'):
            raise ValueError()
        return semantic_goal(record.get('parsed'))

    def fragment_dict(fragment):
        return {
            'id': fragment.id,
            'kind': fragment.kind,
            'source': fragment.source,
            'authority': fragment.authority,
            'priority': fragment.priority,
            'required': fragment.required,
            'evidence_ids': list(fragment.evidence_ids),
            'metadata': fragment.metadata,
            'content': fragment.content,
        }

    class Handler(parent):
        def local_request(self):
            allowed = {f'127.0.0.1:{server.server_port}', f'localhost:{server.server_port}'}
            host = self.headers.get('Host', '')
            origin = self.headers.get('Origin')
            return host in allowed and (origin is None or origin in {f'http://{h}' for h in allowed} | {'http://127.0.0.1:5174', 'http://localhost:5174'})

        def do_GET(self):
            if not self.local_request():
                return self.json(403, {'error': '仅允许本地页面访问。'})
            if self.path == '/model-test/config':
                self.json(200, {'model': caller.config.model, 'csrf': token,
                               'ready': bool(os.environ.get(caller.config.token_env)),
                               'timeout': caller.config.timeout})
            elif self.path == '/model-test/history':
                with sqlite3.connect(database) as db:
                    rows = db.execute('SELECT data FROM tests ORDER BY created DESC LIMIT 50').fetchall()
                self.json(200, {'items': [json.loads(row[0]) for row in rows]})
            else:
                super().do_GET()

        def do_POST(self):
            if not self.local_request():
                return self.json(403, {'error': '仅允许本地页面访问。'})
            if self.path not in {'/model-test/run', '/semantic-test/analyze',
                                 '/semantic-test/context', '/semantic-test/plan'}:
                return self.reject()
            if not secrets.compare_digest(self.headers.get('X-Model-Test-Token', ''), token):
                return self.json(403, {'error': '请刷新页面后重试。'})
            if self.headers.get_content_type() != 'application/json':
                return self.json(415, {'error': '仅接受 JSON。'})
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 32768:
                    raise ValueError()
                self.connection.settimeout(10)
                data = json.loads(self.rfile.read(size))
                if self.path == '/model-test/run':
                    question, expected = data.get('question'), data.get('expected', '')
                    if not isinstance(question, str) or not 0 < len(question.strip()) <= 8000:
                        raise ValueError()
                    if not isinstance(expected, str) or len(expected) > 8000:
                        raise ValueError()
                    request_id = str(uuid.UUID(data['id']))
                elif self.path == '/semantic-test/analyze':
                    goal = data.get('goal')
                    conversation = data.get('conversation', [])
                    if (not isinstance(goal, str) or not 0 < len(goal.strip()) <= 8000
                            or not isinstance(conversation, list)
                            or len(conversation) > 50):
                        raise ValueError()
                elif self.path == '/semantic-test/context':
                    analysis_response_id = data.get('analysis_response_id')
                    robot_id = data.get('robot_id') or None
                    if (robot_id is not None and
                            (not isinstance(robot_id, str) or not robot_id
                             or '/' in robot_id)):
                        raise ValueError()
                    uuid.UUID(analysis_response_id)
                else:
                    context_request_id = str(uuid.UUID(
                        data.get('context_request_id')
                    ))
            except (ValueError, KeyError, TypeError, AttributeError, TimeoutError):
                return self.json(400, {'error': '请求内容无效；请检查目标、语义 JSON 和字段类型。'})

            if self.path == '/semantic-test/context':
                semantic_store = Store(directory)
                try:
                    goal_context = analyzed_goal(semantic_store, analysis_response_id)
                    catalog = {item['name']: item for item in semantic_store.list('skills')}
                    request = ContextRequest(
                        request_id=str(uuid.uuid4()),
                        phase='planning',
                        goal=goal_context,
                        robot_id=robot_id,
                    )
                    fragments = ContextBuilder(semantic_store).build(request, catalog).fragments
                    prepared = caller.prepare(
                        'planning',
                        {'goal': goal_context.original_input, 'skills': catalog},
                        context=fragments,
                    )
                    semantic_store.put('context_test_previews', request.request_id, {
                        'id': request.request_id,
                        'analysis_response_id': analysis_response_id,
                        'robot_id': robot_id,
                        'goal_context': goal_context.as_dict(),
                        'catalog': catalog,
                        'created_at': time.time(),
                    })
                    return self.json(200, {
                        'request_id': request.request_id,
                        'phase': request.phase,
                        'catalog_size': len(catalog),
                        'fragments': [fragment_dict(item) for item in fragments],
                        'messages': list(prepared.request.messages),
                        'allocation': prepared.allocation.as_dict(),
                    })
                except Exception as exc:
                    return self.json(400, {'error': f'上下文生成失败：{exc}'})
                finally:
                    semantic_store.close()

            if not lock.acquire(blocking=False):
                return self.json(409, {'error': '已有测试正在进行，请等待后查看历史记录。'})
            try:
                if self.path == '/semantic-test/analyze':
                    semantic_store = Store(directory)
                    try:
                        result = GoalAnalyzer(
                            semantic_store, config, caller=caller
                        ).analyze(goal, conversation)
                        return self.json(200, result.as_dict())
                    except Exception as exc:
                        return self.json(502, {
                            'error': '语义分析失败，请检查模型响应契约和服务端审计记录。',
                            'error_type': type(exc).__name__,
                        })
                    finally:
                        semantic_store.close()
                if self.path == '/semantic-test/plan':
                    semantic_store = Store(directory)
                    try:
                        preview = semantic_store.get(
                            'context_test_previews', context_request_id
                        )
                        if not preview:
                            return self.json(409, {
                                'error': '上下文预览不存在或已失效，请重新生成上下文。'
                            })
                        goal_context = semantic_goal(preview['goal_context'])
                        catalog = preview['catalog']
                        request = ContextRequest(
                            request_id=context_request_id,
                            phase='planning',
                            goal=goal_context,
                            robot_id=preview.get('robot_id'),
                        )
                        planner = Planner(semantic_store, config)
                        plan = planner.plan(
                            goal_context.original_input,
                            catalog,
                            context_request=request,
                        )
                        response = semantic_store.get(
                            'model_responses', planner.last_response_id
                        )
                        return self.json(200, {
                            'request_id': request.request_id,
                            'analysis_response_id': preview[
                                'analysis_response_id'
                            ],
                            'planning_response_id': planner.last_response_id,
                            'context_manifest_id': response.get(
                                'context_manifest_id'
                            ),
                            'catalog_size': len(catalog),
                            'plan': plan,
                        })
                    except Exception as exc:
                        return self.json(502, {
                            'error': '真实规划失败；请检查技能目录、模型响应契约和审计记录。',
                            'error_type': type(exc).__name__,
                        })
                    finally:
                        semantic_store.close()
                with sqlite3.connect(database) as db:
                    previous = db.execute('SELECT data FROM tests WHERE id=?', (request_id,)).fetchone()
                if previous:
                    return self.json(200, json.loads(previous[0]))
                record = {'id': request_id, 'created_at': time.time(), 'question': question,
                          'expected': expected, 'model': caller.config.model, 'status': 'requesting'}
                save(record)
                started = time.monotonic()
                try:
                    result = caller.call('qa', {'question': question})
                    record.update(status='completed', answer=result.content,
                                  actual_model=result.actual_model, response_id=result.response_id,
                                  http_status=result.transport.status_code,
                                  verdict=('matched' if result.content.strip() == expected.strip() else 'mismatched')
                                  if expected.strip() else 'unjudged')
                except Exception as exc:
                    response = exc.response if isinstance(exc, ModelCallError) else None
                    record.update(status='failed', error='模型调用失败，请检查服务端配置、凭证或稍后手动重试。',
                                  error_type=type(exc).__name__, http_status=response.status_code if response else None)
                record['elapsed_ms'] = round((time.monotonic() - started) * 1000)
                save(record)
                self.json(200, record)
            finally:
                lock.release()

    server.RequestHandlerClass = Handler
    return server


def main():
    parser = argparse.ArgumentParser(description='本地模型问答测试 UI（真实 API 调用）')
    parser.add_argument('--root', required=True)
    parser.add_argument('--model-config', default='.runtime/model-config.json')
    parser.add_argument('--port', type=int, default=8767)
    parser.add_argument('--static', default='ui/dist')
    args = parser.parse_args()
    server = make_server(args.root, json.loads(Path(args.model_config).read_text()), args.port, args.static)
    print(f'Model test UI: http://127.0.0.1:{server.server_port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
