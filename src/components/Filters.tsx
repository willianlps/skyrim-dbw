import type { ReactNode } from "react";

/** Filter panel shown in the sidebar (each view builds its own). */
export function FiltersPanel({
  active,
  onClear,
  children,
}: {
  active: boolean;
  onClear: () => void;
  children: ReactNode;
}) {
  return (
    <div className="filters-panel">
      <div className="filters-head">
        <span>Filters</span>
        {active && (
          <button className="link-btn" onClick={onClear}>
            Clear
          </button>
        )}
      </div>
      {children}
    </div>
  );
}

export function FilterGroup({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="filter-group">
      <div className="filter-title">{title}</div>
      {children}
    </div>
  );
}

export function FilterSelect({
  title,
  value,
  onChange,
  options,
}: {
  title: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <FilterGroup title={title}>
      <select
        className="select full"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-label={title}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </FilterGroup>
  );
}

export function FilterToggle({
  label,
  on,
  onClick,
}: {
  label: string;
  on: boolean;
  onClick: () => void;
}) {
  return (
    <div className="filter-group">
      <button className={`toggle full${on ? " on" : ""}`} aria-pressed={on} onClick={onClick}>
        {label}
      </button>
    </div>
  );
}

export interface Option {
  value: string;
  /** Text shown instead of the value. */
  label?: string;
  count: number;
}

/** Single-choice list with counts. Clicking the active option clears it. */
export function OptionList({
  title,
  allLabel,
  options,
  value,
  onChange,
}: {
  title: string;
  allLabel: string;
  options: Option[];
  value: string | null;
  onChange: (value: string | null) => void;
}) {
  return (
    <FilterGroup title={title}>
      <div className="options">
        <button className={`option${value === null ? " on" : ""}`} onClick={() => onChange(null)}>
          <span className="option-label">{allLabel}</span>
        </button>
        {options.map((o) => (
          <button
            key={o.value}
            className={`option${value === o.value ? " on" : ""}`}
            onClick={() => onChange(value === o.value ? null : o.value)}
            title={o.label ?? o.value}
          >
            <span className="option-label">{o.label ?? o.value}</span>
            <span className="option-count">{o.count}</span>
          </button>
        ))}
      </div>
    </FilterGroup>
  );
}

/** Counts items per key, sorted by count (desc) and then by name. */
export function countBy<T>(items: readonly T[], key: (item: T) => string): [string, number][] {
  const counts = new Map<string, number>();
  for (const item of items) {
    const k = key(item);
    if (k) counts.set(k, (counts.get(k) ?? 0) + 1);
  }
  return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
}
