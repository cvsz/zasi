"""Local model gateway.

The reference gateway uses a deterministic simulator by default. When the
operator explicitly configures a loopback Ollama endpoint, the gateway may
also call that endpoint. The plan never sends user data to a hosted model.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Mapping
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from .agent_models import ModelSelection, canonicalize_action_payload


_SIMULATOR_NAME = "deterministic_simulator"


def _canonical(payload: Mapping[str, Any]) -> str:
    return json.dumps(
        canonicalize_action_payload(dict(payload)),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _digest(payload: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _validate_loopback_url(base_url: str) -> str:
    """Parse and validate a loopback HTTP URL for the Ollama adapter."""
    if not isinstance(base_url, str) or not base_url:
        raise ValueError("ollama base url must be a non-empty string")
    parsed = urlsplit(base_url)
    if (
        parsed.scheme != "http"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.hostname.lower() not in {"localhost", "127.0.0.1", "::1"}
    ):
        raise ValueError("ollama base url must be a loopback http://localhost URL")
    return base_url.rstrip("/")


class ModelGateway:
    """Simulator-first model selection and proposal gateway."""

    def __init__(
        self,
        *,
        base_url: str = "",
        model: str = "",
        timeout_seconds: float = 3.0,
    ):
        self._base_url = ""
        self._model = ""
        self._timeout_seconds = 3.0
        if base_url:
            self._base_url = _validate_loopback_url(base_url)
            self._model = (model or "").strip()
        if not isinstance(timeout_seconds, (int, float)) or isinstance(timeout_seconds, bool):
            raise ValueError("timeout_seconds must be a number")
        if timeout_seconds < 0.1 or timeout_seconds > 30.0:
            raise ValueError("timeout_seconds must be between 0.1 and 30 seconds")
        self._timeout_seconds = float(timeout_seconds)

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def model(self) -> str:
        return self._model

    @property
    def timeout_seconds(self) -> float:
        return self._timeout_seconds

    def status(self) -> Dict[str, Any]:
        if not self._base_url:
            return {
                "mode": "deterministic_simulator",
                "model": _SIMULATOR_NAME,
                "status": "simulator",
                "disclosures": [
                    "No local model is configured. The deterministic simulator is used for all proposals."
                ],
            }
        try:
            response = self._get_tags()
        except Exception:
            return {
                "mode": "ollama_loopback",
                "model": self._model or "unknown",
                "status": "unavailable",
                "disclosures": [
                    "Ollama loopback endpoint did not respond. The deterministic simulator is used as the safe fallback."
                ],
            }
        models = response.get("models") if isinstance(response, dict) else None
        if not isinstance(models, list):
            return {
                "mode": "ollama_loopback",
                "model": self._model or "unknown",
                "status": "unavailable",
                "disclosures": [
                    "Ollama loopback response was not understood. The deterministic simulator is used as the safe fallback."
                ],
            }
        return {
            "mode": "ollama_loopback",
            "model": self._model or "unknown",
            "status": "ready",
            "disclosures": [
                "Loopback Ollama adapter is enabled. The runtime treats model output as an untrusted proposal."
            ],
        }

    def select(self, policy: Mapping[str, Any]) -> ModelSelection:
        if not isinstance(policy, Mapping):
            policy = {}
        forced = str(policy.get("mode", "")).strip() if isinstance(policy, Mapping) else ""
        if forced == "ollama_loopback" and self._base_url:
            selection_status = "ready"
        elif forced and forced != "deterministic_simulator":
            selection_status = "unavailable"
        elif self._base_url:
            selection_status = "ready"
        else:
            selection_status = "simulator"
        mode = "ollama_loopback" if (self._base_url and selection_status == "ready") else "deterministic_simulator"
        model = self._model if mode == "ollama_loopback" else _SIMULATOR_NAME
        digest = _digest(
            {
                "mode": mode,
                "model": model,
                "policy": dict(policy),
                "status": selection_status,
            }
        )
        if mode == "ollama_loopback":
            disclosures = (
                "Loopback Ollama adapter. The planner treats model output as an untrusted proposal.",
            )
        else:
            disclosures = (
                "Deterministic local simulator. No hosted model is contacted.",
            )
        return ModelSelection(
            mode=mode,
            model=model,
            status=selection_status,
            proposal_digest=digest,
            disclosures=disclosures,
        )

    def propose(
        self,
        *,
        task: str,
        context: Mapping[str, Any],
        policy: Mapping[str, Any],
    ) -> Dict[str, Any]:
        selection = self.select(policy)
        if selection.mode == "ollama_loopback":
            try:
                body = json.dumps(
                    {
                        "model": self._model,
                        "prompt": task,
                        "context": dict(context),
                        "stream": False,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
                request = Request(
                    f"{self._base_url}/api/generate",
                    data=body,
                    method="POST",
                    headers={"Content-Type": "application/json"},
                )
                with urlopen(request, timeout=self._timeout_seconds) as response:  # nosec - validated loopback
                    payload = json.loads(response.read().decode("utf-8"))
            except Exception:
                fallback = self._simulator_propose(task=task, context=context, policy=policy)
                fallback["status"] = "simulator_fallback"
                fallback["disclosures"] = list(fallback.get("disclosures", [])) + [
                    "Ollama request failed; the deterministic simulator is used as the safe fallback."
                ]
                return fallback
            if not isinstance(payload, dict):
                raise ValueError("ollama response is not an object")
            response_text = str(payload.get("response", ""))
            digest = _digest(
                {
                    "mode": "ollama_loopback",
                    "model": self._model,
                    "task": task,
                    "response": response_text,
                }
            )
            return {
                "mode": "ollama_loopback",
                "model": self._model,
                "status": "ready",
                "proposal_text": response_text,
                "proposal_digest": digest,
                "disclosures": [
                    "Loopback Ollama response recorded; the planner treats it as an untrusted proposal.",
                ],
            }
        return self._simulator_propose(task=task, context=context, policy=policy)

    def _simulator_propose(
        self,
        *,
        task: str,
        context: Mapping[str, Any],
        policy: Mapping[str, Any],
    ) -> Dict[str, Any]:
        canonical = _canonical({"task": task, "context": dict(context), "policy": dict(policy)})
        digest = "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return {
            "mode": "deterministic_simulator",
            "model": _SIMULATOR_NAME,
            "status": "simulator",
            "proposal_text": f"simulator://plan/{digest[:16]}",
            "proposal_digest": digest,
            "disclosures": [
                "Deterministic local simulator. No external service is contacted.",
            ],
        }

    def _get_tags(self) -> Dict[str, Any]:
        request = Request(f"{self._base_url}/api/tags", method="GET")
        with urlopen(request, timeout=self._timeout_seconds) as response:  # nosec - validated loopback
            return json.loads(response.read().decode("utf-8"))


__all__ = ["ModelGateway"]
