import tempfile
import unittest
from contextlib import asynccontextmanager
from pathlib import Path

import httpx

from backend.app import create_app
from src.control_plane.config import Settings
from src.control_plane.storage import ControlPlaneStore


class ChunkedBody(httpx.AsyncByteStream):
    def __init__(self, chunks):
        self.chunks = chunks

    async def __aiter__(self):
        for chunk in self.chunks:
            yield chunk


class ControlPlaneAPITests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        settings = Settings.from_mapping(
            {
                "ZASI_PROFILE": "local",
                "ZASI_API_KEY": "test-bootstrap-secret",
                "ZASI_CORS_ORIGINS": "http://localhost:5173",
                "ZASI_DATABASE_PATH": str(Path(self.tempdir.name) / "control-plane.db"),
            }
        )
        self.store = ControlPlaneStore(settings.database_path)
        self.app = create_app(settings=settings, store=self.store)

    async def asyncTearDown(self):
        self.store.close()
        self.tempdir.cleanup()

    @asynccontextmanager
    async def client(self):
        async with self.app.router.lifespan_context(self.app):
            transport = httpx.ASGITransport(app=self.app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as client:
                yield client

    async def test_session_requires_bootstrap_secret_and_returns_scoped_token(self):
        async with self.client() as client:
            rejected = await client.post(
                "/api/v2/sessions",
                json={"api_key": "wrong-secret"},
            )
            self.assertEqual(rejected.status_code, 401)
            self.assertEqual(rejected.json()["error"]["code"], "AUTH_REQUIRED")

            response = await client.post(
                "/api/v2/sessions",
                json={"api_key": "test-bootstrap-secret"},
            )
            self.assertEqual(response.status_code, 201)
            body = response.json()
            self.assertEqual(body["tenant_id"], "local")
            self.assertEqual(body["principal_id"], "local-operator")
            self.assertNotIn("test-bootstrap-secret", response.text)
            self.assertTrue(body["access_token"])

            current = await client.get(
                "/api/v2/sessions/current",
                headers={"Authorization": f"Bearer {body['access_token']}"},
            )
            self.assertEqual(current.status_code, 200)
            self.assertEqual(current.json()["tenant_id"], "local")
            self.assertIn("workspace:write", current.json()["scopes"])
            memory = await client.post(
                "/api/v2/memory",
                json={"content": "durable workspace note"},
                headers={"Authorization": f"Bearer {body['access_token']}"},
            )
            self.assertEqual(memory.status_code, 201)
            deleted = await client.delete(
                f"/api/v2/memory/{memory.json()['memory_id']}",
                headers={"Authorization": f"Bearer {body['access_token']}"},
            )
            self.assertEqual(deleted.status_code, 200)

    async def test_chunked_request_body_is_bounded_before_json_parsing(self):
        settings = Settings.from_mapping(
            {
                "ZASI_PROFILE": "local",
                "ZASI_API_KEY": "test-bootstrap-secret",
                "ZASI_CORS_ORIGINS": "http://localhost:5173",
                "ZASI_DATABASE_PATH": str(Path(self.tempdir.name) / "small-body.db"),
                "ZASI_MAX_BODY": "64",
            }
        )
        store = ControlPlaneStore(settings.database_path)
        app = create_app(settings=settings, store=store)
        try:
            async with app.router.lifespan_context(app):
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(
                    transport=transport, base_url="http://testserver"
                ) as client:
                    response = await client.post(
                        "/api/v2/sessions",
                        content=ChunkedBody([b'{"api_key":"', b"x" * 128, b'"}']),
                        headers={"Content-Type": "application/json"},
                    )
                    self.assertEqual(response.status_code, 413)
                    self.assertEqual(response.json()["error"]["code"], "REQUEST_TOO_LARGE")
        finally:
            store.close()

    async def test_openapi_is_authenticated_and_declares_bearer_security(self):
        async with self.client() as client:
            unauthenticated = await client.get("/api/v2/openapi.json")
            self.assertEqual(unauthenticated.status_code, 401)
            session = await client.post(
                "/api/v2/sessions", json={"api_key": "test-bootstrap-secret"}
            )
            headers = {"Authorization": f"Bearer {session.json()['access_token']}"}
            document = await client.get("/api/v2/openapi.json", headers=headers)
            self.assertEqual(document.status_code, 200)
            self.assertIn("BearerAuth", document.json()["components"]["securitySchemes"])
            self.assertEqual(
                document.json()["paths"]["/api/v2/capabilities"]["get"]["security"],
                [{"BearerAuth": []}],
            )

    async def test_json_contract_rejects_malformed_body_and_wrong_media_type(self):
        async with self.client() as client:
            malformed = await client.post(
                "/api/v2/sessions",
                content=b"{",
                headers={"Content-Type": "application/json"},
            )
            self.assertEqual(malformed.status_code, 400)
            self.assertEqual(malformed.json()["error"]["code"], "MALFORMED_JSON")
            wrong_type = await client.post(
                "/api/v2/sessions",
                content=b"{}",
                headers={"Content-Type": "text/plain"},
            )
            self.assertEqual(wrong_type.status_code, 415)
            self.assertEqual(wrong_type.json()["error"]["code"], "UNSUPPORTED_MEDIA_TYPE")

    async def test_unauthenticated_stream_and_mutation_are_rejected(self):
        async with self.client() as client:
            stream = await client.get("/api/v2/events")
            self.assertEqual(stream.status_code, 401)
            self.assertEqual(stream.json()["error"]["code"], "AUTH_REQUIRED")

            legacy_mutation = await client.get("/api/tick")
            self.assertEqual(legacy_mutation.status_code, 410)

    async def test_readiness_reports_local_dependencies(self):
        async with self.client() as client:
            response = await client.get("/health/ready")
            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertEqual(body["status"], "ready")
            self.assertEqual(body["checks"]["database"], "ready")
            self.assertEqual(body["checks"]["redis"], "disabled")

    async def test_invalid_audit_cursor_is_a_bounded_client_error(self):
        async with self.client() as client:
            session = await client.post(
                "/api/v2/sessions", json={"api_key": "test-bootstrap-secret"}
            )
            headers = {"Authorization": f"Bearer {session.json()['access_token']}"}
            response = await client.get(
                "/api/v2/audit?after=not-a-timestamp",
                headers=headers,
            )
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json()["error"]["code"], "INVALID_CURSOR")

    async def test_intent_plan_and_scoped_event_replay_are_read_only_until_run(self):
        async with self.client() as client:
            session_response = await client.post(
                "/api/v2/sessions",
                json={"api_key": "test-bootstrap-secret"},
            )
            session = session_response.json()
            headers = {"Authorization": f"Bearer {session['access_token']}"}
            payload = {
                "source_kind": "text",
                "source_text": "show system status",
                "goal": {
                    "verb": "observe",
                    "object": "system.status",
                    "parameters": {},
                },
                "requested_mode": "observe",
                "requested_risk_tier": "R0",
            }
            intent = await client.post("/api/v2/intents", json=payload, headers=headers)
            self.assertEqual(intent.status_code, 201)
            intent_body = intent.json()
            self.assertEqual(intent_body["status"], "created")

            plan = await client.post(
                f"/api/v2/intents/{intent_body['intent_id']}/plan",
                headers=headers,
            )
            self.assertEqual(plan.status_code, 201)
            self.assertEqual(plan.json()["steps"][0]["side_effect"], "none")

            run = await client.post(
                f"/api/v2/plans/{plan.json()['plan_id']}/run",
                headers={**headers, "Idempotency-Key": "plan-run-1"},
            )
            self.assertEqual(run.status_code, 200)
            self.assertEqual(run.json()["status"], "succeeded")

            forbidden_get = await client.get(
                f"/api/v2/intents/{intent_body['intent_id']}/plan",
                headers=headers,
            )
            self.assertEqual(forbidden_get.status_code, 405)

            events = await client.get(
                "/api/v2/events?after=0",
                headers=headers,
            )
            self.assertEqual(events.status_code, 200)
            self.assertEqual(events.headers["content-type"], "text/event-stream; charset=utf-8")
            self.assertIn("intent.created", events.text)
            self.assertIn("resync", events.text.lower())

    async def test_event_stream_requires_authoritative_resync_after_retention_gap(self):
        async with self.client() as client:
            session_response = await client.post(
                "/api/v2/sessions",
                json={"api_key": "test-bootstrap-secret"},
            )
            session = session_response.json()
            headers = {"Authorization": f"Bearer {session['access_token']}"}
            payload = {
                "source_kind": "text",
                "source_text": "show system status",
                "goal": {
                    "verb": "observe",
                    "object": "system.status",
                    "parameters": {},
                },
                "requested_mode": "observe",
                "requested_risk_tier": "R0",
            }
            await client.post("/api/v2/intents", json=payload, headers=headers)
            await client.post(
                "/api/v2/intents/not-used/plan",
                headers=headers,
            )
            self.store.append_audited_event(
                tenant_id="local",
                actor_kind="system",
                actor_id="test",
                action="test.event",
                target="test",
                outcome="success",
                event_type="test.event",
                aggregate_kind="test",
                aggregate_id="test",
                payload={"test": True},
            )
            for outbox in self.store.list_outbox():
                if outbox["status"] == "pending":
                    self.store.claim_outbox(outbox["id"])
                    self.store.finish_outbox(outbox["id"], success=True)
            self.store.prune_events("local", retain_latest=1)
            events = await client.get("/api/v2/events?after=0", headers=headers)
            self.assertEqual(events.status_code, 200)
            self.assertIn("resync.required", events.text)
            self.assertIn("snapshot_ref", events.text)

    async def test_tool_calls_are_brokered_typed_and_idempotent(self):
        async with self.client() as client:
            session_response = await client.post(
                "/api/v2/sessions",
                json={"api_key": "test-bootstrap-secret"},
            )
            session = session_response.json()
            headers = {"Authorization": f"Bearer {session['access_token']}"}
            preview = await client.post(
                "/api/v2/tools/preview",
                json={
                    "tool_id": "registry.system.status",
                    "requested_risk_tier": "R0",
                    "payload": {},
                },
                headers=headers,
            )
            self.assertEqual(preview.status_code, 200)
            self.assertEqual(preview.json()["decision"], "allow")

            first = await client.post(
                "/api/v2/tools/call",
                json={
                    "tool_id": "registry.system.status",
                    "requested_risk_tier": "R0",
                    "payload": {},
                },
                headers={**headers, "Idempotency-Key": "status-1"},
            )
            self.assertEqual(first.status_code, 200)
            self.assertEqual(first.json()["status"], "succeeded")
            self.assertEqual(first.json()["evidence"]["status"], "verified")
            provenance = first.json()["evidence"]["provenance"]
            for field in ("source", "observed_at", "fresh_until", "input_digest", "output_digest", "method_ref"):
                self.assertIn(field, provenance)

            second = await client.post(
                "/api/v2/tools/call",
                json={
                    "tool_id": "registry.system.status",
                    "requested_risk_tier": "R0",
                    "payload": {},
                },
                headers={**headers, "Idempotency-Key": "status-1"},
            )
            self.assertEqual(second.status_code, 200)
            self.assertEqual(second.json()["run_id"], first.json()["run_id"])

            missing_key = await client.post(
                "/api/v2/tools/call",
                json={
                    "tool_id": "registry.system.status",
                    "requested_risk_tier": "R0",
                    "payload": {},
                },
                headers=headers,
            )
            self.assertEqual(missing_key.status_code, 400)
            self.assertEqual(missing_key.json()["error"]["code"], "IDEMPOTENCY_REQUIRED")

            cursor_mismatch = await client.get(
                "/api/v2/events?after=0",
                headers={**headers, "X-ZASI-Event-Cursor": "1"},
            )
            self.assertEqual(cursor_mismatch.status_code, 400)
            self.assertEqual(cursor_mismatch.json()["error"]["code"], "CURSOR_MISMATCH")

            header_only_resume = await client.get(
                "/api/v2/events",
                headers={**headers, "Last-Event-ID": "1"},
            )
            self.assertEqual(header_only_resume.status_code, 200)
            self.assertIn("stream.end", header_only_resume.text)

    async def test_audit_session_revoke_and_safe_read_models(self):
        async with self.client() as client:
            session_response = await client.post(
                "/api/v2/sessions", json={"api_key": "test-bootstrap-secret"}
            )
            session = session_response.json()
            headers = {"Authorization": f"Bearer {session['access_token']}"}
            audit = await client.get("/api/v2/audit", headers=headers)
            self.assertEqual(audit.status_code, 200)
            self.assertTrue(any(item["action"] == "session.created" for item in audit.json()["records"]))
            self.assertIsInstance(audit.json()["next_cursor"], str)
            audit_page = await client.get(
                "/api/v2/audit",
                params={"after": audit.json()["next_cursor"]},
                headers=headers,
            )
            self.assertEqual(audit_page.status_code, 200)
            self.assertEqual(audit_page.json()["records"], [])
            self.assertIsNone(audit_page.json()["next_cursor"])

            briefing = await client.post("/api/v2/briefings", json={}, headers=headers)
            self.assertEqual(briefing.status_code, 201)
            self.assertEqual(briefing.json()["content"]["status"], "unavailable")
            self.assertIn("disclosure", briefing.json()["content"])

            artifact = await client.post(
                "/api/v2/artifacts",
                content=b"bounded fixture",
                headers={**headers, "Content-Type": "text/plain"},
            )
            self.assertEqual(artifact.status_code, 201)
            artifact_body = artifact.json()
            self.assertTrue(artifact_body["digest"].startswith("sha256:"))
            self.assertNotIn("artifacts", artifact.text)
            fetched = await client.get(
                f"/api/v2/artifacts/{artifact_body['artifact_id']}", headers=headers
            )
            self.assertEqual(fetched.status_code, 200)
            self.assertEqual(fetched.json()["status"], "quarantined")

            revoked = await client.post("/api/v2/sessions/revoke", headers=headers)
            self.assertEqual(revoked.status_code, 200)
            current = await client.get("/api/v2/sessions/current", headers=headers)
            self.assertEqual(current.status_code, 401)

    async def test_governed_mcp_discovery_and_read_call(self):
        async with self.client() as client:
            session_response = await client.post(
                "/api/v2/sessions", json={"api_key": "test-bootstrap-secret"}
            )
            token = session_response.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}
            initialize = await client.post(
                "/api/v2/mcp",
                json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                headers=headers,
            )
            self.assertEqual(initialize.status_code, 200)
            self.assertEqual(initialize.json()["result"]["serverInfo"]["name"], "zasi-governed-control-plane")

            listed = await client.post(
                "/api/v2/mcp",
                json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
                headers=headers,
            )
            self.assertEqual(listed.status_code, 200)
            self.assertEqual(listed.json()["result"]["tools"][0]["name"], "registry.system.status")

            called = await client.post(
                "/api/v2/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {"name": "registry.system.status", "arguments": {}},
                },
                headers={**headers, "Idempotency-Key": "mcp-status-1"},
            )
            self.assertEqual(called.status_code, 200)
            self.assertEqual(called.json()["result"]["status"], "succeeded")

    async def test_plan_approval_cannot_be_added_to_read_only_plan(self):
        async with self.client() as client:
            session_response = await client.post(
                "/api/v2/sessions", json={"api_key": "test-bootstrap-secret"}
            )
            session = session_response.json()
            headers = {"Authorization": f"Bearer {session['access_token']}"}
            intent = await client.post(
                "/api/v2/intents",
                json={
                    "source_kind": "text",
                    "source_text": "show system status",
                    "goal": {"verb": "observe", "object": "system.status", "parameters": {}},
                    "requested_mode": "observe",
                    "requested_risk_tier": "R0",
                },
                headers=headers,
            )
            plan = await client.post(
                f"/api/v2/intents/{intent.json()['intent_id']}/plan", headers=headers
            )
            response = await client.post(
                f"/api/v2/plans/{plan.json()['plan_id']}/approve",
                json={"digest": plan.json()["digest"], "reason": "not needed"},
                headers=headers,
            )
            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.json()["error"]["code"], "APPROVAL_NOT_REQUIRED")

    async def test_device_pairing_is_one_time_scoped_and_revocable(self):
        async with self.client() as client:
            session_response = await client.post(
                "/api/v2/sessions", json={"api_key": "test-bootstrap-secret"}
            )
            headers = {"Authorization": f"Bearer {session_response.json()['access_token']}"}
            start = await client.post(
                "/api/v2/mobile/pair",
                json={"device_label": "test-phone"},
                headers={**headers, "Idempotency-Key": "pair-phone-1"},
            )
            self.assertEqual(start.status_code, 201)
            pairing = start.json()
            self.assertTrue(pairing["challenge"])
            self.assertNotIn("challenge_hash", start.text)

            replay_start = await client.post(
                "/api/v2/mobile/pair",
                json={"device_label": "test-phone"},
                headers={**headers, "Idempotency-Key": "pair-phone-1"},
            )
            self.assertEqual(replay_start.status_code, 409)
            self.assertEqual(replay_start.json()["error"]["code"], "PAIRING_CONFLICT")

            approved = await client.post(
                f"/api/v2/mobile/{pairing['device_id']}/approve",
                json={"challenge": pairing["challenge"]},
                headers={**headers, "Idempotency-Key": "approve-phone-1"},
            )
            self.assertEqual(approved.status_code, 200)
            self.assertEqual(approved.json()["status"], "active")

            replay = await client.post(
                f"/api/v2/mobile/{pairing['device_id']}/approve",
                json={"challenge": pairing["challenge"]},
                headers={**headers, "Idempotency-Key": "approve-phone-2"},
            )
            self.assertEqual(replay.status_code, 404)

            devices = await client.get("/api/v2/devices", headers=headers)
            self.assertEqual(devices.status_code, 200)
            self.assertEqual(len(devices.json()["devices"]), 1)
            revoked = await client.post(
                f"/api/v2/devices/{pairing['device_id']}/revoke",
                headers={**headers, "Idempotency-Key": "device-revoke-1"},
            )
            self.assertEqual(revoked.status_code, 200)
            self.assertEqual(revoked.json()["status"], "revoked")

    async def test_sequences_and_unavailable_analysis_are_governed(self):
        async with self.client() as client:
            session_response = await client.post(
                "/api/v2/sessions", json={"api_key": "test-bootstrap-secret"}
            )
            headers = {"Authorization": f"Bearer {session_response.json()['access_token']}"}
            sequence = await client.post(
                "/api/v2/sequences",
                json={
                    "name": "read status",
                    "steps": [
                        {"tool_id": "registry.system.status", "risk_tier": "R0", "payload": {}}
                    ],
                },
                headers=headers,
            )
            self.assertEqual(sequence.status_code, 201)
            sequence_body = sequence.json()
            validated = await client.post(
                f"/api/v2/sequences/{sequence_body['sequence_id']}/validate",
                headers=headers,
            )
            self.assertEqual(validated.status_code, 200)
            run = await client.post(
                f"/api/v2/sequences/{sequence_body['sequence_id']}/run",
                headers={**headers, "Idempotency-Key": "sequence-run-1"},
            )
            self.assertEqual(run.status_code, 200)
            self.assertEqual(run.json()["status"], "completed")
            replay = await client.post(
                f"/api/v2/sequences/{sequence_body['sequence_id']}/run",
                headers={**headers, "Idempotency-Key": "sequence-run-1"},
            )
            self.assertEqual(replay.status_code, 200)
            self.assertEqual(
                replay.json()["sequence_run_id"], run.json()["sequence_run_id"]
            )
            self.assertEqual(replay.json()["status"], "completed")

            artifact = await client.post(
                "/api/v2/artifacts",
                content=b"cad fixture",
                headers={**headers, "Content-Type": "model/step"},
            )
            analysis = await client.post(
                "/api/v2/cad/analyze",
                json={"artifact_id": artifact.json()["artifact_id"]},
                headers=headers,
            )
            self.assertEqual(analysis.status_code, 201)
            self.assertEqual(analysis.json()["evidence"]["status"], "unavailable")

    async def test_evidence_correction_is_append_only_and_cannot_claim_verified(self):
        async with self.client() as client:
            session_response = await client.post(
                "/api/v2/sessions", json={"api_key": "test-bootstrap-secret"}
            )
            headers = {"Authorization": f"Bearer {session_response.json()['access_token']}"}
            call = await client.post(
                "/api/v2/tools/call",
                json={
                    "tool_id": "registry.system.status",
                    "requested_risk_tier": "R0",
                    "payload": {},
                },
                headers={**headers, "Idempotency-Key": "evidence-source-1"},
            )
            evidence_id = call.json()["evidence"]["evidence_id"]
            rejected = await client.post(
                f"/api/v2/evidence/{evidence_id}/supersede",
                json={"reason": "not independently verified", "status": "verified", "result": {}},
                headers=headers,
            )
            self.assertEqual(rejected.status_code, 409)
            replacement = await client.post(
                f"/api/v2/evidence/{evidence_id}/supersede",
                json={"reason": "corrected disclosure", "status": "unknown", "result": {"value": None}},
                headers=headers,
            )
            self.assertEqual(replacement.status_code, 201)
            self.assertEqual(replacement.json()["supersedes"], evidence_id)


if __name__ == "__main__":
    unittest.main()
