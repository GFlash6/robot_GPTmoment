"""Content-verified assets and evidence-backed memory, separate from raw MCAP streams."""

import hashlib
import math
import os
import tempfile
import time
import uuid
from pathlib import Path
from .contracts import ContractError, require

KINDS = {
    "rgb",
    "depth",
    "point_cloud",
    "point_cloud_map",
    "occupancy_map",
    "voxel_map",
    "calibration",
    "transform",
    "document",
    "recording",
}
SPATIAL = {
    "rgb",
    "depth",
    "point_cloud",
    "point_cloud_map",
    "occupancy_map",
    "voxel_map",
    "transform",
}


class Memory:
    def __init__(self, store):
        self.store = store
        self.blobs = store.root / "blobs"
        self.blobs.mkdir(exist_ok=True)

    def ingest(self, path, metadata):
        require(
            isinstance(metadata, dict) and metadata.get("kind") in KINDS,
            "unsupported asset category",
        )
        for key in ("source", "encoding"):
            require(
                isinstance(metadata.get(key), str) and bool(metadata[key]),
                f"{key} required",
            )
        kind = metadata["kind"]
        if kind in SPATIAL:
            for key in ("robot_id", "frame_id", "clock_domain", "timestamp_ns"):
                require(
                    key in metadata
                    and metadata[key] is not None
                    and metadata[key] != "",
                    f"spatial asset requires {key}",
                )
            require(
                type(metadata["timestamp_ns"]) is int and metadata["timestamp_ns"] >= 0,
                "invalid timestamp_ns",
            )
        if kind.endswith("_map"):
            require(bool(metadata.get("version")), "map version required")
        for parent in metadata.get("parents", []):
            self.read(parent)
        if kind in {"rgb", "depth"}:
            calibration = self.store.get("assets", metadata.get("calibration_id", ""))
            require(
                calibration is not None
                and calibration["metadata"]["kind"] == "calibration",
                "real calibration asset required",
            )
            self.read(calibration["id"])
        source = Path(path).resolve(strict=True)
        require(source.is_file(), "asset source must be a file")
        fd, staging = tempfile.mkstemp(dir=self.blobs, prefix=".ingest-")
        digest = hashlib.sha256()
        size = 0
        try:
            with os.fdopen(fd, "wb") as dst, source.open("rb") as src:
                for chunk in iter(lambda: src.read(1024 * 1024), b""):
                    dst.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
                dst.flush()
                os.fsync(dst.fileno())
            target = self.blobs / digest.hexdigest()
            # Replacement also repairs a corrupted existing blob with identical original content.
            os.replace(staging, target)
            directory = os.open(self.blobs, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if os.path.exists(staging):
                os.unlink(staging)
        asset = {
            "id": str(uuid.uuid4()),
            "sha256": digest.hexdigest(),
            "size": size,
            "path": str(target),
            "metadata": metadata,
            "created_at": time.time(),
        }
        self.store.put("assets", asset["id"], asset)
        return asset

    def read(self, asset_id):
        a = self.store.get("assets", asset_id)
        require(a is not None, f"unknown asset: {asset_id}")
        try:
            data = Path(a["path"]).read_bytes()
        except OSError as exc:
            raise ContractError(f"asset unavailable: {asset_id}") from exc
        require(
            hashlib.sha256(data).hexdigest() == a["sha256"] and len(data) == a["size"],
            f"asset integrity failed: {asset_id}",
        )
        return data

    def remember(self, kind, text, attributes, evidence, valid_until=None):
        require(
            isinstance(kind, str)
            and bool(kind)
            and isinstance(text, str)
            and bool(text.strip()),
            "memory kind and text required",
        )
        require(
            isinstance(attributes, dict)
            and isinstance(evidence, list)
            and bool(evidence),
            "memory needs attributes and real evidence",
        )
        require(
            valid_until is None
            or (type(valid_until) in (int, float) and math.isfinite(valid_until)),
            "valid_until must be a finite epoch time",
        )
        for asset_id in evidence:
            self.read(asset_id)
        entry = {
            "id": str(uuid.uuid4()),
            "kind": kind,
            "text": text,
            "attributes": attributes,
            "evidence": evidence,
            "created_at": time.time(),
            "valid_until": valid_until,
        }
        with self.store.transaction():
            self.store.put("memories", entry["id"], entry)
            self.store.db.execute(
                "INSERT INTO memory_search VALUES(?,?)", (entry["id"], text)
            )
        return entry

    def search(self, text, kind=None, robot_id=None):
        require(isinstance(text, str) and bool(text.strip()), "search text required")
        with self.store.lock:
            ids = [
                x[0]
                for x in self.store.db.execute(
                    "SELECT id FROM memory_search WHERE memory_search MATCH ?",
                    ('"' + text.replace('"', '""') + '"',),
                )
            ]
        results = []
        for key in ids:
            item = self.store.get("memories", key)
            if kind and item["kind"] != kind:
                continue
            if item["valid_until"] is not None and item["valid_until"] <= time.time():
                continue
            if robot_id and item["attributes"].get("robot_id") != robot_id:
                continue
            for asset in item["evidence"]:
                self.read(asset)
            results.append(item)
        return results

    def query_assets(
        self,
        kind=None,
        robot_id=None,
        frame_id=None,
        start_ns=None,
        end_ns=None,
        version=None,
    ):
        require(kind is None or kind in KINDS, "unsupported asset category")
        require(
            all(x is None or (type(x) is int and x >= 0) for x in (start_ns, end_ns)),
            "invalid time range",
        )
        require(
            start_ns is None or end_ns is None or start_ns <= end_ns,
            "reversed time range",
        )
        found = []
        for asset in self.store.list("assets"):
            m = asset["metadata"]
            if any(
                v is not None and m.get(k) != v
                for k, v in [
                    ("kind", kind),
                    ("robot_id", robot_id),
                    ("frame_id", frame_id),
                    ("version", version),
                ]
            ):
                continue
            ts = m.get("timestamp_ns")
            if start_ns is not None and (type(ts) is not int or ts < start_ns):
                continue
            if end_ns is not None and (type(ts) is not int or ts > end_ns):
                continue
            found.append(asset)
        return found
