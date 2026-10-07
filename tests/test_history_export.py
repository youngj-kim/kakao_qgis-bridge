import unittest
from xml.etree import ElementTree

from kakao_qgis_bridge.history_export import GpxWriter, shapefile_text


class GpxWriterTests(unittest.TestCase):
    def test_escapes_text_and_attributes(self):
        writer = GpxWriter()
        writer.start("gpx", {"creator": 'A&B "tool"'})
        writer.text("name", "A < B & C")
        writer.end("gpx")
        document = writer.document()
        self.assertIn('creator="A&amp;B &quot;tool&quot;"', document)
        self.assertIn("<name>A &lt; B &amp; C</name>", document)

    def test_forbidden_xml_characters_removed_from_text_and_attributes(self):
        illegal = "".join(chr(code) for code in range(32) if code not in (9, 10, 13))
        illegal += "\ud800\udfff\ufffe\uffff"
        allowed = "한글 😀\t\n\r"
        writer = GpxWriter()
        writer.start("gpx", {"creator": "A" + illegal + "B"})
        writer.text("name", allowed + illegal)
        writer.end("gpx")
        document = writer.document()
        root = ElementTree.fromstring(document)
        self.assertEqual(root.attrib["creator"], "AB")
        self.assertEqual(root.findtext("name"), allowed.replace("\r", "\n"))
        for char in illegal:
            self.assertNotIn(char, document)


class ShapefileTextTests(unittest.TestCase):
    def test_character_and_utf8_byte_boundaries(self):
        self.assertEqual(shapefile_text("a" * 254, 254), "a" * 254)
        self.assertEqual(shapefile_text("a" * 255, 254), "a" * 254)
        self.assertEqual(shapefile_text("가" * 84, 254), "가" * 84)
        self.assertEqual(shapefile_text("가" * 85, 254), "가" * 84)
        self.assertEqual(shapefile_text("가" * 10, 5), "가" * 5)
        self.assertEqual(shapefile_text("a" * 252 + "😀", 254), "a" * 252)


if __name__ == "__main__":
    unittest.main()
