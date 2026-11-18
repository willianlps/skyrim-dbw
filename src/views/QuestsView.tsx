import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import Fuse from "fuse.js";
import data from "../data/quests.json";
import type { Dlc, Quest, QuestDetail } from "../types";
import { countBy, FilterSelect, FiltersPanel, OptionList } from "../components/Filters";
import SearchBox from "../components/SearchBox";
import { useCopy } from "../components/Toast";
import { useNav } from "../nav";
import { useIncremental } from "../hooks/useIncremental";

const quests = data as unknown as Quest[];
const DLC_ORDER: Dlc[] = ["Skyrim", "Dawnguard", "Dragonborn", "Hearthfire", "Creation Club"];

// Walkthroughs and stage tables are big, so they live in their own file and
// are only loaded the first time a quest is opened.
let detailsPromise: Promise<Record<string, QuestDetail>> | null = null;
function loadDetails(): Promise<Record<string, QuestDetail>> {
  if (!detailsPromise) {
    detailsPromise = import("../data/quest-details.json").then(
      (m) => ((m as { default?: unknown }).default ?? m) as unknown as Record<string, QuestDetail>
    );
  }
  return detailsPromise;
}

function QuestDetails({ quest }: { quest: Quest }) {
  const copy = useCopy();
  const [detail, setDetail] = useState<QuestDetail | null | undefined>(undefined);

  useEffect(() => {
    let alive = true;
    loadDetails()
      .then((all) => alive && setDetail(all[quest.id] ?? null))
      .catch(() => alive && setDetail(null));
    return () => {
      alive = false;
    };
  }, [quest.id]);

  if (detail === undefined) return <p className="muted">Loading walkthrough…</p>;
  if (detail === null) return <p className="muted">No walkthrough data for this quest.</p>;

  return (
    <>
      {detail.quick.length > 0 && (
        <section>
          <h4>Quick walkthrough</h4>
          <ol className="steps">
            {detail.quick.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ol>
        </section>
      )}

      {detail.walkthrough.length > 0 && (
        <section>
          <h4>Detailed walkthrough</h4>
          {detail.walkthrough.map((sec, i) => (
            <div className="walk" key={i}>
              {sec.heading && <h5>{sec.heading}</h5>}
              {sec.paragraphs.map((p, j) => (
                <p key={j}>{p}</p>
              ))}
            </div>
          ))}
        </section>
      )}

      {detail.notes.length > 0 && (
        <section>
          <h4>Notes</h4>
          <ul className="steps">
            {detail.notes.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ul>
        </section>
      )}

      {detail.stages.length > 0 && (
        <section>
          <h4>Quest stages</h4>
          <table className="stages">
            <thead>
              <tr>
                <th>Stage</th>
                <th>Journal entry</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {detail.stages.map((s, i) => (
                <tr key={i} className={s.finishes ? "finish" : ""}>
                  <td className="stage-num">{s.stage}</td>
                  <td>
                    {s.text}
                    {s.finishes && <span className="flag">Finishes quest</span>}
                  </td>
                  <td>
                    {quest.questId && (
                      <button
                        className="mini"
                        onClick={() => copy(`setstage ${quest.questId} ${s.stage}`, "Command")}
                      >
                        setstage
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </>
  );
}

export default function QuestsView({
  filtersSlot,
  initialQuery,
}: {
  filtersSlot: HTMLElement | null;
  initialQuery: string;
}) {
  const copy = useCopy();
  const { go } = useNav();
  const [query, setQuery] = useState(initialQuery);
  const [dlc, setDlc] = useState<string | null>(null);
  const [questline, setQuestline] = useState<string | null>(null);
  const [radiant, setRadiant] = useState("");
  const [openId, setOpenId] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const fuse = useMemo(
    () =>
      new Fuse(quests, {
        keys: [
          { name: "name", weight: 3 },
          { name: "questId", weight: 2 },
          { name: "giver", weight: 1.5 },
          { name: "locations", weight: 1.5 },
          { name: "questline", weight: 1 },
          { name: "summary", weight: 1 },
          { name: "reward", weight: 0.7 },
        ],
        threshold: 0.28,
        ignoreLocation: true,
      }),
    []
  );

  const dlcs = useMemo(() => {
    const counts = new Map(countBy(quests, (q) => q.dlc));
    return DLC_ORDER.filter((d) => counts.has(d)).map((d) => ({
      value: d,
      count: counts.get(d) ?? 0,
    }));
  }, []);

  const questlines = useMemo(
    () => countBy(quests, (q) => q.questline).map(([value, count]) => ({ value, count })),
    []
  );

  const results = useMemo(() => {
    const q = query.trim();
    let list = q
      ? fuse.search(q).map((r) => r.item)
      : [...quests].sort((a, b) => a.name.localeCompare(b.name));
    if (dlc) list = list.filter((x) => x.dlc === dlc);
    if (questline) list = list.filter((x) => x.questline === questline);
    if (radiant === "only") list = list.filter((x) => x.radiant);
    if (radiant === "hide") list = list.filter((x) => !x.radiant);
    return list;
  }, [query, dlc, questline, radiant, fuse]);

  const { visible, hasMore, sentinel } = useIncremental(results);

  useEffect(() => {
    listRef.current?.scrollTo({ top: 0 });
  }, [query, dlc, questline, radiant]);

  function clearFilters() {
    setDlc(null);
    setQuestline(null);
    setRadiant("");
  }

  if (quests.length === 0) {
    return (
      <div className="empty-big">
        <h2>No quests loaded</h2>
        <p>
          Run <code>python scripts/build_quests.py</code> to generate <code>src/data/quests.json</code>{" "}
          and <code>src/data/quest-details.json</code>.
        </p>
      </div>
    );
  }

  const filtersPanel = (
    <FiltersPanel
      active={dlc !== null || questline !== null || radiant !== ""}
      onClear={clearFilters}
    >
      <OptionList title="Game / DLC" allLabel="All" options={dlcs} value={dlc} onChange={setDlc} />
      <FilterSelect
        title="Radiant quests"
        value={radiant}
        onChange={setRadiant}
        options={[
          { value: "", label: "Show all" },
          { value: "only", label: "Radiant only" },
          { value: "hide", label: "Hide radiant" },
        ]}
      />
      <OptionList
        title="Questline"
        allLabel="All"
        options={questlines}
        value={questline}
        onChange={setQuestline}
      />
    </FiltersPanel>
  );

  return (
    <div className="view">
      <header className="view-head">
        <h1>Quests</h1>
        <p className="muted">
          {results.length.toLocaleString("en-US")} of {quests.length.toLocaleString("en-US")} · click
          a quest for the walkthrough and stage numbers
        </p>
      </header>

      <SearchBox
        value={query}
        onChange={setQuery}
        placeholder="Search by name, giver, location, reward or quest ID…"
      />

      <div className="cards" ref={listRef}>
        {results.length === 0 && <div className="empty">No quests found with these filters.</div>}

        {visible.map((q) => {
          const open = openId === q.id;
          return (
            <article className={`card${open ? " open" : ""}`} key={q.id}>
              <button
                className="card-head"
                aria-expanded={open}
                onClick={() => setOpenId(open ? null : q.id)}
              >
                <div className="card-main">
                  <div className="card-title">{q.name}</div>
                  <div className="card-sub">
                    <span className="badge">{q.questline}</span>
                    {q.radiant && <span className="badge radiant">Radiant</span>}
                    {q.dlc !== "Skyrim" && <span className="badge dlc">{q.dlc}</span>}
                    {q.giver && <span className="plugin">From: {q.giver}</span>}
                  </div>
                  {q.summary && <p className="card-desc">{q.summary}</p>}
                </div>
              </button>

              {open && (
                <div className="detail">
                  <div className="facts">
                    {q.giver && (
                      <div>
                        <div className="fact-label">Quest giver</div>
                        <div className="fact-value">{q.giver}</div>
                      </div>
                    )}
                    {q.reward && (
                      <div>
                        <div className="fact-label">Reward</div>
                        <div className="fact-value">{q.reward}</div>
                      </div>
                    )}
                    {q.next && (
                      <div>
                        <div className="fact-label">Next quest</div>
                        <div className="fact-value">{q.next}</div>
                      </div>
                    )}
                    {q.questId && (
                      <div>
                        <div className="fact-label">Quest ID</div>
                        <div className="fact-value">
                          <code className="formid">{q.questId}</code>{" "}
                          <button className="mini" onClick={() => copy(q.questId, "Quest ID")}>
                            copy
                          </button>
                        </div>
                      </div>
                    )}
                  </div>

                  {q.locations.length > 0 && (
                    <section>
                      <h4>Locations</h4>
                      <div className="chip-row">
                        {q.locations.map((loc) => (
                          <button
                            key={loc}
                            className="chip-link"
                            title="Search in Locations"
                            onClick={() => go("locations", loc)}
                          >
                            {loc}
                          </button>
                        ))}
                      </div>
                    </section>
                  )}

                  {q.giver && (
                    <div className="actions">
                      <button onClick={() => go("npcs", q.giver)}>Search “{q.giver}” in NPCs</button>
                    </div>
                  )}

                  <QuestDetails quest={q} />
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
