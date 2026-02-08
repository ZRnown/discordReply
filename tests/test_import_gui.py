import os
import sys
import unittest


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)


class TestGuiImport(unittest.TestCase):
    def test_import_gui_module(self):
        __import__("src.gui")


if __name__ == "__main__":
    unittest.main()
