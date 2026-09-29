"""Format-independent helpers used by route history exporters."""


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
        text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        if attribute:
            text = text.replace('"', "&quot;").replace("'", "&apos;")
        return text
