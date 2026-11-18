"""Builds src/data/locations.json: every exterior place and interior cell, for
Skyrim, Dawnguard, Dragonborn (and Hearthfire / Creation Club cells when found).

Usage (from the project root):
    python scripts/fetch_markers.py        # once, creates src/data/markers.json
    python scripts/build_locations.py      # add --refresh to ignore the cache
                                           # add --no-interiors to skip skyrimcodex.com

Sources
  * src/data/markers.json     exterior map markers (FormID -> player.moveto)
  * UESP "Places" pages       short descriptions of where each place is
  * skyrimcodex.com/location  interior cells (cell ID -> coc)

Needs internet only for this step. Please check the terms of use of every site
before redistributing the generated data.
"""
import json
import re
import sys

from uesp_common import (DATA, fetch_url, fetch_wiki, heading_chain, norm, one_line, parse, setup_console,
                         slug, table_records, write_json)

OUTPUT = DATA / "locations.json"
MARKERS = DATA / "markers.json"
CODEX_URL = "https://www.skyrimcodex.com/location"
PLACE_PAGES = ["Skyrim:Places", "Dawnguard:Places", "Dragonborn:Places"]

PLUGIN_DLC = {
    "Skyrim.esm": "Skyrim", "Update.esm": "Skyrim", "Dawnguard.esm": "Dawnguard",
    "HearthFires.esm": "Hearthfire", "Dragonborn.esm": "Dragonborn",
}

# coc cell-ID prefix -> DLC
CELL_DLC = [("DLC1", "Dawnguard"), ("DLC2", "Dragonborn"), ("BYOH", "Hearthfire"), ("cc", "Creation Club")]

# Cell-ID / name prefix -> region (cities and towns)
REGIONS = [
    "Whiterun", "Solitude", "Riften", "Windhelm", "Markarth", "Falkreath", "Winterhold", "Dawnstar",
    "Morthal", "Riverwood", "Rorikstead", "Ivarstead", "Dragon Bridge", "Karthwasten", "Shor's Stone",
    "Darkwater Crossing", "Helgen", "Raven Rock", "Skaal Village", "Tel Mithryn", "Thirsk", "Fort Dawnguard",
]

CATEGORY_WORDS = [
    ("Inn", ("inn", "tavern", "cauldron", "tankard", "bannered mare", "bee and barb", "retching netch",
             "winking skeever", "sleeping giant", "silver-blood inn", "braidwood inn", "vilemyr", "nightgate")),
    ("Shop", ("shop", "store", "smithy", "forge", "alchemist", "apothecary", "emporium", "stables")),
    ("House", ("house", "home", "manor", "cottage", "residence", "hearthfire")),
    ("Temple", ("temple", "shrine", "chapel", "hall of the dead", "college")),
    ("Ruin", ("ruin", "barrow", "crypt", "tomb", "sanctuary", "vault", "forebears", "holding")),
    ("Cave", ("cave", "cavern", "grotto", " den", "lair")),
    ("Mine", ("mine", "quarry")),
    ("Fort", ("fort", "keep", "castle", "palace", "garrison", "barracks", "watchtower", "tower", "citadel")),
    ("Dungeon", ("dungeon", "prison", "jail", "catacomb", "cellar", "basement")),
    ("Camp", ("camp", "hideout")),
]


def category_for(name: str, cell_id: str = "") -> str:
    low = (name + " " + cell_id).lower()
    for cat, words in CATEGORY_WORDS:
        if any(w in low for w in words):
            return cat
    return "Interior"


def split_camel(s: str) -> str:
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def dlc_for_cell(cell_id: str) -> str:
    for prefix, dlc in CELL_DLC:
        if cell_id.startswith(prefix) and (prefix != "cc" or cell_id[2:3].isupper() or cell_id[2:3].isdigit()):
            return dlc
    return "Skyrim"


def region_for(*texts: str) -> str:
    for t in texts:
        low = t.lower().replace(" ", "")
        for r in REGIONS:
            if r.lower().replace(" ", "") in low:
                return r
    return ""


# ----------------------------------------------------------- UESP "Places"
SEP = re.compile(r"\s+[-–—:]\s+|\s*:\s+")


def read_places(html: str, dlc: str):
    """Returns {normalised name: (name, description, category)} from a Places page."""
    doc = parse(html)
    out = {}

    def add(name, desc, cat):
        name = one_line(name)
        if not name or len(name) > 60:
            return
        desc = one_line(desc)
        old = out.get(norm(name))
        if old is None or (not old[1] and desc):
            out[norm(name)] = (name, desc, cat)

    for i, b in enumerate(doc.blocks):
        chain = [h for h in heading_chain(doc.blocks, i) if h]
        cat = chain[-1] if chain else ""
        if b[0] == "li":
            parts = SEP.split(b[1], maxsplit=1)
            if len(parts) == 2 and len(parts[0]) <= 60:
                add(parts[0], parts[1], cat)
        elif b[0] == "table":
            head, rows = table_records(b[1])
            if not head:
                continue
            name_i = next((k for k, h in enumerate(head) if h in ("name", "place", "location", "cell")), None)
            desc_i = next((k for k, h in enumerate(head) if h in ("description", "notes", "details", "info", "where")), None)
            if name_i is None or desc_i is None:
                continue
            for r in rows:
                if len(r) > max(name_i, desc_i):
                    add(r[name_i]["t"].split("\n")[0], r[desc_i]["t"], cat)
    return out


# ------------------------------------------------------------ skyrimcodex
CELL_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_]{5,}$")


def read_codex(html: str):
    """Returns [(name, cell id)] from a page listing interior cells."""
    doc = parse(html)
    found = []
    for b in doc.blocks:
        if b[0] != "table":
            continue
        head, rows = table_records(b[1])
        name_i = id_i = None
        if head:
            id_i = next((k for k, h in enumerate(head) if "cellid" in h or h in ("id", "editorid", "code", "console", "coc")), None)
            name_i = next((k for k, h in enumerate(head) if h in ("name", "location", "cell", "place")), None)
        for r in rows:
            texts = [c["t"].split("\n")[0].strip() for c in r]
            cid = name = ""
            if id_i is not None and id_i < len(texts):
                cid = re.sub(r"^coc\s+", "", texts[id_i], flags=re.I).strip()
                if name_i is not None and name_i < len(texts):
                    name = texts[name_i]
            else:  # unknown header: look for something shaped like an editor ID
                for k, t in enumerate(texts):
                    t2 = re.sub(r"^coc\s+", "", t, flags=re.I)
                    if CELL_ID.match(t2) and not t2.islower() and cid == "":
                        cid = t2
                        name = next((x for j, x in enumerate(texts) if j != k and x), "")
            if cid and CELL_ID.match(cid):
                found.append((name or split_camel(cid), cid))
    # Also accept "coc <id>" snippets outside tables.
    for b in doc.blocks:
        if b[0] in ("li", "p"):
            m = re.search(r"\bcoc\s+([A-Za-z][A-Za-z0-9_]{5,})", b[1])
            if m:
                found.append((split_camel(m.group(1)), m.group(1)))
    return found


def codex_pages(first_html: str):
    """Pagination links found on the first page (page=N or /page/N)."""
    urls = set()
    for m in re.finditer(r'href="([^"]*?(?:[?&]page=\d+|/page/\d+)[^"]*)"', first_html):
        href = m.group(1).replace("&amp;", "&")
        if href.startswith("/"):
            href = "https://www.skyrimcodex.com" + href
        if href.startswith("http"):
            urls.add(href)
    return sorted(urls, key=lambda u: int(re.findall(r"\d+", u)[-1]))[:400]


# -------------------------------------------------------------------- main
def main() -> None:
    setup_console()
    refresh = "--refresh" in sys.argv
    interiors = "--no-interiors" not in sys.argv
    locations, used = [], set()

    def add(loc):
        key = (loc["kind"], loc.get("formId") or loc.get("cellId") or norm(loc["name"]))
        if key in used:
            return
        used.add(key)
        loc["id"] = slug(f'{loc["kind"]}-{loc["name"]}-{key[1]}')
        locations.append(loc)

    # 1. UESP descriptions
    places = {}
    for title in PLACE_PAGES:
        html, src = fetch_wiki(title, refresh)
        if html is None:
            print(f"! {title}: could not download ({src})")
            continue
        dlc = "Dawnguard" if title.startswith("Dawn") else "Dragonborn" if title.startswith("Dragon") else "Skyrim"
        got = read_places(html, dlc)
        print(f"{title}: {len(got)} places with descriptions ({src})")
        for k, v in got.items():
            places.setdefault(k, (*v, dlc))

    # 2. Exterior markers
    markers = []
    if MARKERS.exists():
        markers = json.loads(MARKERS.read_text(encoding="utf-8"))
    else:
        print("! src/data/markers.json not found: run python scripts/fetch_markers.py first")
    matched = set()
    for m in markers:
        key = norm(m["name"])
        hit = places.get(key)
        if hit:
            matched.add(key)
        add({
            "name": m["name"], "kind": "exterior", "category": m.get("type") or "Place",
            "region": "", "dlc": PLUGIN_DLC.get(m.get("plugin", ""), "Skyrim"),
            "description": hit[1] if hit else "", "formId": m["formId"],
        })
    print(f"Exteriors from markers: {len(markers)} ({len(matched)} with a description)")

    # 3. Places that are not map markers (towns, regions, landmarks...)
    extra = 0
    for key, (name, desc, cat, dlc) in places.items():
        if key in matched or not desc:
            continue
        before = len(locations)
        cat = cat[:-1] if cat.endswith("s") and not cat.endswith("ss") else cat
        add({"name": name, "kind": "exterior", "category": cat or "Place", "region": "",
             "dlc": dlc, "description": desc})
        extra += len(locations) - before
    print(f"Extra places from UESP (no map marker): {extra}")

    # 4. Interiors
    n_int = 0
    if interiors:
        html, src = fetch_url(CODEX_URL, refresh)
        if html is None:
            print(f"! skyrimcodex.com: could not download ({src}); interiors skipped")
        else:
            pages = [html]
            for u in codex_pages(html):
                h, _ = fetch_url(u, refresh)
                if h:
                    pages.append(h)
            seen_ids = set()
            for h in pages:
                for name, cid in read_codex(h):
                    if cid in seen_ids:
                        continue
                    seen_ids.add(cid)
                    region = region_for(cid, name)
                    cat = category_for(name, cid)
                    hit = places.get(norm(name))
                    desc = hit[1] if hit and hit[1] else (f"{cat} in {region}." if region and cat != "Interior" else
                                                          f"Interior in {region}." if region else "")
                    before = len(locations)
                    add({"name": name, "kind": "interior", "category": cat, "region": region,
                         "dlc": dlc_for_cell(cid), "description": desc, "cellId": cid})
                    n_int += len(locations) - before
            print(f"Interiors: {n_int} from {len(pages)} page(s)")
            if n_int == 0:
                print("  No interior cells recognised. The site layout may differ from what the script expects;")
                print("  send the files in scripts/cache/ named url-https-www-skyrimcodex-com-location*.html")

    if not locations:
        print("Nothing found: locations.json was NOT changed.")
        sys.exit(1)

    locations.sort(key=lambda l: (l["name"].lower(), l["kind"]))
    write_json(OUTPUT, locations)
    by = {}
    for l in locations:
        by[(l["kind"], l["dlc"])] = by.get((l["kind"], l["dlc"]), 0) + 1
    print(f"\n{len(locations)} locations written to {OUTPUT}")
    for k, n in sorted(by.items()):
        print(f"  {n:5d}  {k[0]:8s} {k[1]}")


if __name__ == "__main__":
    main()
