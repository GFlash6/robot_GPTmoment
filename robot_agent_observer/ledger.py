"""Versioned read models over a live SQLite ledger, never a runtime controller."""
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import json
import sqlite3


class ObserverError(Exception):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code, self.status = code, status


def clean(value):
    """Exclude configured secrets/endpoints; render remaining untrusted values as text."""
    hidden = {'model_config','token_env','authorization','api_key','access_token','password','secret','endpoint','allowed_roots'}
    if isinstance(value, dict):
        return {k:clean(v) for k,v in value.items() if k.lower() not in hidden}
    if isinstance(value, list): return [clean(v) for v in value]
    if type(value) is int and abs(value)>2**53-1: return str(value)
    return value


def decode(row):
    if row is None: raise ObserverError('NOT_FOUND','记录不存在',404)
    try:
        data=json.loads(row['data'])
        if not isinstance(data,dict): raise ValueError('not an object')
        return data
    except (ValueError,TypeError) as exc:
        raise ObserverError('LEDGER_INVALID','账本包含无法解析的记录',422) from exc


class Ledger:
    def __init__(self, root):
        self.path=Path(root).resolve()/'ledger.sqlite'

    @contextmanager
    def read(self):
        if not self.path.is_file():
            raise ObserverError('LEDGER_MISSING','未找到运行账本；请连接实际运行目录',503)
        db=None
        try:
            db=sqlite3.connect(self.path.as_uri()+'?mode=ro',uri=True,timeout=1,isolation_level=None)
            db.row_factory=sqlite3.Row
            db.execute('PRAGMA query_only=ON')
            db.execute('BEGIN')
            required={'objects':{'collection','id','data'},'resources':{'name','capacity'},'leases':{'owner','resource','units'},'events':{'seq','ts','task','type','data'}}
            for table,columns in required.items():
                actual={row['name'] for row in db.execute(f'PRAGMA table_info({table})')}
                if not columns.issubset(actual): raise ObserverError('SCHEMA_UNSUPPORTED','账本结构与观察 API 不兼容',422)
            yield db
        except sqlite3.OperationalError as exc:
            busy='locked' in str(exc).lower() or 'busy' in str(exc).lower()
            raise ObserverError('LEDGER_BUSY' if busy else 'LEDGER_INVALID','账本忙，请稍后刷新' if busy else '账本读取失败',503 if busy else 422) from exc
        except sqlite3.DatabaseError as exc:
            raise ObserverError('LEDGER_INVALID','账本读取失败',422) from exc
        finally:
            if db is not None: db.close()

    def response(self, fn):
        with self.read() as db: result=fn(db)
        return {'api_version':'1','observed_at':datetime.now(timezone.utc).isoformat(),'data':clean(result)}

    @staticmethod
    def get(db, collection, key):
        return decode(db.execute('SELECT data FROM objects WHERE collection=? AND id=?',(collection,key)).fetchone())

    @staticmethod
    def summary(task):
        steps=task.get('steps',{})
        return {k:v for k,v in task.items() if k in {'id','robot_id','goal','priority','created_at','status','revision','generation','replans','max_replans','model_response_id'}} | {
            'step_count':len(steps),'completed_steps':sum(s.get('status')=='succeeded' for s in steps.values())}

    def overview(self):
        def query(db):
            counts={r['status'] or 'unknown':r['n'] for r in db.execute("SELECT json_extract(data,'$.status') AS status,COUNT(*) AS n FROM objects WHERE collection='tasks' GROUP BY status")}
            collections={r['collection']:r['n'] for r in db.execute('SELECT collection,COUNT(*) AS n FROM objects GROUP BY collection')}
            last=db.execute('SELECT MAX(seq) AS seq,MAX(ts) AS ts FROM events').fetchone()
            recent=[]
            for r in db.execute('SELECT * FROM events ORDER BY seq DESC LIMIT 8'):
                recent.append({**dict(r),'data':decode(r)})
            return {'task_counts':counts,'collections':collections,'resource_count':db.execute('SELECT COUNT(*) FROM resources').fetchone()[0],
                    'lease_count':db.execute('SELECT COUNT(*) FROM leases').fetchone()[0], 'latest_event_seq':last['seq'] or 0,
                    'latest_event_at':last['ts'],'recent_events':recent,'worker_status':'unobserved','robot_status':'unobserved'}
        return self.response(query)

    def listing(self, collection, params):
        limit=integer(params,'limit',50,1,200);offset=integer(params,'offset',0,0,10_000_000)
        filters={'tasks':{'robot_id':'$.robot_id','status':'$.status'},'assets':{'kind':'$.metadata.kind','robot_id':'$.metadata.robot_id','frame_id':'$.metadata.frame_id','version':'$.metadata.version'},'memories':{'kind':'$.kind'},'model_responses':{'status':'$.status'}}[collection]
        where=['collection=?'];args=[collection]
        for key,path in filters.items():
            if params.get(key): where.append('CAST(json_extract(data,?) AS TEXT)=?');args.extend([path,params[key]])
        if collection=='assets':
            for key,op in [('start_ns','>='),('end_ns','<=')]:
                if params.get(key): where.append(f"json_extract(data,'$.metadata.timestamp_ns'){op}?");args.append(integer(params,key,0,0,2**63-1))
        if params.get('q'):
            where.append('(id LIKE ? OR data LIKE ?)');escaped=params['q'].replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
            where[-1]="(id LIKE ? ESCAPE '\\' OR data LIKE ? ESCAPE '\\')";args.extend(['%'+escaped+'%']*2)
        sql=' AND '.join(where)
        def query(db):
            total=db.execute('SELECT COUNT(*) FROM objects WHERE '+sql,args).fetchone()[0]
            rows=db.execute("SELECT data FROM objects WHERE "+sql+" ORDER BY json_extract(data,'$.created_at') DESC,id DESC LIMIT ? OFFSET ?",[*args,limit,offset])
            items=[]
            for row in rows:
                value=decode(row)
                if collection=='tasks': value=self.summary(value)
                elif collection=='model_responses': value={k:v for k,v in value.items() if k not in {'raw','plan'}}
                elif collection=='assets': value={k:v for k,v in value.items() if k!='path'}
                items.append(value)
            return {'items':items,'total':total,'offset':offset,'limit':limit}
        return self.response(query)

    def task(self, task_id):
        def query(db):
            task=self.get(db,'tasks',task_id)
            executions=[decode(r) for r in db.execute("SELECT data FROM objects WHERE collection='executions' AND json_extract(data,'$.task_id')=? ORDER BY json_extract(data,'$.created_at'),id",(task_id,))]
            row=db.execute("SELECT data FROM objects WHERE collection='controls' AND id=?",(task_id,)).fetchone()
            history=[]
            for r in db.execute("SELECT id,data FROM objects WHERE collection='plan_history' AND substr(id,1,?)=?",(len(task_id)+1,task_id+':')):
                history.append({'key':r['id'],**decode(r)})
            return {'task':task,'executions':executions,'control':decode(row) if row else None,'history':history}
        return self.response(query)

    def events(self,task_id,params):
        after=integer(params,'after_seq',0,0,2**63-1);limit=integer(params,'limit',100,1,500)
        def query(db):
            self.get(db,'tasks',task_id)
            rows=list(db.execute('SELECT * FROM events WHERE task=? AND seq>? ORDER BY seq LIMIT ?',(task_id,after,limit+1)))
            items=[{**dict(r),'data':decode(r)} for r in rows[:limit]]
            return {'items':items,'next_seq':items[-1]['seq'] if items else after,'has_more':len(rows)>limit}
        return self.response(query)

    def resources(self):
        def query(db):
            resources=[{**dict(r),'used':0,'owners':[]} for r in db.execute('SELECT * FROM resources ORDER BY name')]
            indexed={r['name']:r for r in resources}
            for row in db.execute('SELECT * FROM leases ORDER BY resource,owner'):
                lease=dict(row);resource=indexed.get(lease['resource'])
                if resource is None: continue
                execution=db.execute("SELECT data FROM objects WHERE collection='executions' AND id=?",(lease['owner'],)).fetchone()
                e=decode(execution) if execution else {}
                resource['used']+=lease['units'];resource['owners'].append({**lease,'task_id':e.get('task_id'),'step':e.get('step'),'status':e.get('status')})
            return {'items':resources}
        return self.response(query)

    def model(self,key): return self.response(lambda db:self.get(db,'model_responses',key))


def integer(params,key,default,low,high):
    try: value=int(params.get(key,default))
    except (ValueError,TypeError) as exc: raise ObserverError('INVALID_QUERY',f'{key} 必须为整数') from exc
    if not low<=value<=high: raise ObserverError('INVALID_QUERY',f'{key} 超出允许范围')
    return value
