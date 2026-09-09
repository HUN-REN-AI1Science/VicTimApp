/**
 * Configuration panel — the region, and only the region.
 *
 * Everything here is true of every tile: one soil column's properties, one
 * climate, one grid, one set of plant functional types. Nothing that can differ
 * between two tiles is edited here. Land use — management and initial
 * vegetation — belongs to the tile, so it is edited on the Region tab against
 * the tile the map has selected. See `TileTypeEditor`.
 *
 * Grouped the way the upstream models group their own inputs — site, weather,
 * plant functional types — so that someone who has configured FORMIND or
 * GRASSMIND finds the same categories in the same order.
 */

import type { ParameterPayload, ScenarioConfig } from "../types";
import { NumberField } from "./fields";
import { ParameterForm } from "./ParameterForm";

type Patch = (update: (draft: ScenarioConfig) => void) => void;

/** `GridConfig` bounds nx and ny at 1..16 -- the API's only defence against a
 *  scenario that would run for hours. Clamp here so the form cannot submit a
 *  value the backend will reject. */
const clampTiles = (value: number) => Math.min(16, Math.max(1, Math.round(value)));

export function Sidebar({
  config,
  patch,
  treeParams,
  grassParams,
  onRun,
  running,
}: {
  config: ScenarioConfig;
  patch: Patch;
  treeParams: ParameterPayload | null;
  grassParams: ParameterPayload | null;
  onRun: () => void;
  running: boolean;
}) {
  const tiles = config.grid.nx * config.grid.ny;

  return (
    <aside className="sidebar">
      <h1>VicTim</h1>

      <details className="section">
        <summary>Run</summary>
        <div className="field">
          <label>scenario name</label>
          <input
            type="text"
            value={config.name}
            onChange={(event) => patch((d) => void (d.name = event.target.value))}
          />
        </div>
        <NumberField
          label="length"
          unit="years"
          step="1"
          value={config.years}
          onChange={(v) => patch((d) => void (d.years = Math.max(1, Math.round(v))))}
        />
        <NumberField
          label="record interval"
          unit="days"
          step="1"
          value={config.record_every_days}
          onChange={(v) => patch((d) => void (d.record_every_days = Math.max(1, Math.round(v))))}
        />
        <NumberField
          label="random seed"
          step="1"
          value={config.seed}
          onChange={(v) => patch((d) => void (d.seed = Math.round(v)))}
        />
      </details>

      <details className="section">
        <summary>Region</summary>
        <NumberField
          label="tiles across"
          step="1"
          value={config.grid.nx}
          onChange={(v) => patch((d) => void (d.grid.nx = clampTiles(v)))}
        />
        <NumberField
          label="tiles down"
          step="1"
          value={config.grid.ny}
          onChange={(v) => patch((d) => void (d.grid.ny = clampTiles(v)))}
        />
        <NumberField
          label="tile size"
          unit="m"
          value={config.grid.tile_size_m}
          onChange={(v) => patch((d) => void (d.grid.tile_size_m = v))}
        />
        <p className="hint">
          {config.grid.nx} × {config.grid.ny} = {tiles} tile{tiles === 1 ? "" : "s"},{" "}
          {((tiles * config.grid.tile_size_m ** 2) / 10000).toFixed(2)} ha. Every tile is
          simulated in full, so the run takes about that many times as long as one. What each
          tile <em>is</em> is set on the Region tab.
        </p>
        <div className="field">
          <label>seed dispersal</label>
          <select
            value={config.grid.dispersal}
            onChange={(e) =>
              patch((d) => void (d.grid.dispersal = e.target.value as "none" | "exponential"))
            }
          >
            <option value="none">none (tiles independent)</option>
            <option value="exponential">exponential kernel</option>
          </select>
        </div>
        <div className="field">
          <label>lateral shading</label>
          <select
            value={config.grid.lateral_shading}
            onChange={(e) =>
              patch((d) => void (d.grid.lateral_shading = e.target.value as "none" | "sky_view"))
            }
          >
            <option value="none">none (open horizon)</option>
            <option value="sky_view">sky view factor</option>
          </select>
        </div>
        <p className="hint">
          Two fluxes cross a tile boundary: seeds, once a year, and the sky a tall neighbour
          takes, every day. With both off, every tile is an independent column — useful for
          checking that a grid reproduces a single tile, and not much else.
        </p>
      </details>

      <details className="section">
        <summary>Site (soil)</summary>
        <p className="hint">
          One soil column per tile, and every tile's column starts from these values. Soil is a
          property of the site, not of the land use — a meadow and the wood beside it stand on
          the same ground.
        </p>
        <NumberField label="depth" unit="m" value={config.site.depth_m}
          onChange={(v) => patch((d) => void (d.site.depth_m = v))} />
        <NumberField label="sand fraction" value={config.site.sand_fraction}
          onChange={(v) => patch((d) => void (d.site.sand_fraction = v))} />
        <NumberField label="clay fraction" value={config.site.clay_fraction}
          onChange={(v) => patch((d) => void (d.site.clay_fraction = v))} />
        <NumberField label="field capacity" unit="mm" value={config.site.field_capacity_mm}
          onChange={(v) => patch((d) => void (d.site.field_capacity_mm = v))} />
        <NumberField label="wilting point" unit="mm" value={config.site.wilting_point_mm}
          onChange={(v) => patch((d) => void (d.site.wilting_point_mm = v))} />
        <NumberField label="initial slow SOM" unit="kgC m-2" value={config.site.initial_slow_c}
          onChange={(v) => patch((d) => void (d.site.initial_slow_c = v))} />
        <NumberField label="initial mineral N" unit="kgN m-2" value={config.site.initial_mineral_n}
          onChange={(v) => patch((d) => void (d.site.initial_mineral_n = v))} />
      </details>

      <details className="section">
        <summary>Weather</summary>
        <NumberField label="latitude" unit="deg" value={config.weather.latitude_deg}
          onChange={(v) => patch((d) => void (d.weather.latitude_deg = v))} />
        <NumberField label="mean temperature" unit="degC" value={config.weather.mean_temperature_c}
          onChange={(v) => patch((d) => void (d.weather.mean_temperature_c = v))} />
        <NumberField label="seasonal amplitude" unit="degC"
          value={config.weather.temperature_amplitude_c}
          onChange={(v) => patch((d) => void (d.weather.temperature_amplitude_c = v))} />
        <NumberField label="annual precipitation" unit="mm"
          value={config.weather.annual_precipitation_mm}
          onChange={(v) => patch((d) => void (d.weather.annual_precipitation_mm = v))} />
        <NumberField label="peak radiation" unit="MJ m-2 d-1"
          value={config.weather.peak_radiation_mj_m2}
          onChange={(v) => patch((d) => void (d.weather.peak_radiation_mj_m2 = v))} />
      </details>

      <details className="section">
        <summary>Seed rain</summary>
        <p className="hint">
          Seeds arriving from outside the simulated region (m-2 y-1), the same for every tile.
          Seeds moving <em>between</em> tiles are the dispersal kernel, under Region.
        </p>
        {Object.entries(config.vegetation.external_seed_rain).map(([pft, value]) => (
          <NumberField
            key={pft}
            label={pft}
            value={value}
            onChange={(v) => patch((d) => void (d.vegetation.external_seed_rain[pft] = v))}
          />
        ))}
      </details>

      <details className="section">
        <summary>Tree types (FORMIND)</summary>
        {treeParams && (
          <ParameterForm
            payload={treeParams}
            overrides={config.vegetation.tree_pft_overrides}
            onChange={(next) => patch((d) => void (d.vegetation.tree_pft_overrides = next))}
          />
        )}
      </details>

      <details className="section">
        <summary>Grass types (GRASSMIND)</summary>
        {grassParams && (
          <ParameterForm
            payload={grassParams}
            overrides={config.vegetation.grass_pft_overrides}
            onChange={(next) => patch((d) => void (d.vegetation.grass_pft_overrides = next))}
          />
        )}
      </details>

      <div className="run-bar">
        <button className="primary" onClick={onRun} disabled={running}>
          {running ? "Simulating…" : `Run ${config.years} years`}
        </button>
      </div>
    </aside>
  );
}
