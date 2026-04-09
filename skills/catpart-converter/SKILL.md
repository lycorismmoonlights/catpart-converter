---
name: catpart-converter
description: Convert CATIA CATPart files into readable exchange formats such as STEP, OBJ, and STL by calling the local workspace conversion script, then extract engineering summaries from supported outputs. Use when the user asks to inspect, convert, or ingest CATPart files.
---

# CATPart Converter

## When to use

Use this skill when the user wants to:

- convert a `.CATPart` file into a format Codex can inspect
- inspect CATIA part geometry through a readable exchange format
- batch-convert CATPart files into `STEP`, `OBJ`, `STL`, `IGES`, or `BREP`
- extract engineering summaries after conversion
- re-analyze an existing `STEP`, `OBJ`, or `STL` file without converting again

## Default workflow

1. Prefer `STEP` unless the user asks for another format.
2. Run the local converter script:

```bash
python3 plugins/catpart-converter/scripts/convert_catpart.py "<input.CATPart>" --format step
```

3. If the conversion succeeds, read the terminal summary or JSON report first.
4. For `STEP`, prefer the generated engineering summary for names, units, and topology counts, then open the `.step` file when deeper inspection is needed.
5. If the backend is missing, explain that the plugin is installed but still needs an external CATIA-capable converter backend.

## Backend setup

The script will auto-detect a backend in this order:

1. `CATPART_CONVERTER_TEMPLATE`
2. `CATPART_CONVERTER_BIN`
3. common `CAD Exchanger` executable names and paths

You can probe the environment with:

```bash
python3 plugins/catpart-converter/scripts/convert_catpart.py --probe
```

## Output guidance

- Use `STEP` for downstream analysis in Codex.
- Use `OBJ` or `STL` when the user specifically wants mesh output.
- Write a JSON report with `--report <path>` when you need a durable conversion log.
- `STEP` summaries are the best option for engineering metadata. Mesh summaries are useful for geometry size and complexity, but not for B-Rep semantics.
- Use `--analysis-only` when the user already has a converted `STEP`, `OBJ`, or `STL`.
- Use `--assume-unit mm` or `--assume-unit m` for mesh files when unit labeling matters.

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
