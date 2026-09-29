"""Read genuine model evidence through HTTP; corrupt only isolated ledger backups."""
import json
from pathlib import Path
import sqlite3
import threading
import uuid

import httpx

from robot_agent_observer.server import make_server
from robot_agent_observer.ledger import Ledger


def test_actual_model_context_http_and_corrupt_links():
    source = Path('.runtime/session-summary-validation/c5f8cb4e-15b9-4722-9220-117a16ab4009/ledger/ledger.sqlite')
    assert source.is_file(), 'requires the recorded real-model summary validation ledger'
    root = Path('.runtime/context-observer-validation') / str(uuid.uuid4())
    root.mkdir(parents=True)
    original = sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True)
    writer = sqlite3.connect(root / 'ledger.sqlite')
    original.backup(writer)
    original.close()
    records = [json.loads(r[0]) for r in writer.execute("SELECT data FROM objects WHERE collection='model_responses'")]
    assert records and all(r['raw'] and r['status'] == 'validated' for r in records)
    before = list(writer.iterdump())
    server = make_server(root, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    report = {'source_ledger': str(source), 'mock_used': False, 'simulation_used': False,
              'new_model_calls': 0, 'context_records': []}
    try:
        with httpx.Client(base_url=f'http://127.0.0.1:{server.server_port}', trust_env=False) as client:
            for record in records:
                response = client.get('/api/v1/models/' + record['id'] + '/context')
                assert response.status_code == 200
                data = response.json()['data']
                assert data['integrity']['status'] == 'matched', data
                assert data['integrity']['actual_bundle_hash'] == record['context_bundle_hash']
                wire = json.loads(writer.execute("SELECT data FROM objects WHERE collection='context_bundles' AND id=?",
                                                (record['context_bundle_id'],)).fetchone()[0])
                assert data['bundle'] == wire
                assert data['manifest']['request_id'] == wire['request']['request_id']
                assert data['allocation'] == record['context_allocation']
                report['context_records'].append({'id': record['id'], 'method': record['method'],
                    'bundle_hash': record['context_bundle_hash'], 'actual_response_id': record['response_id']})
            assert client.get('/api/v1/models/absent-record/context').status_code == 404
            assert client.post('/api/v1/models/' + records[0]['id'] + '/context').status_code == 405
            assert list(writer.iterdump()) == before
            record = next(r for r in records if r['method'] == 'session_summary')
            path = '/api/v1/models/' + record['id'] + '/context'
            bundle_id = record['context_bundle_id']
            original_wire = writer.execute("SELECT data FROM objects WHERE collection='context_bundles' AND id=?", (bundle_id,)).fetchone()[0]
            damaged = json.loads(original_wire)
            damaged['fragments'][0]['content']['turns'][0]['content'] += '\nActual copied-ledger corruption.'
            writer.execute("UPDATE objects SET data=? WHERE collection='context_bundles' AND id=?", (json.dumps(damaged), bundle_id))
            writer.commit()
            result = client.get(path).json()['data']
            assert result['integrity']['status'] == 'inconsistent'
            assert 'bundle_hash_mismatch' in result['integrity']['issues']
            writer.execute("DELETE FROM objects WHERE collection='context_bundles' AND id=?", (bundle_id,));writer.commit()
            assert 'missing_bundle' in client.get(path).json()['data']['integrity']['issues']
            writer.execute("INSERT INTO objects(collection,id,data) VALUES('context_bundles',?,?)", (bundle_id, original_wire));writer.commit()
            manifest_id = record['context_manifest_id']
            raw_manifest = writer.execute("SELECT data FROM objects WHERE collection='context_manifests' AND id=?",(manifest_id,)).fetchone()[0]
            damaged = json.loads(raw_manifest);damaged['request_id'] = 'damaged-copied-link'
            writer.execute("UPDATE objects SET data=? WHERE collection='context_manifests' AND id=?",(json.dumps(damaged),manifest_id));writer.commit()
            assert 'request_manifest_mismatch' in client.get(path).json()['data']['integrity']['issues']
            writer.execute("UPDATE objects SET data=? WHERE collection='context_manifests' AND id=?",(raw_manifest,manifest_id));writer.commit()
            assert client.get(path).json()['data']['integrity']['status'] == 'matched'
            assert sorted(writer.iterdump()) == sorted(before)
        legacy_root = Path('.runtime/memory-validation/83872251-288f-402a-b821-592ce3297033/ledger')
        legacy_db = sqlite3.connect((legacy_root / 'ledger.sqlite').resolve().as_uri() + '?mode=ro', uri=True)
        try:
            legacy = next(json.loads(row[0]) for row in legacy_db.execute("SELECT data FROM objects WHERE collection='model_responses'")
                          if not json.loads(row[0]).get('context_bundle_id') and not json.loads(row[0]).get('context_manifest_id'))
        finally:
            legacy_db.close()
        assert legacy['raw'] and legacy['actual_model'] and legacy['response_id']
        data = Ledger(legacy_root).model_context(legacy['id'])['data']
        assert data['integrity']['status'] == 'unavailable' and data['bundle'] is None and data['manifest'] is None
        report['legacy_evidence'] = {'root': str(legacy_root), 'model_record_id': legacy['id'],
            'actual_response_id': legacy['response_id'], 'status': data['integrity']['status']}
        report.update(status='passed', checks=['actual HTTP links for all recorded model methods',
            'no ledger mutation by reads', 'no model or execution dispatch', '404 absent model', '405 mutation',
            'bundle corruption', 'missing linked bundle', 'manifest mismatch', 'restored original evidence',
            'actual legacy model record remains unavailable without invented context'])
    except Exception as exc:
        report.update(status='failed', error=str(exc))
        raise
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)
        writer.close()
        (root / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print('actual context observer report:', root / 'report.json')
