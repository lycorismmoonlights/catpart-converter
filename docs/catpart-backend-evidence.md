# CATPart Backend Evidence Matrix

This document tracks local CATPart conversion and measurement routes checked for the plugin. It focuses on two target outcomes:

- Convert native `.CATPart` / `.CATProduct` to STEP locally.
- Read exact mass/volume directly from native CATPart, or from a precise B-Rep exchange export.

## Current Machine Status

As of 2026-05-30, `scripts/convert_catpart.py --probe` reports no installed CATPart-capable backend on this Mac.

Available:

- FreeCAD via `/opt/anaconda3/envs/catpart-geo/bin/freecadcmd`
- Exact analysis for existing STEP, BREP, and IGES files
- Local conversion among existing STEP, BREP, IGES, STL, and OBJ exchange files

Missing:

- CATIA V5 `catstart`
- CAD Exchanger Batch / `ExchangerConv`
- CAD Exchanger Python SDK package/license
- Datakit CrossManager CLI
- HOOPS Exchange `ImportExport`
- 3D-Tool `Convert.exe`
- TransMagic COMMAND / `TMCmd`
- CoreTechnologie 3D_Evolution / 3D_Kernel_IO wrapper
- Autodesk Fusion app
- CADfix / SpinFire Convert executables

## Adopted Backend Profiles

| Backend | Local STEP path | Exact native mass/volume path | Platform notes | Plugin status |
| --- | --- | --- | --- | --- |
| CATIA V5 batch | Yes, through CATIA `ExportData` | Yes, through CATIA `Product.Analyze` | Requires CATIA V5 and licenses | Implemented as `--backend catia` |
| CAD Exchanger Batch | Yes, through `ExchangerConv -i input -e output` CLI | No native mass path exposed here; analyze exported STEP/BREP/IGES | Commercial, macOS/Windows/Linux product family; FreeCAD add-on docs confirm 30-day evaluation and `ExchangerConv` on Linux/macOS, `ExchangerConv.exe` on Windows | Implemented as `--backend cadexchanger` / built-in template |
| CAD Exchanger Python SDK | Yes, through SDK `ModelData_ModelReader` to `ModelData_ModelWriter` conversion | SDK product pages advertise analysis/measurement APIs including volumes, surface areas, centroids, and bounding boxes; this plugin currently uses the SDK for conversion and then FreeCAD for exact STEP/BREP/IGES metrics | Commercial SDK; examples require CAD Exchanger SDK package, evaluation/commercial license, and CPython 3.7-3.11 on macOS Apple Silicon | Implemented as `--backend cadexsdk` |
| Datakit CrossManager CLI | Yes, if licensed and command template is supplied | No native mass path exposed here; analyze exported STEP/BREP/IGES | Commercial; 2026 product note says no-GUI CLI runs on Windows, Linux, and macOS; public pages do not expose stable CLI syntax | Implemented as `--backend datakit` |
| HOOPS Exchange ImportExport | Yes, if SDK sample is built and licensed | SDK can expose B-Rep/metadata; exact mass extraction would need a dedicated SDK wrapper | Commercial SDK; macOS sample path documented | Implemented as `--backend hoops` |
| 3D-Tool NativeCAD Converter | Yes, through `Convert.exe -i ... -o ...` | No native mass path exposed here; analyze exported STEP/BREP/IGES | Windows-only commercial tool | Implemented as `--backend 3dtool` |
| TransMagic COMMAND | Yes, through `TMCmd` and output flags such as `-ofstp` | Yes, through generated XML mass reports when `-xmlasm -xmlmass -xmlbbox -xmlsurf` are available | Commercial Windows executable command interface | Implemented as `--backend transmagic` |
| CoreTechnologie 3D_Evolution / 3D_Kernel_IO | Yes, if licensed and command template or wrapper is supplied | No stable public mass-report CLI exposed here; analyze exported STEP/BREP/IGES or parse configured vendor reports | Commercial; 3D_Evolution supports automation/batch/script workflows; 3D_Kernel_IO API is documented as available on Windows, Linux, and Mac | Implemented as `--backend coretechnologie` with required template |

## Additional Candidates Checked

| Candidate | Evidence | Verdict |
| --- | --- | --- |
| Autodesk Fusion | Official Autodesk docs list CATIA V5 `.CATPart/.CATProduct` import and STEP export. Homebrew has `autodesk-fusion` cask. The public `ImportManager` API lists STEP, IGES, SAT, SMT, Fusion archive, SVG, and DXF import option constructors, but not a CATIA/CATPart import option. | Plausible manual GUI route, but not a quiet local CLI/API backend for CATPart based on public API docs. Requires app install, Autodesk login/licensing, and likely manual upload/open/export flow. Not auto-installed. |
| Open Cascade CAD Assistant | Official page lists STEP, IFC, IGES, BREP, glTF, JT, PLY, STL, OBJ, 3DM, DXF, SAT, XT, etc. CATPart is not listed. | Not suitable for native CATPart import. Useful only after conversion to open exchange formats. |
| FreeCAD / OCCT | Local FreeCAD is installed and exact analysis works for STEP/BREP/IGES. OCCT/CAD Assistant docs cover open/neutral formats, not CATPart. | Not a CATPart importer. Keep as post-conversion exact geometry backend. |
| SimLab CADVRter | Vendor page says Windows/macOS, 100% local, CLI, CATIA V5 import. Export list is VR/mesh-oriented: PDF, 3DS, 3MF, DAE, CTM, DWG/DXF, FBX, glTF/GLB, OSG, SKP, STL, USDZ, U3D, OBJ. | Useful for local visualization/mesh outputs, but not a direct STEP or exact mass/volume path. Not adopted for this plugin's STEP target. |
| CADfix | CAD Interop page lists CATIA V5 import and STEP export; matrix notes Windows-only for CADfix 13 SP2 DX/CAE. | Viable commercial Windows backend, not currently useful on this Mac. |
| Spatial 3D InterOp SDK | Official Spatial material says it reads/writes CATPart/CATProduct and STEP, imports exact B-Rep geometry and metadata, and provides C++/C# samples plus 3DScript for prototyping. | Strong SDK route, but no installed SDK or stable local CLI was found here. Not implemented until an SDK wrapper or callable script is available. |
| NVIDIA Omniverse CAD Converter | Docs list CATIA V5 files and local/batch CAD converter service, but target is USD. | Useful for USD ingestion, not direct STEP or exact mass/volume. Not adopted for this plugin's STEP target. |
| ODA MCAD SDK | Official ODA page advertises native MCAD access, exact B-Rep, Common API to STEP, and macOS support. However, the same page states the free trial currently supports SolidWorks and Inventor only; CATIA `.CATPart` geometry is scheduled for beta in July 2026 and full release later. | Promising future SDK route, but not a usable CATPart backend on this machine as of 2026-05-30. Not adopted yet. |
| SpinFire Convert / Theorem | Vendor pages describe CATIA V5 independent and batch translation solutions. | Viable commercial backend class, but no installed executable or public command template found locally. Can be configured via `--backend custom`. |

## Practical Next Steps

1. If a licensed backend is available, set the corresponding environment variable and re-run:

```bash
python3 scripts/convert_catpart.py --probe
```

2. For exact mass/volume from native CATPart, prefer CATIA V5 batch because the plugin already extracts CATIA `Product.Analyze` values.

3. For exact mass/volume through exchange, use any successful CATPart-to-STEP/BREP/IGES backend followed by the plugin's FreeCAD analysis.

4. Avoid treating CAD Assistant, FreeCAD, or generic OCCT as native CATPart readers. They remain valuable after conversion, not before.

5. Treat Autodesk Fusion as a manual GUI route unless a custom Fusion add-in is available. The plugin's `--probe` reports it separately from automatic CATPart backends.

## Sources

- CAD Assistant: https://www.opencascade.com/products/cad-assistant/
- CAD Exchanger formats: https://cadexchanger.com/formats/
- CAD Exchanger SDK product page: https://cadexchanger.com/products/sdk/
- CAD Exchanger Python SDK examples: https://github.com/cadexchanger/cadexchanger-sdk-python-examples
- CAD Exchanger Python SDK transfer example: https://github.com/cadexchanger/cadexchanger-sdk-python-examples/blob/main/conversion/transfer/transfer.py
- CAD Exchanger FreeCAD add-on evidence: https://github.com/yorikvanhavre/CADExchanger
- CAD Exchanger CLI command example: https://www.skypack.dev/view/cadex
- CADfix: https://www.cadinterop.com/en/our-products/cadfix.html
- Autodesk Fusion file formats: https://www.autodesk.com/support/technical/article/caas/sfdcarticles/sfdcarticles/File-formats-supported-by-Fusion-360.html
- Autodesk Fusion export formats: https://www.autodesk.com/support/technical/article/caas/sfdcarticles/sfdcarticles/Export-format-options-for-Fusion-360.html
- Autodesk Fusion `ImportManager` API: https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/ImportManager.htm
- Datakit CrossManager CLI: https://www.datakit.com/en/news/product-focus-crossmanager-cli-241.html
- Datakit CrossManager formats/licensing: https://www.datakit.com.cn/crossmanager.html
- CoreTechnologie 3D_Evolution: https://coretechnologie.com/products/3d-evolution/
- CoreTechnologie Enterprise Data Manager: https://coretechnologie.com/products/3d-evolution/enterprise-data-manager/
- CoreTechnologie 3D_Kernel_IO: https://www.coretechnologie.com/fileadmin/user_upload/3D_Kernel_IO_Brochure__EN.pdf
- Spatial 3D InterOp: https://www.spatial.com/products/BIM-Interop
- SimLab CADVRter: https://www.cadinterop.com/en/our-products/simlab/simlab-cadvrter.html
- TransMagic converter: https://transmagic.com/cad-file-converter/
- TransMagic COMMAND: https://support.transmagic.com/hc/en-us/articles/201894039-What-is-TM-Command
- TransMagic COMMAND user guide PDF: https://www.transmagic.com/downloads/transmagic-command.pdf
- HOOPS Exchange ImportExport setup: https://docs.techsoft3d.com/exchange/2024.8.0/tutorials/environment-setup.html
- NVIDIA Omniverse CAD Converter service: https://docs.omniverse.nvidia.com/kit/docs/omni.services.convert.cad/503.2.5/Overview.html
- ODA MCAD SDK: https://www.opendesign.com/products/mcad-sdk
- SpinFire Convert / Theorem CATIA V5: https://www.techsoft3d.com/enterprise/spinfire-convert/cad-data-translation/catia-v5/
