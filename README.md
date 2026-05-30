# CATPart Converter

`CATPart Converter` is a local Codex plugin that standardizes conversion of CATIA `.CATPart` files into formats Codex can inspect more easily, then extracts engineering-facing summaries from supported outputs.

The plugin itself does not reverse-engineer CATPart directly. Instead, it wraps a locally installed converter backend and gives you one stable CLI:

- Recommended readable output: `STEP` (`.step` / `.stp`)
- Native CATIA path: if CATIA V5 `catstart` is installed, `--backend catia` can run a generated CATScript to export `.CATPart` and collect native `Product.Analyze` mass properties
- pycatia path: on Windows CATIA workstations with `pycatia` installed, `--backend pycatia` can automate CATIA V5 through COM, export STEP/IGES/STL, and collect native `Product.Analyze` mass properties
- CAD Exchanger SDK path: if the CAD Exchanger Python SDK package and license are configured, `--backend cadexsdk` can run the SDK `ModelReader -> ModelWriter` flow for CATIA V5 to STEP and other exchange outputs
- Datakit path: if Datakit CrossManager CLI is installed and its command template is provided, `--backend datakit` can be used for CATIA V5 to STEP conversion
- HOOPS path: if the HOOPS Exchange SDK `ImportExport` sample is built and licensed, `--backend hoops` can use its `ImportExport input output` command shape for CATIA V5 file-to-file conversion
- 3D-Tool path: on Windows with 3D-Tool NativeCAD Converter installed, `--backend 3dtool` uses the documented `Convert.exe -i ... -o ...` batch interface
- TransMagic path: on Windows with TransMagic COMMAND installed, `--backend transmagic` uses the documented `TMCmd` flow for CATIA V5 to STEP and can parse generated XML mass/bounding/surface reports
- CoreTechnologie path: if 3D_Evolution, Enterprise Data Manager, or a 3D_Kernel_IO wrapper is installed, `--backend coretechnologie` can use a configured command template for CATIA/STEP conversion
- Local `STEP` conversion: existing `.step` / `.stp` files can be converted with `FreeCAD` without a CATPart-specific backend
- Mesh outputs: `OBJ`, `STL`, `GLTF`, `GLB`
- Exchange outputs: `IGES`, `BREP` / `BRP`, `PRC`, `SAT`, `X_T`, `X_B`

After conversion, the script now inspects supported outputs automatically:

- `STEP`: product names, schema, unit, topology counts, and when `FreeCAD` is available, exact B-Rep volume, area, center of gravity, and bounding box
- `BREP`: when `FreeCAD` is available, exact B-Rep volume, area, center of gravity, topology counts, and bounding box
- `IGES`: when `FreeCAD` is available, exact imported geometry volume, area, center of gravity, topology counts, and bounding box
- `OBJ`: vertex count, polygon face count, triangle count, area, watertight volume, centroids, object/material names, exact bounding box
- `STL`: triangle count, encoding type, area, watertight volume, centroids, exact bounding box

Exact `FreeCAD` reports also include per-solid details, shell counts, static moments, inertia matrices, and principal inertia properties when the imported shape exposes them.

When the CATIA V5 batch backend is available, conversion reports can also include `native_catia_analysis` from CATIA's own `Product.Analyze` object: mass, volume, wet area, gravity center, and inertia matrix. This requires CATIA to open the source file in design mode and have the relevant export/analysis licenses.

When the pycatia backend is available, conversion reports can include `native_pycatia_analysis` from the same CATIA `Product.Analyze` object, but accessed through Python COM automation instead of a generated CATScript.

When the TransMagic COMMAND backend is available, conversion reports can include `native_transmagic_analysis` parsed from TransMagic XML output options such as mass properties, bounding box, and surface area.

`STEP` text analysis also scans parameter values broadly. It reports counts and ranges for integers, real numbers, scientific notation, signed values, logical values (`.T.`, `.F.`, `.U.`), enumerations, entity references, strings, omitted values (`$`), and derived values (`*`).

## Why `STEP`

`STEP` is the default recommendation because it is a text-based CAD exchange format. After conversion, Codex can open the `.step` file directly and continue inspecting or transforming it.

## Files

- `scripts/convert_catpart.py`: conversion entry point
- `skills/catpart-converter/SKILL.md`: Codex usage instructions
- `docs/catpart-backend-evidence.md`: checked backend evidence, platform notes, and why some near-miss tools are not enough for native CATPart
- `.codex-plugin/plugin.json`: plugin manifest

## Quick Start

Probe whether a backend is configured:

```bash
python3 scripts/convert_catpart.py --probe
```

If `freecadcmd` is available locally, `--probe` will also report that exact `STEP`, `BREP`, and `IGES` geometry analysis is enabled.

When no CATPart-capable converter is configured, `--probe` and failed conversion reports include a `diagnostics` object. That object separates the missing native CATPart import capability from the local FreeCAD capabilities that are still available for existing `STEP`, `BREP`, `IGES`, `OBJ`, and `STL` files, and it lists the environment variables needed to attach an external backend.

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

Convert an existing STEP file locally with FreeCAD:

```bash
python3 scripts/convert_catpart.py \
  /path/to/model.step \
  --source-format step \
  --format brep \
  --output /path/to/model.brep \
  --report /path/to/model.step-conversion.json
```

When `--backend auto` is used, `.step`, `.stp`, `.brep`, `.iges`, and `.igs` inputs automatically use the local FreeCAD conversion path for supported targets: `STEP`, `BREP`, `IGES`, `STL`, and `OBJ`.

Use CATIA V5 batch mode when `catstart` is available:

```bash
export CATPART_CATIA_CATSTART_BIN="/path/to/DassaultSystemes/Bxx/code/command/catstart"
python3 scripts/convert_catpart.py \
  /path/to/part.CATPart \
  --backend catia \
  --format step \
  --report /path/to/part.catia-conversion.json
```

Optional CATIA environment settings:

```bash
export CATPART_CATIA_ENV="CATIA.V5Rxx"
export CATPART_CATIA_DIRENV="/path/to/CATEnv"
```

Use pycatia on a Windows CATIA V5 workstation:

```bash
set CATPART_PYCATIA_PYTHON=C:\Python311\python.exe
python scripts\convert_catpart.py C:\path\part.CATPart --backend pycatia --format step
```

This path uses CATIA V5's COM automation through pycatia. It still requires CATIA to be installed and licensed locally, but it avoids needing to locate `catstart`.

Use CAD Exchanger Python SDK when licensed and installed:

```bash
export CATPART_CADEX_SDK_PYTHON="/path/to/python3.11"
export CATPART_CADEX_LICENSE_FILE="/path/to/cadex_license.py"
python3 scripts/convert_catpart.py /path/to/part.CATPart --backend cadexsdk --format step
```

The CAD Exchanger SDK examples show a Python `ModelData_ModelReader` to `ModelData_ModelWriter` conversion flow. The SDK package and `cadex_license.py` license file are distributed through CAD Exchanger evaluation or Customer Corner, not public PyPI. You can set `CATPART_CADEX_LICENSE` directly instead of `CATPART_CADEX_LICENSE_FILE` if you need a secret-manager style setup.

Use Datakit CrossManager CLI when licensed and installed:

```bash
export CATPART_DATKIT_BIN="/absolute/path/to/CrossManagerCLI"
export CATPART_DATKIT_TEMPLATE='"{executable}" --input "{input}" --output "{output}"'
python3 scripts/convert_catpart.py /path/to/part.CATPart --backend datakit --format step
```

Datakit's public pages confirm CATIA V5 input and multiple exchange outputs including STEP, but do not publish a stable command syntax in the pages available here, so this plugin requires `CATPART_DATKIT_TEMPLATE` instead of guessing.

Use HOOPS Exchange when the SDK is licensed and the `ImportExport` sample is built:

```bash
export CATPART_HOOPS_IMPORTEXPORT_BIN="/path/to/HOOPS_Exchange/samples/exchange/exchangesource/ImportExport/ImportExport"
python3 scripts/convert_catpart.py /path/to/part.CATPart --backend hoops --format step
```

Tech Soft 3D's public documentation shows the macOS `ImportExport` sample running from Terminal and converting CATIA V5 files by passing an input path and output path. This plugin uses that documented command shape by default; set `CATPART_HOOPS_TEMPLATE` if your built sample wrapper needs different arguments.

Use 3D-Tool NativeCAD Converter on Windows:

```bash
set CATPART_THREEDTOOL_BIN=C:\Program Files\3D-Tool V17\Convert.exe
python scripts\convert_catpart.py C:\path\part.CATPart --backend 3dtool --format step
```

Use TransMagic COMMAND on Windows:

```bash
set CATPART_TRANSMAGIC_BIN=C:\Program Files\TransMagic Inc\TransMagic RXX\System\code\bin\TMCmd.exe
python scripts\convert_catpart.py C:\path\part.CATPart --backend transmagic --format step
```

The built-in TransMagic template uses `-ofstp` for STEP and also requests XML assembly, mass, bounding-box, and surface-area reports. If your installation uses a different command shape, set `CATPART_TRANSMAGIC_TEMPLATE`.

Use CoreTechnologie 3D_Evolution or a 3D_Kernel_IO wrapper when licensed and installed:

```bash
export CATPART_CORETECHNOLOGIE_BIN="/absolute/path/to/3D_Evolution"
export CATPART_CORETECHNOLOGIE_TEMPLATE='"{executable}" --input "{input}" --output "{output}"'
python3 scripts/convert_catpart.py /path/to/part.CATPart --backend coretechnologie --format step
```

CoreTechnologie public material confirms CATIA and STEP support plus automation/batch/script workflows, but does not publish one stable command syntax in the pages available here, so this plugin requires `CATPART_CORETECHNOLOGIE_TEMPLATE` instead of guessing.

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

The script supports these backend modes:

1. `--backend auto`
   Looks for a configured template first, then tries configured native CATPart-capable backends and common executable names.

2. `--backend cadexchanger`
   Uses the built-in preset command shape:

```text
{executable} -i {input} -e {output}
```

3. `--backend cadexsdk`
   Uses `scripts/cadex_sdk_transfer.py` with the CAD Exchanger Python SDK package and license.

4. `--backend catia`
   Uses CATIA V5 batch automation through `catstart`.

5. `--backend pycatia`
   Uses `scripts/pycatia_convert.py` with pycatia and CATIA V5 COM automation.

6. `--backend datakit`
   Uses Datakit CrossManager CLI with a configured command template.

7. `--backend hoops`
   Uses the HOOPS Exchange `ImportExport` sample command shape.

8. `--backend 3dtool`
   Uses 3D-Tool NativeCAD Converter on Windows.

9. `--backend transmagic`
   Uses TransMagic COMMAND / `TMCmd` on Windows and parses generated XML mass-property reports when present.

10. `--backend coretechnologie`
   Uses CoreTechnologie 3D_Evolution, Enterprise Data Manager, or a 3D_Kernel_IO wrapper with a configured command template.

11. `--backend custom`
   Uses your exact command template.

You can configure the backend with environment variables:

- `CATPART_CONVERTER_BIN`
  Absolute path to the converter executable.

- `CATPART_CONVERTER_TEMPLATE`
  A full command template with placeholders such as `{input}` and `{output}`.

- `CATPART_FREECAD_CMD`
  Optional absolute path to `freecadcmd` or `FreeCADCmd` for exact `STEP` geometry analysis.

- `CATPART_CATIA_CATSTART_BIN`
  Optional absolute path to CATIA V5 `catstart`. Enables `--backend catia` for native CATPart opening, STEP/IGES/STL export, and CATIA `Product.Analyze` mass-property extraction.

- `CATPART_CATIA_ENV`
  Optional CATIA environment name passed to `catstart -env`.

- `CATPART_CATIA_DIRENV`
  Optional CATIA environment directory passed to `catstart -direnv`.

- `CATPART_CATIA_TIMEOUT_SECONDS`
  Optional timeout for CATIA batch conversion. Defaults to `300` seconds.

- `CATPART_PYCATIA_PYTHON`
  Optional Python executable where `pycatia` is installed. Enables `--backend pycatia` on Windows CATIA V5 workstations.

- `CATPART_CADEX_SDK_PYTHON`
  Optional Python executable where the CAD Exchanger SDK `cadexchanger` package is installed. Enables `--backend cadexsdk` when a license is also configured.

- `CATPART_CADEX_LICENSE`
  Optional CAD Exchanger SDK license key string for `--backend cadexsdk`.

- `CATPART_CADEX_LICENSE_FILE`
  Optional path to a CAD Exchanger SDK license text file or `cadex_license.py` file.

- `CATPART_DATKIT_BIN`
  Optional absolute path to Datakit CrossManager CLI.

- `CATPART_DATKIT_TEMPLATE`
  Required command template for `--backend datakit`, because public Datakit pages confirm CrossManager CLI capability but do not expose stable syntax.

- `CATPART_HOOPS_IMPORTEXPORT_BIN`
  Optional absolute path to the built HOOPS Exchange `ImportExport` sample. Enables `--backend hoops`.

- `CATPART_HOOPS_TEMPLATE`
  Optional command template for HOOPS Exchange. Defaults to `"{executable}" "{input}" "{output}"`.

- `CATPART_THREEDTOOL_BIN`
  Optional absolute path to 3D-Tool `Convert.exe`. Enables `--backend 3dtool` with the documented `"{executable}" -i "{input}" -o "{output}"` command shape.

- `CATPART_TRANSMAGIC_BIN`
  Optional absolute path to TransMagic COMMAND `TMCmd.exe`. Enables `--backend transmagic`.

- `CATPART_TRANSMAGIC_TEMPLATE`
  Optional command template for TransMagic. Defaults to `"{executable}" -od"{output_dir}" -otd "{input}" -of{transmagic_format} -xmlasm -xmlbbox -xmlmass -xmlsurf`.

- `CATPART_CORETECHNOLOGIE_BIN`
  Optional absolute path to CoreTechnologie 3D_Evolution, Enterprise Data Manager, or a 3D_Kernel_IO wrapper.

- `CATPART_CORETECHNOLOGIE_TEMPLATE`
  Required command template for `--backend coretechnologie`, because public CoreTechnologie pages confirm automation capability but do not expose stable syntax.

- `CATPART_FREECAD_TIMEOUT_SECONDS`
  Optional timeout for `FreeCAD` exact geometry analysis. Defaults to `45` seconds.

- `CATPART_DETAIL_LIMIT`
  Optional maximum number of solids and shells included in detailed exact-geometry output. Defaults to `100`.

- `CATPART_MESH_LINEAR_DEFLECTION`
  Optional linear deflection for local FreeCAD mesh exports such as `OBJ`. Defaults to `0.1`.

- `CATPART_MESH_ANGULAR_DEFLECTION`
  Optional angular deflection for local FreeCAD mesh exports such as `OBJ`. Defaults to `0.5`.

Example:

```bash
export CATPART_CONVERTER_BIN="/Applications/CAD Exchanger.app/Contents/MacOS/ExchangerConv"
export CATPART_CONVERTER_TEMPLATE='"{executable}" -i "{input}" -e "{output}"'
```

Then run:

```bash
python3 scripts/convert_catpart.py /path/to/part.CATPart
```

## Notes

- Add this folder to your Codex local plugin path or marketplace as needed.
- If no backend is installed, the script exits with a clear setup message instead of failing silently.
- Missing CATPart backends are reported with structured diagnostics, including current FreeCAD capabilities, supported local exchange formats, example external backends, and `CATPART_CONVERTER_BIN` / `CATPART_CONVERTER_TEMPLATE` setup hints.
- `--backend catia` uses CATIA V5 batch automation through `catstart -run "CNEXT -batch -macro ..."`. It is the preferred path for native CATPart mass/volume when CATIA and the needed licenses are installed locally.
- `--backend pycatia` uses CATIA V5 COM automation through Python. It is useful when CATIA is installed on Windows and pycatia is easier to configure than a `catstart` batch environment.
- `--backend cadexsdk` uses CAD Exchanger's Python SDK conversion API when the private SDK package and license are configured. It is a direct SDK route rather than the `ExchangerConv` batch executable.
- `--backend datakit`, `--backend hoops`, `--backend 3dtool`, `--backend transmagic`, and `--backend coretechnologie` cover additional real-world CATPart converters discovered from vendor documentation. `--probe` reports their environment variables and whether they are detected.
- `--backend transmagic` can add `native_transmagic_analysis` from generated XML mass, bounding-box, and surface-area reports when TransMagic COMMAND creates them.
- `--probe` also separates manual GUI routes such as Autodesk Fusion from automatic backends, so Fusion can be tracked without being misreported as a headless converter.
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
