"""Use installed rosbag2 storage plugins; never fabricate missing sensor streams."""

import hashlib
import json
import os
import signal
import subprocess
import time
from pathlib import Path
from .contracts import require, ContractError


def discover(wait=1.0):
    import rclpy
    from rclpy.context import Context

    context = Context()
    rclpy.init(context=context)
    node = rclpy.create_node("robot_agent_discovery", context=context)
    from rclpy.executors import SingleThreadedExecutor

    executor = SingleThreadedExecutor(context=context)
    executor.add_node(node)
    try:
        end = time.monotonic() + wait
        while time.monotonic() < end:
            executor.spin_once(timeout_sec=0.1)
        return dict(node.get_topic_names_and_types())
    finally:
        executor.shutdown()
        node.destroy_node()
        rclpy.shutdown(context=context)


def record(topics, output, duration, robot_id, storage="sqlite3", use_sim_time=False):
    require(
        isinstance(topics, list)
        and bool(topics)
        and all(isinstance(t, str) and t.startswith("/") for t in topics),
        "explicit absolute ROS2 topics required",
    )
    require(
        type(duration) in (int, float) and 0 < duration <= 86400,
        "duration must be 0..86400 seconds",
    )
    require(isinstance(robot_id, str) and bool(robot_id), "robot_id required")
    require(storage in {"sqlite3", "mcap"}, "supported storage: sqlite3 or mcap")
    import rosbag2_py

    require(
        storage in rosbag2_py.get_registered_writers(),
        f"rosbag2 storage plugin not installed: {storage}",
    )
    found = discover()
    require(
        all(t in found for t in topics),
        "requested topics are absent: "
        + ", ".join(t for t in topics if t not in found),
    )
    output = Path(output).resolve()
    require(not output.exists(), "recording destination already exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ros2",
        "bag",
        "record",
        "--storage",
        storage,
        "--output",
        str(output),
        *topics,
    ]
    if use_sim_time:
        command.append("--use-sim-time")
    log_path = output.parent / (output.name + ".recorder.log")
    with log_path.open("x") as log:
        proc = subprocess.Popen(
            command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True
        )
        try:
            deadline = time.monotonic() + duration
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    break
                time.sleep(min(0.1, max(0, deadline - time.monotonic())))
        finally:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGINT)
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
                raise ContractError(
                    "rosbag2 failed to finalize; retained files are not verified"
                )
    require(
        proc.returncode in (0, -signal.SIGINT),
        "rosbag2 exited with error; inspect " + str(log_path),
    )
    reader = rosbag2_py.SequentialReader()
    reader.open(
        rosbag2_py.StorageOptions(uri=str(output), storage_id=storage),
        rosbag2_py.ConverterOptions("", ""),
    )
    counts = {t: 0 for t in topics}
    while reader.has_next():
        topic, data, stamp = reader.read_next()
        if topic in counts:
            counts[topic] += 1
    del reader
    files = []
    for p in sorted(output.iterdir()):
        if not p.is_file():
            continue
        h = hashlib.sha256()
        with p.open("rb") as src:
            for chunk in iter(lambda: src.read(1024 * 1024), b""):
                h.update(chunk)
        files.append(
            {"file": p.name, "sha256": h.hexdigest(), "size": p.stat().st_size}
        )
    result = {
        "robot_id": robot_id,
        "storage": storage,
        "topics": found,
        "message_counts": counts,
        "files": files,
        "use_sim_time": use_sim_time,
        "status": "succeeded" if all(counts.values()) else "failed",
    }
    (output / "robot-agent-manifest.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    )
    require(
        all(counts.values()),
        "one or more requested topics produced zero actual messages; recording retained as failed",
    )
    return result
