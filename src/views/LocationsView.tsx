import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import Fuse from "fuse.js";
import data from "../data/locations.json";
import type { Dlc, Location } from "../types";
import { countBy, FilterSelect, FiltersPanel, OptionList } from "../components/Filters";
import SearchBox from "../components/SearchBox";
import { useCopy } from "../components/Toast";
import { useIncremental } from "../hooks/useIncremental";

const locations = data as unknown as Location[];
const DLC_ORDER: Dlc[] = ["Skyrim", "Dawnguard", "Dragonborn", "Hearthfire", "Creation Club"];

export default function LocationsView({
  filtersSlot,
  initialQuery,
}: {
  filtersSlot: HTMLElement | null;
  initialQuery: string;
}) {
  const copy = useCopy();
  const [query, setQuery] = useState(initialQuery);
  const [dlc, setDlc] = useState<string | null>(null);
  const [kind, setKind] = useState("");
  const [category, setCategory] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const fuse = useMemo(
    () =>
      new Fuse(locations, {
        keys: [
          { name: "name", weight: 3 },
          { name: "cellId", weight: 2 },
          { name: "formId", weight: 2 },
          { name: "category", weight: 1 },
          { name: "region", weight: 1 },
          { name: "description", weight: 0.7 },
        ],
        threshold: 0.28,
        ignoreLocation: true,
      }),
    []
  );

  const dlcs = useMemo(() => {
    const counts = new Map(countBy(locations, (l) => l.dlc));
    return DLC_ORDER.filter((d) => counts.has(d)).map((d) => ({
      value: d,
      count: counts.get(d) ?? 0,
    }));
  }, []);

  const categories = useMemo(
    () => countBy(locations, (l) => l.category).map(([value, count]) => ({ value, count })),
    []
  );

  const results = useMemo(() => {
    const q = query.trim();
    let list = q
      ? fuse.search(q).map((r) => r.item)
      : [...locations].sort((a, b) => a.name.localeCompare(b.name));
    if (dlc) list = list.filter((l) => l.dlc === dlc);
    if (kind) list = list.filter((l) => l.kind === kind);
    if (category) list = list.filter((l) => l.category === category);
    return list;
  }, [query, dlc, kind, category, fuse]);

  const { visible, hasMore, sentinel } = useIncremental(results);

  useEffect(() => {
    listRef.current?.scrollTo({ top: 0 });
  }, [query, dlc, kind, category]);

  function clearFilters() {
    setDlc(null);
    setKind("");
    setCategory(null);
  }

  if (locations.length === 0) {
    return (
      <div className="empty-big">
        <h2>No locations loaded</h2>
        <p>
          Run <code>python scripts/build_locations.py</code> to generate{" "}
          <code>src/data/locations.json</code>.
        </p>
      </div>
    );
  }

  const filtersPanel = (
    <FiltersPanel active={dlc !== null || kind !== "" || category !== null} onClear={clearFilters}>
      <OptionList
        title="Game / DLC"
        allLabel="All"
        options={dlcs}
        value={dlc}
        onChange={setDlc}
      />
      <FilterSelect
        title="Kind"
        value={kind}
        onChange={setKind}
        options={[
          { value: "", label: "Exterior and interior" },
          { value: "exterior", label: "Exterior only" },
          { value: "interior", label: "Interior only" },
        ]}
      />
      <OptionList
        title="Category"
        allLabel="All"
        options={categories}
        value={category}
        onChange={setCategory}
      />
    </FiltersPanel>
  );

  return (
    <div className="view">
      <header className="view-head">
        <h1>Locations</h1>
        <p className="muted">
          {results.length.toLocaleString("en-US")} of {locations.length.toLocaleString("en-US")} ·
          exteriors use <code>player.moveto</code>, interiors use <code>coc</code>
        </p>
      </header>

      <SearchBox
        value={query}
        onChange={setQuery}
        placeholder="Search by name, description, FormID or cell ID…"
      />

      <div className="cards" ref={listRef}>
        {results.length === 0 && <div className="empty">Nothing found with these filters.</div>}

        {visible.map((l) => (
          <article className="card" key={l.id}>
            <div className="card-body">
              <div className="card-main">
                <div className="card-title">{l.name}</div>
                <div className="card-sub">
                  <span className={`badge ${l.kind}`}>
                    {l.kind === "interior" ? "Interior" : "Exterior"}
                  </span>
                  <span className="badge">{l.category}</span>
                  {l.dlc !== "Skyrim" && <span className="badge dlc">{l.dlc}</span>}
                  {l.region && <span className="plugin">{l.region}</span>}
                </div>
                <p className="card-desc">
                  {l.description ||
                    (l.kind === "interior" ? "Interior cell." : "No description available.")}
                </p>
              </div>

              <div className="card-side">
                {l.formId && <code className="formid">{l.formId}</code>}
                {l.cellId && <code className="formid">{l.cellId}</code>}
                <div className="actions">
                  {l.formId && (
                    <button
                      className="primary"
                      onClick={() => copy(`player.moveto ${l.formId}`, "Command")}
                    >
                      Copy moveto
                    </button>
                  )}
                  {l.cellId && (
                    <button className="primary" onClick={() => copy(`coc ${l.cellId}`, "Command")}>
                      Copy coc
                    </button>
                  )}
                  {l.formId && (
                    <button onClick={() => copy(l.formId ?? "", "FormID")}>Copy ID</button>
                  )}
                </div>
              </div>
            </div>
          </article>
        ))}

        {hasMore && <div ref={sentinel} className="sentinel" />}
      </div>

      {filtersSlot && createPortal(filtersPanel, filtersSlot)}
    </div>
  );
}
