from pathlib import Path
import unittest

from kakao_qgis_bridge.viewer_page import VIEWER_SCRIPTS, load_viewer_template


class ViewerTemplateTests(unittest.TestCase):
    def test_packaged_scripts_are_inlined_once_before_main(self):
        plugin_dir = Path(__file__).resolve().parents[1] / "kakao_qgis_bridge"
        html = load_viewer_template(plugin_dir)
        main = html.index("const kakaoAppKey")
        for marker, filename in VIEWER_SCRIPTS.items():
            self.assertNotIn(marker, html)
            source = (plugin_dir / "web" / filename).read_text(encoding="utf-8")
            self.assertEqual(html.count(source), 1)
            self.assertLess(html.index(source), main)
        self.assertIn("__KAKAO_APP_KEY_JSON__", html)
        self.assertIn('qrc:///qtwebchannel/qwebchannel.js', html)


if __name__ == "__main__":
    unittest.main()
