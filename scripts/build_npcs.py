"""Builds src/data/npcs.json: uniquely named NPCs of Skyrim, Dawnguard and
Dragonborn, with a short "who and where" description, plus flags for marriage
candidates and followers.

Usage (from the project root):
    python scripts/fetch_followers.py      # once, creates src/data/followers.json
    python scripts/build_npcs.py           # add --refresh to ignore the cache

Sources (UESP): the People pages (and the per-hold People pages they link to),
the Marriage page, and src/data/followers.json for follower details.
Needs internet only for this step.
"""
import json
import re
import sys

from uesp_common import (DATA, dlc_from_title, fetch_wiki, heading_chain, norm, one_line, parse,
                         setup_console, slug, table_records, write_json)

OUTPUT = DATA / "npcs.json"
FOLLOWERS = DATA / "followers.json"
# On UESP every People page lives in the Skyrim: namespace (Dawnguard:/Dragonborn: titles only redirect).
# Skyrim:People links to one "<place> People" page per city, town, fort, ruin, DLC location...
ROOT_PAGES = ["Skyrim:People", "Skyrim:Dawnguard NPCs"]
ROOT_DLC = {"Skyrim:Dawnguard NPCs": "Dawnguard"}

# Places that only exist in a DLC (used when the page itself has no DG/DB tag).
AREA_DLC = {
    "Dawnguard": ["Fort Dawnguard", "Volkihar", "Castle Volkihar", "Dayspring Canyon", "Darkfall Cave",
                  "Arkngthamz", "Dimhollow", "Forgotten Vale", "Sunderstone Gorge", "Dawnguard"],
    "Dragonborn": ["Raven Rock", "Tel Mithryn", "Skaal Village", "Thirsk", "Solstheim", "Fahlbtharz",
                   "Bloodskal", "Hrothmund", "Brodir Grove", "Apocrypha", "Bloodmoon", "Frostmoon",
                   "Saering", "Benkongerike", "Kolbjorn", "Isinfier", "Nchardak", "Ramshackle", "Tree Stone",
                   "Wind Stone", "Miraak", "Temple of Miraak", "Altar of Miraak", "Skaal"],
    "Hearthfire": ["Lakeview Manor", "Heljarchen Hall", "Windstad Manor", "Hearthfire"],
}
MARRIAGE_PAGES = ["Skyrim:Marriage"]
MAX_SUBPAGES = 400

GENERIC_HEADS = {"people", "npcs", "notes", "see also", "references", "contents", "navigation", "overview",
                 "residents", "characters", "other", "miscellaneous", "external links", "trivia", "bugs"}

TAGS = {"DG": "Dawnguard", "DB": "Dragonborn", "HF": "Hearthfire", "CC": "Creation Club"}

RACES = ["Altmer", "Argonian", "Bosmer", "Breton", "Dunmer", "Imperial", "Khajiit", "Nord", "Orc",
         "Redguard", "Snow Elf", "Falmer", "Dremora", "Dwarf", "Draugr", "Vampire"]


def area_from_title(title: str) -> str:
    """'Skyrim:Whiterun People' -> 'Whiterun'; 'Skyrim:People' -> ''."""
    t = title.split(":", 1)[-1]
    t = re.sub(r"\bPeople\b|\bNPCs?\b", "", t).strip()
    return t


def looks_like_name(s: str) -> bool:
    if not s or len(s) > 45 or s[0].islower() or len(s.split()) > 6:
        return False
    if re.search(r"\d{3,}|^\W", s):
        return False
    return norm(s) not in {norm(g) for g in GENERIC_HEADS}


def area_dlc(area: str, default: str) -> str:
    low = area.lower()
    for dlc, names in AREA_DLC.items():
        if any(n.lower() in low for n in names):
            return dlc
    return default


def tag_dlc(text: str, default: str) -> str:
    for tag, dlc in TAGS.items():
        if re.search(r"(?<![A-Za-z])" + tag + r"(?![A-Za-z])", text):
            return dlc
    return default


def find_race(text: str) -> str:
    for r in RACES:
        if re.search(r"\b" + r + r"s?\b", text, re.I):
            return r
    return ""


def is_marriage_cell(cell: dict) -> bool:
    blob = " ".join(cell["alts"]).lower() + " " + cell["t"].lower()
    return "marri" in blob or "wedding" in blob or "amulet of mara" in blob


def read_people(html: str, title: str, default_dlc: str):
    """Yields dicts with name/area/place/role/race/sex/marriable/dlc from a People page."""
    doc = parse(html)
    page_area = area_from_title(title)
    out = []

    def head_place(i):
        chain = [h for h in heading_chain(doc.blocks, i) if h]
        for h in reversed(chain):
            if norm(h) not in {norm(g) for g in GENERIC_HEADS}:
                return h
        return ""

    for i, b in enumerate(doc.blocks):
        if b[0] == "table":
            head, rows = table_records(b[1])
            if head is None:
                head = []
            name_i = next((k for k, h in enumerate(head) if h in ("name", "npc", "npcname", "character", "person")), None)
            if name_i is None:  # headerless table: the column with the most links holds the names
                width = max((len(r) for r in rows), default=0)
                links = [sum(1 for r in rows if k < len(r) and r[k]["links"]) for k in range(width)]
                if width >= 2 and links and max(links) >= max(2, len(rows) // 2):
                    name_i = links.index(max(links))
                    head = ["name" if k == name_i else ("location" if k == 0 else "notes") for k in range(width)]
            if name_i is None:
                continue

            def col(*names):
                return next((k for k, h in enumerate(head) if h in names), None)

            race_i, sex_i = col("race"), col("sex", "gender")
            where_i = col("location", "place", "residence", "home", "where", "cell")
            role_i = col("role", "class", "occupation", "notes", "description", "services", "type", "faction")
            for r in rows:
                if name_i >= len(r):
                    continue
                name = one_line(r[name_i]["t"].split("\n")[0])
                if not looks_like_name(name):
                    continue
                get = lambda k: one_line(r[k]["t"]) if k is not None and k < len(r) else ""
                text_all = " ".join(c["t"] for c in r)
                out.append({
                    "name": name, "area": get(where_i) if page_area in ("Dawnguard", "Dragonborn") else (page_area or head_place(i)),
                    "place": "" if page_area in ("Dawnguard", "Dragonborn") else get(where_i),
                    "role": get(role_i), "race": get(race_i) or find_race(text_all),
                    "sex": get(sex_i), "marriable": any(is_marriage_cell(c) for c in r),
                    "dlc": tag_dlc(text_all, area_dlc(page_area or head_place(i), default_dlc)), "text": text_all,
                })
        elif b[0] == "li":
            m = re.match(r"^([A-Z][^-–—:(]{1,44}?)\s*(?:\(([^)]*)\))?\s*(?:[-–—:]\s*(.*))?$", b[1])
            if not m or not looks_like_name(m.group(1).strip()):
                continue
            name = m.group(1).strip()
            rest = " ".join(x for x in (m.group(2), m.group(3)) if x)
            out.append({
                "name": name, "area": page_area or "", "place": head_place(i), "role": one_line(rest),
                "race": find_race(rest), "sex": "", "marriable": is_marriage_cell({"alts": [], "t": b[1]}),
                "dlc": tag_dlc(b[1], area_dlc(page_area or head_place(i), default_dlc)), "text": b[1],
            })
    return out, doc


def subpages(doc, root_title: str):
    """Per-place People pages linked from a People page (any namespace prefix)."""
    found = []
    for _, title in doc.links:
        if re.match(r"^(Skyrim|Dawnguard|Dragonborn|Hearthfire):", title) and re.search(r"\bPeople$", title):
            if title != root_title and title not in found:
                found.append(title)
    return found[:MAX_SUBPAGES]


def marriage_names(refresh: bool):
    names = set()
    for title in MARRIAGE_PAGES:
        html, src = fetch_wiki(title, refresh)
        if html is None:
            print(f"! {title}: could not download ({src}); marriage flags come from the People pages only")
            continue
        doc = parse(html)
        for b in doc.blocks:
            if b[0] == "table":
                head, rows = table_records(b[1])
                if head and any(h in ("name", "npc", "spouse", "candidate") for h in head):
                    i = next(k for k, h in enumerate(head) if h in ("name", "npc", "spouse", "candidate"))
                    for r in rows:
                        if i < len(r) and looks_like_name(one_line(r[i]["t"].split("\n")[0])):
                            names.add(norm(r[i]["t"].split("\n")[0]))
        # Candidate lists are usually links inside list items / tables under a "candidates" heading.
        for i, b in enumerate(doc.blocks):
            if b[0] == "li" and "candidate" in " ".join(heading_chain(doc.blocks, i)).lower():
                m = re.match(r"^([A-Z][^-–—:(]{1,44}?)\s*(?:[-–—:(]|$)", b[1])
                if m and looks_like_name(m.group(1).strip()):
                    names.add(norm(m.group(1)))
        print(f"{title}: {len(names)} marriage candidates")
    return names


def follower_data():
    if not FOLLOWERS.exists():
        print("! src/data/followers.json not found: run python scripts/fetch_followers.py for follower details")
        return {}
    out = {}
    for f in json.loads(FOLLOWERS.read_text(encoding="utf-8")):
        out.setdefault(norm(f["name"]), []).append(f)
    return out


def to_follower_info(f: dict) -> dict:
    return {
        "kind": f.get("kind", "npc"), "group": f.get("group", ""), "howToObtain": f.get("howToObtain", ""),
        "description": f.get("description", ""), "skills": f.get("skills", []),
        "maxLevel": f.get("maxLevel"), "maxLevelText": f.get("maxLevelText", ""), "moral": f.get("moral", ""),
        "blades": bool(f.get("blades")), "steward": bool(f.get("steward")), "essential": bool(f.get("essential")),
    }


def describe(n: dict) -> str:
    who = n["role"] or ("Follower" if n["follower"] else "Unique character")
    who = who.rstrip(".")
    where = ", ".join(x for x in (n["place"], n["area"]) if x and x.lower() != "unknown")
    s = f"{who}."
    if where:
        s += f" Found at {where}."
    return s


def main() -> None:
    setup_console()
    refresh = "--refresh" in sys.argv

    raw = []
    queue = [(t, ROOT_DLC.get(t, dlc_from_title(t))) for t in ROOT_PAGES]
    done = set()
    while queue:
        title, dlc = queue.pop(0)
        if title in done:
            continue
        done.add(title)
        html, src = fetch_wiki(title, refresh)
        if html is None:
            print(f"! {title}: could not download ({src})")
            continue
        people, doc = read_people(html, title, dlc)
        print(f"{title}: {len(people)} entries ({src})")
        raw.extend(people)
        if title in ROOT_PAGES:
            queue.extend((t, dlc_from_title(t)) for t in subpages(doc, title))

    married = marriage_names(refresh)
    followers = follower_data()

    npcs = {}
    for r in raw:
        key = (norm(r["name"]), r["dlc"])
        cur = npcs.get(key)
        if cur is None:
            npcs[key] = dict(r)
        else:  # merge duplicates: keep the first, fill blanks
            for f in ("area", "place", "role", "race", "sex"):
                if not cur[f] and r[f]:
                    cur[f] = r[f]
            cur["marriable"] = cur["marriable"] or r["marriable"]

    result = []
    for (nkey, dlc), r in npcs.items():
        fl = followers.get(nkey, [])
        info = to_follower_info(next((f for f in fl if f.get("kind") != "creature"), fl[0])) if fl else None
        is_follower = bool(fl) or bool(re.search(r"\bfollower\b", r["role"], re.I))
        marriable = r["marriable"] or nkey in married or any(f.get("marry") for f in fl)
        n = {
            "id": slug(f'{r["name"]}-{dlc}'), "name": r["name"], "dlc": dlc, "area": r["area"],
            "place": r["place"], "role": r["role"], "description": "", "marriable": marriable,
            "follower": is_follower, "race": r["race"] or (fl[0].get("race", "") if fl else ""),
            "sex": r["sex"] or (fl[0].get("sex", "") if fl else ""),
            "dead": bool(re.search(r"found dead|dead body|corpse", r["text"], re.I)),
            "followerInfo": info,
        }
        n["description"] = describe(n)
        result.append(n)

    # Followers that never showed up on the People pages (creatures, quest followers...)
    listed = {k[0] for k in npcs}
    for nkey, fl in followers.items():
        if nkey in listed:
            continue
        f = fl[0]
        text = f.get("description") or f.get("howToObtain") or "Follower"
        result.append({
            "id": slug(f'{f["name"]}-{f.get("group", "")}'), "name": f["name"], "dlc": "Skyrim", "area": "",
            "place": "", "role": f.get("group", "Follower"), "description": one_line(text)[:240],
            "marriable": bool(f.get("marry")), "follower": True, "race": f.get("race", ""),
            "sex": f.get("sex", ""), "dead": False, "followerInfo": to_follower_info(f),
        })

    if not result:
        print("No NPCs found: npcs.json was NOT changed.")
        print("Send the files in scripts/cache/ (uesp-skyrim-people*.html) so the parser can be adjusted.")
        sys.exit(1)

    ids = set()
    for n in result:
        base, k = n["id"], 2
        while n["id"] in ids:
            n["id"], k = f"{base}-{k}", k + 1
        ids.add(n["id"])
    result.sort(key=lambda n: n["name"].lower())
    write_json(OUTPUT, result)

    print(f"\n{len(result)} NPCs written to {OUTPUT}")
    print(f"  marriable: {sum(n['marriable'] for n in result)}  followers: {sum(n['follower'] for n in result)}  "
          f"unique (neither): {sum(not n['marriable'] and not n['follower'] for n in result)}")
    for dlc in ("Skyrim", "Dawnguard", "Dragonborn", "Hearthfire", "Creation Club"):
        c = sum(n["dlc"] == dlc for n in result)
        if c:
            print(f"  {c:5d}  {dlc}")
    print(f"  without area: {sum(not n['area'] for n in result)}  without race: {sum(not n['race'] for n in result)}")


if __name__ == "__main__":
    main()
