import type { SectionId } from "./nav";

export interface SectionDef {
  id: SectionId;
  label: string;
  icon: string;
}

// To add a new section: create its JSON in src/data, a view in src/views,
// list it here and render it in App.tsx.
export const SECTIONS: SectionDef[] = [
  { id: "npcs", label: "NPCs", icon: "☻" },
  { id: "locations", label: "Locations", icon: "⌖" },
  { id: "quests", label: "Quests", icon: "✦" },
];
