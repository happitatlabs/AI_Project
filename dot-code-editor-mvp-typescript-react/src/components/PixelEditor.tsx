import { useState } from "react";
import { PalettePanel } from "./PalettePanel";
import type {
  ColorKey,
  Palette,
  PaletteLimit,
  ShiftDirection,
  SpriteGrid,
  ToolMode,
} from "../types/sprite";

type PixelEditorProps = {
  spriteGrid: SpriteGrid;
  palette: Palette;
  paletteLimit: PaletteLimit;
  selectedColorKey: ColorKey;
  toolMode: ToolMode;
  canUndo: boolean;
  canRedo: boolean;
  onCellAction: (row: number, column: number) => void;
  onPaletteSelect: (key: ColorKey) => void;
  onPaletteColorChange: (key: ColorKey, color: string) => void;
  onToolModeChange: (toolMode: ToolMode) => void;
  onUndo: () => void;
  onRedo: () => void;
  onClear: () => void;
  onFlipHorizontal: () => void;
  onFlipVertical: () => void;
  onShift: (direction: ShiftDirection) => void;
};

const TOOL_OPTIONS: Array<{ value: ToolMode; label: string }> = [
  { value: "paint", label: "Paint" },
  { value: "erase", label: "Erase" },
  { value: "eyedropper", label: "Pick" },
];

export function PixelEditor({
  spriteGrid,
  palette,
  paletteLimit,
  selectedColorKey,
  toolMode,
  canUndo,
  canRedo,
  onCellAction,
  onPaletteSelect,
  onPaletteColorChange,
  onToolModeChange,
  onUndo,
  onRedo,
  onClear,
  onFlipHorizontal,
  onFlipVertical,
  onShift,
}: PixelEditorProps) {
  const [isPointerDown, setIsPointerDown] = useState(false);
  const size = spriteGrid.length;

  function handleCellPointerDown(row: number, column: number) {
    setIsPointerDown(true);
    onCellAction(row, column);
  }

  function handleCellPointerEnter(row: number, column: number) {
    if (isPointerDown && toolMode !== "eyedropper") {
      onCellAction(row, column);
    }
  }

  return (
    <section className="editorShell" aria-labelledby="editor-title">
      <div className="editorTopbar">
        <div>
          <h2 id="editor-title">Editor</h2>
          <p>{size}x{size} code grid</p>
        </div>
        <div className="selectedColor">
          <span className="selectedColorLabel">현재 선택 색상</span>
          <span
            className={`selectedSwatch${palette[selectedColorKey] === "transparent" ? " isTransparent" : ""}`}
            style={
              palette[selectedColorKey] === "transparent"
                ? undefined
                : { backgroundColor: palette[selectedColorKey] }
            }
          />
          <span>{selectedColorKey}</span>
        </div>
      </div>

      <div className="toolbar" aria-label="Editor tools">
        <div className="segmentedControl">
          {TOOL_OPTIONS.map((tool) => (
            <button
              className={toolMode === tool.value ? "isActive" : ""}
              key={tool.value}
              type="button"
              onClick={() => onToolModeChange(tool.value)}
            >
              {tool.label}
            </button>
          ))}
        </div>

        <div className="buttonCluster">
          <button type="button" onClick={onUndo} disabled={!canUndo} title="Undo">
            Undo
          </button>
          <button type="button" onClick={onRedo} disabled={!canRedo} title="Redo">
            Redo
          </button>
          <button type="button" onClick={onClear}>
            Clear
          </button>
        </div>

        <div className="buttonCluster">
          <button type="button" onClick={onFlipHorizontal}>
            Flip H
          </button>
          <button type="button" onClick={onFlipVertical}>
            Flip V
          </button>
        </div>

        <div className="buttonCluster">
          <button type="button" onClick={() => onShift("up")} title="Move up">
            Up
          </button>
          <button type="button" onClick={() => onShift("down")} title="Move down">
            Down
          </button>
          <button type="button" onClick={() => onShift("left")} title="Move left">
            Left
          </button>
          <button type="button" onClick={() => onShift("right")} title="Move right">
            Right
          </button>
        </div>
      </div>

      <PalettePanel
        palette={palette}
        paletteLimit={paletteLimit}
        selectedColorKey={selectedColorKey}
        onSelectColor={onPaletteSelect}
        onUpdateColor={onPaletteColorChange}
      />

      <div
        className="pixelGrid"
        style={{ gridTemplateColumns: `repeat(${size}, minmax(0, 1fr))` }}
        onPointerLeave={() => setIsPointerDown(false)}
        onPointerUp={() => setIsPointerDown(false)}
      >
        {spriteGrid.map((row, rowIndex) =>
          Array.from(row).map((colorKey, columnIndex) => {
            const color = palette[colorKey] ?? "transparent";
            const isTransparent = color === "transparent";

            return (
              <button
                aria-label={`Pixel ${columnIndex + 1}, ${rowIndex + 1}, ${colorKey}`}
                className={`pixelCell${isTransparent ? " isTransparent" : ""}`}
                key={`${rowIndex}-${columnIndex}`}
                type="button"
                onPointerDown={() => handleCellPointerDown(rowIndex, columnIndex)}
                onPointerEnter={() => handleCellPointerEnter(rowIndex, columnIndex)}
                style={isTransparent ? undefined : { backgroundColor: color }}
              />
            );
          }),
        )}
      </div>
    </section>
  );
}
