import type { Palette, PixelGridResult, RgbColor, SampledPixel } from "../types/sprite";
import { PALETTE_KEYS } from "./paletteKeys";

type WeightedColor = RgbColor & {
  count: number;
};

type ColorBucket = {
  colors: WeightedColor[];
  population: number;
};

export function buildSpriteFromPixels(
  pixels: SampledPixel[],
  size: number,
  paletteLimit: number,
): PixelGridResult {
  const sourceColors = pixels.filter((pixel): pixel is RgbColor => pixel !== null);
  const paletteColors = quantizeColors(sourceColors, Math.min(paletteLimit, PALETTE_KEYS.length));
  const palette: Palette = { "0": "transparent" };

  paletteColors.forEach((color, index) => {
    palette[PALETTE_KEYS[index]] = rgbToHex(color);
  });

  const rows: string[] = [];

  for (let row = 0; row < size; row += 1) {
    let rowValue = "";

    for (let column = 0; column < size; column += 1) {
      const pixel = pixels[row * size + column];

      if (!pixel || paletteColors.length === 0) {
        rowValue += "0";
      } else {
        rowValue += PALETTE_KEYS[getNearestColorIndex(pixel, paletteColors)];
      }
    }

    rows.push(rowValue);
  }

  return { palette, spriteGrid: rows };
}

function quantizeColors(colors: RgbColor[], limit: number): RgbColor[] {
  const weighted = buildWeightedColors(colors);

  if (weighted.length <= limit) {
    return weighted
      .sort((first, second) => second.count - first.count)
      .map(({ r, g, b }) => ({ r, g, b }));
  }

  const buckets: ColorBucket[] = [
    {
      colors: weighted,
      population: weighted.reduce((total, color) => total + color.count, 0),
    },
  ];

  while (buckets.length < limit) {
    const splitIndex = getNextBucketIndex(buckets);

    if (splitIndex === -1) {
      break;
    }

    const [first, second] = splitBucket(buckets[splitIndex]);
    buckets.splice(splitIndex, 1, first, second);
  }

  return buckets
    .map((bucket) => ({
      color: averageBucket(bucket),
      population: bucket.population,
    }))
    .sort((first, second) => second.population - first.population)
    .map(({ color }) => color);
}

function buildWeightedColors(colors: RgbColor[]): WeightedColor[] {
  const colorMap = new Map<string, WeightedColor>();

  colors.forEach((color) => {
    const key = `${color.r},${color.g},${color.b}`;
    const existing = colorMap.get(key);

    if (existing) {
      existing.count += 1;
      return;
    }

    colorMap.set(key, { ...color, count: 1 });
  });

  return Array.from(colorMap.values());
}

function getNextBucketIndex(buckets: ColorBucket[]): number {
  let bestIndex = -1;
  let bestScore = 0;

  buckets.forEach((bucket, index) => {
    if (bucket.colors.length < 2) {
      return;
    }

    const score = getBucketRange(bucket) * bucket.population;

    if (score > bestScore) {
      bestScore = score;
      bestIndex = index;
    }
  });

  return bestIndex;
}

function splitBucket(bucket: ColorBucket): [ColorBucket, ColorBucket] {
  const channel = getDominantChannel(bucket.colors);
  const sorted = [...bucket.colors].sort((first, second) => first[channel] - second[channel]);
  const splitAt = getWeightedMedianIndex(sorted);
  const leftColors = sorted.slice(0, splitAt);
  const rightColors = sorted.slice(splitAt);

  return [makeBucket(leftColors), makeBucket(rightColors)];
}

function makeBucket(colors: WeightedColor[]): ColorBucket {
  return {
    colors,
    population: colors.reduce((total, color) => total + color.count, 0),
  };
}

function getWeightedMedianIndex(colors: WeightedColor[]): number {
  const total = colors.reduce((sum, color) => sum + color.count, 0);
  const midpoint = total / 2;
  let runningTotal = 0;

  for (let index = 0; index < colors.length; index += 1) {
    runningTotal += colors[index].count;

    if (runningTotal >= midpoint) {
      return Math.min(index + 1, colors.length - 1);
    }
  }

  return Math.max(1, Math.floor(colors.length / 2));
}

function getBucketRange(bucket: ColorBucket): number {
  const ranges = getRanges(bucket.colors);
  return Math.max(ranges.r, ranges.g, ranges.b);
}

function getDominantChannel(colors: WeightedColor[]): keyof RgbColor {
  const ranges = getRanges(colors);

  if (ranges.r >= ranges.g && ranges.r >= ranges.b) {
    return "r";
  }

  if (ranges.g >= ranges.r && ranges.g >= ranges.b) {
    return "g";
  }

  return "b";
}

function getRanges(colors: WeightedColor[]): RgbColor {
  const initial = {
    minR: 255,
    maxR: 0,
    minG: 255,
    maxG: 0,
    minB: 255,
    maxB: 0,
  };

  const ranges = colors.reduce((current, color) => {
    return {
      minR: Math.min(current.minR, color.r),
      maxR: Math.max(current.maxR, color.r),
      minG: Math.min(current.minG, color.g),
      maxG: Math.max(current.maxG, color.g),
      minB: Math.min(current.minB, color.b),
      maxB: Math.max(current.maxB, color.b),
    };
  }, initial);

  return {
    r: ranges.maxR - ranges.minR,
    g: ranges.maxG - ranges.minG,
    b: ranges.maxB - ranges.minB,
  };
}

function averageBucket(bucket: ColorBucket): RgbColor {
  const totals = bucket.colors.reduce(
    (current, color) => {
      return {
        r: current.r + color.r * color.count,
        g: current.g + color.g * color.count,
        b: current.b + color.b * color.count,
        count: current.count + color.count,
      };
    },
    { r: 0, g: 0, b: 0, count: 0 },
  );

  return {
    r: Math.round(totals.r / totals.count),
    g: Math.round(totals.g / totals.count),
    b: Math.round(totals.b / totals.count),
  };
}

function getNearestColorIndex(color: RgbColor, paletteColors: RgbColor[]): number {
  let nearestIndex = 0;
  let nearestDistance = Number.POSITIVE_INFINITY;

  paletteColors.forEach((paletteColor, index) => {
    const distance = getColorDistance(color, paletteColor);

    if (distance < nearestDistance) {
      nearestDistance = distance;
      nearestIndex = index;
    }
  });

  return nearestIndex;
}

function getColorDistance(first: RgbColor, second: RgbColor): number {
  return (
    (first.r - second.r) ** 2 +
    (first.g - second.g) ** 2 +
    (first.b - second.b) ** 2
  );
}

function rgbToHex(color: RgbColor): string {
  return `#${toHexPair(color.r)}${toHexPair(color.g)}${toHexPair(color.b)}`;
}

function toHexPair(value: number): string {
  return value.toString(16).padStart(2, "0");
}
