from pathlib import Path
import unittest
from html.parser import HTMLParser

from kakao_qgis_bridge.viewer_page import VIEWER_SCRIPTS, load_viewer_template


class ViewerTemplateTests(unittest.TestCase):
    def test_guidance_is_outside_collapsible_explorer(self):
        class Parents(HTMLParser):
            def __init__(self):
                super().__init__()
                self.stack = []
                self.parents = {}

            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                element_id = attrs.get("id")
                if element_id:
                    self.parents[element_id] = list(self.stack)
                if tag not in {"input", "img", "meta", "link", "br", "hr"}:
                    self.stack.append((tag, element_id))

            def handle_endtag(self, tag):
                for i in range(len(self.stack) - 1, -1, -1):
                    if self.stack[i][0] == tag:
                        del self.stack[i:]
                        break

        parser = Parents()
        path = Path(__file__).resolve().parents[1] / "kakao_qgis_bridge/web/kakao_viewer.html"
        parser.feed(path.read_text(encoding="utf-8"))
        self.assertIn(("div", "explorer-body"), parser.parents["route-origin-input"])
        self.assertIn(("div", "explorer-body"), parser.parents["search-results"])
        self.assertNotIn(("div", "explorer-body"), parser.parents["route-guidance-panel"])
        self.assertIn(("header", "search-panel"), parser.parents["route-guidance-panel"])
        for element_id in ("route-guidance-list", "route-history-list", "route-guidance-toggle"):
            self.assertIn(("section", "route-guidance-panel"), parser.parents[element_id])

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
