"""Cooperative, durable file-copy skill for large data assets.

No background writer exists: each poll writes one bounded chunk and fsyncs it.
A cancel reply therefore observes an idle writer and a real partial output.
"""

import hashlib
import os
from pathlib import Path
from .contracts import require, ContractError


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def copy_step(store, operation, execution_id, args, spec):
    saved = store.get("local_results", execution_id)
    if saved is not None:
        return saved
    job = store.get("copy_jobs", execution_id)
    if job is None:
        require(operation == "start", "copy has no durable execution record")
    try:
        if job is None:
            source = Path(args["source"]).resolve(strict=True)
            target = Path(args["target"]).resolve()
            roots = [Path(p).resolve() for p in spec.get("allowed_roots", [])]
            for path in (source, target):
                require(
                    any(path == r or r in path.parents for r in roots),
                    "copy path outside allowed roots",
                )
            require(source.is_file() and source != target, "invalid copy paths")
            stat = source.stat()
            with target.open("xb") as out:
                out.flush()
                os.fsync(out.fileno())
            job = {
                "source": str(source),
                "target": str(target),
                "source_inode": stat.st_ino,
                "source_mtime_ns": stat.st_mtime_ns,
                "size": stat.st_size,
                "offset": 0,
                "target_inode": target.stat().st_ino,
                "chunk_bytes": args.get("chunk_bytes", 1024 * 1024),
            }
            store.put("copy_jobs", execution_id, job)
        source = Path(job["source"])
        target = Path(job["target"])
        stat = source.stat()
        target_stat = target.stat()
        require(
            (stat.st_ino, stat.st_mtime_ns, stat.st_size)
            == (job["source_inode"], job["source_mtime_ns"], job["size"]),
            "copy source changed",
        )
        require(
            target_stat.st_ino == job["target_inode"]
            and target_stat.st_size == job["offset"],
            "copy target changed or previous write was not checkpointed",
        )
        if operation == "cancel":
            result = {
                "execution_id": execution_id,
                "status": "canceled",
                "quiescent": True,
                "output": {"path": str(target), "bytes_copied": target_stat.st_size},
                "evidence": [{"source": target.as_uri(), "bytes": target_stat.st_size}],
            }
        else:
            with source.open("rb") as src, target.open("r+b") as dst:
                src.seek(job["offset"])
                dst.seek(job["offset"])
                data = src.read(job["chunk_bytes"])
                dst.write(data)
                dst.flush()
                os.fsync(dst.fileno())
            job["offset"] += len(data)
            store.put("copy_jobs", execution_id, job)
            if job["offset"] == job["size"]:
                actual = digest(target)
                require(actual == digest(source), "copy digest mismatch")
                result = {
                    "execution_id": execution_id,
                    "status": "succeeded",
                    "quiescent": True,
                    "output": {
                        "path": str(target),
                        "sha256": actual,
                        "size": job["size"],
                        "verified": True,
                    },
                    "evidence": [
                        {"source": target.as_uri(), "sha256": actual},
                        {"source": source.as_uri(), "sha256": actual},
                    ],
                }
            else:
                require(bool(data), "copy source ended before recorded size")
                return {
                    "execution_id": execution_id,
                    "status": "running",
                    "quiescent": False,
                    "output": {"bytes_copied": job["offset"]},
                    "evidence": [{"source": target.as_uri(), "bytes": job["offset"]}],
                }
    except (OSError, ContractError) as exc:
        result = {
            "execution_id": execution_id,
            "status": "failed",
            "quiescent": True,
            "output": {},
            "evidence": [
                {"source": "local:file.copy", "error_type": type(exc).__name__}
            ],
            "error": type(exc).__name__ + ": " + str(exc),
        }
    store.put("local_results", execution_id, result)
    return result
