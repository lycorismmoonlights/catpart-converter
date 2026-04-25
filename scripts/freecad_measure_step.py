#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

import Part

INPUT_ENV_NAMES = ("CATPART_EXACT_GEOMETRY_INPUT", "CATPART_STEP_INPUT")


def round_number(value: float, digits: int = 9) -> float:
    return round(float(value), digits)


def bound_box_payload(bound_box: object) -> dict[str, object]:
    minimum = [
        round_number(bound_box.XMin),
        round_number(bound_box.YMin),
        round_number(bound_box.ZMin),
    ]
    maximum = [
        round_number(bound_box.XMax),
        round_number(bound_box.YMax),
        round_number(bound_box.ZMax),
    ]
    size = [
        round_number(bound_box.XLength),
        round_number(bound_box.YLength),
        round_number(bound_box.ZLength),
    ]
    diagonal = round_number(
        math.sqrt(bound_box.XLength ** 2 + bound_box.YLength ** 2 + bound_box.ZLength ** 2)
    )
    return {
        "min": minimum,
        "max": maximum,
        "size": size,
        "diagonal": diagonal,
    }


def point_payload(point: object | None) -> list[float] | None:
    if point is None:
        return None
    return [
        round_number(point.x),
        round_number(point.y),
        round_number(point.z),
    ]


def main() -> int:
    raw_input = None
    for env_name in INPUT_ENV_NAMES:
        raw_input = os.environ.get(env_name)
        if raw_input:
            break
    if raw_input is None and len(sys.argv) == 2:
        raw_input = sys.argv[1]
    if raw_input is None:
        print(
            "Usage: freecad_measure_step.py <path/to/model.step> or set CATPART_EXACT_GEOMETRY_INPUT",
            file=sys.stderr,
        )
        return 2

    step_path = Path(raw_input).expanduser().resolve()
    if not step_path.exists():
        print(f"STEP file not found: {step_path}", file=sys.stderr)
        return 2

    shape = Part.Shape()
    shape.read(str(step_path))
    center = getattr(shape, "CenterOfGravity", None)

    payload = {
        "shape_type": shape.ShapeType,
        "is_null": shape.isNull(),
        "is_valid": shape.isValid(),
        "surface_area": round_number(shape.Area),
        "volume": round_number(shape.Volume),
        "center_of_gravity": point_payload(center),
        "bbox": bound_box_payload(shape.BoundBox),
        "topology": {
            "solids": len(shape.Solids),
            "shells": len(shape.Shells),
            "faces": len(shape.Faces),
            "edges": len(shape.Edges),
            "vertices": len(shape.Vertexes),
            "wires": len(shape.Wires),
            "compounds": len(shape.Compounds),
            "comp_solids": len(shape.CompSolids),
        },
    }

    print("JSON_RESULT=" + json.dumps(payload, separators=(",", ":")))
    return 0


exit_code = main()
if exit_code:
    raise SystemExit(exit_code)
