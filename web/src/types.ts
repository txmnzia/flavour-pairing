export interface Ingredient {
  id: number;
  name: string;
  freq: number;
}

export interface Pairing {
  ingredient: Ingredient;
  score: number;
  coverage: number;
}

export interface CategoryLane {
  category: string;
  pairings: Pairing[];
}

export type DbStatus =
  | { state: "idle" }
  | { state: "loading"; progress: string }
  | { state: "ready" }
  | { state: "error"; message: string };
