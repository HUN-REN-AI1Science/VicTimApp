/**
 * Generic PFT parameter editor.
 *
 * Renders whatever `GET /api/parameters/{model}` describes: it knows nothing
 * about pmax or crown_lai. Adding a parameter to `TreePFT` or `GrassPFT` in
 * Python makes it appear here with no change to this file, which is the point of
 * serving a parameter *schema* rather than a hard-coded form.
 */

import { useState } from "react";
import type { ParameterPayload, ParameterSpec } from "../types";

export function ParameterForm({
  payload,
  overrides,
  onChange,
}: {
  payload: ParameterPayload;
  overrides: Record<string, Record<string, number>>;
  onChange: (next: Record<string, Record<string, number>>) => void;
}) {
  const [activePft, setActivePft] = useState(String(payload.pfts[0]?.id ?? ""));
  const pft = payload.pfts.find((p) => p.id === activePft);
  if (!pft) return null;

  const groups = payload.schema.reduce<Record<string, ParameterSpec[]>>((acc, spec) => {
    (acc[spec.group] ??= []).push(spec);
    return acc;
  }, {});

  const valueOf = (spec: ParameterSpec): number =>
    overrides[activePft]?.[spec.name] ?? Number(pft[spec.name] ?? spec.default);

  const setValue = (spec: ParameterSpec, raw: string) => {
    const next = { ...overrides, [activePft]: { ...(overrides[activePft] ?? {}) } };
    if (raw === "") {
      delete next[activePft][spec.name];
      if (Object.keys(next[activePft]).length === 0) delete next[activePft];
    } else {
      next[activePft][spec.name] = Number(raw);
    }
    onChange(next);
  };

  const edited = Object.keys(overrides[activePft] ?? {}).length;

  return (
    <div>
      <div className="pft-tabs">
        {payload.pfts.map((p) => (
          <button
            key={String(p.id)}
            className={`pft-tab${p.id === activePft ? " active" : ""}`}
            onClick={() => setActivePft(String(p.id))}
          >
            <i className="swatch" style={{ background: String(p.colour) }} />
            {String(p.label)}
          </button>
        ))}
      </div>

      {Object.entries(groups).map(([group, specs]) => (
        <div key={group}>
          <div className="group-label">{group}</div>
          {specs.map((spec) => (
            <div className="field" key={spec.name}>
              <label htmlFor={`${activePft}-${spec.name}`}>
                {spec.name.replace(/_/g, " ")}
                <br />
                <span className="unit">{spec.unit}</span>
              </label>
              <input
                id={`${activePft}-${spec.name}`}
                type="number"
                step="any"
                value={valueOf(spec)}
                onChange={(event) => setValue(spec, event.target.value)}
              />
            </div>
          ))}
        </div>
      ))}

      {edited > 0 && (
        <p className="hint">
          {edited} parameter{edited === 1 ? "" : "s"} overridden for this type.{" "}
          <button
            onClick={() => {
              const next = { ...overrides };
              delete next[activePft];
              onChange(next);
            }}
          >
            Reset
          </button>
        </p>
      )}
    </div>
  );
}
