/**
 * Mirrors `packages/backend/src/backend/schemas.py`.
 *
 * Hand-written rather than generated so the repo has no codegen step; the API
 * contract test (`packages/backend/tests/test_api.py`) is what keeps the two in
 * agreement. If you add a field, add it in both places.
 */

export interface SiteConfig {
  tile_size_m: number;
  depth_m: number;
  sand_fraction: number;
  clay_fraction: number;
  field_capacity_mm: number;
  wilting_point_mm: number;
  initial_active_c: number;
  initial_slow_c: number;
  initial_passive_c: number;
  initial_mineral_n: number;
}

export interface WeatherConfig {
  latitude_deg: number;
  mean_temperature_c: number;
  temperature_amplitude_c: number;
  annual_precipitation_mm: number;
  peak_radiation_mj_m2: number;
  years_of_variability: number;
  seed: number;
}

export interface MowingConfig {
  day_of_year: number;
  cut_height_m: number;
  removal_fraction: number;
  woody_kill_height_m: number;
}

export interface GrazingConfig {
  start_day: number;
  end_day: number;
  intake_fraction_per_day: number;
  return_fraction: number;
  min_height_m: number;
  woody_kill_height_m: number;
  woody_kill_fraction: number;
}

export interface FertilisationConfig {
  day_of_year: number;
  nitrogen_kg_m2: number;
}

export type ManagementPresetId =
  | "abandoned"
  | "extensive_meadow"
  | "intensive_meadow"
  | "pasture"
  | "custom";

export interface ManagementConfig {
  preset: ManagementPresetId;
  mowing: MowingConfig[];
  grazing: GrazingConfig[];
  fertilisation: FertilisationConfig[];
}

/** What stands on the tile at year zero, and the PFTs and seed rain it draws on. */
export interface VegetationConfig {
  include_forest: boolean;
  include_grassland: boolean;
  initial_sward_density_per_m2: number;
  initial_trees_per_tile: number;
  initial_tree_pft: string;
  initial_tree_dbh: number;
  external_seed_rain: Record<string, number>;
  tree_pft_overrides: Record<string, Record<string, number>>;
  grass_pft_overrides: Record<string, Record<string, number>>;
}

export interface ScenarioConfig {
  name: string;
  years: number;
  record_every_days: number;
  seed: number;
  site: SiteConfig;
  weather: WeatherConfig;
  management: ManagementConfig;
  vegetation: VegetationConfig;
}

export interface JobStatus {
  id: string;
  name: string;
  state: "queued" | "running" | "done" | "failed";
  progress: number;
  simulated_days: number;
  total_days: number;
  created_at: string;
  finished_at: string | null;
  error: string | null;
}

export type TileRecord = Record<string, number>;

export interface SimulationResults {
  id: string;
  scenario: ScenarioConfig;
  recorded_days: number[];
  years: number[];
  series: TileRecord[];
}

/** One cohort in the vertical stand diagram. */
export interface StandRow {
  pft: string;
  colour: string;
  n: number;
  dbh: number;
  height: number;
  crown_base: number;
  crown_diameter: number;
}

export interface SwardRow {
  pft: string;
  colour: string;
  plants: number;
  shoot_c: number;
  height: number;
  leaf_area: number;
}

export interface HistogramBin {
  lower: number;
  upper: number;
  stems: number;
}

export interface ProfileRecord {
  stand_profile?: StandRow[];
  sward_profile?: SwardRow[];
  dbh_histogram?: HistogramBin[];
}

/** One adjustable model parameter, as described by the backend. */
export interface ParameterSpec {
  name: string;
  group: string;
  unit: string;
  default: number | boolean;
  type: "number" | "boolean";
}

export interface ParameterPayload {
  model: "formind" | "grassmind";
  schema: ParameterSpec[];
  pfts: Array<Record<string, number | string | boolean>>;
}

export interface ManagementPreset {
  id: ManagementPresetId;
  label: string;
  description: string;
  mowing: MowingConfig[];
  grazing: GrazingConfig[];
  fertilisation: FertilisationConfig[];
}
