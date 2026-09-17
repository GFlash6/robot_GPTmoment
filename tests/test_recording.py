from pathlib import Path


def test_mcap_preserves_actual_file_bytes_and_timestamps(tmp_path):
    from robot_agent.recording import Recorder, messages

    raw = Path(__file__).read_bytes()
    target = tmp_path / "observations.mcap"
    with Recorder(target) as recorder:
        recorder.append(
            "/documents/test",
            "text/plain",
            raw,
            123456789,
            123456790,
            {"kind": "document", "source": str(Path(__file__))},
        )
    records = list(messages(target))
    assert len(records) == 1
    assert records[0]["data"] == raw
    assert records[0]["publish_time"] == 123456789
    assert records[0]["log_time"] == 123456790
    assert records[0]["metadata"]["kind"] == "document"
