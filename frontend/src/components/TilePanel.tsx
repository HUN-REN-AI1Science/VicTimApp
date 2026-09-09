/**
 * Everything one tile has to say: its stand structure and its own charts.
 *
 * Moved out of `App` unchanged when the view became one tab per tile. Every
 * number here is a property of a single tile — with a 2D region there is no
 * global series to plot, because the tiles do not share a soil column or a light
 * profile, only fluxes between them.
 *
 * Values arrive per m² of ground, as everything the API returns does; the
 * conversions here are for display only and each is labelled in its heading.
 */

import { Histogram, LineChart, type Series } from "./Charts";
import { DEFAULT_HEIGHT_AXIS_M, StandProfile } from "./StandProfile";
import type { ParameterPayload, ProfileRecord, TileRecord } from "../types";

const TREE_COLOURS: Record<string, string> = {
  pioneer: "#8fbf5a",
  mid: "#3f7d4e",
  late: "#1f4f36",
};
const GRASS_COLOURS: Record<string, string> = {
  grass: "#9bbf3c",
  forb: "#d98cb3",
  legume: "#e8a33d",
};

export function TilePanel({
  x,
  y,
  series,
  years,
  index,
  profile,
  tileSizeM,
  heightAxisM = DEFAULT_HEIGHT_AXIS_M,
  treeParams,
  grassParams,
}: {
  x: number;
  y: number;
  series: TileRecord[];
  years: number[];
  index: number;
  profile?: ProfileRecord;
  tileSizeM: number;
  heightAxisM?: number;
  treeParams: ParameterPayload | null;
  grassParams: ParameterPayload | null;
}) {
  const record = series[index];
  const pick = (key: string) => series.map((r) => r[key] ?? 0);

  // PFT colours are served by the API and match the models' own conventions; the
  // maps above are only fallbacks for a PFT the backend did not describe.
  const colourOf = (params: ParameterPayload | null, id: string, fallback: Record<string, string>) =>
    String(params?.pfts.find((p) => String(p.id) === id)?.colour ?? fallback[id] ?? "#3f7d4e");

  const treePfts = treeParams?.pfts.map((p) => String(p.id)) ?? [];
  const grassPfts = grassParams?.pfts.map((p) => String(p.id)) ?? [];

  const biomassSeries: Series[] = [
    ...treePfts.map((id) => ({
      label: `tree: ${id}`,
      colour: colourOf(treeParams, id, TREE_COLOURS),
      values: pick(`forest_biomass_c_${id}`),
    })),
    ...grassPfts.map((id) => ({
      label: `grass: ${id}`,
      colour: colourOf(grassParams, id, GRASS_COLOURS),
      values: pick(`grassland_shoot_c_${id}`),
      dashed: true,
    })),
  ];

  const shaded = (record?.sky_view_fraction ?? 1) < 1;

  return (
    <>
      <div className="views">
        <section className="card">
          <h2>
            Stand structure
            <em>
              tile ({x}, {y}) · {tileSizeM} m
            </em>
          </h2>
          {profile?.stand_profile || profile?.sward_profile ? (
            <StandProfile
              stand={profile.stand_profile ?? []}
              sward={profile.sward_profile ?? []}
              tileSizeM={tileSizeM}
              floorLightFraction={record?.floor_light_fraction ?? 1}
              heightAxisM={heightAxisM}
            />
          ) : (
            <p className="hint">No vertical structure recorded for this step.</p>
          )}
        </section>

        <section className="card">
          <h2>
            This tile, this year <em>({x}, {y})</em>
          </h2>
          {record ? (
            <>
              <dl className="readout">
                <div>
                  <dt>leaf area index</dt>
                  <dd>{record.lai?.toFixed(2)}</dd>
                </div>
                <div>
                  <dt>floor light</dt>
                  <dd>{((record.floor_light_fraction ?? 0) * 100).toFixed(1)}%</dd>
                </div>
                <div>
                  <dt>soil water</dt>
                  <dd>{((record.relative_water_content ?? 0) * 100).toFixed(0)}%</dd>
                </div>
                <div>
                  <dt>trees</dt>
                  <dd>{((record.forest_stems ?? 0) * 10000).toFixed(0)} ha⁻¹</dd>
                </div>
                <div>
                  <dt>sward</dt>
                  <dd>{((record.grassland_shoot_c ?? 0) * 1000).toFixed(0)} gC m⁻²</dd>
                </div>
                <div>
                  <dt>canopy top</dt>
                  <dd>{(record.canopy_top_m ?? 0).toFixed(1)} m</dd>
                </div>
                <div>
                  <dt>sky visible</dt>
                  <dd>{((record.sky_view_fraction ?? 1) * 100).toFixed(0)}%</dd>
                </div>
              </dl>
              {shaded && (
                <p className="hint">
                  Neighbouring canopies take {(100 - (record.sky_view_fraction ?? 1) * 100).toFixed(0)}%
                  of this tile’s sky before its own profile attenuates anything. Floor light is a
                  fraction of what the tile receives, not of the open sky.
                </p>
              )}
            </>
          ) : (
            <p className="hint">Nothing recorded for this step.</p>
          )}
        </section>
      </div>

      <div className="charts">
        <section className="card">
          <h2>
            Biomass by functional type <em>kgC m⁻²</em>
          </h2>
          <LineChart x={years} series={biomassSeries} marker={years[index]} />
        </section>

        <section className="card">
          <h2>
            Canopy and light <em>m² m⁻² · fraction</em>
          </h2>
          <LineChart
            x={years}
            marker={years[index]}
            series={[
              { label: "leaf area index", colour: "#2f6f4e", values: pick("lai") },
              {
                label: "floor light fraction",
                colour: "#c9a227",
                values: pick("floor_light_fraction"),
              },
              {
                label: "sky visible",
                colour: "#7a93a8",
                values: pick("sky_view_fraction"),
                dashed: true,
              },
            ]}
          />
        </section>

        <section className="card">
          <h2>
            Stems by diameter class <em>stems m⁻² · cm</em>
          </h2>
          {profile?.dbh_histogram ? (
            <Histogram bins={profile.dbh_histogram} />
          ) : (
            <p className="hint">No trees in this tile yet.</p>
          )}
        </section>

        <section className="card">
          <h2>
            Soil carbon and nitrogen <em>kgC m⁻² · kgN m⁻²</em>
          </h2>
          <LineChart
            x={years}
            marker={years[index]}
            series={[
              { label: "soil carbon", colour: "#4a3a26", values: pick("soil_c") },
              {
                label: "mineral N (×100)",
                colour: "#5b3f74",
                values: pick("mineral_n").map((v) => v * 100),
              },
            ]}
          />
        </section>

        <section className="card">
          <h2>
            Production <em>kgC m⁻² y⁻¹</em>
          </h2>
          <LineChart
            x={years}
            marker={years[index]}
            series={[
              { label: "forest NPP", colour: "#3f7d4e", values: pick("forest_npp") },
              { label: "grassland NPP", colour: "#9bbf3c", values: pick("grassland_npp") },
              {
                label: "harvest removed",
                colour: "#b4531f",
                values: pick("grassland_harvest_c"),
              },
            ]}
          />
        </section>

        <section className="card">
          <h2>
            Sward height and diversity <em>m · Shannon H′</em>
          </h2>
          <LineChart
            x={years}
            marker={years[index]}
            series={[
              {
                label: "sward height",
                colour: "#8a9e3b",
                values: pick("grassland_mean_height"),
              },
              {
                label: "functional diversity",
                colour: "#d98cb3",
                values: pick("grassland_shannon_diversity"),
              },
            ]}
          />
        </section>
      </div>
    </>
  );
}
