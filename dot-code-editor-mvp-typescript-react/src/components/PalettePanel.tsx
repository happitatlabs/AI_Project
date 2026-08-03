import { useState } from "react";
import type { ColorKey, Palette } from "../types/sprite";
import type { PaletteLimit } from "../types/sprite";
import type { HsvColor } from "../utils/colorConvert";
import { hexToHsv, hsvToHex } from "../utils/colorConvert";
import { getPaletteColorKeys, isHexColor } from "../utils/paletteKeys";

type PalettePanelProps = {
  palette: Palette;
  paletteLimit: PaletteLimit;
  selectedColorKey: ColorKey;
  onSelectColor: (key: ColorKey) => void;
  onUpdateColor: (key: ColorKey, color: string) => void;
};

export function PalettePanel({
  palette,
  paletteLimit,
  selectedColorKey,
  onSelectColor,
  onUpdateColor,
}: PalettePanelProps) {
  const [editingColorKey, setEditingColorKey] = useState<ColorKey | null>(null);
  const [editingHsv, setEditingHsv] = useState<HsvColor>({ h: 0, s: 0, v: 0 });
  const paletteKeys = ["0", ...getPaletteColorKeys(paletteLimit)];
  const editingColor = editingColorKey ? palette[editingColorKey] : null;

  function handleOpenColorModal(key: ColorKey, value: string) {
    onSelectColor(key);

    if (value !== "transparent") {
      setEditingHsv(hexToHsv(value));
      setEditingColorKey(key);
    }
  }

  function handleHsvChange(channel: keyof HsvColor, value: number) {
    if (!editingColorKey) {
      return;
    }

    const nextHsv = {
      ...editingHsv,
      [channel]: value,
    };

    setEditingHsv(nextHsv);
    onUpdateColor(editingColorKey, hsvToHex(nextHsv));
  }

  return (
    <section className="editorPalette" aria-labelledby="palette-title">
      <h2 className="srOnly" id="palette-title">
        Palette
      </h2>
      <div className="paletteGrid">
        {paletteKeys.map((key) => {
          const value = palette[key] ?? "transparent";
          const isTransparent = value === "transparent";
          const isSelected = selectedColorKey === key;

          return (
            <div className={`paletteSlot${isSelected ? " isSelected" : ""}`} key={key}>
              <button
                className="paletteSwatchButton"
                type="button"
                onClick={() => handleOpenColorModal(key, value)}
                title={isTransparent ? "Select transparent" : `Edit color ${key}`}
              >
                <span
                  className={`swatch${isTransparent ? " isTransparent" : ""}`}
                  style={isTransparent ? undefined : { backgroundColor: value }}
                />
              </button>
              <button
                className="paletteKeyButton"
                type="button"
                onClick={() => onSelectColor(key)}
                title={`Select color ${key}`}
              >
                <span className="paletteKey">{key}</span>
              </button>
            </div>
          );
        })}
      </div>
      {editingColorKey && editingColor && editingColor !== "transparent" ? (
        <div className="colorModalBackdrop" role="presentation" onMouseDown={() => setEditingColorKey(null)}>
          <div
            aria-labelledby="color-modal-title"
            className="colorModal"
            role="dialog"
            aria-modal="true"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div className="sectionHeader">
              <h2 id="color-modal-title">색상 변경</h2>
              <span className="sectionMeta">Key {editingColorKey}</span>
            </div>
            <div className="colorModalPreview">
              <span
                className="colorModalSwatch"
                style={{ backgroundColor: isHexColor(editingColor) ? editingColor : "#111111" }}
              />
              <span>
                {editingColorKey} {editingColor}
              </span>
            </div>
            <div className="hsvControls">
              <label className="hsvSlider hueSlider">
                <span>Hue</span>
                <input
                  aria-label="Hue"
                  type="range"
                  min="0"
                  max="359"
                  value={editingHsv.h}
                  onChange={(event) => handleHsvChange("h", Number(event.target.value))}
                />
                <output>{editingHsv.h}</output>
              </label>
              <label className="hsvSlider">
                <span>Saturation</span>
                <input
                  aria-label="Saturation"
                  type="range"
                  min="0"
                  max="100"
                  value={editingHsv.s}
                  onChange={(event) => handleHsvChange("s", Number(event.target.value))}
                />
                <output>{editingHsv.s}%</output>
              </label>
              <label className="hsvSlider">
                <span>Value</span>
                <input
                  aria-label="Value"
                  type="range"
                  min="0"
                  max="100"
                  value={editingHsv.v}
                  onChange={(event) => handleHsvChange("v", Number(event.target.value))}
                />
                <output>{editingHsv.v}%</output>
              </label>
            </div>
            <button type="button" onClick={() => setEditingColorKey(null)}>
              닫기
            </button>
          </div>
        </div>
      ) : null}
    </section>
  );
}
