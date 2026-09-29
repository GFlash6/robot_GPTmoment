"""Actual HTTP comparison of saved real-model planning/recovery evidence; no mock IO."""
import hashlib
import json
from pathlib import Path
import sqlite3
import threading
import uuid

import httpx

from robot_agent_observer.ledger import Ledger, clean
from robot_agent_observer.server import make_server


def test_real_planning_recovery_context_diff():
    source_root = Path('.runtime/replanning-context-validation/93593234-4e6a-44a8-8bf0-e4ba3ae8ade9')
    source = source_root / 'ledger/ledger.sqlite'
    assert source.is_file(), 'requires the completed real-model recovery validation ledger'
    root = Path('.runtime/context-diff-validation') / str(uuid.uuid4())
    root.mkdir(parents=True)
    original = sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True)
    writer = sqlite3.connect(root / 'ledger.sqlite')
    original.backup(writer)
    original.close()
    writer.execute('PRAGMA journal_mode=WAL')
    baseline = sorted(writer.iterdump())
    records = [json.loads(row[0]) for row in writer.execute(
        "SELECT data FROM objects WHERE collection='model_responses'")]
    assert len(records) >= 4 and all(r['status'] == 'validated' and r['raw'] and r['response_id'] for r in records)
    bundles = {r['id']: json.loads(writer.execute(
        "SELECT data FROM objects WHERE collection='context_bundles' AND id=?", (r['context_bundle_id'],)
    ).fetchone()[0]) for r in records}
    first = next(r for r in records if r['method'] == 'planning' and bundles[r['id']]['request']['phase'] == 'planning')
    recovery = next(r for r in records if r['method'] == 'planning' and bundles[r['id']]['request']['phase'] == 'replanning')
    server = make_server(root, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    report = {'source_ledger': str(source), 'source_report': str(source_root / 'report.json'),
              'source_report_sha256': hashlib.sha256((source_root / 'report.json').read_bytes()).hexdigest(),
              'mock_used': False, 'simulation_used': False, 'new_model_calls': 0,
              'actual_response_ids': [r['response_id'] for r in records], 'pairs_checked': 0}
    try:
        with httpx.Client(base_url=f'http://127.0.0.1:{server.server_port}', trust_env=False) as client:
            path = f"/api/v1/models/{recovery['id']}/context-diff"
            def compare(after, before):
                response = client.get(f'/api/v1/models/{after}/context-diff', params={'against': before})
                assert response.status_code == 200, response.text
                return response.json()['data']

            for left in records:
                for right in records:
                    data = compare(right['id'], left['id'])
                    assert data['status'] == 'compared' and data['lineage'] == 'explicit_pair_not_verified'
                    assert data['before']['model_record_id'] == left['id']
                    assert data['after']['model_record_id'] == right['id']
                    a, b = clean(bundles[left['id']]), clean(bundles[right['id']])
                    a_ids, b_ids = {f['id'] for f in a['fragments']}, {f['id'] for f in b['fragments']}
                    delta = data['changes']
                    assert {f['id'] for f in delta['fragments']['added']} == b_ids - a_ids
                    assert {f['id'] for f in delta['fragments']['removed']} == a_ids - b_ids
                    assert delta['fragments']['order']['before'] == [f['id'] for f in a['fragments']]
                    assert delta['fragments']['order']['after'] == [f['id'] for f in b['fragments']]
                    expected_request_fields = {k for k in a['request'].keys() | b['request'].keys()
                                               if a['request'].get(k) != b['request'].get(k)}
                    assert {d['field'] for d in delta['request']} == expected_request_fields
                    for f in delta['fragments']['added']:
                        original_content = next(x['content'] for x in b['fragments'] if x['id'] == f['id'])
                        assert f['content_sha256'] == hashlib.sha256(json.dumps(
                            original_content, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()
                    if left['id'] == right['id']:
                        assert not any(delta[k] for k in ('request', 'manifest', 'allocation', 'provider_diagnostics'))
                        assert not delta['fragments']['changed']
                        assert delta['fragments']['unchanged_ids'] == sorted(a_ids)
                    report['pairs_checked'] += 1

            data = compare(recovery['id'], first['id'])
            assert {f['id'] for f in data['changes']['fragments']['added']} == {'task-state', 'session-summary'}
            assert {'phase', 'task_id', 'context_snapshot_id'} <= {c['field'] for c in data['changes']['request']}
            budget = next(c for c in data['changes']['manifest'] if c['field'] == 'input_token_limit')
            assert budget['before'] == 32768 and budget['after'] == 18719
            session = next(c for c in data['changes']['fragments']['changed'] if c['id'] == 'session')
            assert 'content_sha256' in {c['field'] for c in session['fields']}
            capabilities = next(c for c in data['changes']['fragments']['changed'] if c['id'] == 'capabilities')
            assert capabilities['fields'] == [{'field': 'source', 'before_present': True, 'after_present': True,
                                              'before': 'skill_registry', 'after': 'frozen_skill_catalog'}]
            assert 'goal' in data['changes']['fragments']['unchanged_ids']
            assert data['scope_differences'] == ['task_id']
            reverse = compare(first['id'], recovery['id'])
            assert reverse['changes']['fragments']['removed'] == data['changes']['fragments']['added']
            report['planning_to_recovery'] = data
            assert client.get(path).status_code == 400
            assert client.get(path, params={'against': '   '}).status_code == 400
            assert client.get(path, params={'against': 'absent'}).status_code == 404
            assert client.get('/api/v1/models/absent/context-diff', params={'against': first['id']}).status_code == 404
            assert client.post(path, json={'against': first['id']}).status_code == 405
            assert sorted(writer.iterdump()) == baseline

            # Real corruption of an isolated ledger copy, never a fabricated model response.
            bundle_id = recovery['context_bundle_id']
            raw_bundle = writer.execute("SELECT data FROM objects WHERE collection='context_bundles' AND id=?", (bundle_id,)).fetchone()[0]
            broken = json.loads(raw_bundle)
            broken['fragments'][0]['content'] = 'Corrupted stored context in isolated backup.'
            writer.execute("UPDATE objects SET data=? WHERE collection='context_bundles' AND id=?", (json.dumps(broken), bundle_id))
            writer.commit()
            bad = compare(recovery['id'], first['id'])
            assert bad['status'] == 'unavailable' and bad['changes'] is None
            assert 'bundle_hash_mismatch' in bad['after']['integrity']['issues']
            writer.execute("UPDATE objects SET data=? WHERE collection='context_bundles' AND id=?", (raw_bundle, bundle_id))
            writer.commit()

            manifest_id = recovery['context_manifest_id']
            raw_manifest = writer.execute("SELECT data FROM objects WHERE collection='context_manifests' AND id=?", (manifest_id,)).fetchone()[0]
            damaged = json.loads(raw_manifest)
            damaged['included'].append(damaged['included'][0])
            # An actual concurrent commit cannot change the second read in a held snapshot.
            ledger = Ledger(root)
            with ledger.read() as db:
                old = ledger._model_context(db, recovery['id'])
                writer.execute("UPDATE objects SET data=? WHERE collection='context_manifests' AND id=?", (json.dumps(damaged), manifest_id))
                writer.commit()
                assert ledger._model_context(db, recovery['id']) == old
            bad = compare(recovery['id'], first['id'])
            assert bad['status'] == 'unavailable' and bad['changes'] is None
            assert 'ambiguous_fragment_allocation' in bad['after']['comparison_issues']
            writer.execute("UPDATE objects SET data=? WHERE collection='context_manifests' AND id=?", (raw_manifest, manifest_id))
            writer.commit()
            assert compare(recovery['id'], first['id']) == data
            assert sorted(writer.iterdump()) == baseline

        # Actual legacy evidence has no Bundle; comparison must not mean "identical".
        legacy_root = Path('.runtime/memory-validation/83872251-288f-402a-b821-592ce3297033/ledger')
        with sqlite3.connect((legacy_root / 'ledger.sqlite').resolve().as_uri() + '?mode=ro', uri=True) as db:
            legacy = next(json.loads(row[0]) for row in db.execute("SELECT data FROM objects WHERE collection='model_responses'")
                          if not json.loads(row[0]).get('context_bundle_id') and not json.loads(row[0]).get('context_manifest_id'))
        assert legacy['raw'] and legacy['response_id']
        absent = Ledger(legacy_root).model_context_diff(legacy['id'], {'against': legacy['id']})['data']
        assert absent['status'] == 'unavailable' and absent['changes'] is None
        report['legacy_response_id'] = legacy['response_id']
        report.update(status='passed', checks=['all ordered genuine model pairs and self comparison',
            'actual task-state and summary addition', 'actual session content and budget changes',
            'reverse direction', 'invalid query and missing records', 'GET only and unchanged ledger',
            'real copied-bundle corruption rejected', 'duplicate allocation rejected',
            'concurrent actual commit preserves SQLite read snapshot', 'actual legacy evidence unavailable',
            'original copied ledger fully restored'])
    except Exception as exc:
        report.update(status='failed', error=str(exc))
        raise
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)
        writer.close()
        (root / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print('actual context diff report:', root / 'report.json')
