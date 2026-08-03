import { useState } from "react";
import type { Palette, SpriteGrid } from "../types/sprite";

type PreviewPanelProps = {
  spriteGrid: SpriteGrid;
  palette: Palette;
};

const SCALE_OPTIONS = [4, 6, 8, 12] as const;

export function PreviewPanel({ spriteGrid, palette }: PreviewPanelProps) {
  const [scale, setScale] = useState<(typeof SCALE_OPTIONS)[number]>(8);
  const [showChecker, setShowChecker] = useState(true);
  const size = spriteGrid.length;

  return (
    <section className="panelSection" aria-labelledby="preview-title">
      <div className="sectionHeader">
        <h2 id="preview-title">Preview</h2>
        <span className="sectionMeta">{scale}x</span>
      </div>

      <div className="previewControls">
        <label>
          Scale
          <select value={scale} onChange={(event) => setScale(Number(event.target.value) as typeof scale)}>
            {SCALE_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option}x
              </option>
            ))}
          </select>
        </label>
        <label className="checkboxLabel">
          <input
            type="checkbox"
            checked={showChecker}
            onChange={(event) => setShowChecker(event.target.checked)}
          />
          Checker
        </label>
      </div>

      <div className={`previewStage${showChecker ? " hasChecker" : ""}`}>
        <div
          className="previewSprite"
          style={{
            gridTemplateColumns: `repeat(${size}, ${scale}px)`,
            gridAutoRows: `${scale}px`,
          }}
        >
          {spriteGrid.map((row, rowIndex) =>
            Array.from(row).map((colorKey, columnIndex) => {
              const color = palette[colorKey] ?? "transparent";

              return (
                <span
                  className="previewPixel"
                  key={`${rowIndex}-${columnIndex}`}
                  style={{
                    width: scale,
                    height: scale,
                    backgroundColor: color === "transparent" ? undefined : color,
                  }}
                />
              );
            }),
          )}
        </div>
      </div>
    </section>
  );
}
