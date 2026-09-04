"""Bounded local speech adapters with explicit provenance.

The adapters call installed local executables directly.  They do not use a
shell, inherit the application's secret environment, authorize actions, or
claim speaker identity.  A successful result means only that the selected
local model/tool produced a bounded artifact for the supplied bytes/text.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import wave
from typing import Dict, Optional, Sequence, Tuple


MAX_AUDIO_BYTES = 16 * 1024 * 1024
MAX_MODEL_BYTES = 4 * 1024 * 1024 * 1024
MAX_TRANSCRIPT_CHARS = 16 * 1024
MAX_SYNTHESIS_BYTES = 16 * 1024 * 1024
MAX_SYNTHESIS_SECONDS = 300.0
_AUDIO_SUFFIXES: Dict[str, str] = {
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/wave": ".wav",
    "audio/mpeg": ".mp3",
    "audio/ogg": ".ogg",
    "audio/flac": ".flac",
}


class SpeechAdapterError(ValueError):
    """Raised when a local speech adapter cannot produce bounded evidence."""


@dataclass(frozen=True)
class SpeechTranscription:
    """A source- and model-bound local transcription result."""

    text: str
    adapter_id: str
    adapter_version: str
    source_digest: str
    model_digest: str
    executable_digest: str
    evidence_state: str
    disclosure: str


@dataclass(frozen=True)
class SpeechSynthesis:
    """A bounded WAV result produced by a local text-to-speech executable."""

    audio_bytes: bytes
    content_type: str
    sample_rate_hz: int
    channels: int
    duration_seconds: float
    audio_digest: str
    adapter_id: str
    adapter_version: str
    executable_digest: str
    evidence_state: str
    disclosure: str


def _digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _digest_file(path: Path, *, max_bytes: int) -> str:
    try:
        metadata = path.stat()
    except OSError as exc:
        raise SpeechAdapterError("speech dependency file is unavailable") from exc
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > max_bytes:
        raise SpeechAdapterError("speech dependency file is outside the safe bound")
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise SpeechAdapterError("speech dependency file cannot be read") from exc
    return "sha256:" + digest.hexdigest()


def _resolve_executable(value: Optional[str], default: str) -> Tuple[Path, str]:
    configured = (value or default).strip()
    if not configured:
        raise SpeechAdapterError("speech executable is required")
    candidate = Path(configured)
    if not candidate.is_absolute():
        located = shutil.which(configured)
        if not located:
            raise SpeechAdapterError("speech executable is unavailable")
        candidate = Path(located)
    try:
        resolved = candidate.resolve(strict=True)
        metadata = resolved.stat()
    except OSError as exc:
        raise SpeechAdapterError("speech executable is unavailable") from exc
    if not stat.S_ISREG(metadata.st_mode) or not os.access(resolved, os.X_OK):
        raise SpeechAdapterError("speech executable is not runnable")
    return resolved, _digest_file(resolved, max_bytes=64 * 1024 * 1024)


def _minimal_environment() -> Dict[str, str]:
    """Avoid passing ZASI credentials and unrelated process state to tools."""
    return {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "LANG": "C",
        "LC_ALL": "C",
    }


def _run(
    command: Sequence[str],
    *,
    cwd: Path,
    timeout_seconds: float,
) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            list(command),
            cwd=os.fspath(cwd),
            env=_minimal_environment(),
            shell=False,
            check=False,
            capture_output=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise SpeechAdapterError("speech executable exceeded its timeout") from exc
    except OSError as exc:
        raise SpeechAdapterError("speech executable could not be started") from exc


def _safe_temp_file(directory: Path, name: str, payload: bytes) -> Path:
    path = directory / name
    path.write_bytes(payload)
    path.chmod(0o600)
    return path


def _normalize_transcript(value: bytes) -> str:
    try:
        text = value.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SpeechAdapterError("speech transcript is not UTF-8") from exc
    text = " ".join(text.split())
    if not text:
        raise SpeechAdapterError("speech executable returned an empty transcript")
    if len(text) > MAX_TRANSCRIPT_CHARS:
        raise SpeechAdapterError("speech transcript exceeds the safe bound")
    if any(ord(character) < 0x20 and character not in "\t\n\r" for character in text):
        raise SpeechAdapterError("speech transcript contains control characters")
    return text


class WhisperCppSTTAdapter:
    """Run a local whisper.cpp model against a bounded audio payload."""

    adapter_id = "zasi.stt.whisper-cpp"
    adapter_version = "1.0.0"

    def __init__(
        self,
        *,
        model_path: str,
        executable: Optional[str] = None,
        language: str = "en",
        timeout_seconds: float = 120.0,
        max_audio_bytes: int = MAX_AUDIO_BYTES,
    ) -> None:
        if not model_path or not Path(model_path).is_absolute():
            raise SpeechAdapterError("Whisper model path must be absolute")
        if not language or len(language) > 16 or not language.isalnum():
            raise SpeechAdapterError("Whisper language is invalid")
        if not 1.0 <= timeout_seconds <= 600.0:
            raise SpeechAdapterError("speech timeout is outside the safe bound")
        if not 1 <= max_audio_bytes <= MAX_AUDIO_BYTES:
            raise SpeechAdapterError("audio size bound is invalid")
        model = Path(model_path)
        if model.is_symlink() or not model.is_file():
            raise SpeechAdapterError("Whisper model file is unavailable")
        self._model_path = model.resolve(strict=True)
        self._model_digest = _digest_file(self._model_path, max_bytes=MAX_MODEL_BYTES)
        self._executable, self._executable_digest = _resolve_executable(
            executable,
            "whisper-cli",
        )
        self._language = language
        self._timeout_seconds = timeout_seconds
        self._max_audio_bytes = max_audio_bytes

    def transcribe(self, audio_bytes: bytes, *, content_type: str) -> SpeechTranscription:
        if not isinstance(audio_bytes, bytes) or not audio_bytes:
            raise SpeechAdapterError("audio payload is empty")
        if len(audio_bytes) > self._max_audio_bytes:
            raise SpeechAdapterError("audio payload exceeds the safe bound")
        suffix = _AUDIO_SUFFIXES.get(content_type.split(";", 1)[0].strip().lower())
        if suffix is None:
            raise SpeechAdapterError("audio format is unsupported")

        with tempfile.TemporaryDirectory(prefix="zasi-stt-") as raw_directory:
            directory = Path(raw_directory)
            directory.chmod(0o700)
            input_path = _safe_temp_file(directory, "input" + suffix, audio_bytes)
            output_prefix = directory / "transcript"
            command = (
                str(self._executable),
                "-m",
                str(self._model_path),
                "-f",
                str(input_path),
                "-l",
                self._language,
                "-ng",
                "-nt",
                "-np",
                "-otxt",
                "-of",
                str(output_prefix),
            )
            completed = _run(
                command,
                cwd=directory,
                timeout_seconds=self._timeout_seconds,
            )
            if completed.returncode != 0:
                raise SpeechAdapterError("Whisper transcription failed")
            transcript_path = Path(str(output_prefix) + ".txt")
            if not transcript_path.is_file() or transcript_path.is_symlink():
                raise SpeechAdapterError("Whisper transcript output is missing")
            transcript = _normalize_transcript(transcript_path.read_bytes())

        return SpeechTranscription(
            text=transcript,
            adapter_id=self.adapter_id,
            adapter_version=self.adapter_version,
            source_digest=_digest_bytes(audio_bytes),
            model_digest=self._model_digest,
            executable_digest=self._executable_digest,
            evidence_state="locally_verified",
            disclosure=(
                "Transcribed by the configured local whisper.cpp model in an "
                "argv-only bounded subprocess; output is not speaker authentication."
            ),
        )


class FliteTTSAdapter:
    """Synthesize bounded text with the local Flite executable."""

    adapter_id = "zasi.tts.flite"
    adapter_version = "1.0.0"

    def __init__(
        self,
        *,
        executable: Optional[str] = None,
        timeout_seconds: float = 30.0,
        max_text_chars: int = 4096,
    ) -> None:
        if not 1.0 <= timeout_seconds <= 120.0:
            raise SpeechAdapterError("speech timeout is outside the safe bound")
        if not 1 <= max_text_chars <= 16 * 1024:
            raise SpeechAdapterError("text size bound is invalid")
        self._executable, self._executable_digest = _resolve_executable(executable, "flite")
        self._timeout_seconds = timeout_seconds
        self._max_text_chars = max_text_chars

    def synthesize(self, text: str) -> SpeechSynthesis:
        if not isinstance(text, str) or not text.strip():
            raise SpeechAdapterError("text is empty")
        if len(text) > self._max_text_chars:
            raise SpeechAdapterError("text length exceeds the safe bound")
        if any(ord(character) < 0x20 and character not in "\t\n\r" for character in text):
            raise SpeechAdapterError("text contains control characters")

        with tempfile.TemporaryDirectory(prefix="zasi-tts-") as raw_directory:
            directory = Path(raw_directory)
            directory.chmod(0o700)
            output_path = directory / "speech.wav"
            command = (
                str(self._executable),
                "-t",
                text,
                "-o",
                str(output_path),
            )
            completed = _run(
                command,
                cwd=directory,
                timeout_seconds=self._timeout_seconds,
            )
            if completed.returncode != 0:
                raise SpeechAdapterError("Flite synthesis failed")
            if not output_path.is_file() or output_path.is_symlink():
                raise SpeechAdapterError("Flite waveform output is missing")
            try:
                audio_bytes = output_path.read_bytes()
            except OSError as exc:
                raise SpeechAdapterError("Flite waveform cannot be read") from exc
            if not audio_bytes or len(audio_bytes) > MAX_SYNTHESIS_BYTES:
                raise SpeechAdapterError("Flite waveform is outside the safe bound")
            try:
                with wave.open(str(output_path), "rb") as stream:
                    channels = stream.getnchannels()
                    sample_rate = stream.getframerate()
                    frames = stream.getnframes()
                    sample_width = stream.getsampwidth()
            except (EOFError, wave.Error, OSError) as exc:
                raise SpeechAdapterError("Flite output is not a valid WAV file") from exc
            if (
                channels not in {1, 2}
                or not 8_000 <= sample_rate <= 96_000
                or sample_width not in {1, 2, 3, 4}
                or frames <= 0
            ):
                raise SpeechAdapterError("Flite WAV properties are outside the safe bound")
            duration = frames / float(sample_rate)
            if duration <= 0.0 or duration > MAX_SYNTHESIS_SECONDS:
                raise SpeechAdapterError("Flite WAV duration is outside the safe bound")

        return SpeechSynthesis(
            audio_bytes=audio_bytes,
            content_type="audio/wav",
            sample_rate_hz=sample_rate,
            channels=channels,
            duration_seconds=round(duration, 3),
            audio_digest=_digest_bytes(audio_bytes),
            adapter_id=self.adapter_id,
            adapter_version=self.adapter_version,
            executable_digest=self._executable_digest,
            evidence_state="locally_verified",
            disclosure=(
                "Synthesized by the configured local Flite executable in an "
                "argv-only bounded subprocess; output is assistive audio, not authorization."
            ),
        )
