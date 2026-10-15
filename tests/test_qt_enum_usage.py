"""Guard WKB enum scopes flagged by the plugin repository's Qt6 check."""
import ast
from pathlib import Path
import unittest


class WkbEnumScopeTest(unittest.TestCase):
    def test_geometry_enums_are_explicitly_scoped(self):
        root = Path(__file__).resolve().parents[1] / "kakao_qgis_bridge"
        for path in sorted(root.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if (isinstance(node, ast.Attribute)
                        and isinstance(node.value, ast.Name)
                        and node.value.id == "QgsWkbTypes"
                        and node.attr in {"Point", "LineString", "MultiLineString"}):
                    self.fail(f"{path.name}:{node.lineno}: use QgsWkbTypes.Type.{node.attr}")


if __name__ == "__main__":
    unittest.main()
