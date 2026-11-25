/*
 * "Was ist in Planung": models the workshop is working on, as the shop shows them on
 * /in-planung. Edited here; a new entry goes live with the next deploy.
 */

export type RoadmapStage = "idee" | "konstruktion" | "probedruck" | "bald";

export const ROADMAP_STAGES: readonly {
  code: RoadmapStage;
  label: string;
  text: string;
}[] = [
  {
    code: "idee",
    label: "Idee",
    text: "Vorbild gewählt, Unterlagen werden gesammelt",
  },
  {
    code: "konstruktion",
    label: "In Konstruktion",
    text: "Das Modell entsteht am Rechner",
  },
  {
    code: "probedruck",
    label: "Probedruck",
    text: "Erste Teile aus dem Drucker, Feinschliff",
  },
  { code: "bald", label: "Bald im Shop", text: "Fotos und Preise folgen" },
];

export type RoadmapEntry = {
  name: string;
  /** Scales it is planned in, e.g. ["H0", "TT"]. */
  scales: readonly string[];
  stage: RoadmapStage;
  /** One sentence about the model. */
  note?: string;
  /** Rough timing, e.g. "Frühjahr 2027". */
  when?: string;
};

/** Planned models, most advanced first. Empty: the page invites suggestions instead. */
export const ROADMAP: readonly RoadmapEntry[] = [];
