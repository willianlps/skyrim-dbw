import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import Fuse from "fuse.js";
import data from "../data/npcs.json";
import type { Dlc, Npc } from "../types";
import { countBy, FiltersPanel, OptionList } from "../components/Filters";
import SearchBox from "../components/SearchBox";
import { useNav } from "../nav";
import { useIncremental } from "../hooks/useIncremental";

const npcs = data as unknown as Npc[];
const DLC_ORDER: Dlc[] = ["Skyrim", "Dawnguard", "Dragonborn", "Hearthfire", "Creation Club"];

type NpcType = "marriable" | "follower" | "unique";

/** "Unique" = named NPCs that are neither marriage candidates nor followers. */
function matchesType(n: Npc, type: NpcType): boolean {
  if (type === "marriable") return n.marriable;
  if (type === "follower") return n.follower;
  return !n.marriable && !n.follower;
}

export default function NpcsView({
  filtersSlot,
  initialQuery,
}: {
  filtersSlot: HTMLElement | null;
  initialQuery: string;
}) {
  const { go } = useNav();
  const [query, setQuery] = useState(initialQuery);
  const [type, setType] = useState<string | null>(null);
  const [dlc, setDlc] = useState<string | null>(null);
  const [area, setArea] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const fuse = useMemo(
    () =>
      new Fuse(npcs, {
        keys: [
          { name: "name", weight: 3 },
          { name: "role", weight: 1.5 },
          { name: "place", weight: 1.5 },
          { name: "area", weight: 1 },
          { name: "race", weight: 1 },
          { name: "description", weight: 0.7 },
        ],
        threshold: 0.28,
        ignoreLocation: true,
      }),
    []
  );

  const types = useMemo(
    () =>
      (
        [
          ["marriable", "Marriable"],
          ["follower", "Follower"],
          ["unique", "Unique"],
        ] as [NpcType, string][]
      ).map(([value, label]) => ({
        value,
        label,
        count: npcs.filter((n) => matchesType(n, value)).length,
      })),
    []
  );

  const dlcs = useMemo(() => {
    const counts = new Map(countBy(npcs, (n) => n.dlc));
    return DLC_ORDER.filter((d) => counts.has(d)).map((d) => ({
      value: d,
      count: counts.get(d) ?? 0,
    }));
  }, []);

  const areas = useMemo(
    () => countBy(npcs, (n) => n.area).map(([value, count]) => ({ value, count })),
    []
  );

  const results = useMemo(() => {
    const q = query.trim();
    let list = q
      ? fuse.search(q).map((r) => r.item)
      : [...npcs].sort((a, b) => a.name.localeCompare(b.name));
    if (type) list = list.filter((n) => matchesType(n, type as NpcType));
    if (dlc) list = list.filter((n) => n.dlc === dlc);
    if (area) list = list.filter((n) => n.area === area);
    return list;
  }, [query, type, dlc, area, fuse]);

  const { visible, hasMore, sentinel } = useIncremental(results);

  useEffect(() => {
    listRef.current?.scrollTo({ top: 0 });
  }, [query, type, dlc, area]);

  function clearFilters() {
    setType(null);
    setDlc(null);
    setArea(null);
  }

  if (npcs.length === 0) {
    return (
      <div className="empty-big">
        <h2>No NPCs loaded</h2>
        <p>
          Run <code>python scripts/build_npcs.py</code> to generate <code>src/data/npcs.json</code>.
        </p>
      </div>
    );
  }

  const filtersPanel = (
    <FiltersPanel
      active={type !== null || dlc !== null || area !== null}
      onClear={clearFilters}
    >
      <OptionList title="Type" allLabel="All NPCs" options={types} value={type} onChange={setType} />
      <OptionList
        title="Game / DLC"
        allLabel="All"
        options={dlcs}
        value={dlc}
        onChange={setDlc}
      />
      <OptionList title="Area" allLabel="All" options={areas} value={area} onChange={setArea} />
    </FiltersPanel>
  );

  return (
    <div className="view">
      <header className="view-head">
        <h1>NPCs</h1>
        <p className="muted">
          {results.length.toLocaleString("en-US")} of {npcs.length.toLocaleString("en-US")} · click an
          NPC to see where to find them
        </p>
      </header>

      <SearchBox
        value={query}
        onChange={setQuery}
        placeholder="Search by name, role, place or area…"
      />

      <div className="cards" ref={listRef}>
        {results.length === 0 && <div className="empty">No NPCs found with these filters.</div>}

        {visible.map((n) => {
          const open = openId === n.id;
          const info = n.followerInfo;
          const flags = [
            info?.blades && "Blades",
            info?.steward && "Steward (Hearthfire)",
            info?.essential && "Essential",
            n.dead && "Can be found dead",
          ].filter(Boolean) as string[];

          return (
            <article className={`card${open ? " open" : ""}`} key={n.id}>
              <button
                className="card-head"
                aria-expanded={open}
                onClick={() => setOpenId(open ? null : n.id)}
              >
                <div className="card-main">
                  <div className="card-title">{n.name}</div>
                  <div className="card-sub">
                    {n.marriable && <span className="badge marriage">♥ Marriable</span>}
                    {n.follower && <span className="badge follower">⚔ Follower</span>}
                    {!n.marriable && !n.follower && <span className="badge">★ Unique</span>}
                    {n.dlc !== "Skyrim" && <span className="badge dlc">{n.dlc}</span>}
                    {n.race && (
                      <span className="badge race">{n.sex ? `${n.race} · ${n.sex}` : n.race}</span>
                    )}
                    <span className="plugin">
                      {[n.place, n.area].filter(Boolean).join(" · ")}
                    </span>
                  </div>
                  {n.role && <p className="card-desc">{n.role}</p>}
                </div>
                {info && info.maxLevel !== null && (
                  <div className="level">
                    <div className="level-num">{info.maxLevel}</div>
                    <div className="level-label">max level</div>
                  </div>
                )}
              </button>

              {open && (
                <div className="detail">
                  {n.description && (
                    <section>
                      <h4>Who and where</h4>
                      <p>{n.description}</p>
                    </section>
                  )}

                  {info && (
                    <>
                      {info.howToObtain && (
                        <section>
                          <h4>How to recruit</h4>
                          <p>{info.howToObtain}</p>
                        </section>
                      )}
                      {info.description && info.description !== n.description && (
                        <section>
                          <h4>Follower notes</h4>
                          <p>{info.description}</p>
                        </section>
                      )}
                      <div className="facts">
                        {info.skills.length > 0 && (
                          <div>
                            <div className="fact-label">Primary skills</div>
                            <div className="fact-value">{info.skills.join(", ")}</div>
                          </div>
                        )}
                        <div>
                          <div className="fact-label">Max level</div>
                          <div className="fact-value">
                            {info.maxLevel !== null ? info.maxLevel : info.maxLevelText || "—"}
                          </div>
                        </div>
                        {info.moral && (
                          <div>
                            <div className="fact-label">Morality</div>
                            <div className="fact-value">{info.moral}</div>
                          </div>
                        )}
                        <div>
                          <div className="fact-label">Follower group</div>
                          <div className="fact-value">{info.group}</div>
                        </div>
                      </div>
                    </>
                  )}

                  {flags.length > 0 && (
                    <div className="flags">
                      {flags.map((f) => (
                        <span className="flag" key={f}>
                          {f}
                        </span>
                      ))}
                    </div>
                  )}

                  {(n.place || n.area) && (
                    <div className="actions">
                      <button onClick={() => go("locations", n.place || n.area)}>
                        Find “{n.place || n.area}” in Locations
                      </button>
                    </div>
                  )}
                </div>
              )}
            </article>
          );
        })}

        {hasMore && <div ref={sentinel} className="sentinel" />}
      </div>

      {filtersSlot && createPortal(filtersPanel, filtersSlot)}
    </div>
  );
}
