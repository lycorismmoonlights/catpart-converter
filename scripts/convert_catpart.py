#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
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

CAD_EXCHANGER_EXECUTABLES = [
    "ExchangerConv",
    "ExchangerConv.exe",
    "cadexchangerbatch",
]

CAD_EXCHANGER_PATHS = [
    "/Applications/CAD Exchanger Lab.app/Contents/MacOS/ExchangerConv",
]

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


def round_number(value: float, digits: int = 6) -> float:
    return round(float(value), digits)


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
    return {
        "min": minimum,
        "max": maximum,
        "size": size,
        "unit": unit,
        "inferred": inferred,
    }


def parse_float_triplet(raw_values: str) -> tuple[float, float, float] | None:
    values = [float(match) for match in FLOAT_RE.findall(raw_values)]
    if len(values) < 3:
        return None
    return values[0], values[1], values[2]


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
        return conversion_match.group(1)

    return None


def step_bbox_in_mm(
    bbox: dict[str, Any] | None,
    unit: str | None,
) -> dict[str, Any] | None:
    if not bbox or not unit:
        return None

    scale_to_mm = {
        "um": 0.001,
        "mm": 1.0,
        "cm": 10.0,
        "dm": 100.0,
        "m": 1000.0,
        "km": 1000000.0,
    }.get(unit.lower())
    if scale_to_mm is None:
        return None

    return {
        key: [round_number(value * scale_to_mm) for value in bbox[key]]
        for key in ("min", "max", "size")
    }


def step_records(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    return [record.strip() + ";" for record in text.split(";") if record.strip()]


def analyze_step_file(path: Path) -> dict[str, Any]:
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


def analyze_obj_file(path: Path) -> dict[str, Any]:
    bbox = create_bbox()
    vertex_count = 0
    face_count = 0
    objects: list[str] = []
    materials: list[str] = []

    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            vertex_match = OBJ_VERTEX_RE.match(line)
            if vertex_match:
                vertex_count += 1
                point = (
                    float(vertex_match.group(1)),
                    float(vertex_match.group(2)),
                    float(vertex_match.group(3)),
                )
                update_bbox(bbox, point)
                continue

            if OBJ_FACE_RE.match(line):
                face_count += 1
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

    return {
        "kind": "obj",
        "read_strategy": "textual_obj_analysis",
        "native_catpart_read": False,
        "precision_note": "Derived from converted mesh output. Mesh statistics are exact for the OBJ file.",
        "vertex_count": vertex_count,
        "face_count": face_count,
        "objects": objects,
        "materials": materials,
        "bbox_native_units": finalize_bbox(bbox, unit=None, inferred=False),
    }


def is_binary_stl(path: Path) -> bool:
    file_size = path.stat().st_size
    if file_size < 84:
        return False
    with path.open("rb") as handle:
        header = handle.read(84)
    triangle_count = struct.unpack("<I", header[80:84])[0]
    return 84 + triangle_count * 50 == file_size


def analyze_binary_stl(path: Path) -> dict[str, Any]:
    bbox = create_bbox()
    with path.open("rb") as handle:
        header = handle.read(84)
        triangle_count = struct.unpack("<I", header[80:84])[0]
        for _ in range(triangle_count):
            record = handle.read(50)
            if len(record) < 50:
                break
            vertices = struct.unpack("<12f", record[:48])[3:]
            for index in range(0, 9, 3):
                update_bbox(bbox, (vertices[index], vertices[index + 1], vertices[index + 2]))

    return {
        "kind": "stl",
        "encoding": "binary",
        "read_strategy": "binary_stl_analysis",
        "native_catpart_read": False,
        "precision_note": "Derived from converted mesh output. Triangle count and bounding box are exact for the STL file.",
        "triangle_count": triangle_count,
        "bbox_native_units": finalize_bbox(bbox, unit=None, inferred=False),
    }


def analyze_ascii_stl(path: Path) -> dict[str, Any]:
    bbox = create_bbox()
    triangle_count = 0
    solid_names: list[str] = []

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
                triangle_count += 1
                continue
            if line.startswith("vertex "):
                point = parse_float_triplet(line[len("vertex ") :])
                if point is not None:
                    update_bbox(bbox, point)

    return {
        "kind": "stl",
        "encoding": "ascii",
        "read_strategy": "ascii_stl_analysis",
        "native_catpart_read": False,
        "precision_note": "Derived from converted mesh output. Triangle count and bounding box are exact for the STL file.",
        "triangle_count": triangle_count,
        "solid_names": solid_names,
        "bbox_native_units": finalize_bbox(bbox, unit=None, inferred=False),
    }


def analyze_stl_file(path: Path) -> dict[str, Any]:
    if is_binary_stl(path):
        return analyze_binary_stl(path)
    return analyze_ascii_stl(path)


def analyze_output_file(path: Path, output_format: str) -> dict[str, Any] | None:
    normalized = output_format.lower()
    if normalized in {"step", "stp"}:
        return analyze_step_file(path)
    if normalized == "obj":
        return analyze_obj_file(path)
    if normalized == "stl":
        return analyze_stl_file(path)
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
        return (
            f"STEP analysis: names={names}; unit={unit}; "
            f"solids={topology.get('solids', 0)}; faces={topology.get('faces', 0)}; "
            f"edges={topology.get('edges', 0)}; vertices={topology.get('vertices', 0)}; "
            f"{bbox_text}"
        )

    if kind == "obj":
        bbox = analysis.get("bbox_native_units")
        bbox_text = f"bbox={bbox.get('size')}" if bbox else "bbox unavailable"
        return (
            f"OBJ analysis: vertices={analysis.get('vertex_count', 0)}; "
            f"faces={analysis.get('face_count', 0)}; {bbox_text}"
        )

    if kind == "stl":
        bbox = analysis.get("bbox_native_units")
        bbox_text = f"bbox={bbox.get('size')}" if bbox else "bbox unavailable"
        return (
            f"STL analysis: encoding={analysis.get('encoding')}; "
            f"triangles={analysis.get('triangle_count', 0)}; {bbox_text}"
        )

    return "Analysis available"


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
) -> dict[str, Any]:
    started_at = time.time()
    output_path.parent.mkdir(parents=True, exist_ok=True)

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
        "source_sha256": sha256_of(input_path),
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
            analysis = analyze_output_file(output_path, output_format)
        except Exception as exc:  # pragma: no cover - defensive reporting
            result["analysis_error"] = str(exc)
        else:
            if analysis is not None:
                result["analysis"] = analysis
    return result


def print_probe(backend: BackendSpec) -> None:
    payload = {
        "backend": backend.name,
        "executable": backend.executable,
        "template": backend.template,
        "detected_via": backend.detected_via,
    }
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")


def main() -> int:
    args = parse_args()
    log_stream = sys.stderr if args.report == "-" else sys.stdout

    try:
        backend = resolve_backend(args)
    except BackendNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.probe:
        print_probe(backend)
        return 0

    inputs = validate_inputs(args)
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
            )
        except FileExistsError as exc:
            result = {
                "source": str(input_path),
                "output": str(output_path),
                "format": args.format,
                "backend": backend.name,
                "backend_detected_via": backend.detected_via,
                "status": "failed",
                "error": str(exc),
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
