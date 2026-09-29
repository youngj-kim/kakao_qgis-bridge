import unittest

from kakao_qgis_bridge.history_export import GpxWriter


class GpxWriterTests(unittest.TestCase):
    def test_escapes_text_and_attributes(self):
        writer = GpxWriter()
        writer.start("gpx", {"creator": 'A&B "tool"'})
        writer.text("name", "A < B & C")
        writer.end("gpx")
        document = writer.document()
        self.assertIn('creator="A&amp;B &quot;tool&quot;"', document)
        self.assertIn("<name>A &lt; B &amp; C</name>", document)


if __name__ == "__main__":
    unittest.main()
