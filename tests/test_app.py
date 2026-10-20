import unittest
from unittest.mock import patch

from devsweep.app import App


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


if __name__ == "__main__":
    unittest.main()
