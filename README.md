# CATPart Converter

`CATPart Converter` is a local Codex plugin that standardizes conversion of CATIA `.CATPart` files into formats Codex can inspect more easily, then extracts engineering-facing summaries from supported outputs.

The plugin itself does not reverse-engineer CATPart directly. Instead, it wraps a locally installed converter backend and gives you one stable CLI:

- Recommended readable output: `STEP` (`.step` / `.stp`)
- Mesh outputs: `OBJ`, `STL`, `GLTF`, `GLB`
- Exchange outputs: `IGES`, `BREP`, `X_T`, `X_B`

After conversion, the script now inspects supported outputs automatically:

- `STEP`: product names, schema, unit, topology counts, and when `FreeCAD` is available, exact B-Rep volume, area, center of gravity, and bounding box
- `BREP`: when `FreeCAD` is available, exact B-Rep volume, area, center of gravity, topology counts, and bounding box
- `IGES`: when `FreeCAD` is available, exact imported geometry volume, area, center of gravity, topology counts, and bounding box
- `OBJ`: vertex count, polygon face count, triangle count, area, watertight volume, centroids, object/material names, exact bounding box
- `STL`: triangle count, encoding type, area, watertight volume, centroids, exact bounding box

Exact `FreeCAD` reports also include per-solid details, shell counts, static moments, inertia matrices, and principal inertia properties when the imported shape exposes them.

## Why `STEP`

`STEP` is the default recommendation because it is a text-based CAD exchange format. After conversion, Codex can open the `.step` file directly and continue inspecting or transforming it.

## Files

- `scripts/convert_catpart.py`: conversion entry point
- `skills/catpart-converter/SKILL.md`: Codex usage instructions
- `.codex-plugin/plugin.json`: plugin manifest

## Quick Start

Probe whether a backend is configured:

```bash
python3 scripts/convert_catpart.py --probe
```

If `freecadcmd` is available locally, `--probe` will also report that exact `STEP`, `BREP`, and `IGES` geometry analysis is enabled.

Convert a file to STEP:

```bash
python3 scripts/convert_catpart.py \
  /path/to/part.CATPart \
  --format step \
  --report /path/to/part.conversion.json
```

The command will print an engineering summary in the terminal and also store the structured analysis in the JSON report.

Convert a file to OBJ in a separate output directory:

```bash
python3 scripts/convert_catpart.py \
  /path/to/part.CATPart \
  --format obj \
  --output-dir /path/to/output
```

Analyze an existing exported file without re-running conversion:

```bash
python3 scripts/convert_catpart.py \
  /path/to/mesh.obj \
  --analysis-only \
  --assume-unit mm \
  --report /path/to/mesh.analysis.json
```

Analyze an existing IGES or BREP file with exact geometry metrics:

```bash
python3 scripts/convert_catpart.py \
  /path/to/model.igs \
  --analysis-only \
  --assume-unit mm \
  --report /path/to/model.analysis.json
```

## Backend Configuration

The script supports three modes:

1. `--backend auto`
   Looks for a configured template first, then tries common `CAD Exchanger` executable names.

2. `--backend cadexchanger`
   Uses the built-in preset command shape:

```text
{executable} -i {input} -e {output}
```

3. `--backend custom`
   Uses your exact command template.

You can configure the backend with environment variables:

- `CATPART_CONVERTER_BIN`
  Absolute path to the converter executable.

- `CATPART_CONVERTER_TEMPLATE`
  A full command template with placeholders such as `{input}` and `{output}`.

- `CATPART_FREECAD_CMD`
  Optional absolute path to `freecadcmd` or `FreeCADCmd` for exact `STEP` geometry analysis.

- `CATPART_FREECAD_TIMEOUT_SECONDS`
  Optional timeout for `FreeCAD` exact geometry analysis. Defaults to `45` seconds.

- `CATPART_DETAIL_LIMIT`
  Optional maximum number of solids and shells included in detailed exact-geometry output. Defaults to `100`.

Example:

```bash
export CATPART_CONVERTER_BIN="/Applications/CAD Exchanger Lab.app/Contents/MacOS/ExchangerConv"
export CATPART_CONVERTER_TEMPLATE='"{executable}" -i "{input}" -e "{output}"'
```

Then run:

```bash
python3 scripts/convert_catpart.py /path/to/part.CATPart
```

## Notes

- Add this folder to your Codex local plugin path or marketplace as needed.
- If no backend is installed, the script exits with a clear setup message instead of failing silently.
- `--probe` now reports both conversion backend availability and local analysis capabilities.
- `freecadcmd` is auto-detected from `PATH`, common app paths, and common conda environment locations such as `/opt/anaconda3/envs/*/bin/freecadcmd`.
- For multi-file use, pass multiple input files and an `--output-dir`.
- The plugin still does not natively decode proprietary `CATPart` internals; engineering data is derived from the converted exchange file.
- For `STEP`, product metadata still comes from the STEP text itself. If `FreeCAD` is unavailable, the bounding box remains a `CARTESIAN_POINT` inference rather than a certified metrology result.
- When `FreeCAD` is available, `STEP` reports include exact imported B-Rep area, enclosed volume, center of gravity, and a non-inferred bounding box.
- Existing `BREP` and `IGES` files can now be analyzed directly with `--analysis-only`, and `--assume-unit` can be used to attach a unit label when the source format does not expose one clearly.
- Inertia and principal-axis properties are reported in FreeCAD's imported model units. Per-solid values are included because some imported top-level shapes expose volume but not top-level inertia.
- For `OBJ/STL`, surface area is exact for the mesh. Volume and volume centroid are only reported when the mesh appears watertight and orientation-consistent.
- Invalid `OBJ` faces are skipped and counted instead of crashing the entire analysis run.
