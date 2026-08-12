import { useState } from "react";

type ImageUploaderProps = {
  imageName: string | null;
  onImageLoad: (image: HTMLImageElement, fileName: string) => void;
};

export function ImageUploader({ imageName, onImageLoad }: ImageUploaderProps) {
  const [error, setError] = useState<string | null>(null);

  function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];

    if (!file) {
      return;
    }

    if (!file.type.startsWith("image/")) {
      setError("Choose a PNG, JPG, or WebP image.");
      return;
    }

    const objectUrl = URL.createObjectURL(file);
    const image = new Image();

    image.onload = () => {
      URL.revokeObjectURL(objectUrl);
      setError(null);
      onImageLoad(image, file.name);
    };

    image.onerror = () => {
      URL.revokeObjectURL(objectUrl);
      setError("The image could not be loaded.");
    };

    image.src = objectUrl;
  }

  return (
    <div className="controlGroup">
      <label className="controlLabel" htmlFor="image-upload">
        Image
      </label>
      <input
        id="image-upload"
        className="fileInput"
        type="file"
        accept="image/png,image/jpeg,image/webp"
        onChange={handleFileChange}
      />
      {imageName ? <p className="fileName">{imageName}</p> : <p className="hint">No file loaded.</p>}
      {error ? <p className="errorText">{error}</p> : null}
    </div>
  );
}
