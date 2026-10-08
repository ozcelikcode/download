"""Conservative local editorial screening; staff make the final decision."""

import re
import unicodedata
from html.parser import HTMLParser

MIN_EDITOR_DESCRIPTION = 200
# Deliberately explicit vocabulary. Matches flag review, never censor content.
REVIEW_TERMS = frozenset({
    "amk", "aq", "aminakoyim", "aminakoyayim", "amcik", "siktir", "sikeyim",
    "sikik", "orospu", "orospucocugu", "pic", "yarrak", "gotveren",
    "kahpe", "ibne", "salak", "aptal", "gerizekali", "mal herif",
    "fuck", "fucking", "motherfucker", "bitch", "asshole", "cunt",
    "shit", "idiot", "puta", "cabron", "mierda", "gilipollas",
    "putain", "salope", "connard", "merde",
    "amina koyayim", "amina koyim", "orospu cocugu", "mal herif",
})


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self.hidden += 1
        elif tag in {"br", "p", "div", "li"}:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)
        elif tag in {"p", "div", "li"}:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.parts.append(data)


def visible_text(value: str | None) -> str:
    parser = _Text()
    parser.feed(value or "")
    text = "".join(parser.parts)
    text = "".join(char for char in text if unicodedata.category(char) != "Cf")
    return " ".join(text.split())


def requires_review(*values: str | None) -> bool:
    text = visible_text(" ".join(value or "" for value in values)).casefold().replace("ı", "i")
    text = "".join(char for char in unicodedata.normalize("NFKD", text) if not unicodedata.combining(char))
    text = text.translate(str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "@": "a", "$": "s"}))
    words = re.findall(r"[a-z]+", text)
    # Join short separated letters to catch common obfuscation without substring
    # matching innocent words such as 'picture' or 'Scunthorpe'.
    joined = re.sub(r"\b(?:[a-z][ ._*\-]+){2,}[a-z]\b", lambda m: re.sub(r"[^a-z]", "", m[0]), text)
    candidates = set(words) | set(re.findall(r"[a-z]+", joined))
    return bool(candidates & REVIEW_TERMS) or any(
        re.search(r"\b" + re.escape(term).replace(r"\ ", r"\s+") + r"\b", text)
        for term in REVIEW_TERMS if " " in term
    )
