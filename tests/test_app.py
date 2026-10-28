import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from devsweep.app import App
from devsweep.core import scan


class AppTests(unittest.TestCase):
    def setUp(self):
        self.app = App()
        self.app.withdraw()

    def tearDown(self):
        self.app.destroy()

    def test_no_cleanup_available_on_startup(self):
        self.assertEqual("disabled", str(self.app.trash_button.cget("state")))
        self.assertFalse(self.app.checked)

    def test_invalid_filters_do_not_start_worker(self):
        self.app.days.set("-1")
        with patch("devsweep.app.messagebox.showerror") as error:
            self.app.start_scan()
        error.assert_called_once()
        self.assertFalse(self.app.busy)

    def test_busy_state_prevents_new_scan(self):
        self.app.set_busy(True, scanning=True)
        self.assertEqual("disabled", str(self.app.scan_button.cget("state")))
        self.assertEqual("normal", str(self.app.stop_button.cget("state")))
        self.app.set_busy(False)

    def _export_fixture(self, extension):
        sandbox = Path(".test-work").resolve()
        sandbox.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="export-", dir=sandbox) as directory:
            root = Path(directory)
            self.assertTrue(root.is_relative_to(sandbox))
            target = root / "project" / "node_modules"
            target.mkdir(parents=True)
            (target / "payload.txt").write_text("payload", encoding="utf-8")
            result = scan([root])
            self.app.last_scan_result = result
            self.app.add_rows(result.candidates)
            destination = root / ("inventory" + extension)
            with patch("devsweep.app.filedialog.asksaveasfilename", return_value=str(destination)) as dialog:
                self.app.export()
            self.assertIn(("JSON", "*.json"), dialog.call_args.kwargs["filetypes"])
            self.assertFalse(self.app.checked)
            self.assertTrue(target.exists())
            return destination.read_text(encoding="utf-8-sig"), result

    def test_gui_exports_unchecked_inventory_to_json(self):
        content, result = self._export_fixture(".JSON")
        report = json.loads(content)
        self.assertEqual(1, len(report["candidates"]))
        self.assertTrue(report["read_only"])
        self.assertEqual(result.visited, report["visited"])

    def test_gui_preserves_csv_export(self):
        content, _result = self._export_fixture(".csv")
        rows = list(csv.reader(content.splitlines()))
        self.assertEqual("Bytes lógicos", rows[0][3])
        self.assertEqual("7", rows[1][3])


if __name__ == "__main__":
    unittest.main()
