"""Collector tests are offline; prove numeric filtering and failure visibility."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("collector", Path(__file__).parents[1] / "collect_metrics.py")
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)


class MetricsTests(unittest.TestCase):
    def test_docker_failure_is_visible_and_does_not_print_error_or_secret(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(collector, "command", side_effect=OSError("password=secret")):
                content, ok = collector.collect("vistaverse", Path(directory))
        self.assertFalse(ok)
        self.assertIn("vistaverse_collect_success 0", content)
        self.assertIn('vistaverse_container_running{service="api"} 0', content)
        self.assertNotIn("secret", content)

    def test_numeric_metrics_and_redis_errors(self):
        containers = "\n".join(json.dumps({
            "service": s, "running": True, "restarts": 0, "health": "healthy", "id": s,
        }) for s in collector.SERVICES)
        def fake(*args, **kwargs):
            if args[1] == "ps":
                return "1 2 3 4 5"
            if args[1] == "inspect":
                return json.dumps([{
                    "Config": {"Labels": {"com.docker.compose.service": s}},
                    "State": {"Running": True, "Health": {"Status": "healthy"}},
                    "RestartCount": 0, "Id": s,
                } for s in collector.SERVICES])
            return ("used_memory:100\nmaxmemory:1000\nevicted_keys:0\n"
                    "rejected_connections:0\naof_enabled:1\naof_last_write_status:ok\n"
                    "aof_last_bgrewrite_status:ok\n12\n2")
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(collector, "command", fake):
                content, ok = collector.collect("vistaverse", Path(directory))
        self.assertTrue(ok)
        self.assertIn("vistaverse_oss_pending 12", content)
        self.assertIn("vistaverse_oss_quarantined 2", content)
        self.assertIn("vistaverse_backup_timestamp_seconds 0", content)
        with self.assertRaises(ValueError):
            collector.number("nan")

    def test_only_completed_reports_count_and_output_is_atomic(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            batch = root / "batch"
            batch.mkdir()
            report = batch / "restore-report.json"
            report.write_text(json.dumps({"restore_complete": False, "completed_at_unix": 10}))
            self.assertEqual(collector.latest_report(root, report.name, "restore_complete"), 0)
            report.write_text(json.dumps({"restore_complete": True, "completed_at_unix": 10}))
            self.assertEqual(collector.latest_report(root, report.name, "restore_complete"), 10)
            output = root / "metrics.prom"
            collector.write_metrics(output, "vistaverse_collect_success 1\n")
            self.assertEqual(output.read_text(), "vistaverse_collect_success 1\n")
            self.assertFalse(list(root.glob(".vistaverse-*")))


if __name__ == "__main__":
    unittest.main()
