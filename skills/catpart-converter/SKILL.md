---
name: catpart-converter
description: Convert CATIA CATPart files into readable exchange formats such as STEP, OBJ, and STL by calling the local workspace conversion script, then extract engineering summaries from supported outputs. When FreeCAD is available, STEP, BREP, and IGES summaries also include exact geometry metrics. Use when the user asks to inspect, convert, or ingest CATPart files.
---

# CATPart Converter

## When to use

Use this skill when the user wants to:

- convert a `.CATPart` file into a format Codex can inspect
- convert an existing `.step` or `.stp` file locally with FreeCAD
- inspect CATIA part geometry through a readable exchange format
- batch-convert CATPart files into `STEP`, `OBJ`, `STL`, `IGES`, or `BREP`
- extract engineering summaries after conversion
- re-analyze an existing `STEP`, `OBJ`, `STL`, `BREP`, or `IGES` file without converting again

## Default workflow

1. Prefer `STEP` unless the user asks for another format.
2. If the user already has a `.step` or `.stp`, use local FreeCAD conversion when a different target is needed:

```bash
python3 plugins/catpart-converter/scripts/convert_catpart.py "<input.step>" --source-format step --format brep
```

3. For `.CATPart`, run the local converter script:

```bash
python3 plugins/catpart-converter/scripts/convert_catpart.py "<input.CATPart>" --format step
```

4. If CATIA V5 `catstart` is available, prefer the native batch backend when exact CATPart mass/volume is important:

```bash
python3 plugins/catpart-converter/scripts/convert_catpart.py "<input.CATPart>" --backend catia --format step
```

This backend generates a CATScript, runs `catstart -run "CNEXT -batch -macro ..."`, exports STEP/IGES/STL, and records CATIA `Product.Analyze` mass, volume, wet area, gravity center, and inertia matrix when CATIA exposes them.

5. If Datakit CrossManager CLI is installed, use `--backend datakit` with `CATPART_DATKIT_BIN` and a command template from the installed product:

```bash
CATPART_DATKIT_BIN="/path/to/CrossManagerCLI" \
CATPART_DATKIT_TEMPLATE='"{executable}" --input "{input}" --output "{output}"' \
python3 plugins/catpart-converter/scripts/convert_catpart.py "<input.CATPart>" --backend datakit --format step
```

6. If HOOPS Exchange is installed, licensed, and the `ImportExport` sample is built, use `--backend hoops`:

```bash
CATPART_HOOPS_IMPORTEXPORT_BIN="/path/to/HOOPS_Exchange/samples/exchange/exchangesource/ImportExport/ImportExport" \
python3 plugins/catpart-converter/scripts/convert_catpart.py "<input.CATPart>" --backend hoops --format step
```

7. If 3D-Tool NativeCAD Converter is installed on Windows, use `--backend 3dtool`:

```bash
set CATPART_THREEDTOOL_BIN=C:\Program Files\3D-Tool V17\Convert.exe
python scripts\convert_catpart.py "<input.CATPart>" --backend 3dtool --format step
```

8. If TransMagic COMMAND is installed on Windows, use `--backend transmagic`:

```bash
set CATPART_TRANSMAGIC_BIN=C:\Program Files\TransMagic Inc\TransMagic RXX\System\code\bin\TMCmd.exe
python scripts\convert_catpart.py "<input.CATPart>" --backend transmagic --format step
```

This backend uses the documented `TMCmd` command-line flow and requests XML mass, bounding-box, and surface-area reports when available.

9. If CoreTechnologie 3D_Evolution, Enterprise Data Manager, or a 3D_Kernel_IO wrapper is installed, use `--backend coretechnologie` with `CATPART_CORETECHNOLOGIE_BIN` and a command template from the installed product:

```bash
CATPART_CORETECHNOLOGIE_BIN="/path/to/3D_Evolution" \
CATPART_CORETECHNOLOGIE_TEMPLATE='"{executable}" --input "{input}" --output "{output}"' \
python3 plugins/catpart-converter/scripts/convert_catpart.py "<input.CATPart>" --backend coretechnologie --format step
```

10. If the conversion succeeds, read the terminal summary or JSON report first.
11. For `STEP`, prefer the generated engineering summary first. It combines textual metadata, broad value-type scanning, and exact `FreeCAD` geometry measurements when `freecadcmd` is available.
12. For existing `BREP` or `IGES` files, use `--analysis-only` to get exact topology, area, volume, center of gravity, and bounding box measurements.
13. If the backend is missing for `.CATPart`, explain that the plugin is installed but still needs an external CATIA-capable converter backend.
14. When a report contains `diagnostics`, use it to distinguish missing native CATPart conversion from available local FreeCAD analysis/conversion of existing exchange files.

## Backend setup

The script will auto-detect a backend in this order:

1. `CATPART_CONVERTER_TEMPLATE`
2. `CATPART_CONVERTER_BIN`
3. `CATPART_CATIA_CATSTART_BIN` / common CATIA `catstart` locations
4. `CATPART_DATKIT_BIN` plus `CATPART_DATKIT_TEMPLATE` / common Datakit CrossManager CLI names and paths
5. `CATPART_HOOPS_IMPORTEXPORT_BIN` / common HOOPS Exchange `ImportExport` sample paths
6. `CATPART_THREEDTOOL_BIN` / common 3D-Tool `Convert.exe` paths
7. `CATPART_TRANSMAGIC_BIN` / common TransMagic COMMAND `TMCmd` paths
8. `CATPART_CORETECHNOLOGIE_BIN` plus `CATPART_CORETECHNOLOGIE_TEMPLATE` / common CoreTechnologie paths
9. common `CAD Exchanger` executable names and paths

For exact `STEP`, `BREP`, and `IGES` geometry analysis it will also auto-detect `freecadcmd` from:

1. `CATPART_FREECAD_CMD`
2. `PATH`
3. common macOS app paths
4. common conda environment locations

You can probe the environment with:

```bash
python3 plugins/catpart-converter/scripts/convert_catpart.py --probe
```

If no CATPart-capable backend is found, `--probe` returns structured diagnostics with current FreeCAD capabilities, native backend candidates, required backend examples, and the exact environment variables to configure.

## Output guidance

- Use `STEP` for downstream analysis in Codex.
- Use `OBJ` or `STL` when the user specifically wants mesh output.
- Write a JSON report with `--report <path>` when you need a durable conversion log.
- `STEP` summaries are the best option for engineering metadata. Mesh summaries are useful for geometry size and complexity, but not for B-Rep semantics.
- When `FreeCAD` is available, `STEP` summaries also include exact area, enclosed volume, center of gravity, and a non-inferred bounding box.
- Exact `FreeCAD` summaries can include per-solid details, shell details, static moments, inertia matrices, and principal inertia properties when available.
- `STEP` text summaries include numeric ranges and value-type counts for integers, reals, scientific notation, logicals, enumerations, references, strings, omitted values, and derived values.
- Local FreeCAD conversion can convert existing `STEP/STP/BREP/IGES/IGS` inputs to `STEP/STP/BREP/IGES/IGS/STL/OBJ` when `--backend auto` is used.
- `--probe` reports candidate native CATPart backends for CATIA V5 batch, Datakit CrossManager CLI, HOOPS Exchange ImportExport, 3D-Tool NativeCAD Converter, TransMagic COMMAND, CoreTechnologie 3D_Evolution, and CAD Exchanger Batch.
- `--probe` reports manual CATPart routes such as Autodesk Fusion separately from automatic backends; do not treat a manual route as plugin-level conversion availability.
- Datakit, HOOPS, 3D-Tool, and CoreTechnologie are conversion backends only in this plugin unless their configured reports expose mass properties. Exact native mass/volume still requires CATIA `Product.Analyze`, TransMagic XML mass reports, vendor-specific reports, or a successful STEP/BREP/IGES export followed by FreeCAD analysis.
- Use `--analysis-only` when the user already has a converted `STEP`, `OBJ`, `STL`, `BREP`, or `IGES`.
- Use `--assume-unit mm` or `--assume-unit m` for mesh files when unit labeling matters.
- Use `--assume-unit mm` or `--assume-unit m` for `BREP` and `IGES` when the geometry units are known operationally but not labeled clearly in the surrounding workflow.

## Examples

Convert to STEP:

```bash
python3 plugins/catpart-converter/scripts/convert_catpart.py \
  "/path/to/model.CATPart" \
  --format step \
  --report "/path/to/model.conversion.json"
```

Convert multiple files into one directory:

```bash
python3 plugins/catpart-converter/scripts/convert_catpart.py \
  "/path/to/A.CATPart" \
  "/path/to/B.CATPart" \
  --format obj \
  --output-dir "/path/to/out"
```

Analyze an existing mesh:

```bash
python3 plugins/catpart-converter/scripts/convert_catpart.py \
  "/path/to/model.obj" \
  --analysis-only \
  --assume-unit mm \
  --report "/path/to/model.analysis.json"
```
