import { useMemo, useState } from "react";
import { BackgroundPicker } from "./components/BackgroundPicker";
import { CodeExportPanel } from "./components/CodeExportPanel";
import { HelpPanel } from "./components/HelpPanel";
import { ImageUploader } from "./components/ImageUploader";
import { PixelEditor } from "./components/PixelEditor";
import { PreviewPanel } from "./components/PreviewPanel";
import { samplePalette, sampleSpriteGrid, sampleSpriteName } from "./data/sampleSprite";
import type {
  ColorKey,
  GridSize,
  Palette,
  PaletteLimit,
  RgbColor,
  ShiftDirection,
  SpriteGrid,
  ToolMode,
  TransparencyMode,
} from "./types/sprite";
import {
  createBlankGrid,
  flipGridHorizontal,
  flipGridVertical,
  setGridCell,
  shiftGrid,
} from "./utils/gridTransforms";
import { imageToPixelGrid } from "./utils/imageToPixelGrid";
import { clampGridToPaletteLimit, normalizePaletteForLimit } from "./utils/paletteKeys";

const GRID_SIZE_OPTIONS: GridSize[] = [16, 24, 32, 48, 64];
const PALETTE_LIMIT_OPTIONS: PaletteLimit[] = [4, 8, 16, 32];
const TRANSPARENCY_MODE_OPTIONS: Array<{ value: TransparencyMode; label: string }> = [
  { value: "alpha-only", label: "Alpha only" },
  { value: "none", label: "No transparency" },
  { value: "corner-color", label: "Corner color" },
  { value: "manual-color", label: "Manual background color" },
];
const INITIAL_GRID_SIZE: GridSize = 32;
const INITIAL_TRANSPARENCY_TOLERANCE = 5;
const INITIAL_PALETTE: Palette = normalizePaletteForLimit({
  "0": "transparent",
  "1": "#111111",
}, 16);
const HISTORY_LIMIT = 80;

function App() {
  const [uploadedImage, setUploadedImage] = useState<HTMLImageElement | null>(null);
  const [uploadedImageName, setUploadedImageName] = useState<string | null>(null);
  const [gridSize, setGridSize] = useState<GridSize>(INITIAL_GRID_SIZE);
  const [paletteLimit, setPaletteLimit] = useState<PaletteLimit>(16);
  const [palette, setPalette] = useState<Palette>(INITIAL_PALETTE);
  const [spriteGrid, setSpriteGrid] = useState<SpriteGrid>(() => createBlankGrid(INITIAL_GRID_SIZE));
  const [selectedColorKey, setSelectedColorKey] = useState<ColorKey>("1");
  const [toolMode, setToolMode] = useState<ToolMode>("paint");
  const [transparencyMode, setTransparencyMode] = useState<TransparencyMode>("alpha-only");
  const [transparencyTolerance, setTransparencyTolerance] = useState(INITIAL_TRANSPARENCY_TOLERANCE);
  const [manualBackgroundColor, setManualBackgroundColor] = useState<RgbColor | null>(null);
  const [isPickingBackground, setIsPickingBackground] = useState(false);
  const [history, setHistory] = useState<SpriteGrid[]>([]);
  const [future, setFuture] = useState<SpriteGrid[]>([]);
  const [statusMessage, setStatusMessage] = useState("Load an image, then convert it to a code grid.");
  const [isHelpOpen, setIsHelpOpen] = useState(false);

  const paletteSummary = useMemo(() => {
    const colorCount = Math.max(0, Object.keys(palette).length - 1);
    return `${colorCount} colors + transparent`;
  }, [palette]);

  const transparencySummary = useMemo(() => {
    if (transparencyMode === "corner-color") {
      return `Corner color ±${transparencyTolerance}`;
    }

    if (transparencyMode === "manual-color") {
      return `Manual bg ${manualBackgroundColor ? rgbToHex(manualBackgroundColor) : "not picked"} ±${transparencyTolerance}`;
    }

    return getTransparencyModeLabel(transparencyMode);
  }, [manualBackgroundColor, transparencyMode, transparencyTolerance]);

  function handleImageLoad(image: HTMLImageElement, fileName: string) {
    setUploadedImage(image);
    setUploadedImageName(fileName);
    setManualBackgroundColor(null);
    setIsPickingBackground(false);
    setStatusMessage("Image loaded in browser memory.");
  }

  function handleGridSizeChange(nextSize: GridSize) {
    setGridSize(nextSize);

    if (!uploadedImage) {
      setSpriteGrid(createBlankGrid(nextSize));
      setHistory([]);
      setFuture([]);
    }
  }

  function handleConvert() {
    if (!uploadedImage) {
      setStatusMessage("Choose an image before converting.");
      return;
    }

    if (transparencyMode === "manual-color" && !manualBackgroundColor) {
      setStatusMessage("Pick a manual background color before converting.");
      return;
    }

    const result = imageToPixelGrid(uploadedImage, gridSize, paletteLimit, {
      mode: transparencyMode,
      tolerance: transparencyTolerance,
      backgroundColor: manualBackgroundColor,
    });
    const nextPalette = normalizePaletteForLimit(result.palette, paletteLimit);
    setPalette(nextPalette);
    setSpriteGrid(result.spriteGrid);
    setHistory([]);
    setFuture([]);
    setSelectedColorKey(getFirstPaintKey(nextPalette));
    setToolMode("paint");
    setStatusMessage(
      `Converted to ${gridSize}x${gridSize} with up to ${paletteLimit} colors. Transparency: ${getTransparencyModeLabel(
        transparencyMode,
      )}.`,
    );
  }

  function handleLoadSample() {
    const nextPaletteLimit: PaletteLimit = 8;
    const nextPalette = normalizePaletteForLimit(samplePalette, nextPaletteLimit);
    setGridSize(16);
    setPaletteLimit(nextPaletteLimit);
    setPalette(nextPalette);
    setSpriteGrid(sampleSpriteGrid);
    setSelectedColorKey(getFirstPaintKey(nextPalette));
    setToolMode("paint");
    setHistory([]);
    setFuture([]);
    setStatusMessage(`${sampleSpriteName} sample loaded.`);
  }

  function commitGrid(nextGrid: SpriteGrid) {
    if (nextGrid.join("\n") === spriteGrid.join("\n")) {
      return;
    }

    setHistory((current) => [...current.slice(-(HISTORY_LIMIT - 1)), spriteGrid]);
    setFuture([]);
    setSpriteGrid(nextGrid);
  }

  function handleCellAction(row: number, column: number) {
    const currentKey = spriteGrid[row]?.[column] ?? "0";

    if (toolMode === "eyedropper") {
      setSelectedColorKey(currentKey);
      setToolMode("paint");
      return;
    }

    const nextKey = toolMode === "erase" ? "0" : selectedColorKey;

    if (currentKey === nextKey) {
      return;
    }

    commitGrid(setGridCell(spriteGrid, row, column, nextKey));
  }

  function handleUndo() {
    setHistory((currentHistory) => {
      const previousGrid = currentHistory.at(-1);

      if (!previousGrid) {
        return currentHistory;
      }

      setFuture((currentFuture) => [spriteGrid, ...currentFuture]);
      setSpriteGrid(previousGrid);
      return currentHistory.slice(0, -1);
    });
  }

  function handleRedo() {
    setFuture((currentFuture) => {
      const nextGrid = currentFuture[0];

      if (!nextGrid) {
        return currentFuture;
      }

      setHistory((currentHistory) => [...currentHistory.slice(-(HISTORY_LIMIT - 1)), spriteGrid]);
      setSpriteGrid(nextGrid);
      return currentFuture.slice(1);
    });
  }

  function handleClear() {
    commitGrid(createBlankGrid(spriteGrid.length));
  }

  function handleFlipHorizontal() {
    commitGrid(flipGridHorizontal(spriteGrid));
  }

  function handleFlipVertical() {
    commitGrid(flipGridVertical(spriteGrid));
  }

  function handleShift(direction: ShiftDirection) {
    commitGrid(shiftGrid(spriteGrid, direction));
  }

  function handlePaletteSelect(key: ColorKey) {
    setSelectedColorKey(key);

    if (toolMode === "eyedropper") {
      setToolMode("paint");
    }
  }

  function handlePaletteColorChange(key: ColorKey, color: string) {
    if (key === "0") {
      return;
    }

    setPalette((currentPalette) => ({
      ...currentPalette,
      [key]: color,
    }));
  }

  function handlePaletteLimitChange(nextLimit: PaletteLimit) {
    const nextPalette = normalizePaletteForLimit(palette, nextLimit);
    const nextGrid = clampGridToPaletteLimit(spriteGrid, nextLimit);

    setPaletteLimit(nextLimit);
    setPalette(nextPalette);
    setSpriteGrid(nextGrid);
    setHistory([]);
    setFuture([]);

    if (!nextPalette[selectedColorKey]) {
      setSelectedColorKey(getFirstPaintKey(nextPalette));
    }

    setStatusMessage(`Palette slots changed to ${nextLimit} colors.`);
  }

  function handleTransparencyModeChange(nextMode: TransparencyMode) {
    setTransparencyMode(nextMode);

    if (nextMode !== "manual-color") {
      setIsPickingBackground(false);
    }
  }

  function handleManualBackgroundPick(color: RgbColor) {
    setManualBackgroundColor(color);
    setIsPickingBackground(false);
    setStatusMessage(`Manual background color picked: ${rgbToHex(color)}.`);
  }

  return (
    <div className="appShell">
      <header className="appHeader">
        <div>
          <p className="eyebrow">Canvas-only image processing</p>
          <h1>Dot Code Editor MVP</h1>
          <p className="appIntro">
            Convert browser-local images into editable sprite strings, palette objects, and a React
            renderer.
          </p>
        </div>
        <div className="headerStats" aria-label="Current sprite status">
          <span>{gridSize}x{gridSize}</span>
          <span>{paletteSummary}</span>
          <span>{transparencySummary}</span>
          <button className="helpToggle" type="button" onClick={() => setIsHelpOpen((current) => !current)}>
            {isHelpOpen ? "도움말 닫기" : "도움말"}
          </button>
        </div>
      </header>

      <HelpPanel isOpen={isHelpOpen} />

      <main className="workspace">
        <aside className="leftPanel" aria-label="Input settings">
          <section className="panelSection">
            <div className="sectionHeader">
              <h2>Input</h2>
              <span className="sectionMeta">Local only</span>
            </div>
            <ImageUploader imageName={uploadedImageName} onImageLoad={handleImageLoad} />

            <div className="controlGroup">
              <label className="controlLabel" htmlFor="grid-size">
                Grid size
              </label>
              <select
                id="grid-size"
                value={gridSize}
                onChange={(event) => handleGridSizeChange(Number(event.target.value) as GridSize)}
              >
                {GRID_SIZE_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {option}x{option}
                  </option>
                ))}
              </select>
            </div>

            <div className="controlGroup">
              <label className="controlLabel" htmlFor="palette-limit">
                Palette limit
              </label>
              <select
                id="palette-limit"
                value={paletteLimit}
                onChange={(event) => handlePaletteLimitChange(Number(event.target.value) as PaletteLimit)}
              >
                {PALETTE_LIMIT_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {option} colors
                  </option>
                ))}
              </select>
            </div>

            <div className="controlGroup">
              <label className="controlLabel" htmlFor="transparency-mode">
                Transparency mode
              </label>
              <select
                id="transparency-mode"
                value={transparencyMode}
                onChange={(event) =>
                  handleTransparencyModeChange(event.target.value as TransparencyMode)
                }
              >
                {TRANSPARENCY_MODE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <p className="hint">{getTransparencyModeDescription(transparencyMode)}</p>
            </div>

            {transparencyMode === "corner-color" || transparencyMode === "manual-color" ? (
              <div className="controlGroup">
                <div className="rangeHeader">
                  <label className="controlLabel" htmlFor="transparency-tolerance">
                    Tolerance
                  </label>
                  <span>{transparencyTolerance}</span>
                </div>
                <input
                  id="transparency-tolerance"
                  max="100"
                  min="0"
                  type="range"
                  value={transparencyTolerance}
                  onChange={(event) => setTransparencyTolerance(Number(event.target.value))}
                />
              </div>
            ) : null}

            {transparencyMode === "manual-color" ? (
              <BackgroundPicker
                image={uploadedImage}
                isPicking={isPickingBackground}
                onPickColor={handleManualBackgroundPick}
                onTogglePicking={() => setIsPickingBackground((current) => !current)}
                selectedColor={manualBackgroundColor}
              />
            ) : null}

            <button className="primaryButton" type="button" onClick={handleConvert}>
              Convert Image
            </button>

            <button className="secondaryButton" type="button" onClick={handleLoadSample}>
              샘플 불러오기
            </button>

            <p className="statusText">{statusMessage}</p>
          </section>
        </aside>

        <PixelEditor
          spriteGrid={spriteGrid}
          palette={palette}
          paletteLimit={paletteLimit}
          selectedColorKey={selectedColorKey}
          toolMode={toolMode}
          canUndo={history.length > 0}
          canRedo={future.length > 0}
          onCellAction={handleCellAction}
          onPaletteSelect={handlePaletteSelect}
          onPaletteColorChange={handlePaletteColorChange}
          onToolModeChange={setToolMode}
          onUndo={handleUndo}
          onRedo={handleRedo}
          onClear={handleClear}
          onFlipHorizontal={handleFlipHorizontal}
          onFlipVertical={handleFlipVertical}
          onShift={handleShift}
        />

        <aside className="rightPanel" aria-label="Preview and export">
          <PreviewPanel spriteGrid={spriteGrid} palette={palette} />
          <CodeExportPanel spriteGrid={spriteGrid} palette={palette} />
        </aside>
      </main>
    </div>
  );
}

function getFirstPaintKey(palette: Palette): ColorKey {
  return Object.keys(palette).find((key) => key !== "0") ?? "0";
}

function getTransparencyModeLabel(mode: TransparencyMode): string {
  return TRANSPARENCY_MODE_OPTIONS.find((option) => option.value === mode)?.label ?? "Alpha only";
}

function getTransparencyModeDescription(mode: TransparencyMode): string {
  if (mode === "alpha-only") {
    return "Only pixels with original alpha 0 become transparent.";
  }

  if (mode === "none") {
    return "Every sampled pixel is kept as a palette color.";
  }

  if (mode === "corner-color") {
    return "The four output corners estimate the background color.";
  }

  return "Pick a source pixel as the background color.";
}

function rgbToHex({ r, g, b }: RgbColor): string {
  return `#${toHexPair(r)}${toHexPair(g)}${toHexPair(b)}`;
}

function toHexPair(value: number): string {
  return value.toString(16).padStart(2, "0");
}

export default App;
