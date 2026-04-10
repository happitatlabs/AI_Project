from pathlib import Path
from PIL import Image, ImageChops
root = Path(r"C:\Users\Hyein\ClaudeAI\AI_Project")
segments_dir = root / '.tmp_fullpage_segments'
paths = sorted(segments_dir.glob('segment_*.png'))
if not paths:
    raise SystemExit('no segments captured')
imgs = [Image.open(p).convert('RGB') for p in paths]
filtered = [imgs[0]]
for img in imgs[1:]:
    diff = ImageChops.difference(filtered[-1], img)
    if diff.getbbox() is not None:
        filtered.append(img)
imgs = filtered
width = imgs[0].width
parts = [imgs[0]]
for nxt in imgs[1:]:
    prev = parts[-1]
    max_overlap = min(prev.height, nxt.height, 700)
    best_overlap = 0
    best_score = None
    for overlap in range(max_overlap, 150, -20):
        prev_crop = prev.crop((0, prev.height - overlap, width, prev.height)).resize((max(1, width // 8), max(1, overlap // 8)))
        next_crop = nxt.crop((0, 0, width, overlap)).resize((max(1, width // 8), max(1, overlap // 8)))
        diff = ImageChops.difference(prev_crop, next_crop)
        bbox = diff.getbbox()
        score = 0 if bbox is None else sum(diff.crop(bbox).histogram())
        if best_score is None or score < best_score:
            best_score = score
            best_overlap = overlap
    overlap = best_overlap or 250
    parts.append(nxt.crop((0, overlap, width, nxt.height)))
height = sum(p.height for p in parts)
canvas = Image.new('RGB', (width, height), 'white')
y = 0
for part in parts:
    canvas.paste(part, (0, y))
    y += part.height
out = root / 'project_result_fullpage.png'
canvas.save(out)
print(out)
