"""Measure visible editorial text without inspecting its vocabulary."""
import unicodedata
from html.parser import HTMLParser

MIN_EDITOR_DESCRIPTION = 200


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {'script', 'style'}:
            self.hidden += 1
        elif tag in {'br', 'p', 'div', 'li'}:
            self.parts.append(' ')

    def handle_endtag(self, tag: str) -> None:
        if tag in {'script', 'style'}:
            self.hidden = max(0, self.hidden - 1)
        elif tag in {'p', 'div', 'li'}:
            self.parts.append(' ')

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.parts.append(data)


def visible_text(value: str | None) -> str:
    parser = _Text()
    parser.feed(value or '')
    text = ''.join(char for char in ''.join(parser.parts) if unicodedata.category(char) != 'Cf')
    return ' '.join(text.split())
