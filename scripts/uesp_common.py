"""Shared helpers for the data-building scripts (UESP downloads, caching, HTML parsing).

Every page is downloaded once and cached in scripts/cache/, so re-running a
script is fast and does not hit the website again. Use --refresh on a script to
ignore the cache.
"""
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA = ROOT / "src" / "data"
CACHE = HERE / "cache"

API = "https://en.uesp.net/w/api.php"
WIKI = "https://en.uesp.net/wiki/"
DELAY = 0.8  # seconds between real network requests (be polite to the wiki)
UA = {
    "User-Agent": "SkyrimDB-W/0.1 (personal offline reference app; contact: github.com/willianlps)",
    "Accept-Language": "en-US,en;q=0.8",
}

_last_request = 0.0


# --------------------------------------------------------------------- text
def clean(t: str) -> str:
    """Normalises whitespace, drops footnote marks like [1], keeps line breaks."""
    t = t.replace("\xa0", " ")
    t = re.sub(r"\[\d+\]|\[edit\]", "", t)
    lines = [" ".join(l.split()) for l in t.split("\n")]
    return "\n".join(l for l in lines if l).strip()


def one_line(t: str) -> str:
    return " ".join(clean(t).split())


def norm(s: str) -> str:
    """Lower-case alphanumerics only, for matching names across sources."""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"\(.*?\)", "", s)
    s = re.sub(r"^the", "", s.lower().strip())
    return re.sub(r"[^a-z0-9]", "", s)


def slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "unnamed"


def title_of_href(href: str) -> str:
    """'/wiki/Skyrim:Aela_the_Huntress#x' -> 'Skyrim:Aela the Huntress'."""
    if not href.startswith("/wiki/"):
        return ""
    t = urllib.parse.unquote(href[len("/wiki/"):].split("#")[0])
    return t.replace("_", " ")


# ------------------------------------------------------------------ network
def _sleep_if_needed() -> None:
    global _last_request
    wait = DELAY - (time.time() - _last_request)
    if wait > 0:
        time.sleep(wait)
    _last_request = time.time()


def http_get(url: str, timeout: int = 30) -> str:
    _sleep_if_needed()
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        charset = r.headers.get_content_charset() or "utf-8"
    return raw.decode(charset, errors="replace")


def api_json(params: dict) -> dict:
    q = {"format": "json", "formatversion": "2", **params}
    return json.loads(http_get(API + "?" + urllib.parse.urlencode(q)))


def cache_path(key: str) -> Path:
    return CACHE / (slug(key)[:120] + ".html")


def fetch_wiki(title: str, refresh: bool = False):
    """Returns (html, source) for a UESP page. Uses the cache unless refresh=True.

    Tries the MediaWiki parse API first and falls back to the normal page.
    Returns (None, error text) when both fail.
    """
    p = cache_path("uesp-" + title)
    if p.exists() and not refresh:
        return p.read_text(encoding="utf-8"), "cache"
    errors = []
    try:
        j = api_json({"action": "parse", "page": title, "prop": "text", "redirects": "1"})
        text = j["parse"]["text"]
        if isinstance(text, dict):
            text = text.get("*", "")
        if text:
            CACHE.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
            return text, "api"
    except Exception as e:  # noqa: BLE001
        errors.append(f"API: {e}")
    try:
        text = http_get(WIKI + urllib.parse.quote(title.replace(" ", "_"), safe=":_()'!,-"))
        CACHE.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return text, "page"
    except Exception as e:  # noqa: BLE001
        errors.append(f"page: {e}")
    return None, "; ".join(errors)


def fetch_url(url: str, refresh: bool = False):
    """Same as fetch_wiki, for any URL (no API)."""
    p = cache_path("url-" + url)
    if p.exists() and not refresh:
        return p.read_text(encoding="utf-8"), "cache"
    try:
        text = http_get(url)
    except Exception as e:  # noqa: BLE001
        return None, str(e)
    CACHE.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return text, "page"


def category_members(category: str, refresh: bool = False):
    """Returns ([page titles], [sub-category titles]) of a wiki category (cached)."""
    p = cache_path("cat-" + category).with_suffix(".json")
    if p.exists() and not refresh:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d["pages"], d["subcats"]
    pages, subcats, cont = [], [], {}
    while True:
        j = api_json({"action": "query", "list": "categorymembers", "cmtitle": category,
                      "cmlimit": "500", "cmtype": "page|subcat", **cont})
        for m in j.get("query", {}).get("categorymembers", []):
            (subcats if m["title"].startswith("Category:") else pages).append(m["title"])
        if "continue" in j:
            cont = {"cmcontinue": j["continue"]["cmcontinue"]}
        else:
            break
    CACHE.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"pages": pages, "subcats": subcats}), encoding="utf-8")
    return pages, subcats


# ------------------------------------------------------------------ parsing
class Doc(HTMLParser):
    """Turns wiki HTML into a flat list of blocks.

    blocks:
      ("h", level, text)                 h2/h3/h4 headings
      ("p", text)                        paragraphs
      ("li", text, ordered)              list items outside tables
      ("table", {"heads": [...], "rows": [[cell, ...], ...]})
    cell = {"t": text, "alts": [img alt texts], "links": [(text, title)], "th": bool}
    Rowspans / colspans are expanded so every row has one cell per column.
    """

    SKIP_CLASSES = ("mw-editsection", "toc", "navbox", "reference", "noprint", "metadata")

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks = []
        self.links = []  # (text, title) for every link on the page
        self._skip = None
        self._buf = None  # text buffer for the open h/p/li
        self._buf_kind = None
        self._ol = []
        self._depth = 0
        self._tab = None
        self._row = None
        self._cell = None
        self._span = {}  # column -> [remaining rows, cell] for rowspans
        self._a = None
        self._heads = []

    # -- helpers
    def _begin(self, kind, level=0):
        if self._depth == 0 and self._buf is None:
            self._buf, self._buf_kind, self._level = [], kind, level

    def _end(self, kind):
        if self._buf is not None and self._buf_kind == kind:
            text = clean("".join(self._buf))
            self._buf = None
            if text:
                if kind == "h":
                    self.blocks.append(("h", self._level, text))
                elif kind == "li":
                    self.blocks.append(("li", text, bool(self._ol and self._ol[-1])))
                else:
                    self.blocks.append((kind, text))

    def _add_text(self, d):
        if self._cell is not None:
            self._cell["buf"].append(d)
        elif self._buf is not None:
            self._buf.append(d)

    # -- events
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if self._skip:
            if tag == self._skip[0]:
                self._skip[1] += 1
            return
        cls = a.get("class") or ""
        if tag in ("style", "script", "sup") or any(c in cls for c in self.SKIP_CLASSES):
            self._skip = [tag, 1]
            return
        if tag in ("h2", "h3", "h4"):
            self._begin("h", int(tag[1]))
        elif tag == "p":
            self._begin("p")
        elif tag in ("ol", "ul"):
            if self._depth == 0:
                self._ol.append(tag == "ol")
        elif tag == "li":
            if self._depth == 0:
                self._end("li")
                self._begin("li")
        elif tag == "table":
            if self._depth == 0:
                self._tab = {"heads": [], "rows": []}
                self._span = {}
            self._depth += 1
        elif self._depth == 1:
            if tag == "tr":
                self._row, self._col = [], 0
                self._fill_spans()
            elif tag in ("td", "th") and self._row is not None:
                self._fill_spans()
                self._cell = {"buf": [], "alts": [], "links": [], "th": tag == "th",
                              "rs": _int(a.get("rowspan")), "cs": _int(a.get("colspan"))}
            elif tag in ("br", "li", "p") and self._cell is not None:
                self._cell["buf"].append("\n")
        if tag == "br":
            self._add_text("\n") if self._cell is None else None
        if tag == "img":
            alt = (a.get("alt") or "").strip()
            if alt and self._cell is not None:
                self._cell["alts"].append(alt)
        if tag == "a":
            href = a.get("href") or ""
            self._a = [title_of_href(href), []]

    def _fill_spans(self):
        """Inserts the cells that rowspans from earlier rows put at this position."""
        while self._row is not None and self._col in self._span:
            left, cell = self._span[self._col]
            self._row.append(cell)
            if left <= 1:
                del self._span[self._col]
            else:
                self._span[self._col][0] = left - 1
            self._col += 1

    def handle_endtag(self, tag):
        if self._skip:
            if tag == self._skip[0]:
                self._skip[1] -= 1
                if self._skip[1] == 0:
                    self._skip = None
            return
        if tag == "a" and self._a is not None:
            text = clean("".join(self._a[1]))
            if self._a[0] and text:
                self.links.append((text, self._a[0]))
                if self._cell is not None:
                    self._cell["links"].append((text, self._a[0]))
            self._a = None
        if tag in ("h2", "h3", "h4"):
            self._end("h")
        elif tag == "p":
            self._end("p")
        elif tag == "li" and self._depth == 0:
            self._end("li")
        elif tag in ("ol", "ul") and self._depth == 0:
            if self._ol:
                self._ol.pop()
        elif tag == "table" and self._depth > 0:
            self._depth -= 1
            if self._depth == 0 and self._tab is not None:
                self.blocks.append(("table", self._tab))
                self._tab = None
        elif self._depth == 1:
            if tag in ("td", "th") and self._cell is not None and self._row is not None:
                c = self._cell
                cell = {"t": clean("".join(c["buf"])), "alts": c["alts"], "links": c["links"],
                        "th": c["th"]}
                for _ in range(max(1, c["cs"])):
                    self._row.append(cell)
                    if c["rs"] > 1:
                        self._span[self._col] = [c["rs"] - 1, cell]
                    self._col += 1
                    self._fill_spans()
                self._cell = None
            elif tag == "tr" and self._row is not None:
                self._fill_spans()
                if self._row and self._tab is not None:
                    self._tab["rows"].append(self._row)
                self._row = None

    def handle_data(self, d):
        if self._skip:
            return
        if self._a is not None:
            self._a[1].append(d)
        self._add_text(d)


def _int(v) -> int:
    try:
        return max(1, int(v))
    except (TypeError, ValueError):
        return 1


def parse(html_text: str) -> Doc:
    d = Doc()
    d.feed(html_text)
    d.close()
    return d


def table_records(tab: dict):
    """Splits a parsed table into (header names, rows).

    Header names are normalised (lower-case alphanumerics). Rows are lists of
    cells. A row made only of <th> cells becomes the (new) header; a
    single-cell th row is treated as a sub-title and skipped.
    """
    head, rows = None, []
    for row in tab["rows"]:
        if all(c["th"] for c in row):
            uniq = {id(c) for c in row}
            if len(uniq) == 1 and head is not None:
                continue
            head = [norm(c["t"]) for c in row]
        else:
            rows.append(row)
    return head, rows


def section_of(blocks, idx: int, level: int = 2) -> str:
    """Text of the nearest heading of the given level before block idx."""
    for b in reversed(blocks[:idx]):
        if b[0] == "h" and b[1] <= level:
            return b[2]
    return ""


def heading_chain(blocks, idx: int):
    """[h2, h3, h4] headings in force just before block idx."""
    chain = ["", "", ""]
    for b in blocks[:idx]:
        if b[0] == "h" and 2 <= b[1] <= 4:
            chain[b[1] - 2] = b[2]
            for i in range(b[1] - 1, 3):
                chain[i] = ""
    return chain


# --------------------------------------------------------------------- misc
def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def setup_console() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")


def dlc_from_title(title: str) -> str:
    t = title.lower()
    if t.startswith("dawnguard:"):
        return "Dawnguard"
    if t.startswith("dragonborn:"):
        return "Dragonborn"
    if t.startswith("hearthfire:"):
        return "Hearthfire"
    return "Skyrim"
