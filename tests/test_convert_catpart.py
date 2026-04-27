from __future__ import annotations

import importlib.util
import math
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
