import { useCallback, useMemo, useState } from "react";
import logo from "./assets/logo.png";
import { SECTIONS } from "./categories";
import { NavContext, type SectionId } from "./nav";
import { ToastProvider } from "./components/Toast";
import LocationsView from "./views/LocationsView";
import NpcsView from "./views/NpcsView";
import QuestsView from "./views/QuestsView";
import locations from "./data/locations.json";
import npcs from "./data/npcs.json";
import quests from "./data/quests.json";

interface Pending {
  section: SectionId;
  query: string;
}

export default function App() {
  // The app opens straight on Locations.
  const [section, setSection] = useState<SectionId>("locations");
  // Sidebar element where the active view draws its filters.
  const [filtersSlot, setFiltersSlot] = useState<HTMLDivElement | null>(null);
  // Search handed over by another section (e.g. NPC -> its location).
  const [pending, setPending] = useState<Pending | null>(null);
  const [navKey, setNavKey] = useState(0);

  const counts = useMemo<Record<SectionId, number>>(
    () => ({ npcs: npcs.length, locations: locations.length, quests: quests.length }),
    []
  );

  const select = useCallback((next: SectionId) => {
    setPending(null);
    setSection(next);
  }, []);

  const go = useCallback((next: SectionId, query = "") => {
    setPending({ section: next, query });
    setNavKey((k) => k + 1);
    setSection(next);
  }, []);

  const nav = useMemo(() => ({ go }), [go]);
  const initialQuery = (id: SectionId) => (pending?.section === id ? pending.query : "");

  return (
    <NavContext.Provider value={nav}>
      <ToastProvider>
        <div className="app">
          <aside className="sidebar">
            <div className="brand">
              <img className="brand-mark" src={logo} alt="" />
              <span>
                <span className="brand-name">Skyrim DB-W</span>
                <span className="brand-sub">by willianlps</span>
              </span>
            </div>

            <nav className="nav">
              {SECTIONS.map((s) => (
                <button
                  key={s.id}
                  className={`nav-item${s.id === section ? " active" : ""}`}
                  onClick={() => select(s.id)}
                >
                  <span className="nav-icon">{s.icon}</span>
                  <span className="nav-label">{s.label}</span>
                  <span className="nav-count">{counts[s.id].toLocaleString("en-US")}</span>
                </button>
              ))}
            </nav>

            <div className="filters" ref={setFiltersSlot} />

            <div className="sidebar-foot">Skyrim SE/AE Database</div>
          </aside>

          <main className="main">
            {section === "npcs" && (
              <NpcsView key={navKey} filtersSlot={filtersSlot} initialQuery={initialQuery("npcs")} />
            )}
            {section === "locations" && (
              <LocationsView
                key={navKey}
                filtersSlot={filtersSlot}
                initialQuery={initialQuery("locations")}
              />
            )}
            {section === "quests" && (
              <QuestsView
                key={navKey}
                filtersSlot={filtersSlot}
                initialQuery={initialQuery("quests")}
              />
            )}
          </main>
        </div>
      </ToastProvider>
    </NavContext.Provider>
  );
}
