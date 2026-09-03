"""Bounded, source-backed multimodal artifact observations.

The reference profile deliberately reports only facts that can be derived from
the quarantined bytes.  This module does not run a solver, infer materials,
classify images, authenticate speakers, or authorize actions.
"""

from __future__ import annotations

import hashlib
import hmac
import math
import re
import struct
import zlib
from typing import Any, Dict, Iterable, List, Sequence, Tuple


MAX_ARTIFACT_BYTES = 16 * 1024 * 1024
MAX_GEOMETRY_RECORDS = 2_000_000
MAX_IMAGE_DIMENSION = 32_768
MAX_DECODED_IMAGE_BYTES = 64 * 1024 * 1024

_NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?"
_NUMBER_RE = re.compile(rf"^{_NUMBER}$")
_STEP_POINT_RE = re.compile(
    r"\bCARTESIAN_POINT\s*\(\s*'(?:[^']|'')*'\s*,\s*\(\s*([^)]*?)\s*\)\s*\)",
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
    return {
        "minimum": minimum,
        "maximum": maximum,
        "dimensions": {
            axis: maximum[axis] - minimum[axis] for axis in ("x", "y", "z")
        },
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


def _step(data: bytes) -> Dict[str, Any]:
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ArtifactFormatError("STEP content must be ASCII") from exc
    clean_text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    normalized = clean_text.lstrip("\ufeff \t\r\n")
    upper_text = normalized.upper()
    if (
        not normalized.startswith("ISO-10303-21;")
        or "HEADER;" not in upper_text
        or "DATA;" not in upper_text
        or "ENDSEC;" not in upper_text
        or "END-ISO-10303-21;" not in upper_text
    ):
        raise ArtifactFormatError("STEP exchange structure is invalid")
    points: List[Tuple[float, float, float]] = []
    for match in _STEP_POINT_RE.finditer(clean_text):
        if len(points) >= MAX_GEOMETRY_RECORDS:
            raise ArtifactFormatError("STEP geometry record limit exceeded")
        points.append(_coordinates(match.group(1).split(",")))
    if not points:
        raise ArtifactFormatError("STEP contains no CARTESIAN_POINT geometry")
    unit_match = _STEP_UNIT_RE.search(clean_text)
    units = _unit_name(unit_match.group(1), unit_match.group(2)) if unit_match else "unknown"
    return {
        "format": "STEP",
        "parser": "zasi.step.stdlib",
        "parser_version": "1.0.0",
        "geometry_status": "measured",
        "units": units,
        "vertex_count": len(points),
        "edge_count": len(re.findall(r"\b(?:ORIENTED_)?EDGE\s*\(", clean_text, re.IGNORECASE)),
        "face_count": len(
            re.findall(r"\b(?:ADVANCED_FACE|FACE_SURFACE|ORIENTED_FACE)\s*\(", clean_text, re.IGNORECASE)
        ),
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


def _obj(data: bytes) -> Dict[str, Any]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ArtifactFormatError("OBJ content must be UTF-8") from exc
    points: List[Tuple[float, float, float]] = []
    face_count = 0
    for line_number, line in enumerate(text.splitlines(), 1):
        if line_number > MAX_GEOMETRY_RECORDS:
            raise ArtifactFormatError("OBJ record limit exceeded")
        fields = line.strip().split()
        if not fields or fields[0].startswith("#"):
            continue
        if fields[0] == "v":
            points.append(_coordinates(fields[1:]))
        elif fields[0] == "f":
            if len(fields) < 4:
                raise ArtifactFormatError("OBJ face must contain at least three vertices")
            for reference in fields[1:]:
                index = reference.split("/", 1)[0]
                try:
                    vertex_index = int(index)
                except ValueError as exc:
                    raise ArtifactFormatError("OBJ face contains an invalid vertex index") from exc
                if vertex_index == 0 or abs(vertex_index) > len(points):
                    raise ArtifactFormatError("OBJ face references a missing vertex")
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
    if normalized_type == "application/octet-stream":
        if data.lstrip().startswith(b"ISO-10303-21;"):
            return _step(data)
        if data.lstrip().startswith((b"solid ", b"SOLID ")):
            return _stl(data)
        if re.search(rb"(?m)^\s*v\s+", data):
            return _obj(data)
    raise ArtifactFormatError("CAD media type is not supported by the reference parser")


def _png_dimensions_and_digest(data: bytes) -> Tuple[Dict[str, int], str]:
    if len(data) < 33 or not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ArtifactFormatError("PNG signature is invalid")
    if data[12:16] != b"IHDR":
        raise ArtifactFormatError("PNG IHDR chunk is missing")
    width, height, bit_depth, color_type, compression, filtering, interlace = struct.unpack(
        ">IIBBBBB", data[16:29]
    )
    if not 1 <= width <= MAX_IMAGE_DIMENSION or not 1 <= height <= MAX_IMAGE_DIMENSION:
        raise ArtifactFormatError("PNG dimensions are outside the safe bound")
    if bit_depth == 0 or compression != 0 or filtering != 0 or interlace not in {0, 1}:
        raise ArtifactFormatError("PNG encoding is unsupported")
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color_type)
    if channels is None:
        raise ArtifactFormatError("PNG color type is unsupported")
    row_bytes = (width * bit_depth * channels + 7) // 8
    expected_decoded_size = (row_bytes + 1) * height
    if expected_decoded_size > MAX_DECODED_IMAGE_BYTES:
        raise ArtifactFormatError("PNG decoded image exceeds the safe memory bound")
    idat = bytearray()
    offset = 8
    seen_iend = False
    while offset + 12 <= len(data):
        size = struct.unpack_from(">I", data, offset)[0]
        end = offset + 12 + size
        if end > len(data):
            raise ArtifactFormatError("PNG chunk exceeds artifact bounds")
        kind = data[offset + 4 : offset + 8]
        payload = data[offset + 8 : offset + 8 + size]
        if kind == b"IDAT":
            idat.extend(payload)
        if kind == b"IEND":
            seen_iend = True
            break
        offset = end
    if not idat or not seen_iend:
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
        or interlace == 0
        and len(decoded) != expected_decoded_size
    ):
        raise ArtifactFormatError("PNG decoded image is incomplete or exceeds the safe bound")
    return {"width": width, "height": height}, hashlib.sha256(decoded).hexdigest()


def _jpeg_dimensions(data: bytes) -> Dict[str, int]:
    if len(data) < 4 or data[:2] != b"\xff\xd8":
        raise ArtifactFormatError("JPEG signature is invalid")
    offset = 2
    sof_markers = set(range(0xC0, 0xC4)) | set(range(0xC5, 0xC8)) | set(range(0xC9, 0xCC)) | set(range(0xCD, 0xD0))
    dimensions: Dict[str, int] | None = None
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
            if not 1 <= width <= MAX_IMAGE_DIMENSION or not 1 <= height <= MAX_IMAGE_DIMENSION:
                raise ArtifactFormatError("JPEG dimensions are outside the safe bound")
            if dimensions is not None:
                raise ArtifactFormatError("JPEG contains multiple frame headers")
            dimensions = {"width": width, "height": height}
        elif marker == 0xDA:
            if dimensions is None or segment_length < 8:
                raise ArtifactFormatError("JPEG scan header is incomplete")
            scan_components = data[offset + 2]
            if scan_components < 1 or scan_components > 4 or segment_length != 6 + 2 * scan_components:
                raise ArtifactFormatError("JPEG scan component table is invalid")
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
        pixel_digest = hashlib.sha256(data).hexdigest()
    else:
        raise ArtifactFormatError("image media type is not supported by the reference adapter")
    return {
        "format": image_format,
        "dimensions": dimensions,
        "content_digest": artifact_digest(data),
        "pixel_digest": "sha256:" + pixel_digest,
        "semantic_model": "not_configured",
        "labels": [],
        "confidence": None,
        "disclosure": (
            "The supplied image bytes were decoded for format, dimensions, and content fingerprints. "
            "No semantic vision model is configured; labels and confidence are unavailable."
        ),
    }
