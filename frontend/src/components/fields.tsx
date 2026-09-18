/** Form primitives shared across the sidebar's sections. */

export function NumberField({
  label,
  unit,
  value,
  step = "any",
  onChange,
}: {
  label: string;
  unit?: string;
  value: number;
  step?: string;
  onChange: (value: number) => void;
}) {
  return (
    <div className="field">
      <label>
        {label}
        {unit && (
          <>
            <br />
            <span className="unit">{unit}</span>
          </>
        )}
      </label>
      <input
        type="number"
        step={step}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </div>
  );
}

export function CheckField({
  id,
  label,
  checked,
  onChange,
}: {
  id: string;
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <div className="check">
      <input
        type="checkbox"
        id={id}
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
      />
      <label htmlFor={id}>{label}</label>
    </div>
  );
}
