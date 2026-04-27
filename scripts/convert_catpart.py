#!/usr/bin/env python3
from __future__ import annotations

import argparse
import glob
import hashlib
import importlib.util
import json
import math
import os
import re
import shlex
import shutil
import subprocess
import struct
import sys
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any


FORMAT_EXTENSIONS = {
    "step": ".step",
    "stp": ".stp",
    "obj": ".obj",
    "stl": ".stl",
    "iges": ".iges",
    "igs": ".igs",
    "brep": ".brep",
    "x_t": ".x_t",
    "x_b": ".x_b",
    "gltf": ".gltf",
    "glb": ".glb",
}
ANALYSIS_FORMATS = {"step", "stp", "obj", "stl", "brep", "brp", "iges", "igs"}

CAD_EXCHANGER_EXECUTABLES = [
    "ExchangerConv",
    "ExchangerConv.exe",
    "cadexchangerbatch",
]

CAD_EXCHANGER_PATHS = [
    "/Applications/CAD Exchanger Lab.app/Contents/MacOS/ExchangerConv",
]
FREECAD_EXECUTABLES = [
    "FreeCADCmd",
    "freecadcmd",
]
FREECAD_PATHS = [
    "/Applications/FreeCAD.app/Contents/Resources/bin/FreeCADCmd",
]
FREECAD_GLOB_PATTERNS = [
    "/opt/anaconda3/envs/*/bin/freecadcmd",
    "/opt/anaconda3/envs/*/bin/FreeCADCmd",
    str(Path.home() / "anaconda3/envs/*/bin/freecadcmd"),
    str(Path.home() / "anaconda3/envs/*/bin/FreeCADCmd"),
    str(Path.home() / "miniconda3/envs/*/bin/freecadcmd"),
    str(Path.home() / "miniconda3/envs/*/bin/FreeCADCmd"),
    str(Path.home() / "miniforge3/envs/*/bin/freecadcmd"),
    str(Path.home() / "miniforge3/envs/*/bin/FreeCADCmd"),
    str(Path.home() / "mambaforge/envs/*/bin/freecadcmd"),
    str(Path.home() / "mambaforge/envs/*/bin/FreeCADCmd"),
    str(Path.home() / "micromamba/envs/*/bin/freecadcmd"),
    str(Path.home() / "micromamba/envs/*/bin/FreeCADCmd"),
]
FREECAD_JSON_PREFIX = "JSON_RESULT="
FREECAD_INPUT_ENV_NAMES = ("CATPART_EXACT_GEOMETRY_INPUT", "CATPART_STEP_INPUT")
FREECAD_MEASURE_SCRIPT = Path(__file__).with_name("freecad_measure_step.py")
DEFAULT_FREECAD_TIMEOUT_SECONDS = 45.0
DEFAULT_DETAIL_LIMIT = 100
LENGTH_UNIT_TO_MM = {
    "um": 0.001,
    "mm": 1.0,
    "cm": 10.0,
    "dm": 100.0,
    "m": 1000.0,
    "km": 1000000.0,
    "in": 25.4,
    "inch": 25.4,
    "inches": 25.4,
    "ft": 304.8,
    "foot": 304.8,
    "feet": 304.8,
    "yd": 914.4,
    "yard": 914.4,
    "yards": 914.4,
    "mi": 1609344.0,
    "mile": 1609344.0,
    "miles": 1609344.0,
    "mil": 0.0254,
    "thou": 0.0254,
}
LENGTH_UNIT_ALIASES = {
    "micron": "um",
    "microns": "um",
    "millimeter": "mm",
    "millimeters": "mm",
    "millimetre": "mm",
    "millimetres": "mm",
    "centimeter": "cm",
    "centimeters": "cm",
    "centimetre": "cm",
    "centimetres": "cm",
    "decimeter": "dm",
    "decimeters": "dm",
    "decimetre": "dm",
    "decimetres": "dm",
    "meter": "m",
    "meters": "m",
    "metre": "m",
    "metres": "m",
    "kilometer": "km",
    "kilometers": "km",
    "kilometre": "km",
    "kilometres": "km",
    "inchs": "inch",
    "foots": "foot",
}

CAD_EXCHANGER_TEMPLATE = '"{executable}" -i "{input}" -e "{output}"'
FLOAT_RE = re.compile(r"[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[Ee][-+]?\d+)?")
STEP_ENTITY_RE = re.compile(r"#\d+\s*=\s*([A-Z0-9_]+)\s*\(")
STEP_PRODUCT_RE = re.compile(r"PRODUCT\s*\(\s*'([^']*)'", re.IGNORECASE)
STEP_FILE_DESCRIPTION_RE = re.compile(
    r"FILE_DESCRIPTION\s*\(\s*\((.*?)\)\s*,\s*'([^']*)'\s*\)",
    re.IGNORECASE | re.DOTALL,
)
STEP_FILE_NAME_RE = re.compile(
    r"FILE_NAME\s*\(\s*'([^']*)'\s*,\s*'([^']*)'\s*,\s*\((.*?)\)\s*,\s*\((.*?)\)\s*,\s*'([^']*)'\s*,\s*'([^']*)'\s*,\s*'([^']*)'\s*\)",
    re.IGNORECASE | re.DOTALL,
)
STEP_FILE_SCHEMA_RE = re.compile(
    r"FILE_SCHEMA\s*\(\s*\((.*?)\)\s*\)",
    re.IGNORECASE | re.DOTALL,
)
STEP_CARTESIAN_POINT_RE = re.compile(
    r"CARTESIAN_POINT\s*\(\s*'[^']*'\s*,\s*\((.*?)\)\s*\)",
    re.IGNORECASE | re.DOTALL,
)
STEP_LENGTH_UNIT_RE = re.compile(
    r"SI_UNIT\s*\(\s*(?:\.(MILLI|CENTI|DECI|KILO|MICRO)\.\s*,\s*)?\.(METRE)\.\s*\)",
    re.IGNORECASE,
)
STEP_CONVERSION_UNIT_RE = re.compile(
    r"CONVERSION_BASED_UNIT\s*\(\s*'([^']+)'",
    re.IGNORECASE,
)
OBJ_VERTEX_RE = re.compile(r"^v\s+([-+0-9Ee.]+)\s+([-+0-9Ee.]+)\s+([-+0-9Ee.]+)(?:\s|$)")
OBJ_FACE_RE = re.compile(r"^f\s+")
OBJ_OBJECT_RE = re.compile(r"^(?:o|g)\s+(.+?)\s*$")
OBJ_MATERIAL_RE = re.compile(r"^usemtl\s+(.+?)\s*$")


@dataclass
class BackendSpec:
    name: str
    executable: str
    template: str
    detected_via: str


class BackendNotFoundError(RuntimeError):
    pass


class InvalidMeshFaceError(ValueError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Convert CATIA CATPart files into exchange formats such as STEP, OBJ, and STL."
        )
    )
    parser.add_argument("inputs", nargs="*", help="Input CATPart files")
    parser.add_argument(
        "--format",
        default="step",
        choices=sorted(FORMAT_EXTENSIONS),
        help="Target export format (default: step)",
    )
    parser.add_argument(
        "--output",
        help="Explicit output path for a single input file",
    )
    parser.add_argument(
        "--output-dir",
        help="Directory for generated outputs when converting one or more inputs",
    )
    parser.add_argument(
        "--backend",
        choices=("auto", "cadexchanger", "custom"),
        default="auto",
        help="Backend selection strategy (default: auto)",
    )
    parser.add_argument(
        "--backend-executable",
        help="Absolute path to the converter executable. Overrides auto-detection.",
    )
    parser.add_argument(
        "--backend-cmd",
        help=(
            "Command template. Supported placeholders: {executable}, {input}, {output}, {format}."
        ),
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite an existing output file",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print resolved commands without running them",
    )
    parser.add_argument(
        "--probe",
        action="store_true",
        help="Inspect backend configuration and exit",
    )
    parser.add_argument(
        "--report",
        help="Write a JSON conversion report to a file. Use '-' to print JSON to stdout.",
    )
    parser.add_argument(
        "--skip-analysis",
        action="store_true",
        help="Skip post-conversion engineering analysis of STEP/OBJ/STL outputs.",
    )
    parser.add_argument(
        "--analysis-only",
        action="store_true",
        help="Analyze existing STEP/OBJ/STL files without running a CATPart conversion backend.",
    )
    parser.add_argument(
        "--assume-unit",
        help="Attach a unit label such as mm or m to mesh analysis outputs when the file format has no native unit metadata.",
    )
    return parser.parse_args()


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def normalize_path(path_value: str | Path) -> str:
    return str(Path(path_value).expanduser().resolve())


def module_is_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def round_number(value: float, digits: int = 6) -> float:
    return round(float(value), digits)


def normalize_length_unit_label(unit: str | None) -> str | None:
    if unit is None:
        return None
    normalized = unit.strip().lower()
    if not normalized:
        return None
    return LENGTH_UNIT_ALIASES.get(normalized, normalized)


def close_enough(
    left: float,
    right: float,
    *,
    relative_tolerance: float = 1e-3,
    absolute_tolerance: float = 1e-6,
) -> bool:
    return abs(left - right) <= max(absolute_tolerance, abs(right) * relative_tolerance)


def format_power_unit(length_unit: str | None, power: int) -> str | None:
    if not length_unit:
        return None
    return f"{length_unit}^{power}"


def create_bbox() -> dict[str, list[float] | None]:
    return {"min": None, "max": None}


def update_bbox(bbox: dict[str, list[float] | None], point: tuple[float, float, float]) -> None:
    if bbox["min"] is None or bbox["max"] is None:
        bbox["min"] = [point[0], point[1], point[2]]
        bbox["max"] = [point[0], point[1], point[2]]
        return

    for index, value in enumerate(point):
        bbox["min"][index] = min(bbox["min"][index], value)
        bbox["max"][index] = max(bbox["max"][index], value)


def finalize_bbox(
    bbox: dict[str, list[float] | None],
    *,
    unit: str | None,
    inferred: bool,
) -> dict[str, Any] | None:
    if bbox["min"] is None or bbox["max"] is None:
        return None

    minimum = [round_number(value) for value in bbox["min"]]
    maximum = [round_number(value) for value in bbox["max"]]
    size = [round_number(maximum[index] - minimum[index]) for index in range(3)]
    diagonal = round_number(math.sqrt(size[0] ** 2 + size[1] ** 2 + size[2] ** 2))
    return {
        "min": minimum,
        "max": maximum,
        "size": size,
        "diagonal": diagonal,
        "unit": unit,
        "inferred": inferred,
    }


def scale_bbox_payload(
    bbox: dict[str, Any] | None,
    *,
    scale: float,
    unit: str | None,
    inferred: bool | None = None,
) -> dict[str, Any] | None:
    if not bbox:
        return None

    scaled: dict[str, Any] = {}
    for key in ("min", "max", "size"):
        values = bbox.get(key)
        if values is not None:
            scaled[key] = [round_number(value * scale) for value in values]
    if "diagonal" in bbox and bbox["diagonal"] is not None:
        scaled["diagonal"] = round_number(bbox["diagonal"] * scale)
    scaled["unit"] = unit
    scaled["inferred"] = bbox.get("inferred", False) if inferred is None else inferred
    return scaled


def scale_point_payload(point: list[float] | None, scale: float) -> list[float] | None:
    if point is None:
        return None
    return [round_number(value * scale) for value in point]


def freecad_timeout_seconds() -> float:
    raw_value = os.environ.get("CATPART_FREECAD_TIMEOUT_SECONDS")
    if raw_value is None:
        return DEFAULT_FREECAD_TIMEOUT_SECONDS
    try:
        parsed = float(raw_value)
    except ValueError:
        return DEFAULT_FREECAD_TIMEOUT_SECONDS
    return parsed if parsed > 0 else DEFAULT_FREECAD_TIMEOUT_SECONDS


def detail_limit() -> int:
    raw_value = os.environ.get("CATPART_DETAIL_LIMIT")
    if raw_value is None:
        return DEFAULT_DETAIL_LIMIT
    try:
        parsed = int(raw_value)
    except ValueError:
        return DEFAULT_DETAIL_LIMIT
    return max(0, parsed)


def parse_float_triplet(raw_values: str) -> tuple[float, float, float] | None:
    values = [float(match) for match in FLOAT_RE.findall(raw_values)]
    if len(values) < 3:
        return None
    return values[0], values[1], values[2]


def vector_subtract(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return a[0] - b[0], a[1] - b[1], a[2] - b[2]


def vector_cross(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def vector_dot(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def vector_norm(a: tuple[float, float, float]) -> float:
    return math.sqrt(vector_dot(a, a))


def triangle_area_from_points(
    a: tuple[float, float, float],
    b: tuple[float, float, float],
    c: tuple[float, float, float],
) -> float:
    return 0.5 * vector_norm(vector_cross(vector_subtract(b, a), vector_subtract(c, a)))


def average_points(points: list[tuple[float, float, float]]) -> list[float] | None:
    if not points:
        return None
    count = float(len(points))
    totals = [0.0, 0.0, 0.0]
    for point in points:
        totals[0] += point[0]
        totals[1] += point[1]
        totals[2] += point[2]
    return [round_number(value / count) for value in totals]


def polygon_face_vertex_indices(face_tokens: list[str], vertex_count: int) -> list[int]:
    indices: list[int] = []
    for token in face_tokens:
        vertex_ref = token.split("/")[0]
        if not vertex_ref:
            continue
        try:
            raw_index = int(vertex_ref)
        except ValueError as exc:
            raise InvalidMeshFaceError(f"invalid vertex reference: {token}") from exc
        resolved_index = raw_index - 1 if raw_index > 0 else vertex_count + raw_index
        if resolved_index < 0 or resolved_index >= vertex_count:
            raise InvalidMeshFaceError(
                f"vertex reference {raw_index} is out of range for {vertex_count} vertices"
            )
        indices.append(resolved_index)
    return indices


def triangulate_face(face_indices: list[int]) -> list[tuple[int, int, int]]:
    if len(face_indices) < 3:
        return []
    if len(face_indices) == 3:
        return [(face_indices[0], face_indices[1], face_indices[2])]
    return [
        (face_indices[0], face_indices[index], face_indices[index + 1])
        for index in range(1, len(face_indices) - 1)
    ]


def mesh_measurement_units(unit: str | None) -> dict[str, str | None]:
    if not unit:
        return {
            "length": None,
            "area": None,
            "volume": None,
        }
    return {
        "length": unit,
        "area": f"{unit}^2",
        "volume": f"{unit}^3",
    }


def deduped_vertex_index(
    point: tuple[float, float, float],
    *,
    vertex_map: dict[tuple[float, float, float], int],
    vertices: list[tuple[float, float, float]],
    precision: int = 9,
) -> int:
    key = (
        round(point[0], precision),
        round(point[1], precision),
        round(point[2], precision),
    )
    if key in vertex_map:
        return vertex_map[key]
    index = len(vertices)
    vertex_map[key] = index
    vertices.append(point)
    return index


def extract_quoted_strings(raw_value: str) -> list[str]:
    values = [item for item in re.findall(r"'([^']*)'", raw_value) if item]
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


def classify_length_unit(step_text: str) -> str | None:
    match = STEP_LENGTH_UNIT_RE.search(step_text)
    if match:
        prefix = (match.group(1) or "").upper()
        unit = match.group(2).upper()
        if unit == "METRE":
            if prefix == "MILLI":
                return "mm"
            if prefix == "CENTI":
                return "cm"
            if prefix == "DECI":
                return "dm"
            if prefix == "KILO":
                return "km"
            if prefix == "MICRO":
                return "um"
            return "m"

    conversion_match = STEP_CONVERSION_UNIT_RE.search(step_text)
    if conversion_match:
        return normalize_length_unit_label(conversion_match.group(1))

    return None


def step_bbox_in_mm(
    bbox: dict[str, Any] | None,
    unit: str | None,
) -> dict[str, Any] | None:
    if not bbox or not unit:
        return None

    scale_to_mm = LENGTH_UNIT_TO_MM.get(normalize_length_unit_label(unit) or "")
    if scale_to_mm is None:
        return None

    return scale_bbox_payload(bbox, scale=scale_to_mm, unit="mm")


def step_records(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    return [record.strip() + ";" for record in text.split(";") if record.strip()]


def analyze_step_textual_file(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    records = step_records(path)
    entity_counts: Counter[str] = Counter()
    product_names: list[str] = []
    bbox = create_bbox()

    for record in records:
        entity_match = STEP_ENTITY_RE.search(record)
        if entity_match:
            entity_counts[entity_match.group(1).upper()] += 1

        product_match = STEP_PRODUCT_RE.search(record)
        if product_match:
            name = product_match.group(1).strip()
            if name and name not in product_names:
                product_names.append(name)

        if "CARTESIAN_POINT" in record.upper():
            point_match = STEP_CARTESIAN_POINT_RE.search(record)
            if point_match:
                point = parse_float_triplet(point_match.group(1))
                if point is not None:
                    update_bbox(bbox, point)

    file_description_match = STEP_FILE_DESCRIPTION_RE.search(text)
    file_name_match = STEP_FILE_NAME_RE.search(text)
    file_schema_match = STEP_FILE_SCHEMA_RE.search(text)
    length_unit = classify_length_unit(text)
    bbox_native = finalize_bbox(bbox, unit=length_unit, inferred=True)

    topological_counts = {
        "solids": sum(
            entity_counts.get(name, 0)
            for name in (
                "MANIFOLD_SOLID_BREP",
                "BREP_WITH_VOIDS",
                "FACETED_BREP",
            )
        ),
        "shells": entity_counts.get("CLOSED_SHELL", 0) + entity_counts.get("OPEN_SHELL", 0),
        "faces": entity_counts.get("ADVANCED_FACE", 0) + entity_counts.get("FACE_SURFACE", 0),
        "edges": entity_counts.get("EDGE_CURVE", 0),
        "oriented_edges": entity_counts.get("ORIENTED_EDGE", 0),
        "vertices": entity_counts.get("VERTEX_POINT", 0),
    }

    analysis = {
        "kind": "step",
        "read_strategy": "textual_step_analysis",
        "native_catpart_read": False,
        "precision_note": (
            "Derived from the converted STEP file. Names and topology counts are reliable "
            "within the exchanged model; the bounding box is inferred from raw "
            "CARTESIAN_POINT records and may not fully reflect transformed assembly context."
        ),
        "file_description": None,
        "file_name": None,
        "timestamp": None,
        "authors": [],
        "organizations": [],
        "preprocessor_version": None,
        "originating_system": None,
        "authorization": None,
        "schemas": extract_quoted_strings(file_schema_match.group(1)) if file_schema_match else [],
        "product_names": product_names,
        "length_unit": length_unit,
        "bbox_native_units": bbox_native,
        "bbox_mm": step_bbox_in_mm(bbox_native, length_unit),
        "topology": topological_counts,
        "entity_counts": dict(entity_counts.most_common(20)),
        "curves_and_surfaces": {
            "bspline_curves": entity_counts.get("B_SPLINE_CURVE_WITH_KNOTS", 0),
            "bspline_surfaces": entity_counts.get("B_SPLINE_SURFACE_WITH_KNOTS", 0),
            "circles": entity_counts.get("CIRCLE", 0),
            "planes": entity_counts.get("PLANE", 0),
            "cylindrical_surfaces": entity_counts.get("CYLINDRICAL_SURFACE", 0),
        },
    }

    if file_description_match:
        descriptions = extract_quoted_strings(file_description_match.group(1))
        analysis["file_description"] = descriptions
        analysis["implementation_level"] = file_description_match.group(2)

    if file_name_match:
        analysis["file_name"] = file_name_match.group(1)
        analysis["timestamp"] = file_name_match.group(2)
        analysis["authors"] = extract_quoted_strings(file_name_match.group(3))
        analysis["organizations"] = extract_quoted_strings(file_name_match.group(4))
        analysis["preprocessor_version"] = file_name_match.group(5)
        analysis["originating_system"] = file_name_match.group(6)
        analysis["authorization"] = file_name_match.group(7)

    return analysis


def parse_freecad_json(stdout: str) -> dict[str, Any]:
    for line in reversed(stdout.splitlines()):
        if line.startswith(FREECAD_JSON_PREFIX):
            return json.loads(line[len(FREECAD_JSON_PREFIX) :])
    raise ValueError("FreeCAD completed without emitting a JSON_RESULT payload.")


def discover_freecad_executable() -> tuple[str, str] | None:
    env_override = os.environ.get("CATPART_FREECAD_CMD")
    if env_override:
        override_path = Path(env_override).expanduser().resolve()
        if override_path.exists() and os.access(override_path, os.X_OK):
            return str(override_path), "ENV:CATPART_FREECAD_CMD"

    discovered = discover_executable(FREECAD_EXECUTABLES, FREECAD_PATHS)
    if discovered:
        return discovered

    for pattern in FREECAD_GLOB_PATTERNS:
        for match in sorted(glob.glob(os.path.expanduser(pattern))):
            candidate = Path(match).expanduser()
            if candidate.exists() and os.access(candidate, os.X_OK):
                return str(candidate.resolve()), f"GLOB:{pattern}"

    return None


def infer_step_exact_unit_resolution(
    textual_bbox: dict[str, Any] | None,
    exact_bbox: dict[str, Any] | None,
    textual_unit: str | None,
) -> dict[str, Any]:
    resolution = {
        "native_length_unit": textual_unit,
        "exact_length_unit": None,
        "exact_to_native_length_scale": None,
        "exact_to_mm_length_scale": None,
        "comparison_ratio": None,
        "comparison_samples": 0,
        "comparison_consistent": False,
    }
    if not textual_bbox or not exact_bbox:
        return resolution

    textual_sizes = textual_bbox.get("size") or []
    exact_sizes = exact_bbox.get("size") or []
    ratios: list[float] = []
    for textual_size, exact_size in zip(textual_sizes, exact_sizes):
        if abs(textual_size) <= 1e-9 or abs(exact_size) <= 1e-9:
            continue
        ratios.append(exact_size / textual_size)

    if not ratios:
        return resolution

    average_ratio = sum(ratios) / len(ratios)
    max_deviation = max(abs(item - average_ratio) for item in ratios)
    resolution["comparison_ratio"] = round_number(average_ratio)
    resolution["comparison_samples"] = len(ratios)
    resolution["comparison_consistent"] = (
        abs(average_ratio) > 1e-12
        and max_deviation / abs(average_ratio) <= 1e-3
    )
    if not resolution["comparison_consistent"]:
        return resolution

    scale_to_mm = LENGTH_UNIT_TO_MM.get(normalize_length_unit_label(textual_unit) or "")
    if close_enough(average_ratio, 1.0):
        resolution["exact_length_unit"] = textual_unit
        resolution["exact_to_native_length_scale"] = 1.0
        resolution["exact_to_mm_length_scale"] = scale_to_mm
        return resolution

    if scale_to_mm is not None and close_enough(average_ratio, scale_to_mm):
        resolution["exact_length_unit"] = "mm"
        resolution["exact_to_native_length_scale"] = 1.0 / scale_to_mm
        resolution["exact_to_mm_length_scale"] = 1.0
        return resolution

    return resolution


def run_freecad_exact_shape_analysis(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    discovered = discover_freecad_executable()
    if discovered is None:
        raise BackendNotFoundError("No FreeCAD command backend was found for exact geometry analysis.")

    if not FREECAD_MEASURE_SCRIPT.exists():
        raise FileNotFoundError(f"FreeCAD helper script is missing: {FREECAD_MEASURE_SCRIPT}")

    executable, detected_via = discovered
    environment = os.environ.copy()
    environment[FREECAD_INPUT_ENV_NAMES[0]] = str(path)
    environment["CATPART_DETAIL_LIMIT"] = str(detail_limit())
    timeout_seconds = freecad_timeout_seconds()
    try:
        completed = subprocess.run(
            [executable, str(FREECAD_MEASURE_SCRIPT)],
            capture_output=True,
            env=environment,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"FreeCAD analysis timed out after {round_number(timeout_seconds, 3)} seconds."
        ) from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "FreeCAD analysis failed").strip()
        raise RuntimeError(detail)

    return parse_freecad_json(completed.stdout), {
        "path": executable,
        "detected_via": detected_via,
        "helper_script": str(FREECAD_MEASURE_SCRIPT),
        "timeout_seconds": round_number(timeout_seconds, 3),
        "detail_limit": detail_limit(),
    }


def build_exact_geometry_metadata(
    exact_geometry: dict[str, Any],
    backend_details: dict[str, Any],
    *,
    unit_resolution: dict[str, Any] | None = None,
    bbox_import_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    exact_bbox_import = exact_geometry.get("bbox")
    return {
        "backend": "freecadcmd",
        "backend_path": backend_details["path"],
        "backend_detected_via": backend_details["detected_via"],
        "helper_script": backend_details["helper_script"],
        "timeout_seconds": backend_details["timeout_seconds"],
        "detail_limit": backend_details["detail_limit"],
        "shape_type": exact_geometry.get("shape_type"),
        "is_null": exact_geometry.get("is_null"),
        "is_valid": exact_geometry.get("is_valid"),
        "unit_resolution": unit_resolution,
        "mass_import_units": exact_geometry.get("mass"),
        "freecad_mass_import_units": exact_geometry.get("freecad_mass"),
        "bbox_import_units": bbox_import_payload,
        "surface_area_import_units": round_number(exact_geometry.get("surface_area", 0.0)),
        "volume_import_units": round_number(exact_geometry.get("volume", 0.0)),
        "center_of_mass_import_units": exact_geometry.get("center_of_mass"),
        "center_of_gravity_import_units": exact_geometry.get("center_of_gravity"),
        "bbox_diagonal_import_units": exact_bbox_import.get("diagonal") if exact_bbox_import else None,
        "static_moments_import_units": exact_geometry.get("static_moments"),
        "matrix_of_inertia_import_units": exact_geometry.get("matrix_of_inertia"),
        "principal_properties_import_units": exact_geometry.get("principal_properties"),
        "topology": exact_geometry.get("topology"),
        "solid_details": exact_geometry.get("solid_details"),
        "shell_details": exact_geometry.get("shell_details"),
    }


def merge_step_analyses(
    textual_analysis: dict[str, Any],
    exact_geometry: dict[str, Any],
    backend_details: dict[str, Any],
) -> dict[str, Any]:
    analysis = dict(textual_analysis)
    native_length_unit = normalize_length_unit_label(analysis.get("length_unit"))
    analysis["length_unit"] = native_length_unit
    exact_bbox_import = exact_geometry.get("bbox")
    unit_resolution = infer_step_exact_unit_resolution(
        analysis.get("bbox_native_units"),
        exact_bbox_import,
        native_length_unit,
    )
    exact_length_unit = unit_resolution.get("exact_length_unit")

    bbox_import_payload = None
    if exact_bbox_import:
        bbox_import_payload = dict(exact_bbox_import)
        bbox_import_payload["unit"] = exact_length_unit
        bbox_import_payload["inferred"] = False

    scale_to_native = unit_resolution.get("exact_to_native_length_scale")
    scale_to_mm = unit_resolution.get("exact_to_mm_length_scale")
    surface_area_import = round_number(exact_geometry.get("surface_area", 0.0))
    enclosed_volume_import = round_number(exact_geometry.get("volume", 0.0))
    center_import = exact_geometry.get("center_of_mass") or exact_geometry.get("center_of_gravity")

    surface_area_value = surface_area_import
    surface_area_unit = format_power_unit(exact_length_unit, 2)
    enclosed_volume_value = enclosed_volume_import
    volume_unit = format_power_unit(exact_length_unit, 3)
    center_payload = center_import
    center_unit = exact_length_unit
    bbox_native_payload = analysis.get("bbox_native_units")
    bbox_mm_payload = analysis.get("bbox_mm")

    if scale_to_native is not None and native_length_unit:
        surface_area_value = round_number(surface_area_import * (scale_to_native ** 2))
        surface_area_unit = format_power_unit(native_length_unit, 2)
        enclosed_volume_value = round_number(enclosed_volume_import * (scale_to_native ** 3))
        volume_unit = format_power_unit(native_length_unit, 3)
        center_payload = scale_point_payload(center_import, scale_to_native)
        center_unit = native_length_unit
        bbox_native_payload = scale_bbox_payload(
            exact_bbox_import,
            scale=scale_to_native,
            unit=native_length_unit,
        )
        if scale_to_mm is not None:
            bbox_mm_payload = scale_bbox_payload(
                exact_bbox_import,
                scale=scale_to_mm,
                unit="mm",
            )

    analysis["read_strategy"] = "textual_step_analysis+freecad_exact_geometry"
    analysis["precision_note"] = (
        "Names, schemas, and provenance metadata come from the converted STEP text. "
        "Volume, surface area, center of gravity, topology, and bounding box are "
        "measured from the imported B-Rep using FreeCAD."
    )
    analysis["surface_area"] = surface_area_value
    analysis["surface_area_unit"] = surface_area_unit
    analysis["enclosed_volume"] = enclosed_volume_value
    analysis["volume_unit"] = volume_unit
    analysis["center_of_mass"] = center_payload
    analysis["center_of_mass_unit"] = center_unit
    analysis["center_of_gravity"] = center_payload
    analysis["center_of_gravity_unit"] = center_unit
    exact_topology = exact_geometry.get("topology") or {}
    textual_topology = dict(analysis.get("topology") or {})
    analysis["topology_from_step_entities"] = textual_topology
    analysis["topology_exact"] = exact_topology
    analysis["topology"] = {
        **textual_topology,
        **exact_topology,
    }
    analysis["bbox_from_cartesian_points"] = analysis.get("bbox_native_units")
    if bbox_native_payload is not None:
        analysis["bbox_native_units"] = bbox_native_payload
    if bbox_mm_payload is not None:
        analysis["bbox_mm"] = bbox_mm_payload
    analysis["mass_properties"] = {
        "mass_import_units": exact_geometry.get("mass"),
        "freecad_mass_import_units": exact_geometry.get("freecad_mass"),
        "static_moments_import_units": exact_geometry.get("static_moments"),
        "matrix_of_inertia_import_units": exact_geometry.get("matrix_of_inertia"),
        "principal_properties_import_units": exact_geometry.get("principal_properties"),
        "units_note": (
            "FreeCAD mass-property values are reported in imported model units. "
            "For solids with unit density, mass is numerically equal to enclosed volume."
        ),
    }
    analysis["solid_details"] = exact_geometry.get("solid_details")
    analysis["shell_details"] = exact_geometry.get("shell_details")
    analysis["exact_geometry"] = build_exact_geometry_metadata(
        exact_geometry,
        backend_details,
        unit_resolution=unit_resolution,
        bbox_import_payload=bbox_import_payload,
    )
    return analysis


def analyze_step_file(path: Path) -> dict[str, Any]:
    textual_analysis = analyze_step_textual_file(path)
    try:
        exact_geometry, backend_details = run_freecad_exact_shape_analysis(path)
    except (BackendNotFoundError, FileNotFoundError):
        return textual_analysis
    except Exception as exc:  # pragma: no cover - defensive reporting
        textual_analysis["exact_geometry_error"] = str(exc)
        return textual_analysis

    return merge_step_analyses(textual_analysis, exact_geometry, backend_details)


def analyze_exact_shape_file(
    path: Path,
    *,
    kind: str,
    unit: str | None = None,
) -> dict[str, Any]:
    exact_geometry, backend_details = run_freecad_exact_shape_analysis(path)
    normalized_unit = normalize_length_unit_label(unit)
    bbox_import = exact_geometry.get("bbox")
    bbox_payload = None
    if bbox_import:
        bbox_payload = dict(bbox_import)
        bbox_payload["unit"] = normalized_unit
        bbox_payload["inferred"] = False

    precision_note = (
        "Measured from the imported B-Rep using FreeCAD."
        if normalized_unit
        else "Measured from the imported B-Rep using FreeCAD. Length-derived values are "
        "reported in the model's native units because this format does not expose a "
        "standardized unit label here."
    )
    return {
        "kind": kind,
        "read_strategy": "freecad_exact_geometry",
        "native_catpart_read": False,
        "precision_note": precision_note,
        "length_unit": normalized_unit,
        "assumed_unit": normalized_unit,
        "surface_area": round_number(exact_geometry.get("surface_area", 0.0)),
        "surface_area_unit": format_power_unit(normalized_unit, 2),
        "enclosed_volume": round_number(exact_geometry.get("volume", 0.0)),
        "volume_unit": format_power_unit(normalized_unit, 3),
        "center_of_mass": exact_geometry.get("center_of_mass") or exact_geometry.get("center_of_gravity"),
        "center_of_mass_unit": normalized_unit,
        "center_of_gravity": exact_geometry.get("center_of_mass") or exact_geometry.get("center_of_gravity"),
        "center_of_gravity_unit": normalized_unit,
        "bbox_native_units": bbox_payload,
        "topology": exact_geometry.get("topology") or {},
        "mass_properties": {
            "mass_import_units": exact_geometry.get("mass"),
            "freecad_mass_import_units": exact_geometry.get("freecad_mass"),
            "static_moments_import_units": exact_geometry.get("static_moments"),
            "matrix_of_inertia_import_units": exact_geometry.get("matrix_of_inertia"),
            "principal_properties_import_units": exact_geometry.get("principal_properties"),
            "units_note": (
                "FreeCAD mass-property values are reported in imported model units. "
                "For solids with unit density, mass is numerically equal to enclosed volume."
            ),
        },
        "solid_details": exact_geometry.get("solid_details"),
        "shell_details": exact_geometry.get("shell_details"),
        "exact_geometry": build_exact_geometry_metadata(
            exact_geometry,
            backend_details,
            unit_resolution=None,
            bbox_import_payload=bbox_payload,
        ),
    }


def analyze_triangle_mesh(
    *,
    vertices: list[tuple[float, float, float]],
    triangles: list[tuple[int, int, int]],
    kind: str,
    unit: str | None,
    extra_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    bbox = create_bbox()
    undirected_edge_counts: Counter[tuple[int, int]] = Counter()
    directed_edge_counts: Counter[tuple[int, int]] = Counter()
    degenerate_triangles = 0
    total_area = 0.0
    area_centroid_sum = [0.0, 0.0, 0.0]
    signed_volume = 0.0
    volume_centroid_sum = [0.0, 0.0, 0.0]

    for point in vertices:
        update_bbox(bbox, point)

    for triangle in triangles:
        a_idx, b_idx, c_idx = triangle
        a = vertices[a_idx]
        b = vertices[b_idx]
        c = vertices[c_idx]

        area = triangle_area_from_points(a, b, c)
        if area <= 1e-12:
            degenerate_triangles += 1
            continue

        total_area += area
        surface_centroid = (
            (a[0] + b[0] + c[0]) / 3.0,
            (a[1] + b[1] + c[1]) / 3.0,
            (a[2] + b[2] + c[2]) / 3.0,
        )
        area_centroid_sum[0] += surface_centroid[0] * area
        area_centroid_sum[1] += surface_centroid[1] * area
        area_centroid_sum[2] += surface_centroid[2] * area

        tetra_volume = vector_dot(a, vector_cross(b, c)) / 6.0
        signed_volume += tetra_volume
        tetra_centroid = (
            (a[0] + b[0] + c[0]) / 4.0,
            (a[1] + b[1] + c[1]) / 4.0,
            (a[2] + b[2] + c[2]) / 4.0,
        )
        volume_centroid_sum[0] += tetra_centroid[0] * tetra_volume
        volume_centroid_sum[1] += tetra_centroid[1] * tetra_volume
        volume_centroid_sum[2] += tetra_centroid[2] * tetra_volume

        for start, end in ((a_idx, b_idx), (b_idx, c_idx), (c_idx, a_idx)):
            edge = (start, end) if start < end else (end, start)
            undirected_edge_counts[edge] += 1
            directed_edge_counts[(start, end)] += 1

    watertight = bool(undirected_edge_counts) and all(count == 2 for count in undirected_edge_counts.values())
    orientation_consistent = watertight and all(
        directed_edge_counts.get((edge[0], edge[1]), 0) == 1
        and directed_edge_counts.get((edge[1], edge[0]), 0) == 1
        for edge in undirected_edge_counts
    )

    abs_signed_volume = abs(signed_volume)
    surface_centroid = None
    if total_area > 1e-12:
        surface_centroid = [
            round_number(area_centroid_sum[index] / total_area)
            for index in range(3)
        ]

    volume_centroid = None
    if orientation_consistent and abs_signed_volume > 1e-12:
        orientation_scale = signed_volume if signed_volume != 0 else 1.0
        volume_centroid = [
            round_number(volume_centroid_sum[index] / orientation_scale)
            for index in range(3)
        ]

    bbox_payload = finalize_bbox(bbox, unit=unit, inferred=False)
    bbox_diagonal = None
    if bbox_payload:
        size = bbox_payload["size"]
        bbox_diagonal = round_number(math.sqrt(size[0] ** 2 + size[1] ** 2 + size[2] ** 2))

    units = mesh_measurement_units(unit)
    analysis = {
        "kind": kind,
        "read_strategy": "polyhedral_mesh_analysis",
        "native_catpart_read": False,
        "precision_note": (
            "Derived from converted mesh output. Surface area is exact for the mesh; "
            "volume and volume centroid are reported only when the mesh appears watertight "
            "and orientation-consistent."
        ),
        "vertex_count": len(vertices),
        "triangle_count": len(triangles),
        "degenerate_triangle_count": degenerate_triangles,
        "assumed_unit": unit,
        "surface_area": round_number(total_area),
        "surface_area_unit": units["area"],
        "signed_volume": round_number(signed_volume),
        "enclosed_volume": round_number(abs_signed_volume) if orientation_consistent else None,
        "volume_unit": units["volume"],
        "watertight": watertight,
        "orientation_consistent": orientation_consistent,
        "boundary_edge_count": sum(1 for count in undirected_edge_counts.values() if count == 1),
        "non_manifold_edge_count": sum(1 for count in undirected_edge_counts.values() if count > 2),
        "bbox_native_units": bbox_payload,
        "bbox_diagonal": bbox_diagonal,
        "bbox_diagonal_unit": units["length"],
        "vertex_centroid": average_points(vertices),
        "surface_centroid": surface_centroid,
        "volume_centroid": volume_centroid,
    }
    if extra_fields:
        analysis.update(extra_fields)
    return analysis


def analyze_obj_file(path: Path, unit: str | None = None) -> dict[str, Any]:
    vertices: list[tuple[float, float, float]] = []
    triangles: list[tuple[int, int, int]] = []
    face_count = 0
    invalid_face_count = 0
    invalid_face_examples: list[str] = []
    objects: list[str] = []
    materials: list[str] = []

    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            vertex_match = OBJ_VERTEX_RE.match(line)
            if vertex_match:
                vertices.append(
                    (
                    float(vertex_match.group(1)),
                    float(vertex_match.group(2)),
                    float(vertex_match.group(3)),
                    )
                )
                continue

            if OBJ_FACE_RE.match(line):
                face_count += 1
                try:
                    face_indices = polygon_face_vertex_indices(line.split()[1:], len(vertices))
                except InvalidMeshFaceError as exc:
                    invalid_face_count += 1
                    if len(invalid_face_examples) < 5:
                        invalid_face_examples.append(str(exc))
                    continue
                triangles.extend(triangulate_face(face_indices))
                continue

            object_match = OBJ_OBJECT_RE.match(line)
            if object_match:
                name = object_match.group(1)
                if name not in objects:
                    objects.append(name)
                continue

            material_match = OBJ_MATERIAL_RE.match(line)
            if material_match:
                material = material_match.group(1)
                if material not in materials:
                    materials.append(material)

    return analyze_triangle_mesh(
        vertices=vertices,
        triangles=triangles,
        kind="obj",
        unit=unit,
        extra_fields={
            "face_count": face_count,
            "valid_face_count": face_count - invalid_face_count,
            "invalid_face_count": invalid_face_count,
            "invalid_face_examples": invalid_face_examples,
            "objects": objects,
            "materials": materials,
        },
    )


def is_binary_stl(path: Path) -> bool:
    file_size = path.stat().st_size
    if file_size < 84:
        return False
    with path.open("rb") as handle:
        header = handle.read(84)
    triangle_count = struct.unpack("<I", header[80:84])[0]
    return 84 + triangle_count * 50 == file_size


def analyze_binary_stl(path: Path, unit: str | None = None) -> dict[str, Any]:
    vertices: list[tuple[float, float, float]] = []
    triangles: list[tuple[int, int, int]] = []
    vertex_map: dict[tuple[float, float, float], int] = {}
    with path.open("rb") as handle:
        header = handle.read(84)
        triangle_count = struct.unpack("<I", header[80:84])[0]
        for _ in range(triangle_count):
            record = handle.read(50)
            if len(record) < 50:
                break
            raw_vertices = struct.unpack("<12f", record[:48])[3:]
            triangle_vertices = [
                (raw_vertices[index], raw_vertices[index + 1], raw_vertices[index + 2])
                for index in range(0, 9, 3)
            ]
            triangle_indices = tuple(
                deduped_vertex_index(point, vertex_map=vertex_map, vertices=vertices)
                for point in triangle_vertices
            )
            triangles.append(triangle_indices)

    return analyze_triangle_mesh(
        vertices=vertices,
        triangles=triangles,
        kind="stl",
        unit=unit,
        extra_fields={
            "encoding": "binary",
        },
    )


def analyze_ascii_stl(path: Path, unit: str | None = None) -> dict[str, Any]:
    vertices: list[tuple[float, float, float]] = []
    triangles: list[tuple[int, int, int]] = []
    vertex_map: dict[tuple[float, float, float], int] = {}
    solid_names: list[str] = []
    current_triangle: list[tuple[float, float, float]] = []

    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("solid "):
                name = line[6:].strip()
                if name and name not in solid_names:
                    solid_names.append(name)
                continue
            if line.startswith("facet normal"):
                current_triangle = []
                continue
            if line.startswith("vertex "):
                point = parse_float_triplet(line[len("vertex ") :])
                if point is not None:
                    current_triangle.append(point)
                    if len(current_triangle) == 3:
                        triangle_indices = tuple(
                            deduped_vertex_index(point, vertex_map=vertex_map, vertices=vertices)
                            for point in current_triangle
                        )
                        triangles.append(triangle_indices)
                        current_triangle = []

    return analyze_triangle_mesh(
        vertices=vertices,
        triangles=triangles,
        kind="stl",
        unit=unit,
        extra_fields={
            "encoding": "ascii",
            "solid_names": solid_names,
        },
    )


def analyze_stl_file(path: Path, unit: str | None = None) -> dict[str, Any]:
    if is_binary_stl(path):
        return analyze_binary_stl(path, unit=unit)
    return analyze_ascii_stl(path, unit=unit)


def analyze_output_file(path: Path, output_format: str, assume_unit: str | None = None) -> dict[str, Any] | None:
    normalized = output_format.lower()
    if normalized in {"step", "stp"}:
        return analyze_step_file(path)
    if normalized in {"brep", "brp"}:
        return analyze_exact_shape_file(path, kind="brep", unit=assume_unit)
    if normalized in {"iges", "igs"}:
        return analyze_exact_shape_file(path, kind="iges", unit=assume_unit)
    if normalized == "obj":
        return analyze_obj_file(path, unit=assume_unit)
    if normalized == "stl":
        return analyze_stl_file(path, unit=assume_unit)
    return None


def infer_analysis_format(path: Path) -> str | None:
    suffix = path.suffix.lower().lstrip(".")
    if suffix in ANALYSIS_FORMATS:
        return suffix
    return None


def format_console_summary(analysis: dict[str, Any]) -> str:
    kind = analysis.get("kind")
    if kind == "step":
        names = ", ".join(analysis.get("product_names") or []) or "n/a"
        unit = analysis.get("length_unit") or "unknown"
        topology = analysis.get("topology") or {}
        bbox = analysis.get("bbox_mm") or analysis.get("bbox_native_units")
        bbox_text = "bbox unavailable"
        if bbox:
            size = bbox.get("size")
            bbox_unit = "mm" if analysis.get("bbox_mm") else (bbox.get("unit") or "native")
            bbox_text = f"bbox={size} {bbox_unit}"
        area = analysis.get("surface_area")
        volume = analysis.get("enclosed_volume")
        area_text = (
            f"; area={area} {analysis.get('surface_area_unit') or ''}".strip()
            if area is not None
            else ""
        )
        volume_text = (
            f"; volume={volume} {analysis.get('volume_unit') or ''}".strip()
            if volume is not None
            else ""
        )
        return (
            f"STEP analysis: names={names}; unit={unit}; "
            f"solids={topology.get('solids', 0)}; faces={topology.get('faces', 0)}; "
            f"edges={topology.get('edges', 0)}; vertices={topology.get('vertices', 0)}; "
            f"{bbox_text}{area_text}{volume_text}"
        )

    if kind == "obj":
        bbox = analysis.get("bbox_native_units")
        bbox_text = f"bbox={bbox.get('size')}" if bbox else "bbox unavailable"
        area = analysis.get("surface_area")
        volume = analysis.get("enclosed_volume")
        area_text = f"area={area} {analysis.get('surface_area_unit') or ''}".strip()
        volume_text = (
            f"volume={volume} {analysis.get('volume_unit') or ''}".strip()
            if volume is not None
            else "volume=n/a"
        )
        return (
            f"OBJ analysis: vertices={analysis.get('vertex_count', 0)}; "
            f"faces={analysis.get('face_count', 0)}; triangles={analysis.get('triangle_count', 0)}; "
            f"{area_text}; {volume_text}; watertight={analysis.get('watertight')}; {bbox_text}"
        )

    if kind == "stl":
        bbox = analysis.get("bbox_native_units")
        bbox_text = f"bbox={bbox.get('size')}" if bbox else "bbox unavailable"
        area = analysis.get("surface_area")
        volume = analysis.get("enclosed_volume")
        area_text = f"area={area} {analysis.get('surface_area_unit') or ''}".strip()
        volume_text = (
            f"volume={volume} {analysis.get('volume_unit') or ''}".strip()
            if volume is not None
            else "volume=n/a"
        )
        return (
            f"STL analysis: encoding={analysis.get('encoding')}; "
            f"triangles={analysis.get('triangle_count', 0)}; "
            f"{area_text}; {volume_text}; watertight={analysis.get('watertight')}; {bbox_text}"
        )

    if kind in {"brep", "iges"}:
        bbox = analysis.get("bbox_native_units")
        bbox_text = "bbox unavailable"
        if bbox:
            bbox_text = f"bbox={bbox.get('size')} {bbox.get('unit') or 'native'}".strip()
        area = analysis.get("surface_area")
        volume = analysis.get("enclosed_volume")
        area_text = f"area={area} {analysis.get('surface_area_unit') or ''}".strip()
        volume_text = f"volume={volume} {analysis.get('volume_unit') or ''}".strip()
        topology = analysis.get("topology") or {}
        return (
            f"{kind.upper()} analysis: solids={topology.get('solids', 0)}; "
            f"faces={topology.get('faces', 0)}; edges={topology.get('edges', 0)}; "
            f"vertices={topology.get('vertices', 0)}; {area_text}; {volume_text}; {bbox_text}"
        )

    return "Analysis available"


def discover_exact_geometry_backend() -> dict[str, Any]:
    discovered_freecad = discover_freecad_executable()
    return {
        "python_modules": {
            "OCP": module_is_available("OCP"),
            "cadquery": module_is_available("cadquery"),
            "numpy": module_is_available("numpy"),
        },
        "exact_step_geometry_with_freecad": bool(
            discovered_freecad is not None and FREECAD_MEASURE_SCRIPT.exists()
        ),
        "exact_brep_geometry_with_freecad": bool(
            discovered_freecad is not None and FREECAD_MEASURE_SCRIPT.exists()
        ),
        "exact_iges_geometry_with_freecad": bool(
            discovered_freecad is not None and FREECAD_MEASURE_SCRIPT.exists()
        ),
        "freecad_cmd": {
            "available": discovered_freecad is not None,
            "path": discovered_freecad[0] if discovered_freecad else None,
            "detected_via": discovered_freecad[1] if discovered_freecad else None,
        },
        "freecad_measure_script": {
            "available": FREECAD_MEASURE_SCRIPT.exists(),
            "path": str(FREECAD_MEASURE_SCRIPT),
        },
        "freecad_timeout_seconds": round_number(freecad_timeout_seconds(), 3),
        "detail_limit": detail_limit(),
    }


def probe_environment(args: argparse.Namespace) -> dict[str, Any]:
    exact_geometry_backend = discover_exact_geometry_backend()
    try:
        backend = resolve_backend(args)
    except BackendNotFoundError as exc:
        conversion_backend = {
            "available": False,
            "error": str(exc),
        }
    else:
        conversion_backend = {
            "available": True,
            "name": backend.name,
            "executable": backend.executable,
            "template": backend.template,
            "detected_via": backend.detected_via,
        }

    return {
        "conversion_backend": conversion_backend,
        "analysis_capabilities": {
            "analysis_only_mode": True,
            "textual_step_analysis": True,
            "exact_step_geometry_with_freecad": exact_geometry_backend[
                "exact_step_geometry_with_freecad"
            ],
            "exact_brep_geometry_with_freecad": exact_geometry_backend[
                "exact_brep_geometry_with_freecad"
            ],
            "exact_iges_geometry_with_freecad": exact_geometry_backend[
                "exact_iges_geometry_with_freecad"
            ],
            "polyhedral_obj_analysis": True,
            "polyhedral_stl_analysis": True,
            "mesh_surface_area": True,
            "mesh_volume_when_watertight": True,
            "exact_brep_backend": exact_geometry_backend,
        },
    }


def print_probe(args: argparse.Namespace) -> None:
    json.dump(probe_environment(args), sys.stdout, indent=2)
    sys.stdout.write("\n")


def discover_executable(candidate_names: list[str], extra_paths: list[str]) -> tuple[str, str] | None:
    for candidate in candidate_names:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved, f"PATH:{candidate}"

    for candidate in extra_paths:
        path = Path(candidate).expanduser()
        if path.exists():
            return str(path.resolve()), f"KNOWN_PATH:{path}"

    return None


def resolve_backend(args: argparse.Namespace) -> BackendSpec:
    env_executable = os.environ.get("CATPART_CONVERTER_BIN")
    env_template = os.environ.get("CATPART_CONVERTER_TEMPLATE")
    executable_override = args.backend_executable or env_executable
    template_override = args.backend_cmd or env_template

    if args.backend == "custom":
        if not template_override:
            raise BackendNotFoundError(
                "Custom backend requested but no command template was provided. "
                "Use --backend-cmd or set CATPART_CONVERTER_TEMPLATE."
            )
        return BackendSpec(
            name="custom",
            executable=executable_override or "",
            template=template_override,
            detected_via="CLI_OR_ENV",
        )

    if template_override and args.backend == "auto":
        return BackendSpec(
            name="template",
            executable=executable_override or "",
            template=template_override,
            detected_via="ENV_OR_CLI_TEMPLATE",
        )

    if args.backend in {"auto", "cadexchanger"}:
        if executable_override:
            executable = normalize_path(executable_override)
            return BackendSpec(
                name="cadexchanger",
                executable=executable,
                template=CAD_EXCHANGER_TEMPLATE,
                detected_via="CLI_OR_ENV_EXECUTABLE",
            )

        discovered = discover_executable(CAD_EXCHANGER_EXECUTABLES, CAD_EXCHANGER_PATHS)
        if discovered:
            executable, detected_via = discovered
            return BackendSpec(
                name="cadexchanger",
                executable=executable,
                template=CAD_EXCHANGER_TEMPLATE,
                detected_via=detected_via,
            )

    raise BackendNotFoundError(
        "No CATPart converter backend was found.\n"
        "This plugin wraps an external CATIA-capable converter because CATPart is a "
        "proprietary format.\n\n"
        "Recommended setup:\n"
        "1. Install a converter backend such as CAD Exchanger Batch.\n"
        "2. Set CATPART_CONVERTER_BIN to the executable path.\n"
        "3. Optionally set CATPART_CONVERTER_TEMPLATE if your converter uses different flags.\n\n"
        "Example:\n"
        '  export CATPART_CONVERTER_BIN="/absolute/path/to/ExchangerConv"\n'
        '  export CATPART_CONVERTER_TEMPLATE=\'"{executable}" -i "{input}" -e "{output}"\''
    )


def render_command(backend: BackendSpec, input_path: Path, output_path: Path, output_format: str) -> list[str]:
    if "{executable}" in backend.template and not backend.executable:
        raise ValueError(
            "The selected backend template requires {executable}, but no executable path was provided."
        )
    values = {
        "executable": backend.executable,
        "input": str(input_path),
        "output": str(output_path),
        "format": output_format,
    }
    return [segment.format(**values) for segment in shlex.split(backend.template)]


def determine_output_path(
    input_path: Path,
    output_format: str,
    output: str | None,
    output_dir: str | None,
) -> Path:
    extension = FORMAT_EXTENSIONS[output_format]
    if output:
        return Path(output).expanduser().resolve()

    if output_dir:
        base_dir = Path(output_dir).expanduser().resolve()
        return base_dir / f"{input_path.stem}{extension}"

    return input_path.with_suffix(extension)


def validate_inputs(args: argparse.Namespace) -> list[Path]:
    if args.probe:
        return []

    if not args.inputs:
        raise SystemExit("At least one input file is required unless --probe is used.")

    if args.output and len(args.inputs) != 1:
        raise SystemExit("--output can only be used with exactly one input file.")

    resolved_inputs = [Path(item).expanduser().resolve() for item in args.inputs]
    missing = [str(path) for path in resolved_inputs if not path.exists()]
    if missing:
        raise SystemExit("Input file(s) not found:\n" + "\n".join(missing))
    return resolved_inputs


def write_report(report_path: str, payload: dict[str, Any]) -> None:
    if report_path == "-":
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return

    destination = Path(report_path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")

    print(f"Wrote report: {destination}")


def convert_one(
    backend: BackendSpec,
    input_path: Path,
    output_path: Path,
    output_format: str,
    overwrite: bool,
    dry_run: bool,
    analyze: bool,
    assume_unit: str | None,
) -> dict[str, Any]:
    started_at = time.time()
    source_sha256 = sha256_of(input_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if input_path == output_path:
        raise FileExistsError(
            f"Output path resolves to the source file: {output_path}. Choose a different output path."
        )

    if output_path.exists() and not overwrite:
        raise FileExistsError(
            f"Output already exists: {output_path}. Re-run with --overwrite to replace it."
        )
    if output_path.exists() and overwrite:
        output_path.unlink()

    command = render_command(backend, input_path, output_path, output_format)
    result: dict[str, Any] = {
        "source": str(input_path),
        "output": str(output_path),
        "format": output_format,
        "backend": backend.name,
        "backend_detected_via": backend.detected_via,
        "command": command,
        "status": "dry_run" if dry_run else "pending",
        "started_at_epoch": started_at,
        "source_sha256": source_sha256,
    }

    if dry_run:
        result["status"] = "dry_run"
        result["duration_seconds"] = 0.0
        return result

    completed = subprocess.run(command, capture_output=True, text=True)
    finished_at = time.time()

    result["returncode"] = completed.returncode
    result["stdout"] = completed.stdout
    result["stderr"] = completed.stderr
    result["duration_seconds"] = round(finished_at - started_at, 3)

    if completed.returncode != 0:
        result["status"] = "failed"
        return result

    if not output_path.exists():
        result["status"] = "failed"
        result["stderr"] = (
            (completed.stderr or "")
            + "\nBackend command returned success but no output file was created."
        ).strip()
        return result

    result["status"] = "converted"
    result["output_sha256"] = sha256_of(output_path)
    result["output_size_bytes"] = output_path.stat().st_size
    if analyze:
        try:
            analysis = analyze_output_file(output_path, output_format, assume_unit=assume_unit)
        except Exception as exc:  # pragma: no cover - defensive reporting
            result["analysis_error"] = str(exc)
        else:
            if analysis is not None:
                result["analysis"] = analysis
    return result


def analyze_existing_file(
    path: Path,
    *,
    assume_unit: str | None,
) -> dict[str, Any]:
    analysis_format = infer_analysis_format(path)
    if analysis_format is None:
        raise ValueError(
            f"Unsupported analysis input: {path}. Supported extensions are: "
            + ", ".join(sorted(ANALYSIS_FORMATS))
        )

    analysis = analyze_output_file(path, analysis_format, assume_unit=assume_unit)
    if analysis is None:
        raise ValueError(f"No analyzer is available for: {path}")

    return {
        "source": str(path),
        "format": analysis_format,
        "status": "analyzed",
        "source_sha256": sha256_of(path),
        "source_size_bytes": path.stat().st_size,
        "analysis": analysis,
    }


def main() -> int:
    args = parse_args()
    log_stream = sys.stderr if args.report == "-" else sys.stdout

    if args.probe:
        print_probe(args)
        return 0

    inputs = validate_inputs(args)
    if args.analysis_only:
        results: list[dict[str, Any]] = []
        failures = 0
        for input_path in inputs:
            try:
                result = analyze_existing_file(input_path, assume_unit=args.assume_unit)
            except Exception as exc:
                failures += 1
                result = {
                    "source": str(input_path),
                    "status": "failed",
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                }
                print(f"[FAILED] {input_path.name}: {exc}", file=sys.stderr)
            else:
                print(f"[OK] analyzed {input_path}", file=log_stream)
                print(f"  {format_console_summary(result['analysis'])}", file=log_stream)

            results.append(result)

        report_payload = {
            "results": results,
            "summary": {
                "total": len(results),
                "failed": failures,
                "succeeded": len(results) - failures,
                "mode": "analysis_only",
            },
        }
        if args.report:
            write_report(args.report, report_payload)
        return 1 if failures else 0

    try:
        backend = resolve_backend(args)
    except BackendNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    results: list[dict[str, Any]] = []
    failures = 0

    for input_path in inputs:
        output_path = determine_output_path(
            input_path=input_path,
            output_format=args.format,
            output=args.output,
            output_dir=args.output_dir,
        )

        try:
            result = convert_one(
                backend=backend,
                input_path=input_path,
                output_path=output_path,
                output_format=args.format,
                overwrite=args.overwrite,
                dry_run=args.dry_run,
                analyze=not args.skip_analysis,
                assume_unit=args.assume_unit,
            )
        except (FileExistsError, ValueError) as exc:
            result = {
                "source": str(input_path),
                "output": str(output_path),
                "format": args.format,
                "backend": backend.name,
                "backend_detected_via": backend.detected_via,
                "status": "failed",
                "error": str(exc),
                "error_type": type(exc).__name__,
            }

        results.append(result)
        status = result["status"]
        if status not in {"converted", "dry_run"}:
            failures += 1
            detail = result.get("error") or result.get("stderr") or "conversion failed"
            print(f"[FAILED] {input_path.name} -> {output_path.name}: {detail}", file=sys.stderr)
            continue

        if status == "dry_run":
            command_str = " ".join(shlex.quote(part) for part in result["command"])
            print(f"[DRY RUN] {command_str}", file=log_stream)
            continue

        print(f"[OK] {input_path} -> {output_path}", file=log_stream)
        if result.get("analysis"):
            print(f"  {format_console_summary(result['analysis'])}", file=log_stream)
        elif result.get("analysis_error"):
            print(f"  analysis error: {result['analysis_error']}", file=log_stream)

    report_payload = {
        "results": results,
        "summary": {
            "total": len(results),
            "failed": failures,
            "succeeded": len(results) - failures,
            "format": args.format,
            "backend": backend.name,
        },
    }

    if args.report:
        write_report(args.report, report_payload)

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
