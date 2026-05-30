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
- Datakit CrossManager CLI
- HOOPS Exchange `ImportExport`
- 3D-Tool `Convert.exe`
- Autodesk Fusion app
- TransMagic / CADfix / SpinFire Convert executables

## Adopted Backend Profiles

| Backend | Local STEP path | Exact native mass/volume path | Platform notes | Plugin status |
| --- | --- | --- | --- | --- |
| CATIA V5 batch | Yes, through CATIA `ExportData` | Yes, through CATIA `Product.Analyze` | Requires CATIA V5 and licenses | Implemented as `--backend catia` |
| CAD Exchanger Batch | Yes, through `ExchangerConv`-style CLI | No native mass path exposed here; analyze exported STEP/BREP/IGES | Commercial, macOS/Windows/Linux product family | Implemented as `--backend cadexchanger` / generic template |
| Datakit CrossManager CLI | Yes, if licensed and command template is supplied | No native mass path exposed here; analyze exported STEP/BREP/IGES | Commercial; public pages do not expose stable CLI syntax | Implemented as `--backend datakit` |
| HOOPS Exchange ImportExport | Yes, if SDK sample is built and licensed | SDK can expose B-Rep/metadata; exact mass extraction would need a dedicated SDK wrapper | Commercial SDK; macOS sample path documented | Implemented as `--backend hoops` |
| 3D-Tool NativeCAD Converter | Yes, through `Convert.exe -i ... -o ...` | No native mass path exposed here; analyze exported STEP/BREP/IGES | Windows-only commercial tool | Implemented as `--backend 3dtool` |

## Additional Candidates Checked

| Candidate | Evidence | Verdict |
| --- | --- | --- |
| Autodesk Fusion | Official Autodesk docs list CATIA V5 `.CATPart/.CATProduct` import and STEP export. Homebrew has `autodesk-fusion` cask. | Plausible GUI/API route, but not a quiet local CLI backend. Requires app install, Autodesk login/licensing, and likely Fusion API scripting. Not auto-installed. |
| Open Cascade CAD Assistant | Official page lists STEP, IFC, IGES, BREP, glTF, JT, PLY, STL, OBJ, 3DM, DXF, SAT, XT, etc. CATPart is not listed. | Not suitable for native CATPart import. Useful only after conversion to open exchange formats. |
| FreeCAD / OCCT | Local FreeCAD is installed and exact analysis works for STEP/BREP/IGES. OCCT/CAD Assistant docs cover open/neutral formats, not CATPart. | Not a CATPart importer. Keep as post-conversion exact geometry backend. |
| SimLab CADVRter | Vendor page says Windows/macOS, 100% local, CLI, CATIA V5 import. Export list is VR/mesh-oriented: PDF, 3DS, 3MF, DAE, CTM, DWG/DXF, FBX, glTF/GLB, OSG, SKP, STL, USDZ, U3D, OBJ. | Useful for local visualization/mesh outputs, but not a direct STEP or exact mass/volume path. Not adopted for this plugin's STEP target. |
| TransMagic COMMAND | Vendor pages list CATIA V5 read and STEP write; COMMAND is a Windows executable command interface. | Viable commercial Windows backend, but no macOS executable found here. Can be used through `--backend custom` if installed elsewhere. |
| CADfix | CAD Interop page lists CATIA V5 import and STEP export; matrix notes Windows-only for CADfix 13 SP2 DX/CAE. | Viable commercial Windows backend, not currently useful on this Mac. |
| NVIDIA Omniverse CAD Converter | Docs list CATIA V5 files and local/batch CAD converter service, but target is USD. | Useful for USD ingestion, not direct STEP or exact mass/volume. Not adopted for this plugin's STEP target. |
| SpinFire Convert / Theorem | Vendor pages describe CATIA V5 independent and batch translation solutions. | Viable commercial backend class, but no installed executable or public command template found locally. Can be configured via `--backend custom`. |

## Practical Next Steps

1. If a licensed backend is available, set the corresponding environment variable and re-run:

```bash
python3 scripts/convert_catpart.py --probe
```

2. For exact mass/volume from native CATPart, prefer CATIA V5 batch because the plugin already extracts CATIA `Product.Analyze` values.

3. For exact mass/volume through exchange, use any successful CATPart-to-STEP/BREP/IGES backend followed by the plugin's FreeCAD analysis.

4. Avoid treating CAD Assistant, FreeCAD, or generic OCCT as native CATPart readers. They remain valuable after conversion, not before.

## Sources

- CAD Assistant: https://www.opencascade.com/products/cad-assistant/
- CADfix: https://www.cadinterop.com/en/our-products/cadfix.html
- Autodesk Fusion file formats: https://www.autodesk.com/support/technical/article/caas/sfdcarticles/sfdcarticles/File-formats-supported-by-Fusion-360.html
- Autodesk Fusion export formats: https://www.autodesk.com/support/technical/article/caas/sfdcarticles/sfdcarticles/Export-format-options-for-Fusion-360.html
- SimLab CADVRter: https://www.cadinterop.com/en/our-products/simlab/simlab-cadvrter.html
- TransMagic converter: https://transmagic.com/cad-file-converter/
- TransMagic COMMAND: https://support.transmagic.com/hc/en-us/articles/201894039-What-is-TM-Command
- HOOPS Exchange ImportExport setup: https://docs.techsoft3d.com/exchange/2024.8.0/tutorials/environment-setup.html
- NVIDIA Omniverse CAD Converter service: https://docs.omniverse.nvidia.com/kit/docs/omni.services.convert.cad/503.2.5/Overview.html
- SpinFire Convert / Theorem CATIA V5: https://www.techsoft3d.com/enterprise/spinfire-convert/cad-data-translation/catia-v5/
