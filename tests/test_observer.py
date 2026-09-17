"""Observer API exercises real ledger records and real HTTP; no runtime doubles."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import threading
import httpx
import pytest
from robot_agent.store import Store
from robot_agent.runtime import Runtime
from robot_agent_observer.ledger import Ledger, ObserverError
from robot_agent_observer.server import make_server


def create_task(root):
    store=Store(root);runtime=Runtime(store);runtime.install_local_skills([str(Path(__file__).parent)])
    task=runtime.submit({'steps':[{'id':'ingest','skill':'file.ingest','args':{'path':str(Path(__file__).resolve()),'metadata':{'kind':'document','source':'observer-test-source','encoding':'utf8'}}},{'id':'verify','skill':'asset.verify','deps':['ingest'],'args':{'asset_id':{'$ref':'ingest.asset_id'}}}],'verification':'verify'},'r1',goal='归档实际测试源码并校验')
    runtime.tick(task['id']);return store,task['id']


def test_observer_reads_actual_task_without_changing_ledger(tmp_path):
    store,task=create_task(tmp_path);store.close()
    before=hashlib.sha256((tmp_path/'ledger.sqlite').read_bytes()).hexdigest()
    reader=Ledger(tmp_path)
    overview=reader.overview()['data'];assert overview['task_counts']=={'succeeded':1}
    detail=reader.task(task)['data'];assert len(detail['executions'])==2
    assert detail['task']['steps']['verify']['result']['output']['verified'] is True
    assert 'allowed_roots' not in detail['task']['catalog']['file.ingest']
    page=reader.events(task,{'limit':'1'})['data'];assert page['has_more'] is True
    second=reader.events(task,{'after_seq':str(page['next_seq']),'limit':'500'})['data']
    assert all(e['seq']>page['next_seq'] for e in second['items'])
    assert reader.listing('assets',{})['data']['total']==1
    assert hashlib.sha256((tmp_path/'ledger.sqlite').read_bytes()).hexdigest()==before
    with reader.read() as db:
        import sqlite3
        with pytest.raises(sqlite3.OperationalError): db.execute("DELETE FROM objects")


def test_missing_ledger_is_not_created(tmp_path):
    root=tmp_path/'absent'
    with pytest.raises(ObserverError) as e: Ledger(root).overview()
    assert e.value.code=='LEDGER_MISSING'
    assert not root.exists()


def test_resource_owner_links_to_real_execution(tmp_path):
    store=Store(tmp_path);rt=Runtime(store);rt.install_local_skills([str(tmp_path)])
    spec=rt.catalog()['file.copy'];spec['resources']={'disk':1};rt.register('file.copy',spec);store.set_capacity('r1/disk',2)
    source=tmp_path/'input';source.write_bytes(Path(__file__).read_bytes())
    task=rt.submit({'steps':[{'id':'copy','skill':'file.copy','args':{'source':str(source),'target':str(tmp_path/'output'),'chunk_bytes':32}}],'verification':'copy'},'r1')['id'];rt.tick(task)
    data=Ledger(tmp_path).resources()['data']['items'][0]
    assert data['used']==1 and data['capacity']==2 and data['owners'][0]['task_id']==task
    rt.interrupt(task,'cancel');rt.tick(task)
    assert Ledger(tmp_path).resources()['data']['items'][0]['used']==0
    store.close()


def test_http_get_only_and_pagination(tmp_path):
    store,task=create_task(tmp_path);store.close()
    server=make_server(tmp_path,port=0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with httpx.Client(base_url=f'http://127.0.0.1:{server.server_port}',trust_env=False) as client:
            response=client.get('/api/v1/tasks');assert response.status_code==200
            assert response.json()['data']['items'][0]['id']==task
            assert client.post('/api/v1/tasks',json={}).status_code==405
            assert client.get('/api/v1/tasks?limit=201').status_code==400
            assert client.get('/api/v1/tasks/not-found').status_code==404
            assert client.get('/api/v1/tasks?q=%25').json()['data']['total']==0
            assert client.get('/api/v1/models').json()['data']['items']==[]
    finally: server.shutdown();server.server_close();thread.join()


def test_observer_import_does_not_load_control_runtime():
    result=subprocess.run([sys.executable,'-c',"import sys; import robot_agent_observer.server; assert 'dbos' not in sys.modules; assert 'robot_agent.runtime' not in sys.modules"],capture_output=True,text=True)
    assert result.returncode==0,result.stderr


def test_nanosecond_metadata_preserved_for_browser(tmp_path):
    from robot_agent.memory import Memory
    store=Store(tmp_path)
    source=Path(__file__)
    actual_ns=source.stat().st_mtime_ns
    Memory(store).ingest(source,{'kind':'document','source':'filesystem-mtime','encoding':'utf8','timestamp_ns':actual_ns})
    item=Ledger(tmp_path).listing('assets',{})['data']['items'][0]
    assert item['metadata']['timestamp_ns']==str(actual_ns)
    store.close()
