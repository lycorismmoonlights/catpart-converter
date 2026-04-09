#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
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
