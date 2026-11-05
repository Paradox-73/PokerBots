"""The competition runs Python 3.11: make sure no file needs 3.12 grammar."""
import ast
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Py311(unittest.TestCase):
    def test_parse_as_311(self):
        for base, _, files in os.walk(ROOT):
            for f in files:
                if f.endswith(".py"):
                    path = os.path.join(base, f)
                    with open(path, encoding="utf-8") as fh:
                        ast.parse(fh.read(), path, feature_version=(3, 11))


if __name__ == "__main__":
    unittest.main()
