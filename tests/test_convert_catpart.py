from __future__ import annotations

import argparse
import importlib.util
import math
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "scripts" / "convert_catpart.py"

spec = importlib.util.spec_from_file_location("catpart_converter", MODULE_PATH)
convert_catpart = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = convert_catpart
spec.loader.exec_module(convert_catpart)


class ConvertCatpartTests(unittest.TestCase):
    def export_box_with_freecad(self, temp_path: Path, output_name: str, export_lines: list[str]) -> Path:
        discovered = convert_catpart.discover_freecad_executable()
        if discovered is None:
            self.skipTest("FreeCAD exact geometry backend is not available")

        freecad_cmd, _ = discovered
        output_path = temp_path / output_name
        script_path = temp_path / "make_box.py"
        script_path.write_text(
            "\n".join(
                [
                    "import os",
                    "import FreeCAD as App",
                    "import Part",
                    "",
                    f"output_path = os.path.join(os.path.dirname(__file__), '{output_name}')",
                    "doc = App.newDocument('MakeBox')",
                    "box = doc.addObject('Part::Box', 'Box')",
                    "box.Length = 10",
                    "box.Width = 20",
                    "box.Height = 30",
                    "doc.recompute()",
                    *export_lines,
                ]
            ),
            encoding="utf-8",
        )
        subprocess.run(
            [freecad_cmd, str(script_path)],
            check=True,
            capture_output=True,
            text=True,
        )
        return output_path

    def test_classify_length_unit_normalizes_conversion_based_inches(self) -> None:
        step_text = "CONVERSION_BASED_UNIT('INCH',#42);"
        self.assertEqual(convert_catpart.classify_length_unit(step_text), "inch")

    def test_step_bbox_in_mm_preserves_inferred_flag(self) -> None:
        bbox = {
            "min": [0.0, 0.0, 0.0],
            "max": [1.0, 2.0, 3.0],
            "size": [1.0, 2.0, 3.0],
            "diagonal": round(math.sqrt(14.0), 6),
            "unit": "inch",
            "inferred": True,
        }
        scaled = convert_catpart.step_bbox_in_mm(bbox, "inch")
        assert scaled is not None
        self.assertEqual(scaled["unit"], "mm")
        self.assertTrue(scaled["inferred"])
        self.assertEqual(scaled["size"], [25.4, 50.8, 76.2])

    def test_summarize_step_values_covers_common_value_types(self) -> None:
        text = (
            "#1=EXAMPLE(42,-7,3.5,.25,1.E-3,.T.,.F.,.U.,.ENUM.,$,*,'a''b',#2);"
        )

        summary = convert_catpart.summarize_step_values(text)
        counts = summary["value_type_counts"]
        numeric = summary["numeric"]

        self.assertEqual(numeric["integer_count"], 2)
        self.assertEqual(numeric["real_count"], 3)
        self.assertEqual(numeric["exponential_count"], 1)
        self.assertEqual(numeric["min"], -7.0)
        self.assertEqual(numeric["max"], 42.0)
        self.assertEqual(counts["logical_true"], 1)
        self.assertEqual(counts["logical_false"], 1)
        self.assertEqual(counts["logical_unknown"], 1)
        self.assertEqual(counts["enumeration"], 1)
        self.assertEqual(counts["omitted"], 1)
        self.assertEqual(counts["derived"], 1)
        self.assertEqual(counts["string"], 1)
        self.assertEqual(counts["entity_reference"], 2)

    def test_summarize_step_values_ignores_numbers_inside_comments(self) -> None:
        text = "/* bogus 9999 -7 3.14 .T. #42 */ #1=EXAMPLE(2);"

        summary = convert_catpart.summarize_step_values(text)

        self.assertEqual(summary["value_type_counts"]["comment"], 1)
        self.assertEqual(summary["numeric"]["total_count"], 1)
        self.assertEqual(summary["numeric"]["min"], 2.0)
        self.assertEqual(summary["numeric"]["max"], 2.0)

    def test_probe_includes_catpart_backend_diagnostics_when_missing(self) -> None:
        args = argparse.Namespace(
            backend="auto",
            backend_executable=None,
            backend_cmd=None,
        )

        payload = convert_catpart.probe_environment(args)
        conversion_backend = payload["conversion_backend"]
        if conversion_backend["available"]:
            self.skipTest("A CATPart conversion backend is configured on this machine")

        diagnostics = conversion_backend["diagnostics"]

        self.assertEqual(diagnostics["missing_capability"], "CATPart import/conversion")
        self.assertFalse(diagnostics["catpart_conversion_available"])
        self.assertIn("CATPART_CONVERTER_BIN", diagnostics["configuration"])
        self.assertIn("CATPART_CONVERTER_TEMPLATE", diagnostics["configuration"])
        self.assertIn(
            "step",
            diagnostics["local_capabilities_available"]["local_exchange_output_formats"],
        )
        self.assertIn("current_limitation", diagnostics)

    def test_resolve_catia_backend_from_env(self) -> None:
        original = os.environ.get("CATPART_CATIA_CATSTART_BIN")
        os.environ["CATPART_CATIA_CATSTART_BIN"] = "/bin/echo"
        try:
            args = argparse.Namespace(
                backend="catia",
                backend_executable=None,
                backend_cmd=None,
            )

            backend = convert_catpart.resolve_backend(args)
        finally:
            if original is None:
                os.environ.pop("CATPART_CATIA_CATSTART_BIN", None)
            else:
                os.environ["CATPART_CATIA_CATSTART_BIN"] = original

        self.assertEqual(backend.name, "catia_v5")
        self.assertEqual(backend.executable, "/bin/echo")
        self.assertIn("CNEXT -batch -macro", backend.template)

    def test_resolve_cadexchanger_honors_template_override(self) -> None:
        args = argparse.Namespace(
            backend="cadexchanger",
            backend_executable="/bin/echo",
            backend_cmd='"{executable}" --from "{input}" --to "{output}"',
        )

        backend = convert_catpart.resolve_backend(args)

        self.assertEqual(backend.name, "cadexchanger")
        self.assertEqual(backend.executable, "/bin/echo")
        self.assertIn("--from", backend.template)
        self.assertIn("--to", backend.template)

    def test_resolve_custom_template_requires_executable_when_placeholder_is_used(self) -> None:
        args = argparse.Namespace(
            backend="custom",
            backend_executable=None,
            backend_cmd='"{executable}" --input "{input}" --output "{output}"',
        )

        with self.assertRaises(convert_catpart.BackendNotFoundError):
            convert_catpart.resolve_backend(args)

    def test_resolve_auto_self_contained_template_without_executable(self) -> None:
        args = argparse.Namespace(
            backend="auto",
            backend_executable=None,
            backend_cmd='"/bin/echo" "{input}" "{output}"',
        )

        backend = convert_catpart.resolve_backend(args)

        self.assertEqual(backend.name, "template")
        self.assertEqual(backend.executable, "")
        self.assertIn("/bin/echo", backend.template)

    def test_probe_lists_native_backend_candidates(self) -> None:
        args = argparse.Namespace(
            backend="auto",
            backend_executable=None,
            backend_cmd=None,
        )

        payload = convert_catpart.probe_environment(args)
        candidates = payload["analysis_capabilities"]["native_backend_candidates"]

        self.assertIn("catia_v5_batch", candidates)
        self.assertIn("datakit_crossmanager_cli", candidates)
        self.assertIn("hoops_exchange_importexport", candidates)
        self.assertIn("three_d_tool", candidates)
        self.assertIn("transmagic_command", candidates)
        self.assertIn("cad_exchanger_batch", candidates)

    def test_datakit_probe_searches_cli_app_paths(self) -> None:
        self.assertIn(
            "/Applications/CrossManager*.app/Contents/MacOS/CrossManagerCLI",
            convert_catpart.DATAKIT_CROSSMANAGER_PATHS,
        )
        self.assertIn("CrossManagerCLI.exe", convert_catpart.DATAKIT_CROSSMANAGER_EXECUTABLES)

    def test_probe_lists_manual_catpart_routes(self) -> None:
        args = argparse.Namespace(
            backend="auto",
            backend_executable=None,
            backend_cmd=None,
        )

        payload = convert_catpart.probe_environment(args)
        manual_routes = payload["analysis_capabilities"]["manual_catpart_routes"]
        fusion = manual_routes["autodesk_fusion_manual_gui"]

        self.assertIn("autodesk_fusion_manual_gui", manual_routes)
        self.assertEqual(fusion["automation_level"], "manual_or_gui_assisted")
        self.assertIn("why_not_automatic_backend", fusion)

    def test_exchange_output_formats_are_cli_selectable(self) -> None:
        self.assertIn("brp", convert_catpart.FORMAT_EXTENSIONS)
        self.assertIn("prc", convert_catpart.FORMAT_EXTENSIONS)
        self.assertIn("sat", convert_catpart.FORMAT_EXTENSIONS)
        self.assertTrue(
            convert_catpart.FREECAD_CONVERT_OUTPUT_FORMATS.issubset(
                convert_catpart.FORMAT_EXTENSIONS
            )
        )

    def test_resolve_datakit_backend_from_env_template(self) -> None:
        original_bin = os.environ.get("CATPART_DATKIT_BIN")
        original_template = os.environ.get("CATPART_DATKIT_TEMPLATE")
        os.environ["CATPART_DATKIT_BIN"] = "/bin/echo"
        os.environ["CATPART_DATKIT_TEMPLATE"] = '"{executable}" --input "{input}" --output "{output}"'
        try:
            args = argparse.Namespace(
                backend="datakit",
                backend_executable=None,
                backend_cmd=None,
            )

            backend = convert_catpart.resolve_backend(args)
        finally:
            if original_bin is None:
                os.environ.pop("CATPART_DATKIT_BIN", None)
            else:
                os.environ["CATPART_DATKIT_BIN"] = original_bin
            if original_template is None:
                os.environ.pop("CATPART_DATKIT_TEMPLATE", None)
            else:
                os.environ["CATPART_DATKIT_TEMPLATE"] = original_template

        self.assertEqual(backend.name, "datakit_crossmanager_cli")
        self.assertEqual(backend.executable, "/bin/echo")
        self.assertIn("--input", backend.template)

    def test_resolve_datakit_backend_cmd_with_path_discovery(self) -> None:
        original_path = os.environ.get("PATH")
        original_bin = os.environ.get("CATPART_DATKIT_BIN")
        original_template = os.environ.get("CATPART_DATKIT_TEMPLATE")
        os.environ.pop("CATPART_DATKIT_BIN", None)
        os.environ.pop("CATPART_DATKIT_TEMPLATE", None)
        with tempfile.TemporaryDirectory() as temp_dir:
            executable = Path(temp_dir) / "CrossManagerCLI"
            executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            executable.chmod(0o755)
            os.environ["PATH"] = f"{temp_dir}{os.pathsep}{original_path or ''}"
            try:
                args = argparse.Namespace(
                    backend="datakit",
                    backend_executable=None,
                    backend_cmd='"{executable}" --input "{input}" --output "{output}"',
                )

                backend = convert_catpart.resolve_backend(args)
            finally:
                if original_path is None:
                    os.environ.pop("PATH", None)
                else:
                    os.environ["PATH"] = original_path
                if original_bin is None:
                    os.environ.pop("CATPART_DATKIT_BIN", None)
                else:
                    os.environ["CATPART_DATKIT_BIN"] = original_bin
                if original_template is None:
                    os.environ.pop("CATPART_DATKIT_TEMPLATE", None)
                else:
                    os.environ["CATPART_DATKIT_TEMPLATE"] = original_template

        self.assertEqual(backend.name, "datakit_crossmanager_cli")
        self.assertEqual(backend.executable, str(executable.resolve()))
        self.assertIn("--input", backend.template)

    def test_resolve_hoops_backend_from_env(self) -> None:
        original = os.environ.get("CATPART_HOOPS_IMPORTEXPORT_BIN")
        os.environ["CATPART_HOOPS_IMPORTEXPORT_BIN"] = "/bin/echo"
        try:
            args = argparse.Namespace(
                backend="hoops",
                backend_executable=None,
                backend_cmd=None,
            )

            backend = convert_catpart.resolve_backend(args)
        finally:
            if original is None:
                os.environ.pop("CATPART_HOOPS_IMPORTEXPORT_BIN", None)
            else:
                os.environ["CATPART_HOOPS_IMPORTEXPORT_BIN"] = original

        self.assertEqual(backend.name, "hoops_exchange_importexport")
        self.assertEqual(backend.executable, "/bin/echo")
        self.assertEqual(backend.template, convert_catpart.HOOPS_IMPORTEXPORT_TEMPLATE)

    def test_resolve_hoops_backend_cmd_with_path_discovery(self) -> None:
        original_path = os.environ.get("PATH")
        original_bin = os.environ.get("CATPART_HOOPS_IMPORTEXPORT_BIN")
        original_template = os.environ.get("CATPART_HOOPS_TEMPLATE")
        os.environ.pop("CATPART_HOOPS_IMPORTEXPORT_BIN", None)
        os.environ.pop("CATPART_HOOPS_TEMPLATE", None)
        with tempfile.TemporaryDirectory() as temp_dir:
            executable = Path(temp_dir) / "ImportExport"
            executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            executable.chmod(0o755)
            os.environ["PATH"] = f"{temp_dir}{os.pathsep}{original_path or ''}"
            try:
                args = argparse.Namespace(
                    backend="hoops",
                    backend_executable=None,
                    backend_cmd='"{executable}" "{input}" "{output}"',
                )

                backend = convert_catpart.resolve_backend(args)
            finally:
                if original_path is None:
                    os.environ.pop("PATH", None)
                else:
                    os.environ["PATH"] = original_path
                if original_bin is None:
                    os.environ.pop("CATPART_HOOPS_IMPORTEXPORT_BIN", None)
                else:
                    os.environ["CATPART_HOOPS_IMPORTEXPORT_BIN"] = original_bin
                if original_template is None:
                    os.environ.pop("CATPART_HOOPS_TEMPLATE", None)
                else:
                    os.environ["CATPART_HOOPS_TEMPLATE"] = original_template

        self.assertEqual(backend.name, "hoops_exchange_importexport")
        self.assertEqual(backend.executable, str(executable.resolve()))
        self.assertEqual(backend.template, '"{executable}" "{input}" "{output}"')

    def test_resolve_datakit_backend_requires_template(self) -> None:
        original_bin = os.environ.get("CATPART_DATKIT_BIN")
        original_template = os.environ.get("CATPART_DATKIT_TEMPLATE")
        os.environ["CATPART_DATKIT_BIN"] = "/bin/echo"
        os.environ.pop("CATPART_DATKIT_TEMPLATE", None)
        try:
            args = argparse.Namespace(
                backend="datakit",
                backend_executable=None,
                backend_cmd=None,
            )

            with self.assertRaises(convert_catpart.BackendNotFoundError):
                convert_catpart.resolve_backend(args)
        finally:
            if original_bin is None:
                os.environ.pop("CATPART_DATKIT_BIN", None)
            else:
                os.environ["CATPART_DATKIT_BIN"] = original_bin
            if original_template is not None:
                os.environ["CATPART_DATKIT_TEMPLATE"] = original_template

    def test_resolve_3dtool_backend_from_env(self) -> None:
        original = os.environ.get("CATPART_THREEDTOOL_BIN")
        os.environ["CATPART_THREEDTOOL_BIN"] = "/bin/echo"
        try:
            args = argparse.Namespace(
                backend="3dtool",
                backend_executable=None,
                backend_cmd=None,
            )

            backend = convert_catpart.resolve_backend(args)
        finally:
            if original is None:
                os.environ.pop("CATPART_THREEDTOOL_BIN", None)
            else:
                os.environ["CATPART_THREEDTOOL_BIN"] = original

        self.assertEqual(backend.name, "3d_tool")
        self.assertEqual(backend.executable, "/bin/echo")
        self.assertIn("-i", backend.template)
        self.assertIn("-o", backend.template)

    def test_resolve_3dtool_backend_cmd_still_discovers_path(self) -> None:
        original_path = os.environ.get("PATH")
        original = os.environ.get("CATPART_THREEDTOOL_BIN")
        os.environ.pop("CATPART_THREEDTOOL_BIN", None)
        with tempfile.TemporaryDirectory() as temp_dir:
            executable = Path(temp_dir) / "Convert.exe"
            executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            executable.chmod(0o755)
            os.environ["PATH"] = f"{temp_dir}{os.pathsep}{original_path or ''}"
            try:
                args = argparse.Namespace(
                    backend="3dtool",
                    backend_executable=None,
                    backend_cmd='"{executable}" --ignored "{input}" "{output}"',
                )

                backend = convert_catpart.resolve_backend(args)
            finally:
                if original_path is None:
                    os.environ.pop("PATH", None)
                else:
                    os.environ["PATH"] = original_path
                if original is None:
                    os.environ.pop("CATPART_THREEDTOOL_BIN", None)
                else:
                    os.environ["CATPART_THREEDTOOL_BIN"] = original

        self.assertEqual(backend.name, "3d_tool")
        self.assertEqual(backend.executable, str(executable.resolve()))
        self.assertEqual(backend.template, convert_catpart.THREED_TOOL_TEMPLATE)

    def test_resolve_transmagic_backend_from_env(self) -> None:
        original = os.environ.get("CATPART_TRANSMAGIC_BIN")
        os.environ["CATPART_TRANSMAGIC_BIN"] = "/bin/echo"
        try:
            args = argparse.Namespace(
                backend="transmagic",
                backend_executable=None,
                backend_cmd=None,
            )

            backend = convert_catpart.resolve_backend(args)
        finally:
            if original is None:
                os.environ.pop("CATPART_TRANSMAGIC_BIN", None)
            else:
                os.environ["CATPART_TRANSMAGIC_BIN"] = original

        self.assertEqual(backend.name, "transmagic_command")
        self.assertEqual(backend.executable, "/bin/echo")
        self.assertIn("-of{transmagic_format}", backend.template)
        self.assertIn("-xmlmass", backend.template)

    def test_transmagic_dry_run_builds_command_and_expected_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_path = temp_path / "model.CATPart"
            output_path = temp_path / "model.step"
            input_path.write_text("placeholder", encoding="utf-8")
            backend = convert_catpart.BackendSpec(
                name="transmagic_command",
                executable="/bin/echo",
                template=convert_catpart.TRANSMAGIC_TEMPLATE,
                detected_via="test",
            )

            result = convert_catpart.convert_one_with_transmagic(
                backend=backend,
                input_path=input_path,
                output_path=output_path,
                output_format="step",
                overwrite=False,
                dry_run=True,
                analyze=False,
                assume_unit=None,
            )

        self.assertEqual(result["status"], "dry_run")
        self.assertEqual(result["backend"], "transmagic_command")
        self.assertEqual(result["transmagic_output_format"], "stp")
        self.assertTrue(result["transmagic_expected_output"].endswith("model.stp"))
        self.assertIn("-ofstp", result["command"])
        self.assertIn("-xmlmass", result["command"])

    def test_parse_transmagic_xml_report_extracts_mass_properties(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            xml_path = Path(temp_dir) / "model.xml"
            xml_path.write_text(
                """<?xml version="1.0"?>
<Assembly>
  <Part>
    <Mass>
      <Volume>12.5</Volume>
      <Center_Of_Mass>1 2 3</Center_Of_Mass>
      <Inertia_Tensor>1 0 0 0 2 0 0 0 3</Inertia_Tensor>
    </Mass>
    <Surface_Area>42.25</Surface_Area>
    <Bounding_Box size="10 20 30" />
  </Part>
</Assembly>
""",
                encoding="utf-8",
            )

            parsed = convert_catpart.parse_transmagic_xml_report(xml_path)

        assert parsed is not None
        self.assertEqual(parsed["kind"], "transmagic_xml")
        self.assertEqual(parsed["mass_properties"]["volume"], 12.5)
        self.assertEqual(parsed["mass_properties"]["center_of_mass"], [1.0, 2.0, 3.0])
        self.assertEqual(parsed["surface"]["area"], 42.25)
        self.assertTrue(parsed["bounding_box"]["values"])

    def test_render_catia_batch_macro_exports_and_reads_native_properties(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            macro = convert_catpart.render_catia_batch_macro(
                input_path=temp_path / "model.CATPart",
                output_path=temp_path / "model.step",
                native_report_path=temp_path / "model.catia-native.txt",
                export_format="stp",
            )

        self.assertIn("CATIA.Documents.Open", macro)
        self.assertIn("doc.ExportData exportBasePath, exportFormat", macro)
        self.assertIn("product.Analyze", macro)
        self.assertIn("analyze.Volume", macro)
        self.assertIn("analyze.GetGravityCenter", macro)
        self.assertIn("analyze.GetInertia", macro)

    def test_parse_catia_native_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = Path(temp_dir) / "native.txt"
            report_path.write_text(
                "\n".join(
                    [
                        "status=converted",
                        "mass=1,25",
                        "volume=0.0005",
                        "wet_area=42",
                        "gravity_center=1;2;3",
                        "inertia_matrix=1;0;0;0;2;0;0;0;3",
                        "source=CATIA Product.Analyze",
                    ]
                ),
                encoding="utf-8",
            )

            parsed = convert_catpart.parse_catia_native_report(report_path)

        assert parsed is not None
        self.assertEqual(parsed["kind"], "catia_native")
        self.assertEqual(parsed["status"], "converted")
        self.assertEqual(parsed["mass"], 1.25)
        self.assertEqual(parsed["volume"], 0.0005)
        self.assertEqual(parsed["wet_area"], 42.0)
        self.assertEqual(parsed["gravity_center"], [1.0, 2.0, 3.0])
        self.assertEqual(parsed["inertia_matrix"], [1.0, 0.0, 0.0, 0.0, 2.0, 0.0, 0.0, 0.0, 3.0])

    def test_convert_one_with_catia_dry_run_builds_macro_and_command(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_path = temp_path / "model.CATPart"
            output_path = temp_path / "model.step"
            input_path.write_text("placeholder", encoding="utf-8")
            backend = convert_catpart.BackendSpec(
                name="catia_v5",
                executable="/bin/echo",
                template=convert_catpart.CATIA_BATCH_TEMPLATE,
                detected_via="test",
            )

            result = convert_catpart.convert_one_with_catia(
                backend=backend,
                input_path=input_path,
                output_path=output_path,
                output_format="step",
                overwrite=False,
                dry_run=True,
                analyze=False,
                assume_unit=None,
            )

        self.assertEqual(result["status"], "dry_run")
        self.assertEqual(result["backend"], "catia_v5")
        self.assertIn("-run", result["command"])
        self.assertTrue(Path(result["catia_macro_path"]).exists())

    def test_analyze_obj_file_skips_invalid_faces_instead_of_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            obj_path = Path(temp_dir) / "bad.obj"
            obj_path.write_text("v 0 0 0\nv 1 0 0\nf 1 2 99\n", encoding="utf-8")

            analysis = convert_catpart.analyze_obj_file(obj_path, unit="mm")

        self.assertEqual(analysis["vertex_count"], 2)
        self.assertEqual(analysis["face_count"], 1)
        self.assertEqual(analysis["invalid_face_count"], 1)
        self.assertEqual(analysis["triangle_count"], 0)
        self.assertFalse(analysis["watertight"])
        self.assertTrue(analysis["invalid_face_examples"])

    def test_convert_one_rejects_same_input_and_output_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "model.step"
            input_path.write_text("fake step payload", encoding="utf-8")
            backend = convert_catpart.BackendSpec(
                name="custom",
                executable="/bin/cp",
                template='"{executable}" "{input}" "{output}"',
                detected_via="test",
            )

            with self.assertRaises(FileExistsError):
                convert_catpart.convert_one(
                    backend=backend,
                    input_path=input_path,
                    output_path=input_path,
                    output_format="step",
                    overwrite=True,
                    dry_run=False,
                    analyze=False,
                    assume_unit=None,
                )

            self.assertTrue(input_path.exists())

    def test_local_step_conversion_to_brep_with_freecad_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            step_path = self.export_box_with_freecad(
                temp_path,
                "box.step",
                ["Part.export([box], output_path)"],
            )
            output_path = temp_path / "box.brep"

            result = convert_catpart.convert_one_with_freecad(
                input_path=step_path,
                output_path=output_path,
                output_format="brep",
                source_format="step",
                overwrite=False,
                dry_run=False,
                analyze=True,
                assume_unit="mm",
            )

        self.assertEqual(result["status"], "converted")
        self.assertEqual(result["backend"], "freecad")
        self.assertEqual(result["analysis"]["kind"], "brep")
        self.assertEqual(result["analysis"]["enclosed_volume"], 6000.0)
        self.assertEqual(result["analysis"]["surface_area"], 2200.0)

    def test_auto_backend_falls_back_when_freecad_target_is_unsupported(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            step_path = temp_path / "model.step"
            output_path = temp_path / "model.glb"
            report_path = temp_path / "report.json"
            step_path.write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")
            environment = os.environ.copy()
            environment["CATPART_CONVERTER_BIN"] = "/bin/cp"

            completed = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    str(step_path),
                    "--format",
                    "glb",
                    "--backend-cmd",
                    '"{executable}" "{input}" "{output}"',
                    "--output",
                    str(output_path),
                    "--report",
                    str(report_path),
                ],
                check=False,
                capture_output=True,
                env=environment,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue(output_path.exists())

    def test_analyze_brep_file_with_freecad_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            brep_path = self.export_box_with_freecad(
                temp_path,
                "box.brep",
                ["box.Shape.exportBrep(output_path)"],
            )

            analysis = convert_catpart.analyze_output_file(
                brep_path,
                "brep",
                assume_unit="mm",
            )

        assert analysis is not None
        self.assertEqual(analysis["kind"], "brep")
        self.assertEqual(analysis["surface_area"], 2200.0)
        self.assertEqual(analysis["enclosed_volume"], 6000.0)
        self.assertEqual(analysis["topology"]["faces"], 6)
        self.assertEqual(analysis["solid_details"]["count"], 1)
        self.assertEqual(analysis["solid_details"]["items"][0]["volume"], 6000.0)
        self.assertEqual(analysis["mass_properties"]["mass_import_units"], 6000.0)
        self.assertTrue(analysis["mass_properties"]["matrix_of_inertia_import_units"])

    def test_analyze_iges_file_with_freecad_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            iges_path = self.export_box_with_freecad(
                temp_path,
                "box.igs",
                ["Part.export([box], output_path)"],
            )

            analysis = convert_catpart.analyze_output_file(
                iges_path,
                "igs",
                assume_unit="mm",
            )

        assert analysis is not None
        self.assertEqual(analysis["kind"], "iges")
        self.assertEqual(analysis["surface_area"], 2200.0)
        self.assertEqual(analysis["enclosed_volume"], 6000.0)
        self.assertEqual(analysis["topology"]["faces"], 6)
        self.assertEqual(analysis["surface_area_unit"], "mm^2")
        self.assertEqual(analysis["volume_unit"], "mm^3")


if __name__ == "__main__":
    unittest.main()
