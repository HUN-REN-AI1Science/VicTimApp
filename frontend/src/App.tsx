/**
 * Application shell.
 *
 * Two places, and which one a thing is edited in is the design:
 *
 * * the **sidebar** holds the whole scenario — one soil column's properties,
 *   one climate, one management schedule, one set of PFTs;
 * * the **main view** holds the simulated tile's outputs.
 *
 * A time scrubber drives every view at once, so the stand diagram and the
 * chart cursors always describe the same simulated year.
 */

import { useCallback, useEffect, useMemo, useState } from "react";

import { Sidebar } from "./components/Sidebar";
import { DEFAULT_HEIGHT_AXIS_M } from "./components/StandProfile";
import { TilePanel } from "./components/TilePanel";
import { api, runToCompletion } from "./lib/api";
import type {
  JobStatus,
  ManagementPreset,
  ParameterPayload,
  ProfileRecord,
  ScenarioConfig,
  SimulationResults,
} from "./types";

export default function App() {
  const [config, setConfig] = useState<ScenarioConfig | null>(null);
  const [presets, setPresets] = useState<ManagementPreset[]>([]);
  const [treeParams, setTreeParams] = useState<ParameterPayload | null>(null);
  const [grassParams, setGrassParams] = useState<ParameterPayload | null>(null);

  const [status, setStatus] = useState<JobStatus | null>(null);
  const [results, setResults] = useState<SimulationResults | null>(null);
  const [profiles, setProfiles] = useState<ProfileRecord[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  const [index, setIndex] = useState(0);

  useEffect(() => {
    Promise.all([
      api.defaultScenario(),
      api.managementPresets(),
      api.parameters("formind"),
      api.parameters("grassmind"),
    ])
      .then(([scenario, presetList, tree, grass]) => {
        setConfig(scenario);
        setPresets(presetList);
        setTreeParams(tree);
        setGrassParams(grass);
      })
      .catch((e: Error) => setError(`Could not reach the backend: ${e.message}`));
  }, []);

  // Deep link: `?run=<id>` reopens a finished simulation, so a result can be
  // shared or reloaded without recomputing it.
  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get("run");
    if (!id) return;
    api
      .results(id)
      .then(async (payload) => {
        setResults(payload);
        setConfig(payload.scenario);
        setIndex(payload.years.length - 1);
        setProfiles(await api.profile(id));
      })
      .catch((e: Error) => setError(`Could not load run ${id}: ${e.message}`));
  }, []);

  const patch = useCallback((update: (draft: ScenarioConfig) => void) => {
    setConfig((current) => {
      if (!current) return current;
      const draft = structuredClone(current);
      update(draft);
      return draft;
    });
  }, []);

  const run = useCallback(async () => {
    if (!config) return;
    setRunning(true);
    setError(null);
    setResults(null);
    setProfiles(null);
    try {
      const { results: payload } = await runToCompletion(config, setStatus);
      setResults(payload);
      const url = new URL(window.location.href);
      url.searchParams.set("run", payload.id);
      window.history.replaceState(null, "", url);
      setIndex(payload.years.length - 1);
      setProfiles(await api.profile(payload.id));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setRunning(false);
    }
  }, [config]);

  const series = results?.series ?? [];
  const years = results?.years ?? [];
  const profile = profiles?.[index];

  // One height axis for the whole run, so scrubbing through time shows the stand
  // growing rather than the axis shrinking around it. Fitted to the tallest
  // individual anywhere in the run -- trees or sward -- plus a metre of
  // headroom, so the canopy top never touches the frame.
  const heightAxisM = useMemo(() => {
    let tallest = 0;
    for (const record of profiles ?? []) {
      for (const row of record.stand_profile ?? []) {
        if (row.height > tallest) tallest = row.height;
      }
      for (const row of record.sward_profile ?? []) {
        if (row.height > tallest) tallest = row.height;
      }
    }
    return tallest > 0 ? tallest + 1 : DEFAULT_HEIGHT_AXIS_M;
  }, [profiles]);

  return (
    <div className="app">
      {config && (
        <Sidebar
          config={config}
          patch={patch}
          presets={presets}
          treeParams={treeParams}
          grassParams={grassParams}
          onRun={run}
          running={running}
        />
      )}

      <main className="main">
        <div className="topbar">
          {running && status && (
            <>
              <div className="progress">
                <div style={{ width: `${status.progress * 100}%` }} />
              </div>
              <span className="status">
                {status.state} · year {(status.simulated_days / 365).toFixed(0)} /{" "}
                {(status.total_days / 365).toFixed(0)}
              </span>
            </>
          )}

          {!running && error && <span className="status error">{error}</span>}

          {!running && results && (
            <div className="scrubber">
              <span className="year-badge">year {years[index]?.toFixed(0) ?? 0}</span>
              <input
                type="range"
                min={0}
                max={Math.max(years.length - 1, 0)}
                value={index}
                onChange={(event) => setIndex(Number(event.target.value))}
              />
              <span className="status">{results.scenario.name}</span>
            </div>
          )}

          {!running && !results && !error && (
            <span className="status">configure a scenario, then run it</span>
          )}
        </div>

        {results ? (
          <TilePanel
            series={series}
            years={years}
            index={index}
            profile={profile}
            tileSizeM={results.scenario.site.tile_size_m}
            heightAxisM={heightAxisM}
            treeParams={treeParams}
            grassParams={grassParams}
          />
        ) : (
          config && (
            <div className="empty">
              <div>
                <p>
                  Nothing has been simulated yet. Configure the site, weather and management in
                  the sidebar, then press Run.
                </p>
                <p>
                  Try the abandoned preset over 90 years: the same soil and the same weather
                  become forest once nothing stops the trees.
                </p>
              </div>
            </div>
          )
        )}
      </main>
    </div>
  );
}
