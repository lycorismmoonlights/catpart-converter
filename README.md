# CATPart Converter

`CATPart Converter` is a local Codex plugin that standardizes conversion of CATIA `.CATPart` files into formats Codex can inspect more easily, then extracts engineering-facing summaries from supported outputs.

The plugin itself does not reverse-engineer CATPart directly. Instead, it wraps a locally installed converter backend and gives you one stable CLI:

- Recommended readable output: `STEP` (`.step` / `.stp`)
- Mesh outputs: `OBJ`, `STL`, `GLTF`, `GLB`
- Exchange outputs: `IGES`, `BREP`, `X_T`, `X_B`

After conversion, the script now inspects supported outputs automatically:

- `STEP`: product names, schema, unit, topology counts, inferred bounding box
- `OBJ`: vertex count, face count, object/material names, exact bounding box
- `STL`: triangle count, encoding type, exact bounding box

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
- For multi-file use, pass multiple input files and an `--output-dir`.
- The plugin still does not natively decode proprietary `CATPart` internals; engineering data is derived from the converted exchange file.
- For `STEP`, the bounding box is inferred from `CARTESIAN_POINT` records, so it is useful but should not be treated as a certified metrology result.
