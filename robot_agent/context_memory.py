"""Scoped, evidence-backed memory retrieval for model context."""

import hashlib
import time

from .contracts import require
from .memory import Memory
from .store import dumps


def record_hash(record):
    return hashlib.sha256(dumps(record).encode()).hexdigest()


def resolve_memory(store, memory_id, robot_id):
    item = store.get("memories", memory_id)
    require(item is not None, "context memory no longer exists")
    require(item["attributes"].get("robot_id") == robot_id, "memory outside robot scope")
    require(item["valid_until"] is None or item["valid_until"] > time.time(), "context memory expired")
    assets = []
    for asset_id in item["evidence"]:
        asset = store.get("assets", asset_id)
        require(asset is not None, "memory evidence asset missing")
        require(asset["metadata"].get("robot_id") == robot_id, "memory evidence outside robot scope")
        Memory(store).read(asset_id)
        assets.append({"id": asset_id, "sha256": asset["sha256"], "size": asset["size"]})
    require(bool(assets), "memory evidence required")
    return item, assets


def search_memories(store, text, robot_id, *, kind=None, limit=5):
    """Filter scope and validity before limiting; do not hide corrupt evidence."""
    require(bool(text.strip()), "search text required")
    phrase = '"' + text.replace('"', '""') + '"'
    with store.lock:
        rows = store.db.execute(
            """SELECT m.id FROM memory_search AS m
               JOIN objects AS o ON o.collection='memories' AND o.id=m.id
               WHERE memory_search MATCH ?
                 AND json_extract(o.data, '$.attributes.robot_id')=?
                 AND (? IS NULL OR json_extract(o.data, '$.kind')=?)
                 AND (json_extract(o.data, '$.valid_until') IS NULL
                      OR json_extract(o.data, '$.valid_until')>?)
               ORDER BY rank, m.id LIMIT ?""",
            (phrase, robot_id, kind, kind, time.time(), limit),
        ).fetchall()
    results = []
    for row in rows:
        item, evidence = resolve_memory(store, row["id"], robot_id)
        results.append({"memory": item, "record_hash": record_hash(item), "verified_assets": evidence,
                        "content_authority": "stored_annotation"})
    return results


def verify_bindings(store, bindings, robot_id):
    """Recheck the exact annotation and its actual bytes at use boundaries."""
    for binding in bindings:
        item, _ = resolve_memory(store, binding["memory_id"], robot_id)
        require(record_hash(item) == binding["record_hash"], "bound memory changed; retrieve and bind again")
