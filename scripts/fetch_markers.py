"""Builds src/data/markers.json from the published MapMarker FormID list
(URL constant below), dropping the Japanese names.

Usage (from the project root):
    python scripts/fetch_markers.py

Needs internet only for this step. The app itself works fully offline.

The script tries three ways of reading the page (HTML table, one line per
record, running text) and keeps whichever finds the most markers. If it finds
none, it does NOT overwrite the current markers.json and saves the page to
scripts/page_debug.html together with a diagnosis in the terminal.
"""
import html
import json
import re
import sys
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

URL = "https://rrryutaro.hatenadiary.com/entry/2017/03/30/All_MapMarker_FormID_List"
HERE = Path(__file__).resolve().parent
OUTPUT = HERE.parent / "src" / "data" / "markers.json"
DEBUG = HERE / "page_debug.html"
EXPECTED = 436

# FormID prefix = plugin index in the default Skyrim SE load order.
PLUGINS = {
    "00": "Skyrim.esm",
    "01": "Update.esm",
    "02": "Dawnguard.esm",
    "03": "HearthFires.esm",
    "04": "Dragonborn.esm",
}

HEX8 = re.compile(r"^[0-9a-fA-F]{8}$")
# After the Japanese name comes: <typeId> <English type name> [Japanese type]
TYPE_RE = re.compile(r"\s(\d+)\s([A-Za-z][A-Za-z0-9 \-]*?)(?:\s+[^\x00-\x7f].*)?$")
# "lines" mode: [number] FormID rest
LINE_RE = re.compile(r"^(?:\d+\s+)?([0-9a-fA-F]{8})\s+(.+)$")
# "running text" mode: several records on one line, split at the next "<number> <FormID>".
RECORD_RE = re.compile(
    r"(?<![0-9A-Za-z])(?:\d{1,3}\s+)?([0-9a-fA-F]{8})\s+(.+?)"
    r"(?=\s+\d{1,3}\s+[0-9a-fA-F]{8}\s|\s*$)",
    re.S,
)


# ------------------------------------------------------------------ helpers
class TableReader(HTMLParser):
    """Collects the text of every cell (td/th) of every table row (tr)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self._row = None
        self._cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def to_text(page: str) -> str:
    page = re.sub(r"(?is)<(script|style).*?</\1>", " ", page)
    page = re.sub(r"(?i)<br\s*/?>|</(p|div|li|tr|h\d|pre)>", "\n", page)
    page = re.sub(r"(?i)</t[dh]>", " ", page)
    return html.unescape(re.sub(r"<[^>]+>", "", page))


def split_rest(rest: str):
    """'Riverwood リバーウッド 2 Town 町' -> ('Riverwood', 2, 'Town')."""
    rest = " ".join(rest.split())
    start = next((i for i, c in enumerate(rest) if ord(c) > 127), None)
    if start is None:
        return None
    t = TYPE_RE.search(rest[start:])
    if not t:
        return None
    return rest[:start].strip(), int(t.group(1)), t.group(2).strip()


# ------------------------------------------------------------ three readers
def mode_table(page: str):
    p = TableReader()
    p.feed(page)
    items, skipped = [], []
    for cells in p.rows:
        idx = next((i for i, c in enumerate(cells) if HEX8.match(c)), None)
        if idx is None:
            continue  # header or another table
        try:
            name = cells[idx + 1]
            type_id = int(cells[idx + 3])
            type_name = cells[idx + 4]
        except (IndexError, ValueError):
            skipped.append(" | ".join(cells))
            continue
        items.append((cells[idx], name, type_id, type_name))
    return items, skipped


def mode_lines(page: str):
    items, skipped = [], []
    for row in to_text(page).splitlines():
        row = " ".join(row.split())
        m = LINE_RE.match(row)
        if not m:
            continue
        r = split_rest(m.group(2))
        if r:
            items.append((m.group(1), *r))
        else:
            skipped.append(row)
    return items, skipped


def mode_running(page: str):
    text = " ".join(to_text(page).split())
    items, skipped = [], []
    for m in RECORD_RE.finditer(text):
        r = split_rest(m.group(2))
        if r:
            items.append((m.group(1), *r))
        else:
            skipped.append(m.group(0)[:120])
    return items, skipped


def extract(page: str):
    """Runs the three readers and returns the one that found the most markers."""
    candidates = []
    for name, fn in (("table", mode_table), ("lines", mode_lines), ("running text", mode_running)):
        items, skipped = fn(page)
        candidates.append((len(items), name, items, skipped))
    candidates.sort(key=lambda c: c[0], reverse=True)
    _, name, items, skipped = candidates[0]
    return name, items, skipped


def build(items):
    seen = {}
    for form_id, name, type_id, type_name in items:
        form_id = form_id.upper()
        if form_id in seen:
            continue
        seen[form_id] = {
            "formId": form_id,
            "name": name,
            "typeId": type_id,
            "type": type_name,
            "plugin": PLUGINS.get(form_id[:2], "Unknown"),
        }
    return list(seen.values())


# ------------------------------------------------------------------- main
def download() -> str:
    req = urllib.request.Request(
        URL,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            charset = r.headers.get_content_charset() or "utf-8"
    except urllib.error.URLError as e:
        sys.exit(f"Could not download the page: {e}")
    return raw.decode(charset, errors="replace")


def diagnose(page: str) -> None:
    print("\n--- DIAGNOSIS ---")
    print(f"HTML size: {len(page)} characters")
    print(f"<table: {page.lower().count('<table')} | <tr: {page.lower().count('<tr')} | <pre: {page.lower().count('<pre')}")
    i = page.find("Riverwood")
    if i < 0:
        print("The word 'Riverwood' does NOT appear in the downloaded HTML (the page may differ")
        print("from what was expected: blocked, consent page or loaded by JavaScript).")
        print("Start of the page text:", " ".join(to_text(page).split())[:300])
    else:
        print("HTML around 'Riverwood':")
        print(repr(page[max(0, i - 250): i + 350]))
    print(f"\nThe full page was saved to: {DEBUG}")
    print("Send this excerpt (or the file) so the script can be adjusted.")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")  # keeps the Windows console from crashing on Japanese

    page = download()
    mode, items, skipped = extract(page)
    markers = build(items)

    for row in skipped[:10]:
        print("review:", row)
    if len(skipped) > 10:
        print(f"... and {len(skipped) - 10} more lines to review")

    if not markers:
        DEBUG.write_text(page, encoding="utf-8")
        print("No markers found. markers.json was NOT changed.")
        diagnose(page)
        sys.exit(1)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(markers, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Read via {mode}: {len(markers)} markers written to {OUTPUT}")

    if len(markers) != EXPECTED:
        DEBUG.write_text(page, encoding="utf-8")
        print(f"Warning: expected {EXPECTED}. The page was saved to {DEBUG} for checking.")


if __name__ == "__main__":
    main()
