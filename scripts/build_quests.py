"""Builds src/data/quests.json (list view) and src/data/quest-details.json
(walkthroughs and stage tables, loaded on demand by the app) for every quest of
Skyrim, Dawnguard and Dragonborn.

Usage (from the project root):
    python scripts/build_quests.py             # add --refresh to ignore the cache
                                               # add --limit 20 to test with a few quests

Source: UESP quest categories (Category:Skyrim-Quests, Dawnguard, Dragonborn),
one page per quest. Pages are cached in scripts/cache/, so the script is
resumable: if it stops, run it again and it continues from the cache.
The first run downloads several hundred pages (about 10-15 minutes).
"""
import re
import sys

from uesp_common import (DATA, category_members, clean, dlc_from_title, fetch_wiki, norm, one_line, parse,
                         setup_console, slug, table_records, write_json)

OUT_LIST = DATA / "quests.json"
OUT_DETAIL = DATA / "quest-details.json"

ROOT_CATEGORIES = [
    ("Category:Skyrim-Quests", "Skyrim", "Miscellaneous"),
    ("Category:Dawnguard-Quests", "Dawnguard", "Dawnguard"),
    ("Category:Dragonborn-Quests", "Dragonborn", "Dragonborn"),
]
MAX_DEPTH = 3
SKIP_TITLES = re.compile(r"^(Category:|.*:Quests$|.*:Quest Index$|.*:Quest Objectives$)", re.I)

LABELS = {
    "giver": ("quest giver", "given by", "giver", "quest starter", "starts with", "start"),
    "locations": ("location", "locations", "starting location", "place", "where"),
    "reward": ("reward", "rewards"),
    "questId": ("quest id", "id", "editor id", "questid", "internal id"),
    "next": ("next quest", "next", "followed by", "leads to"),
}


def questline_name(cat: str, fallback: str) -> str:
    n = cat.split(":", 1)[-1]
    n = re.sub(r"^(Skyrim|Dawnguard|Dragonborn)-", "", n)
    n = re.sub(r"-?Quests?$", "", n)
    n = n.replace("-", " ").strip()
    return "Main Quest" if n == "Main" else (n or fallback)


def collect(refresh: bool):
    """Returns {page title: (dlc, questline)}; more specific categories win."""
    found = {}
    for root, dlc, fallback in ROOT_CATEGORIES:
        seen, stack = set(), [(root, 0, fallback)]
        while stack:
            cat, depth, line = stack.pop()
            if cat in seen:
                continue
            seen.add(cat)
            try:
                pages, subcats = category_members(cat, refresh)
            except Exception as e:  # noqa: BLE001
                print(f"! {cat}: {e}")
                continue
            for p in pages:
                if SKIP_TITLES.match(p):
                    continue
                if p not in found or (found[p][1] == fallback and line != fallback):
                    found[p] = (dlc, line)
            if depth < MAX_DEPTH:
                for s in subcats:
                    stack.append((s, depth + 1, questline_name(s, line)))
        print(f"{root}: {sum(1 for v in found.values() if v[0] == dlc)} quest pages so far")
    return found


def parse_label(text: str):
    m = re.match(r"^([A-Za-z][A-Za-z ()/]{1,30}?)\s*:\s*(.+)$", text)
    if not m:
        return None
    label = m.group(1).strip().lower()
    for key, names in LABELS.items():
        if label in names:
            return key, m.group(2).strip()
    return None


def read_quest(html: str, title: str):
    """Returns (list entry fields, detail dict) for one quest page."""
    doc = parse(html)
    f = {"giver": "", "locations": [], "reward": "", "questId": "", "next": ""}
    summary = ""

    def put(key, value):
        value = one_line(value)
        if not value:
            return
        if key == "locations":
            for part in re.split(r"\s*(?:;|\n|\band\b|,)\s*", value):
                part = part.strip(" .")
                if part and part not in f["locations"] and len(part) < 60:
                    f["locations"].append(part)
        elif not f[key]:
            f[key] = value

    quick, walk, stages, notes = [], [], [], []
    mode, cur = None, None  # current section: quick / walk / stages / notes / None
    seen_h2 = False

    for b in doc.blocks:
        kind = b[0]
        if kind == "h":
            name = b[2].lower()
            seen_h2 = True
            if "quick" in name and "walkthrough" in name:
                mode, cur = "quick", None
            elif "detailed" in name and "walkthrough" in name:
                mode, cur = "walk", None
            elif "walkthrough" in name:
                mode, cur = "walk", {"heading": "", "paragraphs": []}
                walk.append(cur)
            elif "stages" in name or "journal" in name or "objectives" in name:
                mode, cur = "stages", None
            elif name.startswith("notes") or name in ("bugs", "trivia"):
                mode, cur = "notes", None
            elif mode == "walk":
                cur = {"heading": b[2], "paragraphs": []}
                walk.append(cur)
            else:
                mode, cur = None, None
            continue

        if kind == "table":
            head, rows = table_records(b[1])
            if head and any("stage" in h or "index" in h for h in head) and any(
                    "entry" in h or "journal" in h or "text" in h or "description" in h for h in head):
                si = next(i for i, h in enumerate(head) if "stage" in h or "index" in h)
                ti = next(i for i, h in enumerate(head)
                          if "entry" in h or "journal" in h or "text" in h or "description" in h)
                for r in rows:
                    if max(si, ti) >= len(r):
                        continue
                    m = re.search(r"\d+", r[si]["t"])
                    if not m:
                        continue
                    text = one_line(r[ti]["t"])
                    blob = " ".join(c["t"] for c in r).lower()
                    stages.append({"stage": int(m.group()), "finishes": "finish" in blob or "completes" in blob,
                                   "text": text})
            elif not seen_h2:  # info box at the top: two-column label / value rows
                for r in b[1]["rows"]:
                    if len(r) >= 2:
                        lab = one_line(r[0]["t"]).rstrip(":").lower()
                        for key, names in LABELS.items():
                            if lab in names:
                                put(key, r[1]["t"])
            continue

        text = b[1]
        lab = parse_label(text)
        if lab and not seen_h2:
            put(*lab)
            continue
        if kind == "p" and not summary and not seen_h2 and len(text) > 40:
            summary = one_line(text)
        if mode == "quick" and kind == "li":
            quick.append(one_line(text))
        elif mode == "notes" and kind == "li":
            notes.append(one_line(text))
        elif mode == "walk" and kind in ("p", "li"):
            if cur is None:
                cur = {"heading": "", "paragraphs": []}
                walk.append(cur)
            cur["paragraphs"].append(one_line(text))
        elif mode == "notes" and kind == "p":
            notes.append(one_line(text))

    walk = [w for w in walk if w["paragraphs"]]
    low = html.lower()
    radiant = bool(re.search(r"\bradiant\b", summary, re.I)) or "radiant quest" in low[:4000]
    return f, summary, radiant, {"quick": quick, "walkthrough": walk, "stages": stages, "notes": notes}


def main() -> None:
    setup_console()
    refresh = "--refresh" in sys.argv
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    found = collect(refresh)
    if not found:
        print("No quest pages found (category listing failed). quests.json was NOT changed.")
        sys.exit(1)

    titles = sorted(found)[:limit] if limit else sorted(found)
    quests, details, failed, ids = [], {}, [], set()
    for n, title in enumerate(titles, 1):
        html, src = fetch_wiki(title, refresh)
        if n % 25 == 0 or n == len(titles):
            print(f"  {n}/{len(titles)} pages processed")
        if html is None:
            failed.append((title, src))
            continue
        dlc, line = found[title]
        dlc = dlc if dlc != "Skyrim" else dlc_from_title(title)
        fields, summary, radiant, detail = read_quest(html, title)
        name = re.sub(r"\s*\((quest|[a-z ]*quest)\)$", "", title.split(":", 1)[-1], flags=re.I)
        qid = slug(f"{dlc}-{name}")
        base, k = qid, 2
        while qid in ids:
            qid, k = f"{base}-{k}", k + 1
        ids.add(qid)
        quests.append({
            "id": qid, "name": name, "questline": line, "dlc": dlc, "summary": summary,
            "giver": fields["giver"], "locations": fields["locations"], "reward": fields["reward"],
            "questId": fields["questId"], "next": fields["next"], "radiant": radiant,
        })
        if detail["quick"] or detail["walkthrough"] or detail["stages"] or detail["notes"]:
            details[qid] = detail

    if not quests:
        print("Every download failed. Nothing was written.")
        for t, e in failed[:5]:
            print("  ", t, e)
        sys.exit(1)

    quests.sort(key=lambda q: q["name"].lower())
    write_json(OUT_LIST, quests)
    write_json(OUT_DETAIL, details)

    print(f"\n{len(quests)} quests written to {OUT_LIST}")
    print(f"{len(details)} walkthroughs written to {OUT_DETAIL}")
    for dlc in ("Skyrim", "Dawnguard", "Dragonborn"):
        print(f"  {sum(q['dlc'] == dlc for q in quests):5d}  {dlc}")
    print(f"  without summary: {sum(not q['summary'] for q in quests)}  without giver: "
          f"{sum(not q['giver'] for q in quests)}  without quest ID: {sum(not q['questId'] for q in quests)}  "
          f"without walkthrough: {len(quests) - len(details)}")
    if failed:
        print(f"\n{len(failed)} pages could not be downloaded (run again to retry):")
        for t, e in failed[:10]:
            print("  ", t, e)
    if sum(not q["summary"] and not q["giver"] for q in quests) > len(quests) // 2:
        print("\nMost quests came out empty: the page layout is probably different from what the script expects.")
        print("Send two or three files from scripts/cache/ (uesp-skyrim-unbound.html, for example).")


if __name__ == "__main__":
    main()
