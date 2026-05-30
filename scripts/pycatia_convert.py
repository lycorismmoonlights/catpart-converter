#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any


def round_number(value: Any, digits: int = 6) -> float | None:
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def rounded_sequence(values: Any) -> list[float] | None:
    if values is None:
        return None
    try:
        parsed = [round_number(item) for item in values]
    except TypeError:
        return None
    if any(item is None for item in parsed):
        return None
    return [item for item in parsed if item is not None]


def write_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def product_from_document(document: Any) -> Any | None:
    product_method = getattr(document, "product", None)
    if callable(product_method):
        try:
            return product_method()
        except Exception:
            pass
    raw_com_object = getattr(document, "com_object", None) or getattr(document, "_com_object", None)
    if raw_com_object is not None:
        try:
            return raw_com_object.Product
        except Exception:
            pass
    return None


def try_design_mode(product: Any) -> None:
    try:
        from pycatia.enumeration.enumeration_types import cat_work_mode_type
    except Exception:
        return
    try:
        product.apply_work_mode(cat_work_mode_type.index("DESIGN_MODE"))
    except Exception:
        return


def analyze_product(product: Any) -> dict[str, Any] | None:
    analyze = getattr(product, "analyze", None)
    if analyze is None:
        analyze = getattr(product, "Analyze", None)
    if analyze is None:
        return None

    payload: dict[str, Any] = {
        "kind": "pycatia_native",
        "source": "CATIA V5 Product.Analyze through pycatia",
        "unit_notes": {
            "mass": "CATIA Product.Analyze mass value",
            "volume": "CATIA Product.Analyze volume value",
            "wet_area": "CATIA Product.Analyze wet area value",
            "gravity_center": "CATIA Product.Analyze gravity center coordinates",
            "inertia_matrix": "CATIA Product.Analyze inertia matrix",
        },
    }

    for name in ("mass", "volume", "wet_area"):
        value = round_number(getattr(analyze, name, None))
        if value is not None:
            payload[name] = value

    gravity_method = getattr(analyze, "get_gravity_center", None)
    if callable(gravity_method):
        payload["gravity_center"] = rounded_sequence(gravity_method())
    elif hasattr(analyze, "GetGravityCenter"):
        try:
            values = [0.0, 0.0, 0.0]
            analyze.GetGravityCenter(values)
            payload["gravity_center"] = rounded_sequence(values)
        except Exception:
            pass

    inertia_method = getattr(analyze, "get_inertia", None)
    if callable(inertia_method):
        payload["inertia_matrix"] = rounded_sequence(inertia_method())
    elif hasattr(analyze, "GetInertia"):
        try:
            values = [0.0] * 9
            analyze.GetInertia(values)
            payload["inertia_matrix"] = rounded_sequence(values)
        except Exception:
            pass

    return {key: value for key, value in payload.items() if value is not None}


def exported_path_for(output_path: Path, catia_export_format: str) -> Path:
    return output_path.with_suffix(f".{catia_export_format}")


def main(input_path: str, output_path: str, catia_export_format: str, report_path: str) -> int:
    started_at = time.time()
    source = Path(input_path).expanduser().resolve()
    destination = Path(output_path).expanduser().resolve()
    report = Path(report_path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)

    document = None
    native: dict[str, Any] = {
        "kind": "pycatia_native",
        "status": "pending",
        "source": "CATIA V5 automation through pycatia",
        "input": str(source),
        "output": str(destination),
        "catia_export_format": catia_export_format,
    }
    try:
        from pycatia import catia

        documents = catia.documents
        documents.open(str(source))
        document = catia.active_document

        product = product_from_document(document)
        if product is not None:
            try_design_mode(product)
            product_analysis = analyze_product(product)
            if product_analysis:
                native.update(product_analysis)

        export_base = destination.with_suffix("")
        document.export_data(str(export_base), catia_export_format, overwrite=True)
        created_path = exported_path_for(destination, catia_export_format)
        if created_path.exists() and created_path != destination:
            if destination.exists():
                destination.unlink()
            shutil.move(str(created_path), str(destination))

        native["status"] = "converted"
        native["duration_seconds"] = round(time.time() - started_at, 3)
        write_report(report, native)
        return 0
    except Exception as exc:
        native["status"] = "failed"
        native["error"] = str(exc)
        native["error_type"] = type(exc).__name__
        native["duration_seconds"] = round(time.time() - started_at, 3)
        write_report(report, native)
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        if document is not None:
            try:
                document.close()
            except Exception:
                pass


if __name__ == "__main__":
    if len(sys.argv) != 5:
        print(
            "Usage: pycatia_convert.py <input-model> <output-model> <catia-export-format> <report-json>",
            file=sys.stderr,
        )
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]))
