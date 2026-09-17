import tempfile
import unittest
from pathlib import Path


class ContractsAndMemory(unittest.TestCase):
    def test_framework_modules_available(self):
        import importlib.util

        self.assertIsNotNone(
            importlib.util.find_spec("robot_agent"), "framework missing"
        )

    def test_success_requires_observed_output_and_quiescence(self):
        from robot_agent.contracts import check_result, ContractError

        spec = {
            "output_schema": {"type": "object", "required": ["digest"]},
            "checks": [{"path": "digest", "op": "nonempty"}],
        }
        with self.assertRaises(ContractError):
            check_result(spec, {"status": "succeeded"}, "e1")
        with self.assertRaises(ContractError):
            check_result(
                spec,
                {
                    "execution_id": "e1",
                    "status": "succeeded",
                    "quiescent": False,
                    "output": {"digest": "abc"},
                    "evidence": [{"source": "file"}],
                },
                "e1",
            )

    def test_real_asset_integrity_and_evidence_references(self):
        from robot_agent.store import Store
        from robot_agent.memory import Memory
        from robot_agent.contracts import ContractError

        with tempfile.TemporaryDirectory() as d:
            s = Store(Path(d) / "state")
            m = Memory(s)
            p = Path(d) / "source.txt"
            p.write_text("recorded task instructions", encoding="utf8")
            a = m.ingest(
                str(p), {"kind": "document", "source": "operator", "encoding": "utf8"}
            )
            self.assertEqual(m.read(a["id"]), p.read_bytes())
            with self.assertRaises(ContractError):
                m.remember("place", "workroom", {}, ["missing"])
            n = m.remember("place", "workroom", {"label": "工作间"}, [a["id"]])
            self.assertEqual(m.search("workroom")[0]["id"], n["id"])
            Path(a["path"]).write_bytes(b"corrupted")
            with self.assertRaises(ContractError):
                m.read(a["id"])
            s.close()

    def test_missing_spatial_metadata_is_rejected(self):
        from robot_agent.store import Store
        from robot_agent.memory import Memory
        from robot_agent.contracts import ContractError

        with tempfile.TemporaryDirectory() as d:
            s = Store(Path(d) / "state")
            p = Path(d) / "points.bin"
            p.write_bytes(bytes(range(32)))
            with self.assertRaises(ContractError):
                Memory(s).ingest(
                    str(p),
                    {"kind": "point_cloud", "source": "sensor", "encoding": "xyz32"},
                )
            s.close()

    def test_dag_rejects_cycles_and_unverified_completion(self):
        from robot_agent.contracts import validate_plan, ContractError

        catalog = {"read": {"input_schema": {"type": "object"}}}
        with self.assertRaises(ContractError):
            validate_plan(
                {
                    "steps": [
                        {"id": "a", "skill": "read", "args": {}, "deps": ["b"]},
                        {"id": "b", "skill": "read", "args": {}, "deps": ["a"]},
                    ],
                    "verification": "b",
                },
                catalog,
            )
        with self.assertRaises(ContractError):
            validate_plan(
                {"steps": [{"id": "a", "skill": "read", "args": {}}]}, catalog
            )

    def test_resource_claim_is_atomic_and_durable(self):
        from robot_agent.store import Store

        with tempfile.TemporaryDirectory() as d:
            s = Store(Path(d))
            s.set_capacity("r1/base", 1)
            s.set_capacity("r1/gpu", 2)
            self.assertTrue(s.acquire("a", {"r1/base": 1}))
            self.assertFalse(s.acquire("b", {"r1/gpu": 1, "r1/base": 1}))
            self.assertEqual([x["owner"] for x in s.leases()], ["a"])
            s.close()
            s = Store(Path(d))
            self.assertFalse(s.acquire("b", {"r1/base": 1}))
            s.release("a")
            self.assertTrue(s.acquire("b", {"r1/base": 1}))
            s.close()


class MemoryQuery(unittest.TestCase):
    def test_queries_filter_real_assets_and_reject_dangling_calibration(self):
        from robot_agent.store import Store
        from robot_agent.memory import Memory
        from robot_agent.contracts import ContractError

        with tempfile.TemporaryDirectory() as d:
            s = Store(Path(d) / "state")
            m = Memory(s)
            p = Path(__file__)
            asset = m.ingest(
                p,
                {
                    "kind": "document",
                    "source": "test-source-file",
                    "encoding": "utf8",
                    "robot_id": "r1",
                    "timestamp_ns": 15,
                },
            )
            self.assertEqual(
                [
                    a["id"]
                    for a in m.query_assets(robot_id="r1", start_ns=10, end_ns=20)
                ],
                [asset["id"]],
            )
            self.assertEqual(m.query_assets(robot_id="r2"), [])
            with self.assertRaises(ContractError):
                m.remember(
                    "note", "file evidence", {}, [asset["id"]], valid_until="not a time"
                )
            s.close()


class StopEvidence(unittest.TestCase):
    def test_malformed_terminal_provenance_is_rejected_for_every_outcome(self):
        from robot_agent.contracts import check_terminal, ContractError

        for status in ("succeeded", "failed", "canceled"):
            for source in (123, "   ", None):
                with (
                    self.subTest(status=status, source=source),
                    self.assertRaises(ContractError),
                ):
                    check_terminal(
                        {
                            "execution_id": "e",
                            "status": status,
                            "quiescent": True,
                            "evidence": [{"source": source}],
                        },
                        "e",
                    )
