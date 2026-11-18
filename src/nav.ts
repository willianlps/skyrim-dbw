import { createContext, useContext } from "react";

export type SectionId = "npcs" | "locations" | "quests";

interface Nav {
  /** Jump to a section, optionally pre-filling its search box. */
  go: (section: SectionId, query?: string) => void;
}

export const NavContext = createContext<Nav>({ go: () => {} });

export function useNav(): Nav {
  return useContext(NavContext);
}
