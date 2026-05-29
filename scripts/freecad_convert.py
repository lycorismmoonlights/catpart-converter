#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import FreeCAD as App
import Mesh
import MeshPart
import Part


INPUT_ENV_NAME = "CATPART_GEOMETRY_INPUT"
OUTPUT_ENV_NAME = "CATPART_GEOMETRY_OUTPUT"
FORMAT_ENV_NAME = "CATPART_GEOMETRY_OUTPUT_FORMAT"
LINEAR_DEFLECTION_ENV_NAME = "CATPART_MESH_LINEAR_DEFLECTION"
ANGULAR_DEFLECTION_ENV_NAME = "CATPART_MESH_ANGULAR_DEFLECTION"
DEFAULT_LINEAR_DEFLECTION = 0.1
DEFAULT_ANGULAR_DEFLECTION = 0.5
JSON_PREFIX = "JSON_RESULT="


def numeric_env(name: str, default: float) -> float:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    try:
        parsed = float(raw_value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def round_number(value: float, digits: int = 9) -> float:
    return round(float(value), digits)


def topology_payload(shape: object) -> dict[str, int]:
    return {
        "solids": len(shape.Solids),
        "shells": len(shape.Shells),
        "faces": len(shape.Faces),
        "edges": len(shape.Edges),
        "vertices": len(shape.Vertexes),
        "wires": len(shape.Wires),
        "compounds": len(shape.Compounds),
        "comp_solids": len(shape.CompSolids),
    }


def read_shape(path: Path) -> object:
    shape = Part.Shape()
    shape.read(str(path))
    if shape.isNull():
        raise RuntimeError(f"FreeCAD imported a null shape from: {path}")
    return shape


def export_shape(shape: object, output_path: Path, output_format: str) -> dict[str, object]:
    normalized_format = output_format.lower()
    if normalized_format in {"brep", "brp"}:
        shape.exportBrep(str(output_path))
        return {"strategy": "shape.exportBrep"}

    if normalized_format in {"step", "stp"}:
        shape.exportStep(str(output_path))
        return {"strategy": "shape.exportStep"}

    if normalized_format in {"iges", "igs"}:
        shape.exportIges(str(output_path))
        return {"strategy": "shape.exportIges"}

    if normalized_format == "stl":
        shape.exportStl(str(output_path))
        return {"strategy": "shape.exportStl"}

    if normalized_format == "obj":
        linear_deflection = numeric_env(LINEAR_DEFLECTION_ENV_NAME, DEFAULT_LINEAR_DEFLECTION)
        angular_deflection = numeric_env(ANGULAR_DEFLECTION_ENV_NAME, DEFAULT_ANGULAR_DEFLECTION)
        doc = App.newDocument("StepMeshExport")
        mesh = MeshPart.meshFromShape(
            Shape=shape,
            LinearDeflection=linear_deflection,
            AngularDeflection=angular_deflection,
            Relative=False,
        )
        mesh_object = doc.addObject("Mesh::Feature", "Mesh")
        mesh_object.Mesh = mesh
        doc.recompute()
        Mesh.export([mesh_object], str(output_path))
        return {
            "strategy": "MeshPart.meshFromShape+Mesh.export",
            "linear_deflection": round_number(linear_deflection),
            "angular_deflection": round_number(angular_deflection),
            "mesh_facets": mesh.CountFacets,
            "mesh_points": mesh.CountPoints,
        }

    raise RuntimeError(f"Unsupported FreeCAD export format: {output_format}")


def main() -> int:
    input_value = os.environ.get(INPUT_ENV_NAME)
    output_value = os.environ.get(OUTPUT_ENV_NAME)
    output_format = os.environ.get(FORMAT_ENV_NAME)
    if not input_value or not output_value or not output_format:
        print(
            f"Set {INPUT_ENV_NAME}, {OUTPUT_ENV_NAME}, and {FORMAT_ENV_NAME}.",
            file=sys.stderr,
        )
        return 2

    input_path = Path(input_value).expanduser().resolve()
    output_path = Path(output_value).expanduser().resolve()
    if not input_path.exists():
        print(f"Input geometry file not found: {input_path}", file=sys.stderr)
        return 2

    shape = read_shape(input_path)
    export_metadata = export_shape(shape, output_path, output_format)
    if not output_path.exists():
        raise RuntimeError(f"FreeCAD did not create the output file: {output_path}")

    payload = {
        "input": str(input_path),
        "output": str(output_path),
        "format": output_format,
        "shape_type": shape.ShapeType,
        "is_valid": shape.isValid(),
        "surface_area": round_number(shape.Area),
        "volume": round_number(shape.Volume),
        "topology": topology_payload(shape),
        "export": export_metadata,
    }
    print(JSON_PREFIX + json.dumps(payload, separators=(",", ":")))
    return 0


exit_code = main()
if exit_code:
    raise SystemExit(exit_code)
