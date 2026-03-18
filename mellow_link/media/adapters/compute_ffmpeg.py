"""
로컬 FFmpeg 기반 미디어 연산 어댑터.

allow_media_compute() & allow_ffmpeg() 일 때만 실제 호출.
ENABLE_FFMPEG=0이면 명확한 에러로 차단.
모든 subprocess/ffmpeg 호출은 이 어댑터 내부에만 존재.
"""
import logging
import math
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, List, Optional

from mellow_link.media.adapters.base import MediaComputeAdapter

logger = logging.getLogger(__name__)

_FFMPEG_BLOCK_MSG = "ENABLE_FFMPEG=0. FFmpeg 호출이 비활성화되어 있습니다. 미디어 연산을 사용하려면 ENABLE_FFMPEG=1로 설정하세요."
_COMPUTE_BLOCK_MSG = "ENABLE_MEDIA_COMPUTE=0. 미디어 로컬 연산이 비활성화되어 있습니다."
_DEFAULT_CRF = 25
_DEFAULT_PRESET = "faster"


def _check_ffmpeg_allowed() -> None:
    try:
        from mellow_link.config.settings import get_settings
        s = get_settings()
        if not s.allow_media_compute():
            raise RuntimeError(_COMPUTE_BLOCK_MSG)
        if not s.allow_ffmpeg():
            raise RuntimeError(_FFMPEG_BLOCK_MSG)
    except RuntimeError:
        raise
    except Exception as e:
        logger.warning("[LocalFFmpegComputeAdapter] settings check failed: %s", e)
        raise RuntimeError(_FFMPEG_BLOCK_MSG)


def _resolve_tool(name: str) -> str:
    """ffmpeg/ffprobe 실행 경로. (video_processor와 동일 로직, 어댑터 자체 구현)"""
    tool = (name or "").strip().lower()
    if tool not in {"ffmpeg", "ffprobe"}:
        return name
    env_full = os.getenv("MELLOW_FFMPEG_PATH" if tool == "ffmpeg" else "MELLOW_FFPROBE_PATH")
    if isinstance(env_full, str) and env_full.strip():
        p = Path(env_full.strip()).expanduser()
        if p.exists():
            return str(p)
    env_dir = os.getenv("MELLOW_FFMPEG_BIN_DIR")
    if isinstance(env_dir, str) and env_dir.strip():
        d = Path(env_dir.strip()).expanduser()
        exe = d / (tool + (".exe" if os.name == "nt" else ""))
        if exe.exists():
            return str(exe)
    comfy_out = os.getenv("MELLOW_COMFY_OUTPUT_DIR")
    if isinstance(comfy_out, str) and comfy_out.strip():
        out_dir = Path(comfy_out.strip()).expanduser()
        try:
            out_dir = out_dir.resolve()
        except Exception:
            pass
        for idx in (2, 1, 3):
            try:
                root = out_dir.parents[idx]
            except Exception:
                continue
            for d in [root / "ffmpeg" / "bin", root / "ffmpeg", root / "tools" / "ffmpeg" / "bin",
                     root / "ComfyUI" / "ffmpeg" / "bin", root / "ComfyUI" / "ffmpeg", root / "bin"]:
                exe = d / (tool + (".exe" if os.name == "nt" else ""))
                if exe.exists():
                    return str(exe)
    found = shutil.which(tool)
    if found:
        return found
    return name


def _resolve_ffmpeg() -> str:
    return _resolve_tool("ffmpeg")


def _resolve_ffprobe() -> str:
    return _resolve_tool("ffprobe")


def _safe_suffix(target_duration: float) -> str:
    sec = int(round(target_duration))
    return f"_looped_{sec}s"


def _get_encoding_params() -> tuple:
    crf, preset = _DEFAULT_CRF, _DEFAULT_PRESET
    raw = os.getenv("MELLOW_VIDEO_CRF")
    if isinstance(raw, str) and raw.strip():
        try:
            crf = max(23, min(28, int(raw.strip())))
        except Exception:
            pass
    raw = os.getenv("MELLOW_VIDEO_PRESET")
    if isinstance(raw, str) and raw.strip() and raw.strip().lower() in ("faster", "medium"):
        preset = raw.strip().lower()
    return crf, preset


def _run_cmd(cmd: List[str], timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
        shell=False,
    )


class LocalFFmpegComputeAdapter(MediaComputeAdapter):
    """FFmpeg 기반 로컬 전용 연산. ENABLE_FFMPEG=0이면 모든 호출에서 차단."""

    def transcode_video(
        self,
        input_path: str | Path,
        output_path: str | Path,
        **kwargs: Any,
    ) -> Path:
        _check_ffmpeg_allowed()
        inp, out = Path(input_path).resolve(), Path(output_path).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        ffmpeg = _resolve_ffmpeg()
        cmd = [
            ffmpeg, "-y", "-i", str(inp),
            "-c:v", kwargs.get("video_codec", "libx264"),
            "-c:a", kwargs.get("audio_codec", "aac"),
            str(out),
        ]
        res = _run_cmd(cmd, timeout=kwargs.get("timeout", 300))
        if res.returncode != 0:
            raise RuntimeError((res.stderr or res.stdout or "ffmpeg failed")[-800:])
        return out

    def generate_thumbnail(
        self,
        input_path: str | Path,
        output_path: str | Path,
        **kwargs: Any,
    ) -> Path:
        _check_ffmpeg_allowed()
        inp, out = Path(input_path).resolve(), Path(output_path).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        ffmpeg = _resolve_ffmpeg()
        t = kwargs.get("time_offset", "0")
        cmd = [ffmpeg, "-y", "-i", str(inp), "-vframes", "1", "-ss", str(t), str(out)]
        res = _run_cmd(cmd, timeout=60)
        if res.returncode != 0:
            raise RuntimeError((res.stderr or res.stdout or "ffmpeg thumbnail failed")[-800:])
        return out

    def merge_audio(
        self,
        video_path: str | Path,
        audio_path: str | Path,
        output_path: str | Path,
        **kwargs: Any,
    ) -> Path:
        _check_ffmpeg_allowed()
        v, a, out = Path(video_path).resolve(), Path(audio_path).resolve(), Path(output_path).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        ffmpeg = _resolve_ffmpeg()
        cmd = [
            ffmpeg, "-y", "-i", str(v), "-i", str(a),
            "-c:v", "copy", "-c:a", "aac", "-shortest",
            str(out),
        ]
        res = _run_cmd(cmd, timeout=kwargs.get("timeout", 300))
        if res.returncode != 0:
            raise RuntimeError((res.stderr or res.stdout or "ffmpeg merge failed")[-800:])
        return out

    def extract_frames(
        self,
        input_path: str | Path,
        output_dir: str | Path,
        **kwargs: Any,
    ) -> List[Path]:
        _check_ffmpeg_allowed()
        inp = Path(input_path).resolve()
        odir = Path(output_dir).resolve()
        odir.mkdir(parents=True, exist_ok=True)
        ffmpeg = _resolve_ffmpeg()
        fps = kwargs.get("fps", "1")
        pattern = str(odir / "frame_%04d.png")
        cmd = [ffmpeg, "-y", "-i", str(inp), "-vf", f"fps={fps}", pattern]
        res = _run_cmd(cmd, timeout=kwargs.get("timeout", 300))
        if res.returncode != 0:
            raise RuntimeError((res.stderr or res.stdout or "ffmpeg extract_frames failed")[-800:])
        return sorted(odir.glob("frame_*.png"))

    def probe_duration_seconds(self, video_path: str | Path) -> Optional[float]:
        _check_ffmpeg_allowed()
        try:
            p = Path(video_path).resolve()
            if not p.exists():
                return None
            try:
                cmd = [
                    _resolve_ffprobe(), "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1", str(p),
                ]
                res = _run_cmd(cmd, timeout=30)
                if res.returncode == 0 and (res.stdout or "").strip():
                    return float((res.stdout or "").strip())
            except FileNotFoundError:
                pass
            cmd = [_resolve_ffmpeg(), "-hide_banner", "-i", str(p)]
            res = _run_cmd(cmd, timeout=30)
            text = (res.stderr or "") + "\n" + (res.stdout or "")
            m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text)
            if not m:
                return None
            hh, mm, ss = m.group(1), m.group(2), m.group(3)
            return int(hh) * 3600.0 + int(mm) * 60.0 + float(ss)
        except Exception:
            return None

    def extend_video_if_needed(
        self,
        input_path: str | Path,
        *,
        target_duration: float = 12.0,
        fps: int = 8,
        mode: str = "boomerang",
        overlap_seconds: float = 0.35,
    ) -> Path:
        _check_ffmpeg_allowed()
        inp = Path(input_path).resolve()
        if not inp.exists():
            return inp
        dur = self.probe_duration_seconds(inp)
        if dur is None or dur >= target_duration:
            return inp
        crf, preset = _get_encoding_params()
        out_path = inp.parent / f"{inp.stem}{_safe_suffix(target_duration)}.mp4"
        out_path = out_path.resolve()
        if mode.lower() in ("boomerang", "pingpong", "ping-pong"):
            self._extend_boomerang(inp, out_path, target_duration=target_duration, fps=fps, crf=crf, preset=preset)
        elif mode.lower() in ("crossfade", "dissolve", "xfade"):
            self._extend_crossfade(inp, out_path, target_duration=target_duration, fps=fps, overlap=overlap_seconds, crf=crf, preset=preset)
        else:
            return inp
        return out_path

    def _extend_boomerang(
        self,
        input_path: Path,
        output_path: Path,
        *,
        target_duration: float,
        fps: int,
        crf: int,
        preset: str,
    ) -> None:
        ff = _resolve_ffmpeg()
        tmp_dir = input_path.parent / ".tmp_video_proc"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        fwd = tmp_dir / (input_path.stem + "_fwd.mp4")
        rev = tmp_dir / (input_path.stem + "_rev.mp4")
        for src, dst, vf in (
            (input_path, fwd, f"fps={fps},format=yuv420p"),
            (input_path, rev, f"reverse,fps={fps},format=yuv420p"),
        ):
            cmd = [ff, "-y", "-i", str(src), "-an", "-vf", vf, "-vcodec", "libx264", "-crf", str(crf), "-preset", preset, "-pix_fmt", "yuv420p", str(dst)]
            res = _run_cmd(cmd, timeout=180)
            if res.returncode != 0:
                raise RuntimeError((res.stderr or res.stdout or "ffmpeg failed")[-800:])
        base_dur = self.probe_duration_seconds(fwd) or 0.0
        cycle_dur = max(0.01, base_dur * 2.0)
        cycles = max(1, int(math.ceil(target_duration / cycle_dur)))
        concat_list = tmp_dir / (input_path.stem + "_concat.txt")
        lines = []
        for _ in range(cycles):
            lines.append(f"file '{fwd.as_posix()}'")
            lines.append(f"file '{rev.as_posix()}'")
        concat_list.write_text("\n".join(lines) + "\n", encoding="utf-8")
        out_path = Path(output_path).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            ff, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
            "-t", str(float(target_duration)), "-an", "-vcodec", "libx264", "-crf", str(crf), "-preset", preset, "-pix_fmt", "yuv420p", "-r", str(int(fps)), str(out_path),
        ]
        res = _run_cmd(cmd, timeout=240)
        if res.returncode != 0:
            raise RuntimeError((res.stderr or res.stdout or "ffmpeg concat failed")[-800:])

    def _extend_crossfade(
        self,
        input_path: Path,
        output_path: Path,
        *,
        target_duration: float,
        fps: int,
        overlap: float,
        crf: int,
        preset: str,
    ) -> None:
        ff = _resolve_ffmpeg()
        tmp_dir = input_path.parent / ".tmp_video_proc"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        base = tmp_dir / (input_path.stem + "_base.mp4")
        cmd = [
            ff, "-y", "-i", str(input_path), "-an", "-vf", f"fps={fps},format=yuv420p",
            "-vcodec", "libx264", "-crf", str(crf), "-preset", preset, "-pix_fmt", "yuv420p", str(base),
        ]
        res = _run_cmd(cmd, timeout=180)
        if res.returncode != 0:
            raise RuntimeError((res.stderr or res.stdout or "ffmpeg normalize failed")[-800:])
        base_d = self.probe_duration_seconds(base) or 0.0
        if base_d <= 0.0:
            raise RuntimeError("base clip duration is 0")
        ov = max(0.05, float(overlap))
        ov = min(ov, max(0.05, base_d * 0.4))
        cur = base
        cur_d = base_d
        idx = 0
        while cur_d < target_duration:
            idx += 1
            next_out = tmp_dir / f"{input_path.stem}_xfade_{idx}.mp4"
            offset = max(0.0, cur_d - ov)
            filter_complex = f"[0:v][1:v]xfade=transition=fade:duration={ov}:offset={offset},fps={fps},format=yuv420p[v]"
            cmd = [ff, "-y", "-i", str(cur), "-i", str(base), "-filter_complex", filter_complex, "-map", "[v]", "-an", "-vcodec", "libx264", "-crf", str(crf), "-preset", preset, "-pix_fmt", "yuv420p", str(next_out)]
            res = _run_cmd(cmd, timeout=240)
            if res.returncode != 0:
                raise RuntimeError((res.stderr or res.stdout or "ffmpeg xfade failed")[-800:])
            cur = next_out
            cur_d = self.probe_duration_seconds(cur) or (cur_d + base_d - ov)
            if idx > 10:
                break
        out_path = Path(output_path).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [ff, "-y", "-i", str(cur), "-t", str(float(target_duration)), "-an", "-vcodec", "libx264", "-crf", str(crf), "-preset", preset, "-pix_fmt", "yuv420p", "-r", str(int(fps)), str(out_path)]
        res = _run_cmd(cmd, timeout=240)
        if res.returncode != 0:
            raise RuntimeError((res.stderr or res.stdout or "ffmpeg trim failed")[-800:])
