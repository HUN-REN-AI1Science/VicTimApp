/**
 * Application shell.
 *
 * Three places, and which one a thing is edited in is the design:
 *
 * * the **sidebar** holds what is true of the whole region — one soil column's
 *   properties, one climate, one grid, one set of PFTs;
 * * the **Region tab** holds the map, and through it everything that can differ
 *   between tiles: which land use a tile has, and that land use's management and
 *   initial vegetation. A form that changes one tile is only legible next to the
 *   picture of which tile it changes, so it lives on the map, not in the sidebar;
 * * the **Tile tab** holds one tile's outputs, and follows the map's selection.
 *
 * Two tabs, not one per tile. A 16×16 region is 256 tiles; a strip of 257 tabs
 * is a list, not a selector. The map is the selector, and the Tile tab is the
 * detail view of whatever it has selected.
 *
 * A time scrubber drives every view at once, so the stand diagram, the map and
 * the chart cursors always describe the same simulated year.
 */

import { useCallback, useEffect, useMemo, useState } from "react";

import { Sidebar } from "./components/Sidebar";
import { DEFAULT_HEIGHT_AXIS_M } from "./components/StandProfile";
import { Tabs, type TabItem } from "./components/Tabs";
import { TilePanel } from "./components/TilePanel";
import { RegionPanel } from "./components/RegionPanel";
import { MAP_VARIABLES, type MapVariable } from "./components/TileMap";
import { normaliseAssignment } from "./lib/tiles";
import { api, runToCompletion } from "./lib/api";
import type {
  JobStatus,
  ManagementPreset,
  ParameterPayload,
  ProfileRecord,
  ScenarioConfig,
  SimulationResults,
} from "./types";

const REGION_TAB = "region";
const TILE_TAB = "tile";

/** Which tab a freshly loaded run opens on.
 *
 * A single-tile run has nothing to select, so it opens straight on its tile. A
 * region opens on the map, because choosing which tile to look at is the first
 * thing there is to do. */
const openingTab = (payload: SimulationResults) =>
  payload.scenario.grid.nx * payload.scenario.grid.ny === 1 ? TILE_TAB : REGION_TAB;

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
  const [tile, setTile] = useState({ x: 0, y: 0 });
  const [activeTab, setActiveTab] = useState(REGION_TAB);
  /** null means "colour the map by land use" — the only view before a run. */
  const [mapVariable, setMapVariable] = useState<MapVariable | null>(null);

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
        setTile({ x: 0, y: 0 });
        setActiveTab(openingTab(payload));
        setMapVariable(MAP_VARIABLES[0]);
        setProfiles(await api.profile(id, 0, 0));
      })
      .catch((e: Error) => setError(`Could not load run ${id}: ${e.message}`));
  }, []);

  // Every edit runs through here, and every edit ends with an assignment that
  // has exactly one type per tile. Doing it centrally is what makes "every tile
  // has a land use" an invariant: resizing the grid, deleting a type and
  // loading a scenario cannot each forget it separately.
  const patch = useCallback((update: (draft: ScenarioConfig) => void) => {
    setConfig((current) => {
      if (!current) return current;
      const draft = structuredClone(current);
      update(draft);
      normaliseAssignment(draft, { nx: current.grid.nx, ny: current.grid.ny });
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
      setTile({ x: 0, y: 0 });
      setActiveTab(openingTab(payload));
      setMapVariable(MAP_VARIABLES[0]);
      setProfiles(await api.profile(payload.id, 0, 0));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setRunning(false);
    }
  }, [config]);

  // Clicking the map selects; it does not jump tabs. The Tile tab follows the
  // selection, so the user can keep drawing the region without being thrown out
  // of it, and opens the tile explicitly when they want its outputs.
  const selectTile = useCallback((next: { x: number; y: number }) => setTile(next), []);

  // A tile that no longer exists cannot stay selected. Shrinking the grid must
  // not leave the Tile tab pointing outside it.
  useEffect(() => {
    if (!config) return;
    setTile((current) => {
      const x = Math.min(current.x, config.grid.nx - 1);
      const y = Math.min(current.y, config.grid.ny - 1);
      return x === current.x && y === current.y ? current : { x, y };
    });
  }, [config?.grid.nx, config?.grid.ny]);

  // Re-fetch profiles when the user selects a different tile. Only the tile
  // whose tab is open needs them; the numeric series for every tile already
  // arrived with the results.
  useEffect(() => {
    if (!results) return;
    api.profile(results.id, tile.x, tile.y).then(setProfiles).catch(() => setProfiles(null));
  }, [results, tile.x, tile.y]);

  const series = useMemo(
    () => results?.tiles.find((t) => t.x === tile.x && t.y === tile.y)?.series ?? [],
    [results, tile],
  );
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

  // Do the loaded results still describe the region currently configured? The
  // user can edit the grid after a run, and a map of 25 squares carrying a 9-tile
  // run's colours would be fiction.
  const comparable =
    !!results &&
    !!config &&
    results.scenario.grid.nx === config.grid.nx &&
    results.scenario.grid.ny === config.grid.ny;

  const tabs: TabItem[] = useMemo(
    () => [
      { key: REGION_TAB, label: "Region", title: "the map, and what each tile is" },
      {
        key: TILE_TAB,
        label: `Tile (${tile.x}, ${tile.y})`,
        title: "outputs for the tile selected on the map",
      },
    ],
    [tile.x, tile.y],
  );

  return (
    <div className="app">
      {config && (
        <Sidebar
          config={config}
          patch={patch}
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

        {config && (
          <>
            <Tabs items={tabs} active={activeTab} onSelect={setActiveTab} />

            {activeTab === REGION_TAB ? (
              <RegionPanel
                config={config}
                patch={patch}
                presets={presets}
                /* Output only colours the map while it still describes this
                   region. Editing the grid after a run leaves results whose
                   tiles no longer line up with the squares on screen, so the
                   map falls back to land use rather than drawing a lie. */
                tiles={comparable ? results?.tiles : undefined}
                index={index}
                variable={mapVariable}
                onVariableChange={setMapVariable}
                selected={tile}
                onSelect={selectTile}
                onOpenTile={() => setActiveTab(TILE_TAB)}
              />
            ) : results && comparable ? (
              <TilePanel
                x={tile.x}
                y={tile.y}
                series={series}
                years={years}
                index={index}
                profile={profile}
                tileSizeM={results.scenario.grid.tile_size_m}
                heightAxisM={heightAxisM}
                treeParams={treeParams}
                grassParams={grassParams}
              />
            ) : (
              <div className="empty">
                <div>
                  <p>
                    Nothing has been simulated for tile ({tile.x}, {tile.y}) yet. Draw the region
                    on the <em>Region</em> tab — each tile's land use decides what is on it and
                    what is done to it — then press Run.
                  </p>
                  <p>
                    Try a wooded edge against a mown strip over 90 years: the same soil and the
                    same weather become forest or stay grassland depending on nothing but whether
                    the tile is cut.
                  </p>
                </div>
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}
