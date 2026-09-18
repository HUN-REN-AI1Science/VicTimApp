/**
 * Configuration panel — the whole scenario.
 *
 * One tile, so there is nothing left to scope a form to: site, weather,
 * management and initial vegetation are all properties of the one thing being
 * simulated, and all live here.
 *
 * Grouped the way the upstream models group their own inputs — site, weather,
 * plant functional types — so that someone who has configured FORMIND or
 * GRASSMIND finds the same categories in the same order.
 */

import type { ManagementPreset, ManagementPresetId, ParameterPayload, ScenarioConfig } from "../types";
import { CheckField, NumberField } from "./fields";
import { ParameterForm } from "./ParameterForm";

type Patch = (update: (draft: ScenarioConfig) => void) => void;

export function Sidebar({
  config,
  patch,
  presets,
  treeParams,
  grassParams,
  onRun,
  running,
}: {
  config: ScenarioConfig;
  patch: Patch;
  presets: ManagementPreset[];
  treeParams: ParameterPayload | null;
  grassParams: ParameterPayload | null;
  onRun: () => void;
  running: boolean;
}) {
  const applyPreset = (preset: ManagementPreset) =>
    patch((d) => {
      d.management = {
        preset: preset.id as ManagementPresetId,
        mowing: preset.mowing.map((m) => ({ ...m })),
        grazing: preset.grazing.map((g) => ({ ...g })),
        fertilisation: preset.fertilisation.map((f) => ({ ...f })),
      };
    });

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
        <summary>Site (soil)</summary>
        <NumberField label="tile size" unit="m" value={config.site.tile_size_m}
          onChange={(v) => patch((d) => void (d.site.tile_size_m = v))} />
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

      <details className="section" open>
        <summary>Management</summary>
        <div className="preset-grid">
          {presets.map((preset) => (
            <button
              key={preset.id}
              className={`preset${config.management.preset === preset.id ? " active" : ""}`}
              onClick={() => applyPreset(preset)}
              title={preset.description}
            >
              <strong>{preset.label}</strong>
              <span>{preset.description}</span>
            </button>
          ))}
        </div>

        {config.management.mowing.length > 0 && (
          <>
            <div className="group-label">cuts (day of year / height m)</div>
            {config.management.mowing.map((event, i) => (
              <div className="event-row" key={i}>
                <input
                  type="number"
                  value={event.day_of_year}
                  onChange={(e) =>
                    patch((d) => {
                      d.management.mowing[i].day_of_year = Number(e.target.value);
                      d.management.preset = "custom";
                    })
                  }
                />
                <input
                  type="number"
                  step="0.01"
                  value={event.cut_height_m}
                  onChange={(e) =>
                    patch((d) => {
                      d.management.mowing[i].cut_height_m = Number(e.target.value);
                      d.management.preset = "custom";
                    })
                  }
                />
                <button
                  onClick={() =>
                    patch((d) => {
                      d.management.mowing.splice(i, 1);
                      d.management.preset = "custom";
                    })
                  }
                >
                  ×
                </button>
              </div>
            ))}
          </>
        )}
        <button
          onClick={() =>
            patch((d) => {
              d.management.mowing.push({
                day_of_year: 190,
                cut_height_m: 0.07,
                removal_fraction: 0.9,
                woody_kill_height_m: 0.6,
              });
              d.management.preset = "custom";
            })
          }
        >
          + add cut
        </button>
        <p className="hint">
          A cut also destroys tree saplings below its woody-kill height. That is what keeps a
          managed meadow from turning into woodland.
        </p>
      </details>

      <details className="section">
        <summary>Initial vegetation</summary>
        <CheckField
          id="include-grass"
          label="grassland (GRASSMIND)"
          checked={config.vegetation.include_grassland}
          onChange={(v) => patch((d) => void (d.vegetation.include_grassland = v))}
        />
        <CheckField
          id="include-forest"
          label="forest (FORMIND)"
          checked={config.vegetation.include_forest}
          onChange={(v) => patch((d) => void (d.vegetation.include_forest = v))}
        />
        <NumberField
          label="initial sward density"
          unit="plants m-2"
          value={config.vegetation.initial_sward_density_per_m2}
          onChange={(v) => patch((d) => void (d.vegetation.initial_sward_density_per_m2 = v))}
        />
        <NumberField
          label="planted trees"
          unit="per tile"
          step="1"
          value={config.vegetation.initial_trees_per_tile}
          onChange={(v) =>
            patch((d) => void (d.vegetation.initial_trees_per_tile = Math.max(0, Math.round(v))))
          }
        />
        <NumberField
          label="planted tree size"
          unit="m dbh"
          step="0.01"
          value={config.vegetation.initial_tree_dbh}
          onChange={(v) => patch((d) => void (d.vegetation.initial_tree_dbh = v))}
        />
      </details>

      <details className="section">
        <summary>Seed rain</summary>
        <p className="hint">
          Seeds arriving from outside the simulated tile (m-2 y-1).
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
