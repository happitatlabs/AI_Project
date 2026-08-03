import { useEffect, useRef } from "react";
import type { RgbColor } from "../types/sprite";

type BackgroundPickerProps = {
  image: HTMLImageElement | null;
  selectedColor: RgbColor | null;
  isPicking: boolean;
  onTogglePicking: () => void;
  onPickColor: (color: RgbColor) => void;
};

const PREVIEW_WIDTH = 240;
const PREVIEW_HEIGHT = 150;

export function BackgroundPicker({
  image,
  selectedColor,
  isPicking,
  onTogglePicking,
  onPickColor,
}: BackgroundPickerProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;

    if (!canvas) {
      return;
    }

    const context = canvas.getContext("2d");

    if (!context) {
      return;
    }

    context.clearRect(0, 0, canvas.width, canvas.height);
    context.fillStyle = "#f7f6f2";
    context.fillRect(0, 0, canvas.width, canvas.height);

    if (!image) {
      return;
    }

    const drawRect = getContainRect(canvas.width, canvas.height, image.naturalWidth, image.naturalHeight);
    context.imageSmoothingEnabled = false;
    context.drawImage(image, drawRect.x, drawRect.y, drawRect.width, drawRect.height);
  }, [image]);

  function handlePointerDown(event: React.PointerEvent<HTMLCanvasElement>) {
    const canvas = canvasRef.current;

    if (!canvas || !image || !isPicking) {
      return;
    }

    const canvasRect = canvas.getBoundingClientRect();
    const x = ((event.clientX - canvasRect.left) / canvasRect.width) * canvas.width;
    const y = ((event.clientY - canvasRect.top) / canvasRect.height) * canvas.height;
    const drawRect = getContainRect(canvas.width, canvas.height, image.naturalWidth, image.naturalHeight);

    if (
      x < drawRect.x ||
      y < drawRect.y ||
      x > drawRect.x + drawRect.width ||
      y > drawRect.y + drawRect.height
    ) {
      return;
    }

    const sourceX = clamp(
      Math.floor(((x - drawRect.x) / drawRect.width) * image.naturalWidth),
      0,
      image.naturalWidth - 1,
    );
    const sourceY = clamp(
      Math.floor(((y - drawRect.y) / drawRect.height) * image.naturalHeight),
      0,
      image.naturalHeight - 1,
    );

    onPickColor(sampleImageColor(image, sourceX, sourceY));
  }

  return (
    <div className="backgroundPicker">
      <div className="backgroundPickerControls">
        <button className="secondaryButton" type="button" onClick={onTogglePicking} disabled={!image}>
          {isPicking ? "Cancel pick" : "Pick background"}
        </button>
        <span className="pickedColor">
          <span
            className="pickedColorSwatch"
            style={selectedColor ? { backgroundColor: rgbToHex(selectedColor) } : undefined}
          />
          <span>{selectedColor ? rgbToHex(selectedColor) : "not picked"}</span>
        </span>
      </div>

      {image ? (
        <canvas
          aria-label="Source image background picker"
          className={`backgroundPreview${isPicking ? " isPicking" : ""}`}
          height={PREVIEW_HEIGHT}
          onPointerDown={handlePointerDown}
          ref={canvasRef}
          width={PREVIEW_WIDTH}
        />
      ) : (
        <p className="hint">Load an image before picking a manual background color.</p>
      )}

      {image && isPicking ? <p className="hint">Click a pixel in the source preview.</p> : null}
    </div>
  );
}

function sampleImageColor(image: HTMLImageElement, x: number, y: number): RgbColor {
  const canvas = document.createElement("canvas");
  canvas.width = image.naturalWidth;
  canvas.height = image.naturalHeight;

  const context = canvas.getContext("2d", { willReadFrequently: true });

  if (!context) {
    return { r: 0, g: 0, b: 0 };
  }

  context.drawImage(image, 0, 0);
  const [r, g, b] = context.getImageData(x, y, 1, 1).data;

  return { r, g, b };
}

function getContainRect(
  canvasWidth: number,
  canvasHeight: number,
  imageWidth: number,
  imageHeight: number,
) {
  const scale = Math.min(canvasWidth / imageWidth, canvasHeight / imageHeight);
  const width = imageWidth * scale;
  const height = imageHeight * scale;

  return {
    x: (canvasWidth - width) / 2,
    y: (canvasHeight - height) / 2,
    width,
    height,
  };
}

function rgbToHex({ r, g, b }: RgbColor): string {
  return `#${toHexPair(r)}${toHexPair(g)}${toHexPair(b)}`;
}

function toHexPair(value: number): string {
  return value.toString(16).padStart(2, "0");
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}
