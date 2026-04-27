#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

import Part

INPUT_ENV_NAMES = ("CATPART_EXACT_GEOMETRY_INPUT", "CATPART_STEP_INPUT")
DETAIL_LIMIT_ENV_NAME = "CATPART_DETAIL_LIMIT"
DEFAULT_DETAIL_LIMIT = 100


def round_number(value: float, digits: int = 9) -> float:
    return round(float(value), digits)


def detail_limit() -> int:
    raw_value = os.environ.get(DETAIL_LIMIT_ENV_NAME)
    if raw_value is None:
        return DEFAULT_DETAIL_LIMIT
    try:
        parsed = int(raw_value)
    except ValueError:
        return DEFAULT_DETAIL_LIMIT
    return max(0, parsed)


def as_json_value(value: object) -> object:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return round_number(value)
    if isinstance(value, (list, tuple)):
        return [as_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): as_json_value(item) for key, item in value.items()}
    if all(hasattr(value, attr) for attr in ("x", "y", "z")):
        return point_payload(value)
    return str(value)


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


def matrix_payload(matrix: object | None) -> list[list[float]] | None:
    if matrix is None:
        return None
    rows = []
    for row in range(1, 5):
        rows.append(
            [
                round_number(getattr(matrix, f"A{row}{column}"))
                for column in range(1, 5)
            ]
        )
    return rows


def effective_mass(shape: object) -> float:
    raw_mass = float(getattr(shape, "Mass", 0.0))
    if raw_mass:
        return raw_mass
    volume = float(getattr(shape, "Volume", 0.0))
    return volume if volume else raw_mass


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


def shape_payload(shape: object) -> dict[str, object]:
    center = getattr(shape, "CenterOfMass", None) or getattr(shape, "CenterOfGravity", None)
    principal = getattr(shape, "PrincipalProperties", None)
    return {
        "shape_type": shape.ShapeType,
        "is_null": shape.isNull(),
        "is_valid": shape.isValid(),
        "mass": round_number(effective_mass(shape)),
        "freecad_mass": round_number(getattr(shape, "Mass", 0.0)),
        "surface_area": round_number(shape.Area),
        "volume": round_number(shape.Volume),
        "center_of_mass": point_payload(center),
        "center_of_gravity": point_payload(center),
        "bbox": bound_box_payload(shape.BoundBox),
        "topology": topology_payload(shape),
        "static_moments": as_json_value(getattr(shape, "StaticMoments", None)),
        "matrix_of_inertia": matrix_payload(getattr(shape, "MatrixOfInertia", None)),
        "principal_properties": as_json_value(principal),
    }


def subshape_details(shapes: list[object], limit: int) -> dict[str, object]:
    selected = shapes[:limit] if limit else []
    return {
        "count": len(shapes),
        "returned": len(selected),
        "truncated": len(shapes) > len(selected),
        "items": [
            {
                "index": index,
                **shape_payload(shape),
            }
            for index, shape in enumerate(selected)
        ],
    }


def sum_vectors(vectors: list[list[float] | None]) -> list[float] | None:
    valid_vectors = [vector for vector in vectors if vector is not None]
    if not valid_vectors:
        return None
    return [
        round_number(sum(vector[index] for vector in valid_vectors))
        for index in range(len(valid_vectors[0]))
    ]


def sum_matrices(matrices: list[list[list[float]] | None]) -> list[list[float]] | None:
    valid_matrices = [matrix for matrix in matrices if matrix is not None]
    if not valid_matrices:
        return None
    row_count = len(valid_matrices[0])
    column_count = len(valid_matrices[0][0])
    return [
        [
            round_number(sum(matrix[row][column] for matrix in valid_matrices))
            for column in range(column_count)
        ]
        for row in range(row_count)
    ]


def apply_solid_mass_property_fallback(
    payload: dict[str, object],
    solid_details_payload: dict[str, object],
) -> None:
    items = solid_details_payload.get("items")
    if not isinstance(items, list) or not items:
        return

    if payload.get("static_moments") is None:
        payload["static_moments"] = sum_vectors(
            [item.get("static_moments") for item in items if isinstance(item, dict)]
        )

    if payload.get("matrix_of_inertia") is None:
        payload["matrix_of_inertia"] = sum_matrices(
            [item.get("matrix_of_inertia") for item in items if isinstance(item, dict)]
        )

    if payload.get("principal_properties") is None and len(items) == 1:
        first_item = items[0]
        if isinstance(first_item, dict):
            payload["principal_properties"] = first_item.get("principal_properties")


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
    limit = detail_limit()

    payload = shape_payload(shape)
    solid_details_payload = subshape_details(shape.Solids, limit)
    apply_solid_mass_property_fallback(payload, solid_details_payload)
    payload.update(
        {
            "detail_limit": limit,
            "solid_details": solid_details_payload,
            "shell_details": subshape_details(shape.Shells, limit),
        }
    )

    print("JSON_RESULT=" + json.dumps(payload, separators=(",", ":")))
    return 0


exit_code = main()
if exit_code:
    raise SystemExit(exit_code)
