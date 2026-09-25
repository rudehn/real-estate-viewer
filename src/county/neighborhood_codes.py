"""The county's monthly neighborhood codes page (neighborhood_codes_YYYYMMDD.htm)."""
import html
import re

_ROW = re.compile(r"<tr>\s*<td>\s*(.*?)\s*</td>\s*<td>\s*(.*?)\s*</td>\s*</tr>", re.S | re.I)
_PRIORITY_BOARD = re.compile(r"^.*?PRIORITY BOARD-\s*")


def parse_neighborhood_codes(page: bytes) -> dict[str, str]:
    text = page.decode("cp1252", errors="replace")
    out = {}
    for code, name in _ROW.findall(text):
        code = html.unescape(code).replace("\xa0", " ").strip()
        name = html.unescape(name).replace("\xa0", " ").strip()
        if code and name:
            out[code] = name
    return out


def neighborhood_display_name(name: str) -> str:
    """Drop Dayton's priority-board prefix; the rest names the neighborhood."""
    return _PRIORITY_BOARD.sub("", name).strip() or name
