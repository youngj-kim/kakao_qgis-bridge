"""Format-independent helpers used by route history exporters."""


def shapefile_text(value, max_characters):
    """Preserve the existing character limit and a UTF-8-safe DBF byte limit."""
    text = str(value)[:max_characters]
    return text.encode("utf-8")[:254].decode("utf-8", errors="ignore")


class GpxWriter:
    def __init__(self):
        self.lines = []
        self.level = 0

    def document(self):
        body = "\n".join(self.lines)
        return f'<?xml version="1.0" encoding="utf-8"?>\n{body}\n'

    def start(self, tag, attrs=None):
        self.lines.append(f"{self._indent()}<{tag}{self._attrs(attrs)}>")
        self.level += 1

    def end(self, tag):
        self.level = max(0, self.level - 1)
        self.lines.append(f"{self._indent()}</{tag}>")

    def empty(self, tag, attrs=None):
        self.lines.append(f"{self._indent()}<{tag}{self._attrs(attrs)} />")

    def text(self, tag, value):
        self.lines.append(f"{self._indent()}<{tag}>{self._escape(value)}</{tag}>")

    def _indent(self):
        return "  " * self.level

    @classmethod
    def _attrs(cls, attrs):
        if not attrs:
            return ""
        return "".join(
            f' {key}="{cls._escape(value, attribute=True)}"'
            for key, value in attrs.items()
        )

    @staticmethod
    def _escape(value, attribute=False):
        text = str(value if value is not None else "")
        # XML 1.0 permits TAB/LF/CR, excludes other C0 controls and surrogates.
        text = "".join(char for char in text if ord(char) in (9, 10, 13)
                       or 0x20 <= ord(char) <= 0xD7FF
                       or 0xE000 <= ord(char) <= 0xFFFD
                       or 0x10000 <= ord(char) <= 0x10FFFF)
        text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        if attribute:
            text = text.replace('"', "&quot;").replace("'", "&apos;")
        return text
