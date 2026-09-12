from . import multimodal as _multimodal_impl
from .multimodal import (
    ArtifactFormatError,
    ArtifactIntegrityError,
    MAX_ARTIFACT_BYTES,
    MAX_DECODED_IMAGE_BYTES,
    MAX_GEOMETRY_RECORDS,
    MAX_GLTF_BUFFER_BYTES,
    MAX_GLTF_CHUNKS,
    MAX_GLTF_COLLECTION_ITEMS,
    MAX_GLTF_INDEX_RECORDS,
    MAX_GLTF_JSON_BYTES,
    MAX_GLTF_JSON_DEPTH,
    MAX_IMAGE_DIMENSION,
    MAX_OBJ_FACE_REFERENCES,
    MAX_OBJ_RECORDS,
    MAX_OBJ_VERTICES,
    MAX_TOPOLOGY_RECORDS,
    _gltf_data_uri,
    analyze_image_artifact,
    artifact_digest,
    verify_artifact_digest,
    zlib,
)

# Keep the package-level parser limits patchable for callers/tests while the
# implementation remains in the dedicated multimodal module.  Overrides are
# applied only for the duration of a parse so direct implementation-level
# patches continue to work and test isolation is preserved.
_PATCHABLE_LIMITS = (
    "MAX_ARTIFACT_BYTES",
    "MAX_GEOMETRY_RECORDS",
    "MAX_TOPOLOGY_RECORDS",
    "MAX_OBJ_VERTICES",
    "MAX_OBJ_RECORDS",
    "MAX_OBJ_FACE_REFERENCES",
    "MAX_GLTF_JSON_BYTES",
    "MAX_GLTF_BUFFER_BYTES",
    "MAX_GLTF_JSON_DEPTH",
    "MAX_GLTF_COLLECTION_ITEMS",
    "MAX_GLTF_CHUNKS",
    "MAX_GLTF_INDEX_RECORDS",
    "MAX_IMAGE_DIMENSION",
    "MAX_DECODED_IMAGE_BYTES",
)
_DEFAULT_LIMITS = {name: globals()[name] for name in _PATCHABLE_LIMITS}


def parse_cad_artifact(*args, **kwargs):
    overrides = {
        name: globals()[name]
        for name in _PATCHABLE_LIMITS
        if globals()[name] != _DEFAULT_LIMITS[name]
    }
    previous = {name: getattr(_multimodal_impl, name) for name in overrides}
    try:
        for name, value in overrides.items():
            setattr(_multimodal_impl, name, value)
        return _multimodal_impl.parse_cad_artifact(*args, **kwargs)
    finally:
        for name, value in previous.items():
            setattr(_multimodal_impl, name, value)


__all__ = [
    "ArtifactFormatError",
    "ArtifactIntegrityError",
    "MAX_ARTIFACT_BYTES",
    "MAX_DECODED_IMAGE_BYTES",
    "MAX_GEOMETRY_RECORDS",
    "MAX_GLTF_BUFFER_BYTES",
    "MAX_GLTF_CHUNKS",
    "MAX_GLTF_COLLECTION_ITEMS",
    "MAX_GLTF_INDEX_RECORDS",
    "MAX_GLTF_JSON_BYTES",
    "MAX_GLTF_JSON_DEPTH",
    "MAX_IMAGE_DIMENSION",
    "MAX_OBJ_FACE_REFERENCES",
    "MAX_OBJ_RECORDS",
    "MAX_OBJ_VERTICES",
    "MAX_TOPOLOGY_RECORDS",
    "_gltf_data_uri",
    "analyze_image_artifact",
    "artifact_digest",
    "parse_cad_artifact",
    "verify_artifact_digest",
    "zlib",
]

from .speech_adapters import (
    FliteTTSAdapter,
    MAX_AUDIO_BYTES,
    MAX_MODEL_BYTES,
    MAX_SYNTHESIS_BYTES,
    MAX_SYNTHESIS_SECONDS,
    MAX_TRANSCRIPT_CHARS,
    SpeechAdapterError,
    SpeechSynthesis,
    SpeechTranscription,
)
