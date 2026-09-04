"""Bounded, source-backed multimodal artifact observations.

The reference profile deliberately reports only facts that can be derived from
the quarantined bytes.  This module does not run a solver, infer materials,
classify images, authenticate speakers, or authorize actions.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import io
import json
import math
import re
import struct
import zlib
from typing import Any, Dict, Iterable, List, Sequence, Tuple


MAX_ARTIFACT_BYTES = 16 * 1024 * 1024
MAX_GEOMETRY_RECORDS = 2_000_000
MAX_TOPOLOGY_RECORDS = 2_000_000
MAX_OBJ_VERTICES = min(MAX_GEOMETRY_RECORDS, MAX_ARTIFACT_BYTES // 64)
MAX_OBJ_RECORDS = MAX_OBJ_VERTICES * 2
MAX_OBJ_FACE_REFERENCES = MAX_OBJ_VERTICES
MAX_GLTF_JSON_BYTES = 8 * 1024 * 1024
MAX_GLTF_BUFFER_BYTES = MAX_ARTIFACT_BYTES
MAX_GLTF_JSON_DEPTH = 64
MAX_GLTF_COLLECTION_ITEMS = 100_000
MAX_GLTF_CHUNKS = 64
MAX_GLTF_INDEX_RECORDS = 2_000_000
MAX_IMAGE_DIMENSION = 32_768
MAX_DECODED_IMAGE_BYTES = 64 * 1024 * 1024

_NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?"
_NUMBER_RE = re.compile(rf"^{_NUMBER}$")
_STEP_POINT_RE = re.compile(
    r"(?:\A|[;\r\n])\s*#\d+\s*=\s*CARTESIAN_POINT\s*\(\s*'(?:[^']|'')*'\s*,\s*\(\s*([^)]*?)\s*\)\s*\)\s*;",
    re.IGNORECASE,
)
_STEP_TOPOLOGY_RE = re.compile(
    r"\b(?:(?P<edge>(?:ORIENTED_)?EDGE\s*\()|"
    r"(?P<face>(?:ADVANCED_FACE|FACE_SURFACE|ORIENTED_FACE)\s*\())",
    re.IGNORECASE,
)
_STEP_UNIT_RE = re.compile(
    r"\bSI_UNIT\s*\(\s*\.([A-Z]+)\.\s*,\s*\.([A-Z]+)\.\s*\)",
    re.IGNORECASE,
)
_STL_VERTEX_RE = re.compile(
    rf"^\s*vertex\s+({_NUMBER})\s+({_NUMBER})\s+({_NUMBER})\s*$",
    re.IGNORECASE,
)
_OBJ_FIELD_RE = re.compile(r"\S+")
_ADAM7_PASSES = (
    (0, 0, 8, 8),
    (4, 0, 8, 8),
    (0, 4, 4, 8),
    (2, 0, 4, 4),
    (0, 2, 2, 4),
    (1, 0, 2, 2),
    (0, 1, 1, 2),
)
_GLTF_COMPONENTS = {
    5120: ("b", 1),
    5121: ("B", 1),
    5122: ("h", 2),
    5123: ("H", 2),
    5125: ("I", 4),
    5126: ("f", 4),
}
_GLTF_TYPES = {
    "SCALAR": 1,
    "VEC2": 2,
    "VEC3": 3,
    "VEC4": 4,
    "MAT2": 4,
    "MAT3": 9,
    "MAT4": 16,
}


class ArtifactFormatError(ValueError):
    """Raised when quarantined bytes are not a supported valid artifact."""


class ArtifactIntegrityError(ValueError):
    """Raised when bytes no longer match their immutable artifact digest."""


def artifact_digest(data: bytes) -> str:
    """Return the canonical digest representation used by artifact records."""
    return "sha256:" + hashlib.sha256(data).hexdigest()


def verify_artifact_digest(data: bytes, expected_digest: str) -> None:
    """Fail closed when quarantined content has changed since upload."""
    actual_digest = artifact_digest(data)
    if not isinstance(expected_digest, str) or not hmac.compare_digest(
        actual_digest, expected_digest
    ):
        raise ArtifactIntegrityError("artifact content does not match its recorded digest")


def _bounded_bytes(data: bytes) -> bytes:
    if not isinstance(data, bytes):
        raise ArtifactFormatError("artifact content must be bytes")
    if not data or len(data) > MAX_ARTIFACT_BYTES:
        raise ArtifactFormatError("artifact size is outside the safe bound")
    return data


def _finite_coordinate(token: str) -> float:
    if not _NUMBER_RE.fullmatch(token.strip()):
        raise ArtifactFormatError("geometry contains an invalid coordinate")
    value = float(token)
    if not math.isfinite(value):
        raise ArtifactFormatError("geometry contains a non-finite coordinate")
    return value


def _coordinates(tokens: Sequence[str]) -> Tuple[float, float, float]:
    if len(tokens) != 3:
        raise ArtifactFormatError("geometry coordinates must contain exactly three values")
    return tuple(_finite_coordinate(token) for token in tokens)  # type: ignore[return-value]


def _bounds(points: Iterable[Tuple[float, float, float]]) -> Dict[str, Dict[str, float]]:
    values = list(points)
    if not values:
        raise ArtifactFormatError("artifact contains no geometry vertices")
    minimum = {
        axis: min(point[index] for point in values)
        for index, axis in enumerate(("x", "y", "z"))
    }
    maximum = {
        axis: max(point[index] for point in values)
        for index, axis in enumerate(("x", "y", "z"))
    }
    dimensions = {
        axis: maximum[axis] - minimum[axis] for axis in ("x", "y", "z")
    }
    if not all(math.isfinite(value) for value in dimensions.values()):
        raise ArtifactFormatError("geometry bounding-box dimensions are not finite")
    return {
        "minimum": minimum,
        "maximum": maximum,
        "dimensions": dimensions,
    }


def _unit_name(prefix: str, unit: str) -> str:
    if unit.upper() != "METRE":
        return "unknown"
    return {
        "QUECTO": "qm",
        "RONTO": "rm",
        "YOCTO": "ym",
        "ZEPTO": "zm",
        "ATTO": "am",
        "FEMTO": "fm",
        "PICO": "pm",
        "MILLI": "mm",
        "CENTI": "cm",
        "DECI": "dm",
        "MICRO": "um",
        "NANO": "nm",
        "DECA": "dam",
        "HECTO": "hm",
        "KILO": "km",
        "MEGA": "Mm",
        "GIGA": "Gm",
        "TERA": "Tm",
        "PETA": "Pm",
        "EXA": "Em",
        "ZETTA": "Zm",
        "YOTTA": "Ym",
        "RONNA": "Rm",
        "QUETTA": "Qm",
        "NONE": "m",
    }.get(prefix.upper(), "unknown")


def _step_topology_counts(text: str) -> Tuple[int, int]:
    edge_count = 0
    face_count = 0
    for match in _STEP_TOPOLOGY_RE.finditer(text):
        if match.group("edge") is not None:
            edge_count += 1
        else:
            face_count += 1
        if edge_count + face_count > MAX_TOPOLOGY_RECORDS:
            raise ArtifactFormatError("STEP topology record limit exceeded")
    return edge_count, face_count


def _step(data: bytes) -> Dict[str, Any]:
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ArtifactFormatError("STEP content must be ASCII") from exc
    clean_text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    normalized = clean_text.lstrip("\ufeff \t\r\n")
    if not normalized.upper().startswith("ISO-10303-21;"):
        raise ArtifactFormatError("STEP exchange structure is invalid")
    def step_marker(name: str, start: int = 0) -> Tuple[int, int] | None:
        match = re.search(
            rf"(?:\A|[;\r\n])\s*{name}\s*;",
            clean_text[start:],
            re.IGNORECASE,
        )
        if match is None:
            return None
        return start + match.start(), start + match.end()

    header_match = step_marker("HEADER")
    if header_match is None:
        raise ArtifactFormatError("STEP header section is missing")
    header_end = step_marker("ENDSEC", header_match[1])
    if header_end is None:
        raise ArtifactFormatError("STEP header section is incomplete")
    data_match = step_marker("DATA", header_end[1])
    if data_match is None:
        raise ArtifactFormatError("STEP data section is missing")
    data_end = step_marker("ENDSEC", data_match[1])
    if data_end is None:
        raise ArtifactFormatError("STEP data section is incomplete")
    end_iso = step_marker("END-ISO-10303-21", data_end[1])
    if end_iso is None:
        raise ArtifactFormatError("STEP exchange terminator is missing")
    data_text = clean_text[data_match[1] : data_end[0]]
    points: List[Tuple[float, float, float]] = []
    for match in _STEP_POINT_RE.finditer(data_text):
        if len(points) >= MAX_GEOMETRY_RECORDS:
            raise ArtifactFormatError("STEP geometry record limit exceeded")
        points.append(_coordinates(match.group(1).split(",")))
    if not points:
        raise ArtifactFormatError("STEP contains no CARTESIAN_POINT geometry")
    unit_match = _STEP_UNIT_RE.search(data_text)
    units = _unit_name(unit_match.group(1), unit_match.group(2)) if unit_match else "unknown"
    edge_count, face_count = _step_topology_counts(data_text)
    return {
        "format": "STEP",
        "parser": "zasi.step.stdlib",
        "parser_version": "1.0.0",
        "geometry_status": "measured",
        "units": units,
        "vertex_count": len(points),
        "edge_count": edge_count,
        "face_count": face_count,
        "triangle_count": None,
        "bounding_box": _bounds(points),
        "analysis": {"fea": "not_run", "thermal": "not_run"},
        "mesh_renderable": False,
        "source_digest": artifact_digest(data),
        "disclosure": (
            "Measured from STEP CARTESIAN_POINT entities by the bounded parser. "
            "Topology conversion, material properties, FEA, and thermal analysis were not run."
        ),
    }


def _stl(data: bytes) -> Dict[str, Any]:
    points: List[Tuple[float, float, float]] = []
    triangle_count = 0
    binary = False
    if len(data) >= 84:
        declared = struct.unpack_from("<I", data, 80)[0]
        expected_size = 84 + declared * 50
        binary = declared <= MAX_GEOMETRY_RECORDS and expected_size == len(data)
        if binary:
            triangle_count = declared
            for offset in range(84, len(data), 50):
                for vertex_offset in (12, 24, 36):
                    try:
                        point = struct.unpack_from("<fff", data, offset + vertex_offset)
                    except struct.error as exc:
                        raise ArtifactFormatError("binary STL triangle record is truncated") from exc
                    if not all(math.isfinite(value) for value in point):
                        raise ArtifactFormatError("STL contains a non-finite coordinate")
                    points.append(point)
    if not binary:
        try:
            text = data.decode("ascii")
        except UnicodeDecodeError as exc:
            raise ArtifactFormatError("STL is neither valid binary nor ASCII content") from exc
        saw_solid = False
        saw_endsolid = False
        in_facet = False
        in_loop = False
        facet_points: List[Tuple[float, float, float]] = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            lowered = stripped.lower()
            if lowered == "solid" or lowered.startswith("solid "):
                if saw_solid or in_facet or saw_endsolid:
                    raise ArtifactFormatError("ASCII STL solid header is invalid")
                saw_solid = True
                continue
            if lowered == "endsolid" or lowered.startswith("endsolid "):
                if not saw_solid or in_facet or in_loop or saw_endsolid:
                    raise ArtifactFormatError("ASCII STL solid footer is invalid")
                saw_endsolid = True
                continue
            if lowered.startswith("facet normal "):
                if not saw_solid or saw_endsolid or in_facet or in_loop:
                    raise ArtifactFormatError("ASCII STL facet structure is invalid")
                fields = stripped.split()
                if len(fields) != 5:
                    raise ArtifactFormatError("ASCII STL facet normal is invalid")
                _coordinates(fields[2:])
                in_facet = True
                facet_points = []
                continue
            if lowered == "outer loop":
                if not in_facet or in_loop:
                    raise ArtifactFormatError("ASCII STL loop structure is invalid")
                in_loop = True
                continue
            if lowered == "endloop":
                if not in_loop or len(facet_points) != 3:
                    raise ArtifactFormatError("ASCII STL loop must contain three vertices")
                in_loop = False
                continue
            if lowered == "endfacet":
                if not in_facet or in_loop or len(facet_points) != 3:
                    raise ArtifactFormatError("ASCII STL facet is incomplete")
                if triangle_count >= MAX_GEOMETRY_RECORDS:
                    raise ArtifactFormatError("STL geometry record limit exceeded")
                points.extend(facet_points)
                triangle_count += 1
                facet_points = []
                in_facet = False
                continue
            match = _STL_VERTEX_RE.match(stripped)
            if match:
                if not in_loop or len(facet_points) >= 3:
                    raise ArtifactFormatError("ASCII STL vertex is outside a complete triangle")
                facet_points.append(_coordinates(match.groups()))
                continue
            raise ArtifactFormatError("ASCII STL structure is invalid")
        if not saw_solid or not saw_endsolid or in_facet or in_loop or not points:
            raise ArtifactFormatError("ASCII STL exchange structure is incomplete")
    if not points or triangle_count < 1:
        raise ArtifactFormatError("STL contains no triangles")
    return {
        "format": "STL",
        "parser": "zasi.stl.stdlib",
        "parser_version": "1.0.0",
        "geometry_status": "measured",
        "units": "unknown",
        "vertex_count": len(points),
        "edge_count": None,
        "face_count": triangle_count,
        "triangle_count": triangle_count,
        "bounding_box": _bounds(points),
        "analysis": {"fea": "not_run", "thermal": "not_run"},
        "mesh_renderable": True,
        "source_digest": artifact_digest(data),
        "disclosure": (
            "Measured from STL triangle vertices by the bounded parser. Units, materials, "
            "manufacturing tolerances, FEA, and thermal analysis were not supplied or run."
        ),
    }


def _obj_tokens(line: str) -> Iterable[str]:
    for match in _OBJ_FIELD_RE.finditer(line):
        token = match.group(0)
        if token.startswith("#"):
            return
        yield token


def _obj(data: bytes) -> Dict[str, Any]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ArtifactFormatError("OBJ content must be UTF-8") from exc
    points: List[Tuple[float, float, float]] = []
    face_count = 0
    with io.StringIO(text) as stream:
        for line_number, line in enumerate(stream, 1):
            if line_number > MAX_OBJ_RECORDS:
                raise ArtifactFormatError("OBJ record limit exceeded")
            tokens = iter(_obj_tokens(line))
            try:
                directive = next(tokens)
            except StopIteration:
                continue
            if directive == "v":
                if len(points) >= MAX_OBJ_VERTICES:
                    raise ArtifactFormatError("OBJ vertex limit exceeded")
                values: List[str] = []
                for _ in range(5):
                    try:
                        values.append(next(tokens))
                    except StopIteration:
                        break
                if len(values) not in {3, 4}:
                    raise ArtifactFormatError("OBJ vertex must contain three coordinates and an optional w")
                point = _coordinates(values[:3])
                if len(values) == 4:
                    weight = _finite_coordinate(values[3])
                    if weight == 0:
                        raise ArtifactFormatError("OBJ homogeneous coordinate cannot be zero")
                    point = tuple(value / weight for value in point)  # type: ignore[assignment]
                    if not all(math.isfinite(value) for value in point):
                        raise ArtifactFormatError("OBJ homogeneous coordinate overflows")
                points.append(point)
                try:
                    next(tokens)
                except StopIteration:
                    pass
                else:
                    raise ArtifactFormatError("OBJ vertex contains too many values")
            elif directive == "f":
                reference_count = 0
                for reference in tokens:
                    reference_count += 1
                    if reference_count > MAX_OBJ_FACE_REFERENCES:
                        raise ArtifactFormatError("OBJ face reference limit exceeded")
                    index = reference.split("/", 1)[0]
                    try:
                        vertex_index = int(index)
                    except ValueError as exc:
                        raise ArtifactFormatError("OBJ face contains an invalid vertex index") from exc
                    if vertex_index == 0 or abs(vertex_index) > len(points):
                        raise ArtifactFormatError("OBJ face references a missing vertex")
                if reference_count < 3:
                    raise ArtifactFormatError("OBJ face must contain at least three vertices")
                if face_count >= MAX_OBJ_VERTICES:
                    raise ArtifactFormatError("OBJ face limit exceeded")
                face_count += 1
    if not points:
        raise ArtifactFormatError("OBJ contains no vertices")
    return {
        "format": "OBJ",
        "parser": "zasi.obj.stdlib",
        "parser_version": "1.0.0",
        "geometry_status": "measured",
        "units": "unknown",
        "vertex_count": len(points),
        "edge_count": None,
        "face_count": face_count,
        "triangle_count": None,
        "bounding_box": _bounds(points),
        "analysis": {"fea": "not_run", "thermal": "not_run"},
        "mesh_renderable": True,
        "source_digest": artifact_digest(data),
        "disclosure": (
            "Measured from OBJ vertex and face records by the bounded parser. Units, materials, "
            "manufacturing tolerances, FEA, and thermal analysis were not supplied or run."
        ),
    }


def _gltf_object(pairs: List[Tuple[str, Any]]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ArtifactFormatError("glTF JSON contains a duplicate object key")
        result[key] = value
    return result


def _gltf_constant(value: str) -> Any:
    raise ArtifactFormatError(f"glTF JSON constant {value} is not valid")


def _validate_gltf_json_depth(text: str) -> None:
    depth = 0
    in_string = False
    escaped = False
    for character in text:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character in "[{":
            depth += 1
            if depth > MAX_GLTF_JSON_DEPTH:
                raise ArtifactFormatError("glTF JSON nesting exceeds the safe bound")
        elif character in "]}":
            depth -= 1
            if depth < 0:
                raise ArtifactFormatError("glTF JSON nesting is invalid")
    if in_string or escaped or depth != 0:
        raise ArtifactFormatError("glTF JSON structure is incomplete")


def _gltf_json_document(data: bytes) -> Dict[str, Any]:
    if not data or len(data) > MAX_GLTF_JSON_BYTES:
        raise ArtifactFormatError("glTF JSON exceeds the safe bound")
    trimmed = data.rstrip(b" \t\r\n\x00")
    try:
        text = trimmed.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ArtifactFormatError("glTF JSON must be UTF-8") from exc
    _validate_gltf_json_depth(text)
    try:
        document = json.loads(
            text,
            object_pairs_hook=_gltf_object,
            parse_constant=_gltf_constant,
        )
    except ArtifactFormatError:
        raise
    except (json.JSONDecodeError, RecursionError, MemoryError, ValueError) as exc:
        raise ArtifactFormatError("glTF JSON is invalid") from exc
    if not isinstance(document, dict):
        raise ArtifactFormatError("glTF root must be a JSON object")
    return document


def _gltf_integer(value: Any, name: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ArtifactFormatError(f"glTF {name} must be a bounded integer")
    return value


def _gltf_mapping(value: Any, name: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise ArtifactFormatError(f"glTF {name} must be an object")
    return value


def _gltf_collection(document: Dict[str, Any], name: str, *, required: bool = False) -> List[Any]:
    value = document.get(name)
    if value is None and not required:
        return []
    if not isinstance(value, list) or len(value) > MAX_GLTF_COLLECTION_ITEMS:
        raise ArtifactFormatError(f"glTF {name} collection is invalid or too large")
    if required and not value:
        raise ArtifactFormatError(f"glTF {name} collection is empty")
    return value


def _gltf_data_uri(uri: Any) -> bytes:
    if not isinstance(uri, str) or not uri.lower().startswith("data:"):
        raise ArtifactFormatError("external glTF buffer URIs are not fetched")
    header, separator, payload = uri.partition(",")
    parameters = header.split(";")
    if not separator or not any(parameter.lower() == "base64" for parameter in parameters[1:]):
        raise ArtifactFormatError("glTF buffers require a base64 data URI")
    try:
        return base64.b64decode(payload, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ArtifactFormatError("glTF buffer data URI is invalid") from exc


def _gltf_buffers(document: Dict[str, Any], binary_payload: bytes | None) -> List[bytes]:
    raw_buffers = _gltf_collection(document, "buffers", required=True)
    if binary_payload is not None and (
        len(raw_buffers) != 1
        or not isinstance(raw_buffers[0], dict)
        or raw_buffers[0].get("uri") is not None
    ):
        raise ArtifactFormatError("GLB must contain exactly one URI-less buffer")
    buffers: List[bytes] = []
    total_bytes = 0
    for index, raw_buffer in enumerate(raw_buffers):
        buffer = _gltf_mapping(raw_buffer, f"buffer {index}")
        byte_length = _gltf_integer(buffer.get("byteLength"), f"buffer {index} byteLength", minimum=1)
        if byte_length > MAX_GLTF_BUFFER_BYTES:
            raise ArtifactFormatError("glTF buffer exceeds the safe bound")
        uri = buffer.get("uri")
        if uri is None:
            if binary_payload is None:
                raise ArtifactFormatError("glTF JSON buffer has no embedded data")
            payload = binary_payload
        else:
            if binary_payload is not None:
                raise ArtifactFormatError("GLB must not reference external buffers")
            payload = _gltf_data_uri(uri)
        if len(payload) < byte_length:
            raise ArtifactFormatError("glTF buffer is shorter than its declared length")
        total_bytes += byte_length
        if total_bytes > MAX_GLTF_BUFFER_BYTES:
            raise ArtifactFormatError("glTF buffers exceed the aggregate safe bound")
        buffers.append(payload[:byte_length])
    return buffers


def _gltf_container(data: bytes, media_type: str) -> Tuple[Dict[str, Any], List[bytes], str]:
    binary_types = {"model/gltf-binary", "application/gltf-binary"}
    json_types = {"model/gltf+json", "application/gltf+json"}
    if media_type in binary_types or data.startswith(b"glTF"):
        if len(data) < 20:
            raise ArtifactFormatError("GLB header is incomplete")
        magic, version, declared_length = struct.unpack_from("<4sII", data, 0)
        if magic != b"glTF" or version != 2 or declared_length != len(data):
            raise ArtifactFormatError("GLB header is invalid")
        offset = 12
        chunk_count = 0
        json_payload: bytes | None = None
        binary_payload: bytes | None = None
        while offset < declared_length:
            chunk_count += 1
            if chunk_count > MAX_GLTF_CHUNKS or offset + 8 > declared_length:
                raise ArtifactFormatError("GLB chunk structure is invalid")
            chunk_length, chunk_type = struct.unpack_from("<II", data, offset)
            if chunk_length % 4 != 0:
                raise ArtifactFormatError("GLB chunk length is not aligned")
            end = offset + 8 + chunk_length
            if end > declared_length:
                raise ArtifactFormatError("GLB chunk exceeds artifact bounds")
            payload = data[offset + 8 : end]
            if chunk_type == 0x4E4F534A:
                if chunk_count != 1 or json_payload is not None:
                    raise ArtifactFormatError("GLB JSON chunk is duplicated or misplaced")
                json_payload = payload
            elif chunk_type == 0x004E4942:
                if binary_payload is not None:
                    raise ArtifactFormatError("GLB BIN chunk is duplicated")
                binary_payload = payload
            offset = end
        if json_payload is None or offset != declared_length:
            raise ArtifactFormatError("GLB JSON chunk is missing")
        document = _gltf_json_document(json_payload)
        return document, _gltf_buffers(document, binary_payload), "GLB"
    if media_type not in json_types:
        raise ArtifactFormatError("glTF media type is not supported by the reference parser")
    document = _gltf_json_document(data)
    return document, _gltf_buffers(document, None), "GLTF"


def _gltf_accessor_descriptor(
    accessors: List[Any],
    buffer_views: List[Any],
    buffers: List[bytes],
    accessor_index: Any,
    *,
    expected_type: str | None = None,
    allowed_component_types: frozenset[int] | None = None,
) -> Dict[str, Any]:
    index = _gltf_integer(accessor_index, "accessor index")
    if index >= len(accessors):
        raise ArtifactFormatError("glTF accessor index is out of range")
    accessor = _gltf_mapping(accessors[index], f"accessor {index}")
    if "sparse" in accessor:
        raise ArtifactFormatError("sparse glTF accessors are not enabled")
    view_index = accessor.get("bufferView")
    view_index = _gltf_integer(view_index, f"accessor {index} bufferView")
    if view_index >= len(buffer_views):
        raise ArtifactFormatError("glTF bufferView index is out of range")
    view = _gltf_mapping(buffer_views[view_index], f"bufferView {view_index}")
    buffer_index = _gltf_integer(view.get("buffer"), f"bufferView {view_index} buffer")
    if buffer_index >= len(buffers):
        raise ArtifactFormatError("glTF buffer index is out of range")
    buffer_offset = _gltf_integer(view.get("byteOffset", 0), f"bufferView {view_index} byteOffset")
    view_length = _gltf_integer(view.get("byteLength"), f"bufferView {view_index} byteLength", minimum=1)
    if buffer_offset + view_length > len(buffers[buffer_index]):
        raise ArtifactFormatError("glTF bufferView exceeds its buffer")
    component_type = _gltf_integer(accessor.get("componentType"), f"accessor {index} componentType")
    component_info = _GLTF_COMPONENTS.get(component_type)
    if component_info is None or (
        allowed_component_types is not None and component_type not in allowed_component_types
    ):
        raise ArtifactFormatError("glTF accessor component type is unsupported")
    accessor_type = accessor.get("type")
    if not isinstance(accessor_type, str) or accessor_type not in _GLTF_TYPES:
        raise ArtifactFormatError("glTF accessor type is unsupported")
    if expected_type is not None and accessor_type != expected_type:
        raise ArtifactFormatError(f"glTF accessor must have type {expected_type}")
    component_count = _GLTF_TYPES[accessor_type]
    component_format, component_width = component_info
    element_size = component_count * component_width
    accessor_offset = _gltf_integer(accessor.get("byteOffset", 0), f"accessor {index} byteOffset")
    start = buffer_offset + accessor_offset
    if start % component_width != 0:
        raise ArtifactFormatError("glTF accessor is misaligned")
    normalized = accessor.get("normalized", False)
    if not isinstance(normalized, bool):
        raise ArtifactFormatError("glTF accessor normalized flag is invalid")
    if normalized and component_type == 5126:
        raise ArtifactFormatError("floating-point glTF accessors cannot be normalized")
    count = _gltf_integer(accessor.get("count"), f"accessor {index} count", minimum=1)
    if count > MAX_GEOMETRY_RECORDS:
        raise ArtifactFormatError("glTF accessor count exceeds the safe bound")
    if "byteStride" in view:
        stride = _gltf_integer(
            view["byteStride"], f"bufferView {view_index} byteStride", minimum=element_size
        )
        if stride > 252 or stride % 4 != 0:
            raise ArtifactFormatError("glTF bufferView byteStride is invalid")
    else:
        stride = element_size
    required_end = start + (count - 1) * stride + element_size
    if required_end > buffer_offset + view_length:
        raise ArtifactFormatError("glTF accessor exceeds its bufferView")
    return {
        "buffer": buffers[buffer_index],
        "start": start,
        "stride": stride,
        "format": component_format,
        "components": component_count,
        "component_type": component_type,
        "count": count,
        "normalized": normalized,
    }


def _gltf_normalize(value: int, component_type: int) -> float:
    if component_type == 5120:
        return max(value / 127.0, -1.0)
    if component_type == 5121:
        return value / 255.0
    if component_type == 5122:
        return max(value / 32767.0, -1.0)
    if component_type == 5123:
        return value / 65535.0
    if component_type == 5125:
        return value / 4294967295.0
    raise ArtifactFormatError("glTF normalized component type is unsupported")


def _gltf_accessor_values(descriptor: Dict[str, Any]) -> Iterable[Tuple[float, ...]]:
    format_string = "<" + descriptor["format"] * descriptor["components"]
    for item_index in range(descriptor["count"]):
        values = struct.unpack_from(
            format_string,
            descriptor["buffer"],
            descriptor["start"] + item_index * descriptor["stride"],
        )
        if descriptor["normalized"]:
            yield tuple(
                _gltf_normalize(value, descriptor["component_type"]) for value in values
            )
        else:
            yield tuple(float(value) for value in values)


def _gltf(data: bytes, media_type: str) -> Dict[str, Any]:
    document, buffers, container = _gltf_container(data, media_type)
    asset = _gltf_mapping(document.get("asset"), "asset")
    version = asset.get("version")
    if not isinstance(version, str) or not version.startswith("2."):
        raise ArtifactFormatError("glTF asset version 2 is required")
    buffer_views = _gltf_collection(document, "bufferViews", required=True)
    accessors = _gltf_collection(document, "accessors", required=True)
    meshes = _gltf_collection(document, "meshes", required=True)
    minimum = [math.inf, math.inf, math.inf]
    maximum = [-math.inf, -math.inf, -math.inf]
    vertex_count = 0
    triangle_count = 0
    index_count = 0
    primitive_count = 0
    for mesh_index, raw_mesh in enumerate(meshes):
        mesh = _gltf_mapping(raw_mesh, f"mesh {mesh_index}")
        primitives = mesh.get("primitives")
        if not isinstance(primitives, list) or not primitives or len(primitives) > MAX_GLTF_COLLECTION_ITEMS:
            raise ArtifactFormatError("glTF mesh primitives are invalid or empty")
        for primitive in primitives:
            primitive = _gltf_mapping(primitive, "mesh primitive")
            attributes = _gltf_mapping(primitive.get("attributes"), "primitive attributes")
            position_index = attributes.get("POSITION")
            position = _gltf_accessor_descriptor(
                accessors,
                buffer_views,
                buffers,
                position_index,
                expected_type="VEC3",
                allowed_component_types=frozenset({5126}),
            )
            primitive_vertex_count = position["count"]
            vertex_count += primitive_vertex_count
            if vertex_count > MAX_GEOMETRY_RECORDS:
                raise ArtifactFormatError("glTF geometry record limit exceeded")
            for point in _gltf_accessor_values(position):
                if not all(math.isfinite(value) for value in point):
                    raise ArtifactFormatError("glTF POSITION contains a non-finite coordinate")
                for axis in range(3):
                    minimum[axis] = min(minimum[axis], point[axis])
                    maximum[axis] = max(maximum[axis], point[axis])
            indices = primitive.get("indices")
            if indices is not None:
                index_descriptor = _gltf_accessor_descriptor(
                    accessors,
                    buffer_views,
                    buffers,
                    indices,
                    expected_type="SCALAR",
                    allowed_component_types=frozenset({5121, 5123, 5125}),
                )
                index_count += index_descriptor["count"]
                if index_count > MAX_GLTF_INDEX_RECORDS:
                    raise ArtifactFormatError("glTF index record limit exceeded")
                for index_value in _gltf_accessor_values(index_descriptor):
                    index = int(index_value[0])
                    if index < 0 or index >= primitive_vertex_count:
                        raise ArtifactFormatError("glTF index references a missing POSITION")
                primitive_vertex_count = index_descriptor["count"]
            mode = primitive.get("mode", 4)
            mode = _gltf_integer(mode, "primitive mode")
            if mode > 6:
                raise ArtifactFormatError("glTF primitive mode is unsupported")
            if mode == 4:
                if primitive_vertex_count % 3 != 0:
                    raise ArtifactFormatError("glTF triangle primitive is incomplete")
                triangle_count += primitive_vertex_count // 3
            elif mode in {5, 6}:
                triangle_count += max(0, primitive_vertex_count - 2)
            if triangle_count > MAX_GEOMETRY_RECORDS:
                raise ArtifactFormatError("glTF triangle record limit exceeded")
            primitive_count += 1
    if vertex_count == 0 or not all(math.isfinite(value) for value in minimum + maximum):
        raise ArtifactFormatError("glTF contains no finite POSITION geometry")
    dimensions = {
        axis: maximum[index] - minimum[index]
        for index, axis in enumerate(("x", "y", "z"))
    }
    if not all(math.isfinite(value) for value in dimensions.values()):
        raise ArtifactFormatError("glTF bounding-box dimensions are not finite")
    return {
        "format": container,
        "parser": "zasi.gltf.stdlib",
        "parser_version": "1.0.0",
        "geometry_status": "measured",
        "units": "m",
        "vertex_count": vertex_count,
        "edge_count": None,
        "face_count": triangle_count,
        "triangle_count": triangle_count,
        "mesh_count": len(meshes),
        "primitive_count": primitive_count,
        "buffer_count": len(buffers),
        "index_count": index_count,
        "coordinate_space": "mesh-local",
        "bounding_box": {
            "minimum": {axis: minimum[index] for index, axis in enumerate(("x", "y", "z"))},
            "maximum": {axis: maximum[index] for index, axis in enumerate(("x", "y", "z"))},
            "dimensions": dimensions,
        },
        "analysis": {"fea": "not_run", "thermal": "not_run"},
        "mesh_renderable": True,
        "source_digest": artifact_digest(data),
        "disclosure": (
            "Measured from actual glTF POSITION and index accessor bytes by the bounded stdlib parser. "
            "Bounds are mesh-local; node transforms, sparse accessors, external buffers, materials, "
            "morph targets, FEA, and thermal analysis were not applied or run."
        ),
    }


def parse_cad_artifact(data: bytes, media_type: str) -> Dict[str, Any]:
    """Parse supported geometry bytes without trusting caller-provided metadata."""
    data = _bounded_bytes(data)
    normalized_type = (media_type or "").split(";", 1)[0].strip().lower()
    if normalized_type in {"application/step", "model/step", "application/iges", "model/iges"}:
        if normalized_type in {"application/iges", "model/iges"}:
            raise ArtifactFormatError("IGES parsing is not enabled in the reference adapter")
        return _step(data)
    if normalized_type == "model/stl":
        return _stl(data)
    if normalized_type == "model/obj":
        return _obj(data)
    if normalized_type in {
        "model/gltf+json",
        "application/gltf+json",
        "model/gltf-binary",
        "application/gltf-binary",
    }:
        return _gltf(data, normalized_type)
    if normalized_type == "application/octet-stream":
        if data.lstrip().startswith(b"ISO-10303-21;"):
            return _step(data)
        if data.lstrip().startswith((b"solid ", b"SOLID ")):
            return _stl(data)
        if re.search(rb"(?m)^\s*v\s+", data):
            return _obj(data)
        if data.startswith(b"glTF"):
            return _gltf(data, normalized_type)
    raise ArtifactFormatError("CAD media type is not supported by the reference parser")


def _png_scanline_layout(
    width: int, height: int, bit_depth: int, channels: int, interlace: int
) -> List[Tuple[int, int]]:
    row_bytes = (width * bit_depth * channels + 7) // 8
    if interlace == 0:
        return [(row_bytes, height)]
    layout: List[Tuple[int, int]] = []
    for start_x, start_y, step_x, step_y in _ADAM7_PASSES:
        pass_width = (width - start_x + step_x - 1) // step_x if width > start_x else 0
        pass_height = (height - start_y + step_y - 1) // step_y if height > start_y else 0
        if pass_width and pass_height:
            pass_row_bytes = (pass_width * bit_depth * channels + 7) // 8
            layout.append((pass_row_bytes, pass_height))
    return layout


def _validate_png_filter_bytes(decoded: bytes, layout: Sequence[Tuple[int, int]]) -> None:
    offset = 0
    for row_bytes, row_count in layout:
        for _ in range(row_count):
            if offset >= len(decoded) or decoded[offset] > 4:
                raise ArtifactFormatError("PNG scanline filter is invalid")
            offset += row_bytes + 1
    if offset != len(decoded):
        raise ArtifactFormatError("PNG scanline layout is invalid")


def _png_dimensions_and_digest(data: bytes) -> Tuple[Dict[str, int], str]:
    if len(data) < 33 or not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ArtifactFormatError("PNG signature is invalid")
    first_size = struct.unpack_from(">I", data, 8)[0]
    if first_size != 13 or data[12:16] != b"IHDR":
        raise ArtifactFormatError("PNG IHDR chunk is missing")
    first_crc = struct.unpack_from(">I", data, 29)[0]
    if (zlib.crc32(data[12:29]) & 0xFFFFFFFF) != first_crc:
        raise ArtifactFormatError("PNG IHDR CRC is invalid")
    width, height, bit_depth, color_type, compression, filtering, interlace = struct.unpack(
        ">IIBBBBB", data[16:29]
    )
    if not 1 <= width <= MAX_IMAGE_DIMENSION or not 1 <= height <= MAX_IMAGE_DIMENSION:
        raise ArtifactFormatError("PNG dimensions are outside the safe bound")
    allowed_bit_depths = {
        0: {1, 2, 4, 8, 16},
        2: {8, 16},
        3: {1, 2, 4, 8},
        4: {8, 16},
        6: {8, 16},
    }
    if (
        bit_depth not in allowed_bit_depths.get(color_type, set())
        or compression != 0
        or filtering != 0
        or interlace not in {0, 1}
    ):
        raise ArtifactFormatError("PNG encoding is unsupported")
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color_type)
    if channels is None:
        raise ArtifactFormatError("PNG color type is unsupported")
    scanline_layout = _png_scanline_layout(width, height, bit_depth, channels, interlace)
    expected_decoded_size = sum(
        (row_bytes + 1) * row_count for row_bytes, row_count in scanline_layout
    )
    if expected_decoded_size > MAX_DECODED_IMAGE_BYTES:
        raise ArtifactFormatError("PNG decoded image exceeds the safe memory bound")
    idat = bytearray()
    offset = 8
    seen_ihdr = False
    seen_iend = False
    while offset + 12 <= len(data):
        size = struct.unpack_from(">I", data, offset)[0]
        end = offset + 12 + size
        if end > len(data):
            raise ArtifactFormatError("PNG chunk exceeds artifact bounds")
        kind = data[offset + 4 : offset + 8]
        payload = data[offset + 8 : offset + 8 + size]
        stored_crc = struct.unpack_from(">I", data, end - 4)[0]
        if (zlib.crc32(kind + payload) & 0xFFFFFFFF) != stored_crc:
            raise ArtifactFormatError("PNG chunk CRC is invalid")
        if kind == b"IHDR":
            if seen_ihdr or offset != 8:
                raise ArtifactFormatError("PNG IHDR chunk is duplicated or misplaced")
            seen_ihdr = True
        if kind == b"IDAT":
            idat.extend(payload)
        if kind == b"IEND":
            if size != 0:
                raise ArtifactFormatError("PNG IEND chunk is invalid")
            seen_iend = True
            offset = end
            break
        offset = end
    if not seen_ihdr or not idat or not seen_iend or offset != len(data):
        raise ArtifactFormatError("PNG image data is incomplete")
    try:
        decompressor = zlib.decompressobj()
        decoded = decompressor.decompress(bytes(idat), MAX_DECODED_IMAGE_BYTES + 1)
    except zlib.error as exc:
        raise ArtifactFormatError("PNG image data cannot be decoded") from exc
    if (
        len(decoded) > MAX_DECODED_IMAGE_BYTES
        or not decompressor.eof
        or decompressor.unconsumed_tail
        or decompressor.unused_data
        or len(decoded) != expected_decoded_size
    ):
        raise ArtifactFormatError("PNG decoded image is incomplete or exceeds the safe bound")
    _validate_png_filter_bytes(decoded, scanline_layout)
    return {"width": width, "height": height}, hashlib.sha256(decoded).hexdigest()


def _jpeg_dimensions(data: bytes) -> Dict[str, int]:
    if len(data) < 4 or data[:2] != b"\xff\xd8":
        raise ArtifactFormatError("JPEG signature is invalid")
    offset = 2
    sof_markers = set(range(0xC0, 0xC4)) | set(range(0xC5, 0xC8)) | set(range(0xC9, 0xCC)) | set(range(0xCD, 0xD0))
    dimensions: Dict[str, int] | None = None
    frame_component_ids: frozenset[int] | None = None
    in_scan = False
    saw_scan = False
    saw_scan_data = False
    while offset < len(data):
        marker: int | None = None
        if in_scan:
            while offset < len(data):
                if data[offset] != 0xFF:
                    saw_scan_data = True
                    offset += 1
                    continue
                offset += 1
                while offset < len(data) and data[offset] == 0xFF:
                    offset += 1
                if offset >= len(data):
                    raise ArtifactFormatError("JPEG scan data is incomplete")
                marker = data[offset]
                offset += 1
                if marker == 0x00 or 0xD0 <= marker <= 0xD7:
                    saw_scan_data = True
                    continue
                if marker == 0xD9:
                    if not saw_scan_data or not saw_scan or dimensions is None:
                        raise ArtifactFormatError("JPEG scan data is incomplete")
                    return dimensions
                in_scan = False
                break
            if in_scan:
                raise ArtifactFormatError("JPEG end marker is missing")
        else:
            if data[offset] != 0xFF:
                raise ArtifactFormatError("JPEG marker structure is invalid")
            offset += 1
            while offset < len(data) and data[offset] == 0xFF:
                offset += 1
            if offset >= len(data):
                raise ArtifactFormatError("JPEG marker is incomplete")
            marker = data[offset]
            offset += 1
        if marker is None or marker in {0x00, 0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
            raise ArtifactFormatError("JPEG marker structure is invalid")
        if marker == 0x01:
            continue
        if offset + 2 > len(data):
            raise ArtifactFormatError("JPEG segment length is incomplete")
        segment_length = struct.unpack_from(">H", data, offset)[0]
        if segment_length < 2 or offset + segment_length > len(data):
            raise ArtifactFormatError("JPEG segment exceeds artifact bounds")
        if marker in sof_markers:
            if segment_length < 8:
                raise ArtifactFormatError("JPEG frame header is incomplete")
            height, width = struct.unpack_from(">HH", data, offset + 3)
            components = data[offset + 7]
            if components < 1 or components > 4 or segment_length != 8 + 3 * components:
                raise ArtifactFormatError("JPEG frame component table is invalid")
            component_ids = [data[offset + 8 + 3 * index] for index in range(components)]
            if any(component_id == 0 for component_id in component_ids) or len(set(component_ids)) != components:
                raise ArtifactFormatError("JPEG frame component identifiers are invalid")
            if not 1 <= width <= MAX_IMAGE_DIMENSION or not 1 <= height <= MAX_IMAGE_DIMENSION:
                raise ArtifactFormatError("JPEG dimensions are outside the safe bound")
            if dimensions is not None:
                raise ArtifactFormatError("JPEG contains multiple frame headers")
            dimensions = {"width": width, "height": height}
            frame_component_ids = frozenset(component_ids)
        elif marker == 0xDA:
            if dimensions is None or frame_component_ids is None or segment_length < 8:
                raise ArtifactFormatError("JPEG scan header is incomplete")
            scan_components = data[offset + 2]
            if scan_components < 1 or scan_components > 4 or segment_length != 6 + 2 * scan_components:
                raise ArtifactFormatError("JPEG scan component table is invalid")
            scan_component_ids = [
                data[offset + 3 + 2 * index] for index in range(scan_components)
            ]
            if (
                len(set(scan_component_ids)) != scan_components
                or any(component_id not in frame_component_ids for component_id in scan_component_ids)
            ):
                raise ArtifactFormatError("JPEG scan references an undeclared frame component")
            saw_scan = True
            saw_scan_data = False
            in_scan = True
        offset += segment_length
    raise ArtifactFormatError("JPEG end marker is missing")


def analyze_image_artifact(data: bytes, media_type: str) -> Dict[str, Any]:
    """Decode bounded image structure and fingerprints from actual source bytes.

    This is intentionally an image-observation adapter, not a semantic detector.
    A future detector must add its model identity and independent evaluation before
    labels or confidence can be exposed.
    """
    data = _bounded_bytes(data)
    normalized_type = (media_type or "").split(";", 1)[0].strip().lower()
    if normalized_type == "image/png" or data.startswith(b"\x89PNG\r\n\x1a\n"):
        image_format = "PNG"
        dimensions, pixel_digest = _png_dimensions_and_digest(data)
    elif normalized_type == "image/jpeg" or data.startswith(b"\xff\xd8"):
        image_format = "JPEG"
        dimensions = _jpeg_dimensions(data)
        pixel_digest = None
    else:
        raise ArtifactFormatError("image media type is not supported by the reference adapter")
    return {
        "format": image_format,
        "dimensions": dimensions,
        "content_digest": artifact_digest(data),
        "pixel_digest": None,
        "decoded_payload_digest": (
            "sha256:" + pixel_digest if image_format == "PNG" else None
        ),
        "encoded_content_digest": artifact_digest(data),
        "semantic_model": "not_configured",
        "labels": [],
        "confidence": None,
        "disclosure": (
            "The supplied image bytes were structurally validated for format and dimensions. "
            "PNG decompressed payload and encoded-content fingerprints are recorded; JPEG pixels "
            "were not decoded. No semantic vision model is configured; labels and confidence are unavailable."
        ),
    }
