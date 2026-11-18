export type Dlc = "Skyrim" | "Dawnguard" | "Dragonborn" | "Hearthfire" | "Creation Club";

/** An exterior place (with an optional map-marker FormID) or an interior cell (with a coc code). */
export interface Location {
  id: string;
  name: string;
  kind: "exterior" | "interior";
  /** Cave, Town, Inn, Nordic Ruin... */
  category: string;
  /** City / hold the place belongs to, when known. */
  region: string;
  dlc: Dlc;
  /** Short description of where it is. */
  description: string;
  /** Map marker FormID, used with `player.moveto`. */
  formId?: string;
  /** Cell editor ID, used with `coc`. */
  cellId?: string;
}

/** Extra data for NPCs that can be recruited (from the followers table). */
export interface FollowerInfo {
  kind: "npc" | "creature" | "quest";
  group: string;
  howToObtain: string;
  description: string;
  skills: string[];
  maxLevel: number | null;
  maxLevelText: string;
  moral: string;
  blades: boolean;
  steward: boolean;
  essential: boolean;
}

export interface Npc {
  id: string;
  name: string;
  dlc: Dlc;
  /** City, town or region the NPC lives in. */
  area: string;
  /** Building or spot inside the area. */
  place: string;
  /** Role, trainer tier, skills... */
  role: string;
  /** Short "who and where" description. */
  description: string;
  marriable: boolean;
  follower: boolean;
  race: string;
  sex: string;
  dead: boolean;
  followerInfo: FollowerInfo | null;
}

export interface Quest {
  id: string;
  name: string;
  /** Main Quest, Companions, Miscellaneous, Dawnguard... */
  questline: string;
  dlc: Dlc;
  summary: string;
  giver: string;
  locations: string[];
  reward: string;
  /** Quest editor ID, used with the console (setstage, sqs...). */
  questId: string;
  next: string;
  radiant: boolean;
}

export interface QuestSection {
  heading: string;
  paragraphs: string[];
}

export interface QuestStage {
  stage: number;
  finishes: boolean;
  text: string;
}

/** Heavy quest data, loaded on demand when a quest is opened. */
export interface QuestDetail {
  quick: string[];
  walkthrough: QuestSection[];
  stages: QuestStage[];
  notes: string[];
}
