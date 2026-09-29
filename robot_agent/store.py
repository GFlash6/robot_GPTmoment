"""Robot control ledger. DBOS owns workflow histories, not these resource leases."""

import json
import hashlib
import fcntl
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from .contracts import require


def dumps(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


class Store:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(
            self.root / "ledger.sqlite",
            timeout=30,
            isolation_level=None,
            check_same_thread=False,
        )
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS resources(name TEXT PRIMARY KEY, capacity INTEGER NOT NULL CHECK(capacity>0));
CREATE TABLE IF NOT EXISTS leases(owner TEXT, resource TEXT REFERENCES resources(name), units INTEGER NOT NULL CHECK(units>0), PRIMARY KEY(owner,resource));
CREATE TABLE IF NOT EXISTS objects(collection TEXT, id TEXT, data TEXT NOT NULL, PRIMARY KEY(collection,id));
CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, task TEXT, type TEXT NOT NULL, data TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS events_task_seq ON events(task,seq);
CREATE VIRTUAL TABLE IF NOT EXISTS memory_search USING fts5(id UNINDEXED, text);
""")

    @contextmanager
    def transaction(self):
        with self.lock:
            # Commands wrap existing Runtime transactions in one atomic receipt.
            nested = self.db.in_transaction
            marker = "nested_" + str(time.monotonic_ns())
            self.db.execute(f"SAVEPOINT {marker}" if nested else "BEGIN IMMEDIATE")
            try:
                yield
                self.db.execute(f"RELEASE {marker}" if nested else "COMMIT")
            except BaseException:
                if nested:
                    self.db.execute(f"ROLLBACK TO {marker}")
                    self.db.execute(f"RELEASE {marker}")
                else:
                    self.db.execute("ROLLBACK")
                raise

    @contextmanager
    def task_lock(self, task_id):
        """Serialize worker transitions across connections and DBOS threads."""
        directory = self.root / "task-locks"
        directory.mkdir(exist_ok=True)
        name = hashlib.sha256(task_id.encode()).hexdigest()
        with (directory / name).open("a+") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def put(self, collection, key, value):
        with self.lock:
            self.db.execute(
                "INSERT INTO objects VALUES(?,?,?) ON CONFLICT(collection,id) DO UPDATE SET data=excluded.data",
                (collection, key, dumps(value)),
            )

    def get(self, collection, key):
        with self.lock:
            row = self.db.execute(
                "SELECT data FROM objects WHERE collection=? AND id=?",
                (collection, key),
            ).fetchone()
            return json.loads(row["data"]) if row else None

    def list(self, collection):
        with self.lock:
            return [
                json.loads(x["data"])
                for x in self.db.execute(
                    "SELECT data FROM objects WHERE collection=? ORDER BY id",
                    (collection,),
                )
            ]

    def event(self, task, kind, data):
        with self.lock:
            self.db.execute(
                "INSERT INTO events(ts,task,type,data) VALUES(?,?,?,?)",
                (time.time(), task, kind, dumps(data)),
            )

    def events(self, task):
        with self.lock:
            return [
                dict(x)
                for x in self.db.execute(
                    "SELECT * FROM events WHERE task=? ORDER BY seq", (task,)
                )
            ]

    def event_page(self, task, *, after_seq=0, through_seq=None, limit=100):
        require(type(after_seq) is int and 0 <= after_seq < 2**63, 'invalid event cursor')
        require(type(limit) is int and 1 <= limit <= 500, 'invalid event page limit')
        require(through_seq is None or (type(through_seq) is int and 0 <= through_seq < 2**63),
                'invalid event upper bound')
        with self.lock:
            latest = self.db.execute('SELECT COALESCE(MAX(seq),0) FROM events WHERE task=?', (task,)).fetchone()[0]
            upper = latest if through_seq is None else through_seq
            require(after_seq <= upper <= latest, 'event cursor outside task history')
            for boundary in {after_seq, upper} - {0}:
                require(self.db.execute('SELECT 1 FROM events WHERE task=? AND seq=?', (task, boundary)).fetchone() is not None,
                        'event cursor does not belong to task history')
            rows = list(self.db.execute('SELECT * FROM events WHERE task=? AND seq>? AND seq<=? ORDER BY seq LIMIT ?',
                (task, after_seq, upper, limit + 1)))
            events = [{**dict(row), 'data': json.loads(row['data'])} for row in rows[:limit]]
            return {'events': events, 'next_seq': events[-1]['seq'] if events else after_seq,
                    'through_seq': upper, 'has_more': len(rows) > limit}

    def set_capacity(self, name, capacity):
        require(
            isinstance(name, str)
            and "/" in name
            and type(capacity) is int
            and capacity > 0,
            "resource needs namespace/name and positive integer capacity",
        )
        with self.transaction():
            used = self.db.execute(
                "SELECT COALESCE(SUM(units),0) FROM leases WHERE resource=?", (name,)
            ).fetchone()[0]
            require(capacity >= used, "capacity below allocated units")
            self.db.execute(
                "INSERT INTO resources VALUES(?,?) ON CONFLICT(name) DO UPDATE SET capacity=excluded.capacity",
                (name, capacity),
            )

    def _acquire(self, owner, needs):
        require(
            isinstance(needs, dict)
            and all(type(v) is int and v > 0 for v in needs.values()),
            "invalid resource quantities",
        )
        existing = {
            x["resource"]: x["units"]
            for x in self.db.execute(
                "SELECT resource,units FROM leases WHERE owner=?", (owner,)
            )
        }
        if existing:
            require(existing == needs, "cannot mutate an active resource claim")
            return True
        for name, units in needs.items():
            row = self.db.execute(
                "SELECT capacity FROM resources WHERE name=?", (name,)
            ).fetchone()
            require(row is not None, f"unconfigured resource: {name}")
            used = self.db.execute(
                "SELECT COALESCE(SUM(units),0) FROM leases WHERE resource=?", (name,)
            ).fetchone()[0]
            if used + units > row[0]:
                return False
        self.db.executemany(
            "INSERT INTO leases VALUES(?,?,?)",
            [(owner, k, v) for k, v in needs.items()],
        )
        return True

    def acquire(self, owner, needs):
        with self.transaction():
            return self._acquire(owner, needs)

    def release(self, owner):
        # Internal primitive; Runtime checks an execution's terminal evidence first.
        with self.lock:
            self.db.execute("DELETE FROM leases WHERE owner=?", (owner,))

    def leases(self):
        with self.lock:
            return [
                dict(x)
                for x in self.db.execute("SELECT * FROM leases ORDER BY owner,resource")
            ]

    def close(self):
        with self.lock:
            self.db.close()
