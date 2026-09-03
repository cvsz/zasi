import hashlib
import struct
import tempfile
import unittest
import zlib
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import patch

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

    def test_step_unknown_si_prefix_is_not_silently_reported_as_metres(self):
        from src.control_plane.multimodal import parse_cad_artifact

        pico_step = STEP_FIXTURE.replace(b".MILLI.,.METRE.", b".PICO.,.METRE.")

        result = parse_cad_artifact(pico_step, "application/step")

        self.assertEqual(result["units"], "pm")

    def test_step_geometry_is_read_only_from_the_ordered_data_section(self):
        from src.control_plane.multimodal import ArtifactFormatError, parse_cad_artifact

        header_only_point = b"""ISO-10303-21;
HEADER;
#1=CARTESIAN_POINT('header',(1.,2.,3.));
ENDSEC;
DATA;
ENDSEC;
END-ISO-10303-21;
"""

        with self.assertRaises(ArtifactFormatError):
            parse_cad_artifact(header_only_point, "application/step")

        fake_entity_text = b"""ISO-10303-21;
HEADER;
ENDSEC;
DATA;
THIS IS NOT AN ENTITY CARTESIAN_POINT('fake',(1.,2.,3.));
ENDSEC;
END-ISO-10303-21;
"""
        with self.assertRaises(ArtifactFormatError):
            parse_cad_artifact(fake_entity_text, "application/step")

    def test_step_topology_and_derived_dimensions_are_bounded(self):
        import src.control_plane.multimodal as multimodal

        topology = STEP_FIXTURE.replace(
            b"#5=ADVANCED_FACE('',(),$);",
            b"#5=EDGE('',(),$);#6=EDGE('',(),$);#7=EDGE('',(),$);",
        )
        with patch.object(multimodal, "MAX_TOPOLOGY_RECORDS", 2):
            with self.assertRaises(multimodal.ArtifactFormatError):
                multimodal.parse_cad_artifact(topology, "application/step")

        overflowing = STEP_FIXTURE.replace(
            b"(0.,0.,0.)", b"(-1e308,0.,0.)"
        ).replace(b"(25.,10.,5.)", b"(1e308,10.,5.)")
        with self.assertRaises(multimodal.ArtifactFormatError):
            multimodal.parse_cad_artifact(overflowing, "application/step")

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

    def test_ascii_stl_requires_facet_and_loop_structure(self):
        from src.control_plane.multimodal import ArtifactFormatError, parse_cad_artifact

        vertex_lines_without_facets = b"""solid test
vertex 0 0 0
vertex 1 0 0
vertex 0 1 0
endsolid test
"""

        with self.assertRaises(ArtifactFormatError):
            parse_cad_artifact(vertex_lines_without_facets, "model/stl")

    def test_obj_accepts_and_normalizes_an_optional_homogeneous_coordinate(self):
        from src.control_plane.multimodal import parse_cad_artifact

        obj = b"v 0 0 0 2\nv 2 0 0 2\nv 0 4 0 2\nf 1 2 3\n"

        result = parse_cad_artifact(obj, "model/obj")

        self.assertEqual(result["bounding_box"]["dimensions"], {"x": 1.0, "y": 2.0, "z": 0.0})

    def test_obj_vertex_materialization_has_a_memory_derived_bound(self):
        import src.control_plane.multimodal as multimodal

        obj = b"v 0 0 0\nv 1 0 0\nv 0 1 0\n"
        with patch.object(multimodal, "MAX_OBJ_VERTICES", 2):
            with self.assertRaises(multimodal.ArtifactFormatError):
                multimodal.parse_cad_artifact(obj, "model/obj")

    def test_obj_face_references_are_bounded_before_validation(self):
        import src.control_plane.multimodal as multimodal

        obj = b"v 0 0 0\nf 1 1 1 1\n"
        with patch.object(multimodal, "MAX_OBJ_FACE_REFERENCES", 3):
            with self.assertRaises(multimodal.ArtifactFormatError):
                multimodal.parse_cad_artifact(obj, "model/obj")

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
        self.assertNotEqual(red_result["decoded_payload_digest"], blue_result["decoded_payload_digest"])
        self.assertIsNone(red_result["pixel_digest"])

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

    def test_png_decoder_rejects_output_tail_before_flushing_it(self):
        import src.control_plane.multimodal as multimodal

        def chunk(kind: bytes, payload: bytes) -> bytes:
            return (
                struct.pack(">I", len(payload))
                + kind
                + payload
                + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
            )

        oversized_stream = (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\x00" + b"a" * 100))
            + chunk(b"IEND", b"")
        )

        class FlushGuard:
            def __init__(self, wrapped):
                self._wrapped = wrapped

            def decompress(self, *args, **kwargs):
                return self._wrapped.decompress(*args, **kwargs)

            def flush(self, *args, **kwargs):
                if self._wrapped.unconsumed_tail:
                    raise AssertionError("flush must not process an unconsumed tail")
                return self._wrapped.flush(*args, **kwargs)

            def __getattr__(self, name):
                return getattr(self._wrapped, name)

        real_decompressobj = zlib.decompressobj

        def guarded_decompressobj(*args, **kwargs):
            return FlushGuard(real_decompressobj(*args, **kwargs))

        with patch.object(multimodal, "MAX_DECODED_IMAGE_BYTES", 8), patch.object(
            multimodal.zlib, "decompressobj", guarded_decompressobj
        ):
            with self.assertRaises(multimodal.ArtifactFormatError):
                multimodal.analyze_image_artifact(oversized_stream, "image/png")

    def test_png_rejects_invalid_crc_bit_depth_and_interlaced_payload_length(self):
        from src.control_plane.multimodal import ArtifactFormatError, analyze_image_artifact

        def chunk(kind: bytes, payload: bytes, crc: int | None = None) -> bytes:
            return (
                struct.pack(">I", len(payload))
                + kind
                + payload
                + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF if crc is None else crc)
            )

        invalid_bit_depth = (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 1, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\x00\x00"))
            + chunk(b"IEND", b"")
        )
        invalid_crc = png_fixture(1, 1, b"\xff\x00\x00")[:-1] + bytes([png_fixture(1, 1, b"\xff\x00\x00")[-1] ^ 0x01])
        invalid_adam7_payload = (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 1))
            + chunk(b"IDAT", zlib.compress(b"\x00"))
            + chunk(b"IEND", b"")
        )
        for image in (invalid_bit_depth, invalid_crc, invalid_adam7_payload):
            with self.assertRaises(ArtifactFormatError):
                analyze_image_artifact(image, "image/png")

    def test_png_accepts_valid_narrow_adam7_and_rejects_invalid_filter_bytes(self):
        from src.control_plane.multimodal import ArtifactFormatError, analyze_image_artifact

        def chunk(kind: bytes, payload: bytes) -> bytes:
            return (
                struct.pack(">I", len(payload))
                + kind
                + payload
                + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
            )

        def adam7(payload: bytes) -> bytes:
            return (
                b"\x89PNG\r\n\x1a\n"
                + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 1))
                + chunk(b"IDAT", zlib.compress(payload))
                + chunk(b"IEND", b"")
            )

        result = analyze_image_artifact(adam7(b"\x00\x00"), "image/png")
        self.assertEqual(result["dimensions"], {"width": 1, "height": 1})
        with self.assertRaises(ArtifactFormatError):
            analyze_image_artifact(adam7(b"\x05\x00"), "image/png")

    def test_jpeg_requires_scan_data_and_end_marker(self):
        from src.control_plane.multimodal import ArtifactFormatError, analyze_image_artifact

        frame_only = (
            b"\xff\xd8"
            + b"\xff\xc0"
            + struct.pack(">H", 11)
            + b"\x08\x00\x01\x00\x01\x01\x01\x11\x00"
        )

        with self.assertRaises(ArtifactFormatError):
            analyze_image_artifact(frame_only, "image/jpeg")

        complete_structure = (
            frame_only
            + b"\xff\xda"
            + struct.pack(">H", 8)
            + b"\x01\x01\x00\x00\x3f\x00"
            + b"\x00"
            + b"\xff\xd9"
        )
        result = analyze_image_artifact(complete_structure, "image/jpeg")
        self.assertEqual(result["format"], "JPEG")
        self.assertEqual(result["dimensions"], {"width": 1, "height": 1})
        self.assertIsNone(result["pixel_digest"])
        self.assertEqual(result["encoded_content_digest"], result["content_digest"])

        mismatched_scan_component = (
            frame_only
            + b"\xff\xda"
            + struct.pack(">H", 8)
            + b"\x01\x02\x00\x00\x3f\x00"
            + b"\x00"
            + b"\xff\xd9"
        )
        with self.assertRaises(ArtifactFormatError):
            analyze_image_artifact(mismatched_scan_component, "image/jpeg")


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

    async def test_rejected_analysis_returns_its_persisted_evidence_id(self):
        async with self.client() as (client, headers):
            artifact = await client.post(
                "/api/v2/artifacts",
                content=b"not a STEP exchange",
                headers={**headers, "Content-Type": "application/step"},
            )
            self.assertEqual(artifact.status_code, 201)
            analysis = await client.post(
                "/api/v2/cad/analyze",
                json={"artifact_id": artifact.json()["artifact_id"]},
                headers=headers,
            )
            self.assertEqual(analysis.status_code, 422)
            evidence_id = analysis.json()["error"]["details"]["evidence_id"]
            rejected = await client.get(f"/api/v2/evidence/{evidence_id}", headers=headers)
            self.assertEqual(rejected.status_code, 200)
            self.assertEqual(rejected.json()["status"], "rejected")

    async def test_obj_upload_reaches_quarantine_and_analysis(self):
        obj = b"v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n"
        async with self.client() as (client, headers):
            artifact = await client.post(
                "/api/v2/artifacts",
                content=obj,
                headers={**headers, "Content-Type": "model/obj"},
            )
            self.assertEqual(artifact.status_code, 201)
            analysis = await client.post(
                "/api/v2/cad/analyze",
                json={"artifact_id": artifact.json()["artifact_id"], "analysis_kind": "geometry"},
                headers=headers,
            )
            self.assertEqual(analysis.status_code, 201)
            self.assertEqual(analysis.json()["evidence"]["result"]["format"], "OBJ")

    async def test_cad_solver_kinds_are_rejected_instead_of_verified(self):
        async with self.client() as (client, headers):
            artifact = await client.post(
                "/api/v2/artifacts",
                content=STEP_FIXTURE,
                headers={**headers, "Content-Type": "application/step"},
            )
            analysis = await client.post(
                "/api/v2/cad/analyze",
                json={"artifact_id": artifact.json()["artifact_id"], "analysis_kind": "fea"},
                headers=headers,
            )
            self.assertEqual(analysis.status_code, 422)
            self.assertEqual(analysis.json()["error"]["code"], "UNSUPPORTED_ANALYSIS_KIND")

    async def test_typed_analysis_routes_do_not_return_unrelated_evidence(self):
        async with self.client() as (client, headers):
            unrelated = self.store.create_evidence(
                evidence_id="ev_unrelated_multimodal",
                tenant_id="local",
                principal_id="local-operator",
                kind="action_result",
                status="verified",
                provenance={"adapter_id": "zasi.tool.registry", "origin": "local"},
                result={"value": "not an analysis"},
            )
            for route in ("cad", "vision"):
                response = await client.get(
                    f"/api/v2/{route}/{unrelated['evidence_id']}", headers=headers
                )
                self.assertEqual(response.status_code, 404)
                self.assertEqual(response.json()["error"]["code"], "NOT_FOUND")

    async def test_vision_semantic_kind_is_rejected_until_a_model_is_configured(self):
        async with self.client() as (client, headers):
            artifact = await client.post(
                "/api/v2/artifacts",
                content=png_fixture(1, 1, b"\xff\x00\x00"),
                headers={**headers, "Content-Type": "image/png"},
            )
            analysis = await client.post(
                "/api/v2/vision/analyze",
                json={"artifact_id": artifact.json()["artifact_id"], "analysis_kind": "semantic"},
                headers=headers,
            )
            self.assertEqual(analysis.status_code, 422)
            self.assertEqual(analysis.json()["error"]["code"], "UNSUPPORTED_ANALYSIS_KIND")

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
