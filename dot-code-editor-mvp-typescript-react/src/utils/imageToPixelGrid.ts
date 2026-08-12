import type {
  GridSize,
  PaletteLimit,
  PixelGridResult,
  RgbColor,
  SampledPixel,
  TransparencyOptions,
} from "../types/sprite";
import { buildSpriteFromPixels } from "./paletteQuantize";

const DEFAULT_TRANSPARENCY_OPTIONS: TransparencyOptions = {
  mode: "alpha-only",
  tolerance: 5,
  backgroundColor: null,
};

export function imageToPixelGrid(
  image: HTMLImageElement,
  size: GridSize,
  paletteLimit: PaletteLimit,
  transparencyOptions: TransparencyOptions = DEFAULT_TRANSPARENCY_OPTIONS,
): PixelGridResult {
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;

  const context = canvas.getContext("2d", { willReadFrequently: true });

  if (!context) {
    throw new Error("Canvas 2D context is not available.");
  }

  context.clearRect(0, 0, size, size);
  context.imageSmoothingEnabled = false;

  const sourceRatio = image.naturalWidth / image.naturalHeight;
  const targetRatio = 1;
  let drawWidth: number = size;
  let drawHeight: number = size;
  let offsetX = 0;
  let offsetY = 0;

  if (sourceRatio > targetRatio) {
    drawHeight = Math.max(1, Math.round(size / sourceRatio));
    offsetY = Math.floor((size - drawHeight) / 2);
  } else if (sourceRatio < targetRatio) {
    drawWidth = Math.max(1, Math.round(size * sourceRatio));
    offsetX = Math.floor((size - drawWidth) / 2);
  }

  context.drawImage(image, offsetX, offsetY, drawWidth, drawHeight);

  const { data } = context.getImageData(0, 0, size, size);
  const pixels: SampledPixel[] = [];
  const options = {
    ...DEFAULT_TRANSPARENCY_OPTIONS,
    ...transparencyOptions,
  };
  const cornerBackgroundColor =
    options.mode === "corner-color" ? getCornerRepresentativeColor(data, size) : null;

  for (let index = 0; index < data.length; index += 4) {
    const alpha = data[index + 3];
    const pixel = {
      r: data[index],
      g: data[index + 1],
      b: data[index + 2],
    };

    if (shouldExportTransparent(pixel, alpha, options, cornerBackgroundColor)) {
      pixels.push(null);
    } else {
      pixels.push(pixel);
    }
  }

  return buildSpriteFromPixels(pixels, size, paletteLimit);
}

function shouldExportTransparent(
  pixel: RgbColor,
  alpha: number,
  options: TransparencyOptions,
  cornerBackgroundColor: RgbColor | null,
): boolean {
  if (options.mode === "none") {
    return false;
  }

  if (options.mode === "alpha-only") {
    return alpha === 0;
  }

  if (options.mode === "corner-color") {
    return Boolean(cornerBackgroundColor && isWithinTolerance(pixel, cornerBackgroundColor, options.tolerance));
  }

  return Boolean(
    options.backgroundColor && isWithinTolerance(pixel, options.backgroundColor, options.tolerance),
  );
}

function getCornerRepresentativeColor(data: Uint8ClampedArray, size: number): RgbColor {
  const cornerIndexes = [0, size - 1, size * (size - 1), size * size - 1];
  const totals = cornerIndexes.reduce(
    (current, pixelIndex) => {
      const dataIndex = pixelIndex * 4;

      return {
        r: current.r + data[dataIndex],
        g: current.g + data[dataIndex + 1],
        b: current.b + data[dataIndex + 2],
      };
    },
    { r: 0, g: 0, b: 0 },
  );

  return {
    r: Math.round(totals.r / cornerIndexes.length),
    g: Math.round(totals.g / cornerIndexes.length),
    b: Math.round(totals.b / cornerIndexes.length),
  };
}

function isWithinTolerance(first: RgbColor, second: RgbColor, tolerance: number): boolean {
  const clampedTolerance = Math.min(255, Math.max(0, tolerance));

  return (
    Math.abs(first.r - second.r) <= clampedTolerance &&
    Math.abs(first.g - second.g) <= clampedTolerance &&
    Math.abs(first.b - second.b) <= clampedTolerance
  );
}
