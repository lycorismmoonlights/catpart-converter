#!/usr/bin/env python3
from __future__ import annotations

import importlib
import importlib.util
import os
import sys
from pathlib import Path


def _load_license_from_python_file(path: Path) -> str | None:
    spec = importlib.util.spec_from_file_location("catpart_cadex_license", path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        print(f"Failed to load CAD Exchanger SDK license file {path}: {exc}", file=sys.stderr)
        return None
    value = getattr(module, "Value", None)
    if callable(value):
        return str(value()).strip()
    return None


def license_value() -> str | None:
    env_value = os.environ.get("CATPART_CADEX_LICENSE")
    if env_value and env_value.strip():
        return env_value.strip()

    license_file = os.environ.get("CATPART_CADEX_LICENSE_FILE")
    if license_file:
        path = Path(license_file).expanduser().resolve()
        if not path.exists():
            print(f"CAD Exchanger SDK license file not found: {path}", file=sys.stderr)
            return None
        if path.suffix.lower() == ".py":
            loaded = _load_license_from_python_file(path)
            if loaded:
                return loaded
            print(
                f"CAD Exchanger SDK license Python file has no callable Value(): {path}",
                file=sys.stderr,
            )
            return None
        return path.read_text(encoding="utf-8", errors="replace").strip()

    try:
        module = importlib.import_module("cadex_license")
    except ImportError:
        return None
    value = getattr(module, "Value", None)
    if callable(value):
        return str(value()).strip()
    return None


def main(input_path: str, output_path: str) -> int:
    try:
        import cadexchanger.CadExCore as cadex
    except ImportError as exc:
        print(f"CAD Exchanger SDK Python module is not available: {exc}", file=sys.stderr)
        return 1

    key = license_value()
    if not key:
        print(
            "CAD Exchanger SDK license is not configured. Set CATPART_CADEX_LICENSE, "
            "CATPART_CADEX_LICENSE_FILE, or provide cadex_license.py on PYTHONPATH.",
            file=sys.stderr,
        )
        return 1

    if not cadex.LicenseManager.Activate(key):
        print("Failed to activate CAD Exchanger SDK license.", file=sys.stderr)
        return 1

    Path(output_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)

    model = cadex.ModelData_Model()
    reader = cadex.ModelData_ModelReader()
    if not reader.Read(cadex.Base_UTF16String(input_path), model):
        print(f"Failed to read input model: {input_path}", file=sys.stderr)
        return 1

    cadex.Base_Settings.Default().SetValue(cadex.Base_Settings.UseExceptions, True)
    try:
        writer = cadex.ModelData_ModelWriter()
        if not writer.Write(model, cadex.Base_UTF16String(output_path)):
            print(f"Failed to write output model: {output_path}", file=sys.stderr)
            return 1
    except cadex.Base_Exception as exc:
        print(exc.What(), file=sys.stderr)
        return 1

    print("CAD Exchanger SDK conversion completed.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: cadex_sdk_transfer.py <input-model> <output-model>", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1], sys.argv[2]))
