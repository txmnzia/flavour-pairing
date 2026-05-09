export interface Ingredient {
  id: number;
  name: string;
  freq: number;
}

export interface Cuisine {
  id: number;
  name: string;
  recipeCount: number;
}

export interface Pairing {
  ingredient: Ingredient;
  npmi: number;
  cooccurrence: number;
  /** How many of the selected ingredients this candidate pairs with */
  coverage: number;
}

export type DbStatus =
  | { state: "idle" }
  | { state: "loading"; progress: string }
  | { state: "ready" }
  | { state: "error"; message: string };
