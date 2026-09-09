/**
 * The view selector.
 *
 * With more than one tile there is no such thing as "the" chart: every output is
 * a property of one tile. The tab strip is what makes that legible — the region
 * map sits in the same strip as the tiles it selects, because it *is* the tile
 * selector.
 *
 * Deliberately unstyled beyond two class names and no state of its own. It
 * follows the tab idiom `ParameterForm` already established rather than
 * introducing a UI library the build does not need.
 */

export interface TabItem {
  key: string;
  label: string;
  title?: string;
}

export function Tabs({
  items,
  active,
  onSelect,
}: {
  items: TabItem[];
  active: string;
  onSelect: (key: string) => void;
}) {
  return (
    <div className="viewtabs" role="tablist">
      {items.map((item) => (
        <button
          key={item.key}
          role="tab"
          type="button"
          aria-selected={item.key === active}
          title={item.title}
          className={"viewtab" + (item.key === active ? " active" : "")}
          onClick={() => onSelect(item.key)}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}
