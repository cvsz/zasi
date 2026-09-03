import hashlib
import struct
import tempfile
import unittest
import zlib
from contextlib import asynccontextmanager
from pathlib import Path

import httpx

from backend.app import create_app
from src.control_plane.config import Settings
from src.control_plane.storage import ControlPlaneStore


STEP_FIXTURE = b"""ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('ZASI test part'),'2;1');
ENDSEC;
DATA;
#1=CARTESIAN_POINT('P0',(0.,0.,0.));
#2=CARTESIAN_POINT('P1',(25.,10.,5.));
#3=CARTESIAN_POINT('P2',(5.,7.,2.));
#4=SI_UNIT(.MILLI.,.METRE.);
#5=ADVANCED_FACE('',(),$);
ENDSEC;
END-ISO-10303-21;
"""


def png_fixture(width: int, height: int, pixel: bytes) -> bytes:
    raw = b"".join(b"\x00" + pixel * width for _ in range(height))

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


class MultimodalAdapterTests(unittest.TestCase):
    def test_step_parser_measures_source_geometry_without_claiming_solver_results(self):
        try:
            from src.control_plane.multimodal import parse_cad_artifact
        except ModuleNotFoundError as exc:
            self.fail(f"source-backed multimodal adapter is missing: {exc}")

        result = parse_cad_artifact(STEP_FIXTURE, "application/step")

        self.assertEqual(result["format"], "STEP")
        self.assertEqual(result["parser"], "zasi.step.stdlib")
        self.assertEqual(result["geometry_status"], "measured")
        self.assertEqual(result["units"], "mm")
        self.assertEqual(result["vertex_count"], 3)
        self.assertEqual(result["face_count"], 1)
        self.assertEqual(result["bounding_box"]["dimensions"], {"x": 25.0, "y": 10.0, "z": 5.0})
        self.assertEqual(result["analysis"], {"fea": "not_run", "thermal": "not_run"})
        self.assertEqual(result["source_digest"], "sha256:" + hashlib.sha256(STEP_FIXTURE).hexdigest())

    def test_malformed_step_is_rejected_instead_of_being_reported_as_geometry(self):
        try:
            from src.control_plane.multimodal import ArtifactFormatError, parse_cad_artifact
        except ModuleNotFoundError as exc:
            self.fail(f"source-backed multimodal adapter is missing: {exc}")

        with self.assertRaises(ArtifactFormatError):
            parse_cad_artifact(b"ISO-10303-21;\nDATA;\n#1=NOT_A_POINT;\n", "application/step")

    def test_step_comments_and_incomplete_exchange_sections_cannot_create_geometry(self):
        from src.control_plane.multimodal import ArtifactFormatError, parse_cad_artifact

        comment_only = b"""ISO-10303-21;
HEADER;
ENDSEC;
DATA;
/* #1=CARTESIAN_POINT('fake',(1.,2.,3.)); */
ENDSEC;
END-ISO-10303-21;
"""
        incomplete = b"""ISO-10303-21;
DATA;
#1=CARTESIAN_POINT('P0',(1.,2.,3.));
END-ISO-10303-21;
"""
        with self.assertRaises(ArtifactFormatError):
            parse_cad_artifact(comment_only, "application/step")
        with self.assertRaises(ArtifactFormatError):
            parse_cad_artifact(incomplete, "application/step")

    def test_mesh_parsers_measure_actual_stl_and_obj_vertices(self):
        from src.control_plane.multimodal import parse_cad_artifact

        stl = b"""solid test
facet normal 0 0 1
 outer loop
  vertex 0 0 0
  vertex 2 0 0
  vertex 0 3 0
 endloop
endfacet
endsolid test
"""
        obj = b"v 0 0 0\nv 2 0 0\nv 0 3 0\nf 1 2 3\n"
        stl_result = parse_cad_artifact(stl, "model/stl")
        obj_result = parse_cad_artifact(obj, "model/obj")

        self.assertEqual(stl_result["triangle_count"], 1)
        self.assertEqual(stl_result["bounding_box"]["dimensions"]["y"], 3.0)
        self.assertEqual(obj_result["face_count"], 1)
        self.assertEqual(obj_result["bounding_box"]["dimensions"]["x"], 2.0)

    def test_binary_stl_parser_reads_all_three_vertices_from_each_triangle_record(self):
        from src.control_plane.multimodal import parse_cad_artifact

        triangle = struct.pack(
            "<12fH",
            0.0,
            0.0,
            1.0,
            0.0,
            0.0,
            0.0,
            2.0,
            0.0,
            0.0,
            0.0,
            3.0,
            0.0,
            0,
        )
        binary_stl = b"zasi binary STL".ljust(80, b" ") + struct.pack("<I", 1) + triangle
        result = parse_cad_artifact(binary_stl, "model/stl")

        self.assertEqual(result["triangle_count"], 1)
        self.assertEqual(result["bounding_box"]["dimensions"], {"x": 2.0, "y": 3.0, "z": 0.0})

    def test_image_observation_changes_with_actual_png_input(self):
        try:
            from src.control_plane.multimodal import analyze_image_artifact
        except ModuleNotFoundError as exc:
            self.fail(f"source-backed multimodal adapter is missing: {exc}")

        red = png_fixture(2, 1, b"\xff\x00\x00")
        blue = png_fixture(2, 1, b"\x00\x00\xff")
        red_result = analyze_image_artifact(red, "image/png")
        blue_result = analyze_image_artifact(blue, "image/png")

        self.assertEqual(red_result["format"], "PNG")
        self.assertEqual(red_result["dimensions"], {"width": 2, "height": 1})
        self.assertEqual(red_result["semantic_model"], "not_configured")
        self.assertNotEqual(red_result["content_digest"], blue_result["content_digest"])
        self.assertNotEqual(red_result["pixel_digest"], blue_result["pixel_digest"])

    def test_png_decoder_rejects_dimensions_that_exceed_decoded_memory_bound(self):
        from src.control_plane.multimodal import ArtifactFormatError, analyze_image_artifact

        def chunk(kind: bytes, payload: bytes) -> bytes:
            return (
                struct.pack(">I", len(payload))
                + kind
                + payload
                + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
            )

        huge = (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", 32_768, 32_768, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\x00"))
            + chunk(b"IEND", b"")
        )
        with self.assertRaises(ArtifactFormatError):
            analyze_image_artifact(huge, "image/png")


class MultimodalApiTests(unittest.IsolatedAsyncioTestCase):
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
                transport=transport, base_url="http://testserver"
            ) as client:
                session = await client.post(
                    "/api/v2/sessions", json={"api_key": "test-bootstrap-secret"}
                )
                self.assertEqual(session.status_code, 201)
                yield client, {
                    "Authorization": f"Bearer {session.json()['access_token']}"
                }

    async def test_step_analysis_is_source_backed_and_content_endpoint_is_authorized(self):
        async with self.client() as (client, headers):
            artifact = await client.post(
                "/api/v2/artifacts",
                content=STEP_FIXTURE,
                headers={**headers, "Content-Type": "application/step"},
            )
            self.assertEqual(artifact.status_code, 201)
            artifact_id = artifact.json()["artifact_id"]
            analysis = await client.post(
                "/api/v2/cad/analyze",
                json={"artifact_id": artifact_id, "analysis_kind": "geometry"},
                headers=headers,
            )
            self.assertEqual(analysis.status_code, 201)
            body = analysis.json()
            self.assertEqual(body["evidence"]["status"], "verified")
            self.assertEqual(body["evidence"]["result"]["geometry_status"], "measured")
            self.assertEqual(body["evidence"]["result"]["bounding_box"]["dimensions"]["x"], 25.0)
            self.assertNotIn("storage_ref", body["evidence"]["result"])

            content = await client.get(f"/api/v2/artifacts/{artifact_id}/content", headers=headers)
            self.assertEqual(content.status_code, 200)
            self.assertEqual(content.content, STEP_FIXTURE)
            self.assertEqual(content.headers["X-ZASI-Artifact-Digest"], artifact.json()["digest"])
            self.assertNotIn(str(Path(self.tempdir.name)), content.text)

            unauthenticated = await client.get(f"/api/v2/artifacts/{artifact_id}/content")
            self.assertEqual(unauthenticated.status_code, 401)

    async def test_tampered_quarantine_content_is_rejected(self):
        async with self.client() as (client, headers):
            artifact = await client.post(
                "/api/v2/artifacts",
                content=STEP_FIXTURE,
                headers={**headers, "Content-Type": "application/step"},
            )
            artifact_id = artifact.json()["artifact_id"]
            path = Path(self.app.state.artifact_directory) / f"{artifact_id}.bin"
            path.write_bytes(b"tampered")
            analysis = await client.post(
                "/api/v2/cad/analyze",
                json={"artifact_id": artifact_id},
                headers=headers,
            )
            self.assertEqual(analysis.status_code, 409)
            self.assertEqual(analysis.json()["error"]["code"], "ARTIFACT_INTEGRITY_MISMATCH")

    async def test_vision_analysis_records_actual_image_metadata_and_source_digest(self):
        async with self.client() as (client, headers):
            image = png_fixture(2, 1, b"\xff\x00\x00")
            artifact = await client.post(
                "/api/v2/artifacts",
                content=image,
                headers={**headers, "Content-Type": "image/png"},
            )
            analysis = await client.post(
                "/api/v2/vision/analyze",
                json={"artifact_id": artifact.json()["artifact_id"]},
                headers=headers,
            )
            self.assertEqual(analysis.status_code, 201)
            evidence = analysis.json()["evidence"]
            self.assertEqual(evidence["status"], "verified")
            self.assertEqual(evidence["result"]["dimensions"], {"width": 2, "height": 1})
            self.assertEqual(evidence["result"]["semantic_model"], "not_configured")
            self.assertEqual(evidence["provenance"]["input_digest"], artifact.json()["digest"])
            retrieved = await client.get(
                f"/api/v2/vision/{analysis.json()['analysis_id']}", headers=headers
            )
            self.assertEqual(retrieved.status_code, 200)
            self.assertEqual(retrieved.json()["evidence_id"], evidence["evidence_id"])


if __name__ == "__main__":
    unittest.main()
