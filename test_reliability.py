"""Offline failure injection: contracts, preserved evidence and safe telemetry."""
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import UUID

from ai_transport import AnalysisFailure, MAX_RESPONSE_BYTES, structured_response
from server import Store, analyze, create_server, process_next, validate_observation
from manage import export_records
from test_server import analysis, payload
import telemetry


def envelope(result=None, **changes):
    value = {"status": "completed", "id": "resp_fixture",
             "output": [{"type": "message", "content": [
                 {"type": "output_text", "text": json.dumps(analysis() if result is None else result)}]}]}
    return {**value, **changes}


def opener_for(value):
    return Mock(return_value=io.BytesIO(json.dumps(value).encode()))


class TransportTests(unittest.TestCase):
    def test_request_is_single_attempt_and_response_is_parsed(self):
        opener = opener_for(envelope())
        value, response_id = structured_response({"store": False}, "fake-key", opener)
        self.assertEqual(value, analysis())
        self.assertEqual(response_id, "resp_fixture")
        opener.assert_called_once()
        self.assertEqual(opener.call_args.kwargs["timeout"], 60)

    def test_failures_are_classified_without_exposing_provider_content(self):
        cases = [(TimeoutError("SECRET"), "timeout"),
                 (URLError(TimeoutError("SECRET")), "timeout"),
                 (URLError("SECRET"), "connection"),
                 (OSError("SECRET"), "connection")]
        for status, category in [(401, "authentication"), (403, "authentication"),
                                 (429, "rate_limited"), (503, "provider_unavailable"),
                                 (400, "provider_rejected")]:
            cases.append((HTTPError("https://example.invalid", status, "SECRET", {}, io.BytesIO(b"SECRET")), category))
        for error, category in cases:
            with self.subTest(category=category):
                opener = Mock(side_effect=error)
                with self.assertRaises(AnalysisFailure) as caught:
                    structured_response({}, "fake-key", opener)
                self.assertEqual(str(caught.exception), category)
                opener.assert_called_once()  # Timeout/rate limiting must not duplicate billing.

    def test_malformed_and_refused_outputs_never_become_analyses(self):
        cases = [(None, "invalid_response"),
                 (envelope(status="incomplete"), "incomplete"),
                 (envelope(output=[None]), "invalid_response"),
                 (envelope(output=[{"content": [None]}]), "invalid_response"),
                 (envelope(output=[{"content": [{"type": "refusal", "refusal": "SECRET"}]}]), "refused"),
                 (envelope(output=[{"content": [{"type": "output_text", "text": 7}]}]), "invalid_response"),
                 (envelope(output=[]), "invalid_response"),
                 (envelope(result=[]), "invalid_response")]
        for value, category in cases:
            with self.subTest(value=value):
                with self.assertRaises(AnalysisFailure) as caught:
                    structured_response({}, "fake-key", opener_for(value))
                self.assertEqual(caught.exception.category, category)

    def test_response_body_has_a_read_limit_and_invalid_json_is_rejected(self):
        class Response(io.BytesIO):
            def read(self, size=-1):
                self.requested_size = size
                return super().read(size)
        for raw, expected in [(b"x" * (MAX_RESPONSE_BYTES + 2), "response_too_large"),
                              (b"not-json", "invalid_response"), (b"\xff", "invalid_response")]:
            response = Response(raw)
            with self.assertRaises(AnalysisFailure) as caught:
                structured_response({}, "fake-key", Mock(return_value=response))
            self.assertEqual(caught.exception.category, expected)
            self.assertEqual(response.requested_size, MAX_RESPONSE_BYTES + 1)

    def test_application_schema_is_checked_after_provider_contract(self):
        row = validate_observation(payload())
        row["hint"] = row.get("hint", "uncertain")
        with self.assertRaises(AnalysisFailure) as caught:
            analyze(row, "fake-key", "mock-model", opener_for(envelope(result={"summary": "incomplete"})))
        self.assertEqual(caught.exception.category, "invalid_analysis")


class WorkerFailureTests(unittest.TestCase):
    def test_failure_preserves_evidence_blocks_export_and_logs_only_safe_metadata(self):
        for category in ("timeout", "rate_limited", "refused", "invalid_response"):
            with self.subTest(category=category), tempfile.TemporaryDirectory() as directory:
                store = Store(Path(directory) / "test.sqlite3")
                record = validate_observation(payload(feelings="PRIVATE_USER_TEXT"))
                store.insert(record)
                analyzer = Mock(side_effect=AnalysisFailure(category))
                with self.assertLogs("wainet.events", level="INFO") as captured:
                    self.assertTrue(process_next(store, "PRIVATE_API_KEY", "mock", analyzer))
                with store.connect() as db:
                    saved = db.execute("SELECT * FROM observations").fetchone()
                    self.assertEqual(saved["image"], record["image"])
                    self.assertEqual(saved["feelings"], "PRIVATE_USER_TEXT")
                    self.assertEqual(saved["status"], "failed")
                    self.assertIsNone(saved["analysis"])
                self.assertEqual(export_records(store)["record_count"], 0)
                self.assertFalse(process_next(store, "PRIVATE_API_KEY", "mock", analyzer))
                analyzer.assert_called_once()
                event = json.loads(captured.records[0].getMessage())
                self.assertEqual(event["category"], category)
                self.assertEqual(event["outcome"], "failed")
                self.assertNotIn("PRIVATE", "".join(captured.output))
                self.assertNotIn(record["id"], "".join(captured.output))


class RequestTraceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.server = create_server(0, Path(self.temp.name) / "http.sqlite3")
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def get(self, path):
        request = Request(self.url + path, headers={"X-Request-ID": "PRIVATE_CLIENT_ID",
                                                  "Cookie": "session=PRIVATE_COOKIE"})
        try:
            response = urlopen(request, timeout=3)
        except HTTPError as error:
            response = error
        with response:
            return response.status, response.headers, json.load(response)

    def test_request_ids_are_server_generated_and_urls_are_not_logged(self):
        # Wait for the event itself: HTTP body delivery can precede the finally block.
        event_ready = threading.Event()
        original = telemetry.emit
        def emit(*args, **kwargs):
            original(*args, **kwargs)
            event_ready.set()
        with self.assertLogs("wainet.events", level="INFO") as captured, patch.object(telemetry, "emit", emit):
            status, headers, body = self.get("/api/health?email=PRIVATE_EMAIL")
            self.assertTrue(event_ready.wait(3))
        self.assertEqual(status, 200)
        UUID(headers["X-Request-ID"])
        event = json.loads(captured.records[0].getMessage())
        self.assertEqual(event["request_id"], headers["X-Request-ID"])
        self.assertEqual(event["route"], "/api/health")
        self.assertNotIn("PRIVATE", "".join(captured.output))
        _, second_headers, _ = self.get("/api/health")
        self.assertNotEqual(headers["X-Request-ID"], second_headers["X-Request-ID"])

    def test_health_returns_a_safe_503_when_database_is_unavailable(self):
        with patch.object(self.server.store, "connect", side_effect=sqlite3.OperationalError("PRIVATE_DB_PATH")):
            status, headers, body = self.get("/api/health")
        self.assertEqual(status, 503)
        UUID(headers["X-Request-ID"])
        self.assertEqual(body, {"error": "Storage is temporarily unavailable."})

    def test_unknown_routes_and_methods_cannot_leak_into_events(self):
        self.assertEqual(telemetry.route_label("/PRIVATE_EMAIL?q=SECRET"), "other")
        self.assertEqual(telemetry.route_label("//[malformed"), "other")
        with self.assertRaises(ValueError):
            telemetry.emit("http_request", body="PRIVATE")


if __name__ == "__main__":
    unittest.main()
