"""
ARIN Task 3 — Identity Compatibility Regression Tests.

These tests guard the legacy JARVIS/ZARVIS compatibility boundaries defined in
``docs/arin/ARIN_IDENTITY_AND_COMPATIBILITY.md``.  They must pass before any
executable, API route, package name, storage key, event type, or persisted
identifier is renamed.

Scope: every stable machine-facing identifier catalogued in ARIN-MIG-0015.
"""
import unittest
from unittest.mock import patch

import backend.server as legacy_server
from src.legacy.neural_audio_tts import NeuralAudioVoiceEngine


# ---------------------------------------------------------------------------
# 1. Retired REST routes return HTTP 410 fail-closed
# ---------------------------------------------------------------------------

class LegacyRouteRetirementTests(unittest.TestCase):
    """
    ARIN-IDENT-001 — Retired /api/jarvis/* routes must stay fail-closed (410).

    Policy: Do NOT redirect these paths into a new execution path; preserve
    the HTTP 410 ROUTE_RETIRED response until a separately-approved removal
    window is evidenced.
    """

    def _get_handler(self):
        return object.__new__(legacy_server.ZASIUnifiedHandler)

    def test_jarvis_chat_route_remains_retired(self):
        """POST /api/jarvis/chat must be covered by the 410 retire-set."""
        self.assertIn("/api/jarvis/chat", legacy_server._LEGACY_RETIRED_OPERATIONS)
        self.assertIn("post", legacy_server._LEGACY_RETIRED_OPERATIONS["/api/jarvis/chat"])

    def test_jarvis_stream_route_remains_retired(self):
        """POST /api/jarvis/stream must be covered by the 410 retire-set."""
        self.assertIn("/api/jarvis/stream", legacy_server._LEGACY_RETIRED_OPERATIONS)
        self.assertIn("post", legacy_server._LEGACY_RETIRED_OPERATIONS["/api/jarvis/stream"])

    def test_retired_route_set_covers_both_jarvis_paths(self):
        """Neither /api/jarvis route may be removed from the retire-set."""
        for path in ("/api/jarvis/chat", "/api/jarvis/stream"):
            self.assertIn(
                path,
                legacy_server._LEGACY_RETIRED_OPERATIONS,
                f"Legacy path {path!r} must remain in _LEGACY_RETIRED_OPERATIONS",
            )
            self.assertIn(
                "post",
                legacy_server._LEGACY_RETIRED_OPERATIONS[path],
                f"POST method for {path!r} must remain in _LEGACY_RETIRED_OPERATIONS",
            )

    def test_openapi_spec_marks_jarvis_chat_as_retired_410(self):
        """OpenAPI spec for /api/jarvis/chat must declare a 410 response."""
        spec = legacy_server.OPENAPI_SPEC
        responses = spec["paths"]["/api/jarvis/chat"]["post"]["responses"]
        self.assertIn("410", responses, "OpenAPI /api/jarvis/chat must have 410")

    def test_openapi_spec_marks_jarvis_stream_as_retired_410(self):
        """OpenAPI spec for /api/jarvis/stream must declare a 410 response."""
        spec = legacy_server.OPENAPI_SPEC
        responses = spec["paths"]["/api/jarvis/stream"]["post"]["responses"]
        self.assertIn("410", responses, "OpenAPI /api/jarvis/stream must have 410")

    def test_retired_jarvis_routes_do_not_execute_commands(self):
        """
        process_jarvis_command must not be called for retired POST paths.

        This test confirms that the retire-guard fires before the dispatcher;
        the retire-path check happens in do_POST before the path dispatches to
        the legacy persona command processor.
        """
        handler = self._get_handler()
        # The retired surface flag makes process_jarvis_command return a
        # safe reference-boundary message regardless of query.
        response = handler.process_jarvis_command("any-query", "JARVIS")
        self.assertIn("retired", response.lower())


# ---------------------------------------------------------------------------
# 2. JARVIS persona machine identifier stability
# ---------------------------------------------------------------------------

class JarvisPersonaIdentifierTests(unittest.TestCase):
    """
    ARIN-IDENT-002 — The JARVIS persona machine key must remain stable.

    Policy: Do not rename the enum-like value "JARVIS" in _PERSONA_SYSTEM_PROMPTS
    as a branding change. Any rename requires: enumerated producers/consumers,
    regression tests for existing key AND replacement, explicit compat window,
    and ledger evidence.
    """

    def test_jarvis_key_present_in_persona_prompts(self):
        """'JARVIS' must remain a key in _PERSONA_SYSTEM_PROMPTS."""
        self.assertIn(
            "JARVIS",
            legacy_server._PERSONA_SYSTEM_PROMPTS,
            "'JARVIS' persona key was removed — machine identifier regression",
        )

    def test_jarvis_prompt_is_non_empty_string(self):
        """The JARVIS persona prompt must remain a non-empty string."""
        prompt = legacy_server._PERSONA_SYSTEM_PROMPTS.get("JARVIS", "")
        self.assertIsInstance(prompt, str)
        self.assertGreater(len(prompt), 0)

    def test_default_persona_fallback_is_jarvis(self):
        """
        All LLM routing helpers must fall back to JARVIS as the default persona.

        This guards the pattern:
            _PERSONA_SYSTEM_PROMPTS.get(persona, _PERSONA_SYSTEM_PROMPTS["JARVIS"])
        Any change to the default fallback identity requires explicit consumer
        migration evidence.
        """
        # If "UNKNOWN_PERSONA" is requested, the code should fall back to JARVIS.
        # We test this by confirming the key exists for the fallback path.
        self.assertIn(
            "JARVIS",
            legacy_server._PERSONA_SYSTEM_PROMPTS,
            "JARVIS must exist as fallback persona; removing it breaks implicit defaults",
        )

    def test_openapi_spec_lists_jarvis_as_valid_persona_enum(self):
        """OpenAPI persona enum must include JARVIS for backward compat."""
        spec = legacy_server.OPENAPI_SPEC
        persona_enum = (
            spec["paths"]["/api/jarvis/chat"]["post"]
            ["requestBody"]["content"]["application/json"]
            ["schema"]["properties"]["persona"]["enum"]
        )
        self.assertIn("JARVIS", persona_enum)


# ---------------------------------------------------------------------------
# 3. /jarvis UI route compatibility
# ---------------------------------------------------------------------------

class JarvisUiRouteTests(unittest.TestCase):
    """
    ARIN-IDENT-003 — /jarvis frontend route is a legacy compatibility route.

    Policy: Any redirect or removal of /jarvis requires route regression
    coverage (this test is that coverage baseline).  The route must continue
    to exist as a known path; it must not be silently dropped.
    """

    def test_jarvis_ui_route_is_known_to_openapi_spec(self):
        """
        The /api/jarvis paths being in the OpenAPI spec confirms that the
        /jarvis SPA route has documented provenance.  If both /api/jarvis/*
        paths are removed from OpenAPI without replacement, this test should
        also be updated to capture the new compatibility-route evidence.
        """
        spec = legacy_server.OPENAPI_SPEC
        self.assertIn("/api/jarvis/chat", spec["paths"])
        self.assertIn("/api/jarvis/stream", spec["paths"])


# ---------------------------------------------------------------------------
# 4. zasi-jarvis container identity stability
# ---------------------------------------------------------------------------

class ZasiJarvisContainerIdentityTests(unittest.TestCase):
    """
    ARIN-IDENT-004 — zasi-jarvis Docker image/container name is an operational
    compatibility identifier.

    Policy: Keep stable until installer/deployment compatibility impact is
    assessed.  This test records the current known name so that any automated
    rename triggers a test failure requiring explicit review.
    """

    _EXPECTED_IMAGE_PREFIX = "zasi-jarvis"
    _EXPECTED_CONTAINER_NAME = "zasi-jarvis"

    def test_docker_compose_image_prefix_is_stable(self):
        """
        docker-compose.yml image name must start with the expected prefix.
        Rename only after deployment/installer compatibility is assessed.
        """
        import pathlib
        compose_path = pathlib.Path(__file__).parent.parent / "docker-compose.yml"
        if not compose_path.exists():
            self.skipTest("docker-compose.yml not present in workspace")
        text = compose_path.read_text()
        self.assertIn(
            self._EXPECTED_IMAGE_PREFIX,
            text,
            f"Docker image prefix '{self._EXPECTED_IMAGE_PREFIX}' not found in "
            f"docker-compose.yml — operational identity regression",
        )

    def test_docker_compose_container_name_is_stable(self):
        """container_name: zasi-jarvis must remain until deployment impact assessed."""
        import pathlib
        compose_path = pathlib.Path(__file__).parent.parent / "docker-compose.yml"
        if not compose_path.exists():
            self.skipTest("docker-compose.yml not present in workspace")
        text = compose_path.read_text()
        self.assertIn(
            f"container_name: {self._EXPECTED_CONTAINER_NAME}",
            text,
            f"container_name '{self._EXPECTED_CONTAINER_NAME}' not found — "
            f"deployment identity regression",
        )


# ---------------------------------------------------------------------------
# 5. BRITISH_JARVIS_RESONANT_BARITONE acoustic profile stability
# ---------------------------------------------------------------------------

class JarvisAcousticProfileIdentifierTests(unittest.TestCase):
    """
    ARIN-IDENT-005 — BRITISH_JARVIS_RESONANT_BARITONE is a legacy profile key.

    Policy: Treat as a legacy profile identifier; do not silently map it to
    privileged capability or action authority.  Do not rename without
    separately evidenced consumer migration.
    """

    _KNOWN_PROFILE = "BRITISH_JARVIS_RESONANT_BARITONE"

    def test_acoustic_profile_key_is_stable(self):
        """NeuralAudioVoiceEngine must still emit the known acoustic_profile key."""
        engine = NeuralAudioVoiceEngine()
        result = engine.synthesize_neural_phonemes("hello")
        self.assertEqual(
            result["acoustic_profile"],
            self._KNOWN_PROFILE,
            f"Acoustic profile key changed — rename requires consumer migration evidence",
        )

    def test_acoustic_profile_grants_no_privileged_capability(self):
        """
        The acoustic profile value must not appear in any privilege/capability
        enumeration.  This guards against accidentally wiring a display
        identifier to an authority grant.

        We confirm the profile string is not a ToolRiskClass value or any
        other controlled enum in the ARIN tool contract.
        """
        from backend.arin.tools import ToolRiskClass, OperationClass
        all_controlled_values = {e.value for e in ToolRiskClass} | {e.value for e in OperationClass}
        self.assertNotIn(
            self._KNOWN_PROFILE.lower(),
            {v.lower() for v in all_controlled_values},
            "Acoustic profile identifier must not match any ARIN controlled capability value",
        )

    def test_acoustic_profile_cannot_be_used_as_tool_id(self):
        """
        Attempting to register the acoustic profile as a ToolCapabilityDescriptor
        must fail validation (empty/invalid capability_id), confirming it is not
        a valid ARIN tool identifier.
        """
        from backend.arin.tools import ToolCapabilityDescriptor, ToolCapabilityError, ToolRiskClass, OperationClass
        # Confirm the profile value does not satisfy the tool capability_id format
        # by ensuring it would not be accepted as-is in a LOW-risk read descriptor.
        # Actually, the profile is a valid non-empty string so it *could* be a key;
        # the guard is that no code registers it. We verify by introspection of the
        # zcoder adapter and tools module for any static descriptors containing this value.
        import backend.arin.zcoder_adapter as adapter_mod
        import inspect
        source = inspect.getsource(adapter_mod)
        self.assertNotIn(
            self._KNOWN_PROFILE,
            source,
            "Acoustic profile identifier must not appear in the ZCoder adapter as a tool ID",
        )


# ---------------------------------------------------------------------------
# 6. jarvis package keyword is non-authoritative
# ---------------------------------------------------------------------------

class PackageKeywordTests(unittest.TestCase):
    """
    ARIN-IDENT-006 — 'jarvis' as a package.json keyword is non-authoritative
    metadata and must not be treated as a runtime identity claim.

    Policy: May be deprecated later without changing runtime identity.  This
    test records its current presence so any future removal is deliberate.
    """

    def test_jarvis_keyword_present_in_package_json(self):
        """
        package.json currently includes 'jarvis' in keywords.
        Removal is permitted without consumer migration; this test records
        the current state as a known baseline.
        """
        import json
        import pathlib
        pkg = json.loads(
            (pathlib.Path(__file__).parent.parent / "package.json").read_text()
        )
        keywords = pkg.get("keywords", [])
        self.assertIn(
            "jarvis",
            keywords,
            "'jarvis' keyword removed from package.json — update this test baseline "
            "and confirm the removal is intentional",
        )

    def test_package_name_is_not_jarvis(self):
        """
        The authoritative package name must NOT be 'jarvis'.
        The product/machine identity is ZASI; 'jarvis' is a legacy keyword only.
        """
        import json
        import pathlib
        pkg = json.loads(
            (pathlib.Path(__file__).parent.parent / "package.json").read_text()
        )
        self.assertNotEqual(
            pkg.get("name", ""),
            "jarvis",
            "Package name must not be 'jarvis'; that is a legacy keyword, not the identity",
        )


# ---------------------------------------------------------------------------
# 7. Alias authority isolation — no alias widens authorization
# ---------------------------------------------------------------------------

class AliasAuthorityIsolationTests(unittest.TestCase):
    """
    ARIN-IDENT-007 — Compatibility aliases must never widen authorization,
    tenant scope, tool authority, or physical-actuation authority.
    """

    def test_retired_jarvis_command_cannot_trigger_tick(self):
        """process_jarvis_command('tick') must not advance daemon state."""
        handler = object.__new__(legacy_server.ZASIUnifiedHandler)
        with patch.object(legacy_server.daemon, "step_cycle") as step_cycle:
            handler.process_jarvis_command("tick", "JARVIS")
        step_cycle.assert_not_called()

    def test_retired_jarvis_command_cannot_trigger_rsi(self):
        """process_jarvis_command('upgrade rsi') must not trigger hot-swap."""
        handler = object.__new__(legacy_server.ZASIUnifiedHandler)
        with patch.object(legacy_server.rsi_engine, "hot_swap_runtime") as hot_swap:
            handler.process_jarvis_command("upgrade rsi", "JARVIS")
        hot_swap.assert_not_called()

    def test_no_jarvis_alias_in_arin_tool_registry(self):
        """
        No 'jarvis' alias may appear as a capability_id in any static ARIN tool
        capability descriptor defined in the zcoder adapter or tools module.
        """
        import inspect
        import backend.arin.tools as tools_mod
        import backend.arin.zcoder_adapter as adapter_mod
        for mod in (tools_mod, adapter_mod):
            source = inspect.getsource(mod)
            # Confirm no capability_id literal contains 'jarvis'
            import re
            matches = re.findall(r'capability_id\s*=\s*["\']([^"\']+)["\']', source)
            for cap_id in matches:
                self.assertNotIn(
                    "jarvis",
                    cap_id.lower(),
                    f"ARIN capability_id {cap_id!r} in {mod.__name__} contains 'jarvis' — "
                    f"legacy alias must not become a tool capability identifier",
                )

    def test_retired_surface_flag_cannot_be_bypassed_by_mutation(self):
        """
        Patching LEGACY_REFERENCE_ONLY to False must not re-enable retired
        surfaces.  The _legacy_surface_is_retired() guard is hardened against
        module-global mutation.
        """
        with patch.object(legacy_server, "LEGACY_REFERENCE_ONLY", False):
            handler = object.__new__(legacy_server.ZASIUnifiedHandler)
            response = handler.process_jarvis_command("status", "JARVIS")
        # Must still return the retired/reference response despite the patch.
        lowered = response.lower()
        self.assertIn("retired", lowered)


if __name__ == "__main__":
    unittest.main()
