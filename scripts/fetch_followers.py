"""Builds src/data/followers.json with Skyrim's followers: name, race, how to
recruit, primary skills, max level, etc.

Usage (from the project root):
    python scripts/fetch_followers.py

Needs internet only for this step; the app itself works offline.

The script reads the tables of the UESP follower page by COLUMN NAME (Name,
Description, Primary Skills, Max Level...), so it keeps working if the column
order changes. If it finds nothing it does NOT overwrite the current
followers.json and saves the page to scripts/followers_debug.html.
"""
import json
import re
import sys
import unicodedata
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

PAGE_TITLE = "Skyrim:Follower"
URL_API = "https://en.uesp.net/w/api.php?" + urllib.parse.urlencode(
    {"action": "parse", "page": PAGE_TITLE, "prop": "text", "format": "json",
     "formatversion": "2", "redirects": "1"}
)
URL_PAGE = "https://en.uesp.net/wiki/" + PAGE_TITLE

HERE = Path(__file__).resolve().parent
OUTPUT = HERE.parent / "src" / "data" / "followers.json"
DEBUG = HERE / "followers_debug.html"
MIN_EXPECTED = 80

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120 Safari/537.36"
}

RACES = [
    ("High Elf", "Altmer"), ("Altmer", "Altmer"), ("Wood Elf", "Bosmer"),
    ("Bosmer", "Bosmer"), ("Dark Elf", "Dunmer"), ("Dunmer", "Dunmer"),
    ("Snow Elf", "Snow Elf"), ("Falmer", "Falmer"), ("Argonian", "Argonian"),
    ("Breton", "Breton"), ("Imperial", "Imperial"), ("Khajiit", "Khajiit"),
    ("Nord", "Nord"), ("Orsimer", "Orc"), ("Orc", "Orc"),
    ("Redguard", "Redguard"), ("Dremora", "Dremora"),
]

TRUTHY = {"yes", "y", "true", "check", "checkmark", "✓", "✔", "x"}


# ------------------------------------------------------------------ helpers
def clean(t: str) -> str:
    """Normalises spaces, drops footnote marks like [1], keeps line breaks."""
    t = t.replace("\xa0", " ")
    t = re.sub(r"\[\d+\]", "", t)
    rows = [" ".join(l.split()) for l in t.split("\n")]
    return "\n".join(l for l in rows if l).strip()


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "unnamed"


def truthy(txt: str) -> bool:
    t = txt.strip().lower()
    return t in TRUTHY or t.startswith("yes") or "✓" in t or "✔" in t


def find_race(txt: str) -> str:
    txt = txt[:100]
    best = None
    for key, canon in RACES:
        m = re.search(r"\b" + re.escape(key) + r"s?\b", txt, re.I)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), canon)
    return best[1] if best else ""


def find_sex(txt: str) -> str:
    if re.search(r"\bfemale\b", txt, re.I):
        return "Female"
    if re.search(r"\bmale\b", txt, re.I):
        return "Male"
    return ""


def parse_level(txt: str):
    m = re.search(r"\d+", txt)
    return (int(m.group()) if m else None), " ".join(txt.split())


# ------------------------------------------------------------- HTML reader
HEADINGS = {"h2": 0, "h3": 1, "h4": 2}


class PageReader(HTMLParser):
    """Collects each table with the h2/h3/h4 headings in force when it opens."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []
        self.heads = ["", "", ""]
        self._skip = None
        self._h = None
        self._hbuf = []
        self._depth = 0
        self._tab = None
        self._row = None
        self._cell = None
        self._kind = None
        self._alts = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if self._skip:
            if tag == self._skip[0]:
                self._skip[1] += 1
            return
        cls = a.get("class") or ""
        if tag in ("style", "script", "sup") or (tag == "span" and "mw-editsection" in cls):
            self._skip = [tag, 1]
            return
        if tag in HEADINGS:
            self._h = HEADINGS[tag]
            self._hbuf = []
        elif tag == "table":
            if self._depth == 0:
                self._tab = {"heads": list(self.heads), "rows": []}
            self._depth += 1
        elif self._depth == 1:
            if tag == "tr":
                self._row = []
            elif tag in ("td", "th") and self._row is not None:
                self._cell, self._kind, self._alts = [], tag, []
            elif tag in ("br", "li") and self._cell is not None:
                self._cell.append("\n")
            elif tag == "img" and self._cell is not None:
                alt = (a.get("alt") or "").strip()
                if alt:
                    self._alts.append(alt)

    def handle_endtag(self, tag):
        if self._skip:
            if tag == self._skip[0]:
                self._skip[1] -= 1
                if self._skip[1] == 0:
                    self._skip = None
            return
        if tag in HEADINGS and self._h == HEADINGS[tag]:
            self.heads[self._h] = clean("".join(self._hbuf))
            for i in range(self._h + 1, 3):
                self.heads[i] = ""
            self._h = None
        elif tag == "table" and self._depth > 0:
            self._depth -= 1
            if self._depth == 0 and self._tab is not None:
                self.tables.append(self._tab)
                self._tab = None
        elif self._depth == 1:
            if tag in ("td", "th") and self._cell is not None and self._row is not None:
                text = "".join(self._cell)
                if not text.strip() and self._alts:
                    text = " ".join(self._alts)
                self._row.append((self._kind, text))
                self._cell = None
            elif tag == "tr" and self._row is not None:
                if self._row and self._tab is not None:
                    self._tab["rows"].append(self._row)
                self._row = None

    def handle_data(self, d):
        if self._skip:
            return
        if self._h is not None:
            self._hbuf.append(d)
        if self._cell is not None:
            self._cell.append(d)


def read_table(tab):
    """Returns (normalised header, rows of clean text)."""
    head, rows = None, []
    for row in tab["rows"]:
        if all(k == "th" for k, _ in row):
            if len(row) == 1 and head is not None:
                continue  # sub-group title inside the table
            head = [norm(clean(t)) for _, t in row]
        else:
            rows.append([clean(t) for _, t in row])
    return head, rows


# --------------------------------------------------------------- extraction
def record_kind(heads, head) -> str:
    if "recruitment" in head or "pethf" in head:
        return "creature"
    if "quest" in (heads[0] or "").lower() or "quests" in head:
        return "quest"
    last_head = next((h for h in reversed(heads) if h), "").lower()
    if "creature" in last_head and "people" not in last_head:
        return "creature"
    return "npc"


def extract(page: str):
    p = PageReader()
    p.feed(page)
    p.close()

    followers, irregular, skipped = [], [], []
    seen_values = {k: set() for k in ("marry", "blades", "stewardhf", "essential")}
    used = set()

    for tab in p.tables:
        head, rows = read_table(tab)
        if not head or "name" not in head or "maxlevel" not in head:
            if rows:
                skipped.append((tab["heads"], head))
            continue

        heads = tab["heads"]
        kind = record_kind(heads, head)
        parts = [h for h in heads[1:] if h]
        if kind == "quest":
            group = " · ".join(["Quest followers"] + parts)
        else:
            group = " · ".join(parts) if parts else (heads[0] or "Other")

        for cells in rows:
            if len(cells) == 1:
                continue
            if len(cells) != len(head):
                irregular.append(" | ".join(cells)[:140])
                continue
            c = dict(zip(head, cells))
            name = c.get("name", "").split("\n")[0].strip()
            if not name:
                continue

            description = " ".join((c.get("description") or c.get("notes") or "").split())
            how = []
            if c.get("recruitment"):
                how.append(" ".join(c["recruitment"].split()))
            if c.get("prerequisitequest"):
                how.append("Prerequisite quest: " + " ".join(c["prerequisitequest"].split()))
            if c.get("quests"):
                how.append("Quests: " + " ".join(c["quests"].split()))

            skills = [s.strip() for s in re.split(r"[\n,;/]+", c.get("primaryskills", "")) if s.strip()]
            level, level_text = parse_level(c.get("maxlevel", ""))
            for key in seen_values:
                if c.get(key):
                    seen_values[key].add(c[key].strip()[:20])

            base = slug(name + "-" + group)
            sid, n = base, 2
            while sid in used:
                sid, n = f"{base}-{n}", n + 1
            used.add(sid)

            followers.append({
                "id": sid,
                "name": name,
                "kind": kind,
                "section": heads[0],
                "group": group,
                "race": "" if kind == "creature" else find_race(description),
                "sex": "" if kind == "creature" else find_sex(description),
                "howToObtain": " — ".join(how),
                "description": description,
                "skills": skills,
                "maxLevel": level,
                "maxLevelText": level_text,
                "moral": " ".join(c.get("moral", "").split()),
                "marry": truthy(c.get("marry", "")),
                "blades": truthy(c.get("blades", "")),
                "steward": truthy(c.get("stewardhf", "")),
                "essential": truthy(c.get("essential", "")),
            })
    return followers, irregular, skipped, seen_values


# ------------------------------------------------------------------- main
def download():
    erros = []
    try:
        req = urllib.request.Request(URL_API, headers=UA)
        with urllib.request.urlopen(req, timeout=30) as r:
            j = json.loads(r.read().decode("utf-8", "replace"))
        text = j["parse"]["text"]
        if isinstance(text, dict):
            text = text.get("*", "")
        return text, "UESP API"
    except Exception as e:  # noqa: BLE001
        erros.append(f"API: {e}")
    try:
        req = urllib.request.Request(URL_PAGE, headers=UA)
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8", "replace"), "UESP page"
    except Exception as e:  # noqa: BLE001
        erros.append(f"page: {e}")
    sys.exit("Could not download the data:\n  " + "\n  ".join(erros))


def diagnose(page: str, skipped) -> None:
    print("\n--- DIAGNOSIS ---")
    print(f"HTML size: {len(page)} characters | tables: {page.lower().count('<table')}")
    for heads, head in skipped[:8]:
        print("table skipped under", [h for h in heads if h], "with columns:", head)
    print(f"The page was saved to: {DEBUG}")
    print("Send this text (or the file) so the script can be adjusted.")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    page, origin = download()
    followers, irregular, skipped, seen_values = extract(page)

    if not followers:
        DEBUG.write_text(page, encoding="utf-8")
        print("No followers found. followers.json was NOT changed.")
        diagnose(page, skipped)
        sys.exit(1)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(followers, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Source: {origin}")
    print(f"{len(followers)} followers written to {OUTPUT}")
    by_type, by_group = {}, {}
    for s in followers:
        by_type[s["kind"]] = by_type.get(s["kind"], 0) + 1
        by_group[s["group"]] = by_group.get(s["group"], 0) + 1
    print("By type:", by_type)
    for g, n in by_group.items():
        print(f"  {n:3d}  {g}")
    no_race = sum(1 for s in followers if s["kind"] != "creature" and not s["race"])
    print(f"Without a detected race (NPCs/quest): {no_race}")
    for k, v in seen_values.items():
        if v:
            print(f"Values seen in '{k}':", sorted(v)[:8])
    if irregular:
        print(f"\nRows whose column count differs from the header: {len(irregular)} (skipped)")
        for l in irregular[:10]:
            print("  review:", l)
    if len(followers) < MIN_EXPECTED or irregular:
        DEBUG.write_text(page, encoding="utf-8")
        print(f"\nWarning: result below expectations or rows were skipped. Page saved to {DEBUG}")
        diagnose(page, skipped)


if __name__ == "__main__":
    main()
