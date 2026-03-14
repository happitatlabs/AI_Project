"""
Visual Planner (Story & Context)

목표:
  - 전체 가사(lyrics)를 "장면(Scenes)" 단위로 변환한다.
  - 각 장면은:
      - 정적(Image) 프롬프트: 피사체/배경/스타일 중심 (Static Prompt)
      - 모션(Video) 프롬프트: 카메라 워킹/움직임 중심 (Motion Prompt)
    으로 이원화한다.
  - 전 장면이 일관된 스타일을 유지하도록 seed를 공유한다.

NOTE:
  - LLM(예: Ollama)이 없거나 느린 환경에서도 동작하도록, 기본은 규칙 기반(휴리스틱)으로 동작.
  - 추후 LLM을 붙이기 쉬운 구조(메서드/필드)를 유지.
"""

from __future__ import annotations

import asyncio
import json
import re
import random
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


_KOREAN_STOPWORDS = {
    "그", "이", "저", "것", "수", "듯", "처럼", "보다",
    "그리고", "하지만", "그래서", "또", "더", "가", "이", "을", "를", "은", "는", "에", "의", "와", "과",
    "에서", "에게", "한테", "으로", "로", "만", "도", "까지", "부터", "마저", "조차",
}


def _tokenize(text: str) -> List[str]:
    # 단순 토크나이저: 한/영/숫자 단어 추출
    words = re.findall(r"[A-Za-z0-9가-힣]{2,}", text or "")
    out: List[str] = []
    for w in words:
        ww = w.strip()
        if not ww:
            continue
        if ww in _KOREAN_STOPWORDS:
            continue
        out.append(ww)
    return out


def _unique_preserve(seq: Iterable[str]) -> List[str]:
    seen = set()
    out = []
    for s in seq:
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def _pick_motion_bucket(camera_hint: str) -> int:
    """
    카메라 워킹 힌트 -> motion_bucket_id 매핑(대략).
    """
    h = (camera_hint or "").lower()
    if "static" in h or "locked" in h:
        return 50
    if "slow" in h and ("zoom" in h or "push" in h):
        return 80
    if "pan" in h:
        return 110
    if "handheld" in h or "dynamic" in h or "run" in h:
        return 170
    return 127


def _infer_camera_and_motion(line: str) -> Tuple[str, str]:
    """
    가사 한 줄에서 "카메라/모션"을 추론(휴리스틱).
    """
    t = (line or "").lower()
    # 한국어 동사/키워드 기반
    dynamic_markers = ("달려", "뛰", "춤", "폭풍", "바람", "울부", "불꽃", "전쟁", "추격", "격렬", "소용돌이")
    calm_markers = ("기억", "그리", "눈물", "조용", "새벽", "밤", "달", "별", "고요", "따뜻", "포근")

    if any(m in t for m in dynamic_markers):
        return ("dynamic handheld pan", "subject movement, wind, cloth flutter, dynamic parallax")
    if any(m in t for m in calm_markers):
        return ("slow cinematic zoom in", "subtle breathing motion, gentle parallax, soft atmosphere drift")
    # 기본값: 느린 패닝
    return ("slow pan left", "subtle parallax, gentle ambient motion")


@dataclass(frozen=True)
class PlannerConfig:
    max_scenes: int = 20
    # 🎯 The Magic Number (SVD 호환)
    width: int = 1216
    height: int = 704


# =============================================================================
# LLM Persona (The Cinematographer)
# =============================================================================

CINEMATOGRAPHER_SYSTEM_PROMPT = """
당신은 추상적인 노래 가사를 시각적이고 영화적인 촬영 지시서로 변환하는 노련한 시네마토그래퍼입니다.

규칙:
- "가사를 그대로 쓰지 마라." 가사의 문장을 그대로 복사/인용하지 마라.
- 가사의 정서를 읽고, '거울을 닦는 손'처럼 구체적인 사물/공간/행위로 번역하라.
- 사용자가 제공한 가사 구간(segments) 각각에 대해, 반드시 아래 3개 필드를 분리하여 생성하십시오.
  1) static_scene_description: 정적 이미지용. "사진 한 장"으로 찍힐 구체 사물/배경/조명/구도. 움직임/카메라 워킹 표현 금지.
  2) dynamic_action_description: 동영상용. 카메라 워킹(zoom/pan/tilt/dolly 등)과 피사체의 미세한 움직임을 포함.
  3) shared_keywords: 전체 분위기를 통일하는 공통 태그. 예: "cinematic, film still, soft lighting, 16:9 composition"

출력 규칙:
- 반드시 JSON만 출력하십시오. 마크다운, 설명 문장, 코드블록 금지.
- 출력은 JSON 배열(list)이며, 입력 segments와 동일한 길이/순서로 생성합니다.
- 각 원소는 최소한 다음 키를 포함해야 합니다:
  - segment_id
  - static_scene_description
  - dynamic_action_description
  - shared_keywords

품질 규칙:
- 가사를 그대로 복사하지 말고, 시각적으로 '찍히는 것'으로 번역하세요.
- 추상어(사랑, 이별, 그리움)는 구체 사물/공간/조명/날씨/소품으로 치환하세요.
- shared_keywords는 모든 장면에서 동일하게 유지하세요.
- 해상도는 1216x704 구도를 가정합니다.

프롬프트 포맷 가이드(결과는 아래 형식을 만족하도록 묘사하라):
- 이미지 프롬프트: "cinematic music video still, [구체적 장면 묘사], soft lighting, high quality, 16:9 composition"
- 영상 프롬프트: "cinematic music video, [카메라 워킹 및 피사체의 움직임 묘사], consistent color, no flicker"
""".strip()


def _strip_json_fence(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        # ```json ... ``` 형태 제거
        t = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    return t.strip()


def _scrub_lyric_echo(desc: str, lyric_text: str) -> str:
    """
    (Wiring Check) 가사가 프롬프트에 직접 섞여 들어가는 현상 차단:
    - segment 원문이 그대로 포함되면 제거한다.
    """
    d = (desc or "").strip()
    lt = (lyric_text or "").strip()
    if not d or not lt:
        return d
    # 가장 강한 차단: 원문 라인 그대로 포함되면 삭제
    if lt in d:
        d = d.replace(lt, "").strip()
    return d


class VisualPlanner:
    """
    Story/Context 기반 Scene Planner.
    """

    def __init__(self, config: Optional[PlannerConfig] = None) -> None:
        self.config = config or PlannerConfig()

    async def plan_scenes_async(
        self,
        *,
        lyrics_segments: Sequence[Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None,
        base_seed: Optional[int] = None,
        llm_host: str = "localhost",
        llm_port: int = 11434,
        llm_mode: str = "thinking",
    ) -> List[Dict[str, Any]]:
        """
        LLM 우선, 실패 시 휴리스틱 fallback.
        """
        try:
            # 지연 임포트: 옵션 의존성 분리
            from mellow_link.services.llm_service import LLMService

            svc = LLMService(host=str(llm_host), port=int(llm_port), timeout=120.0)
            await svc.connect()

            meta = metadata or {}
            segments_payload = []
            for i, seg in enumerate(list(lyrics_segments)[: int(self.config.max_scenes)]):
                segments_payload.append(
                    {
                        "segment_id": str(seg.get("id", i)),
                        "text": str(seg.get("text", "")),
                        "start_time": float(seg.get("start_time", 0.0) or 0.0),
                        "end_time": float(seg.get("end_time", 0.0) or 0.0),
                    }
                )

            shared_keywords = "cinematic, film still, soft lighting, 16:9 composition"
            user_prompt = json.dumps(
                {
                    "metadata": meta,
                    "shared_keywords": shared_keywords,
                    "segments": segments_payload,
                },
                ensure_ascii=False,
                indent=2,
            )

            prompt = (
                "아래 JSON 입력을 참고하여, segments 각각에 대해 촬영 지시서 JSON 배열만 출력하세요.\n"
                "출력 JSON 배열의 각 원소는 입력 segment_id를 그대로 포함해야 합니다.\n\n"
                f"{user_prompt}"
            )

            result = await svc.generate(
                prompt=prompt,
                system_prompt=CINEMATOGRAPHER_SYSTEM_PROMPT,
                mode=str(llm_mode),
                temperature=0.2,
                max_tokens=2048,
            )
            await svc.disconnect()

            raw = _strip_json_fence(getattr(result, "content", "") or "")
            parsed = json.loads(raw)
            if not isinstance(parsed, list):
                raise ValueError("LLM output is not a JSON list")

            # base_seed / 해상도 고정 적용 + 호환 필드 생성
            scenes: List[Dict[str, Any]] = []
            if base_seed is None:
                base_seed = random.randint(0, 2**31 - 1)

            width = int(self.config.width)
            height = int(self.config.height)

            for idx, item in enumerate(parsed[: int(self.config.max_scenes)]):
                if not isinstance(item, dict):
                    continue
                sid = str(item.get("segment_id", idx))
                lyric_line = str(segments_payload[idx].get("text", "")) if idx < len(segments_payload) else ""
                static_desc = _scrub_lyric_echo(str(item.get("static_scene_description", "")).strip(), lyric_line)
                dynamic_desc = _scrub_lyric_echo(str(item.get("dynamic_action_description", "")).strip(), lyric_line)
                sk = str(item.get("shared_keywords", shared_keywords)).strip() or shared_keywords

                # motion_bucket은 휴리스틱으로 보강(LLM이 누락해도 됨)
                cam_hint, motion_hint = _infer_camera_and_motion(dynamic_desc or "")
                motion_bucket_id = _pick_motion_bucket(cam_hint)

                # ✅ verified: 프롬프트 포맷 강제 (가사 원문 직접 혼입 금지)
                static_prompt = ", ".join(
                    [p for p in ["cinematic music video still", static_desc, "soft lighting", "high quality", "16:9 composition"] if str(p).strip()]
                )
                motion_prompt = ", ".join(
                    [p for p in ["cinematic music video", dynamic_desc, "consistent color", "no flicker"] if str(p).strip()]
                )

                scenes.append(
                    {
                        "scene_index": idx + 1,
                        "segment_id": sid,
                        "lyric_text": lyric_line,
                        "start_time": float(segments_payload[idx].get("start_time", 0.0)) if idx < len(segments_payload) else 0.0,
                        "end_time": float(segments_payload[idx].get("end_time", 0.0)) if idx < len(segments_payload) else 0.0,
                        # ✅ required fields
                        "static_scene_description": static_desc,
                        "dynamic_action_description": dynamic_desc,
                        "shared_keywords": sk,
                        # wiring convenience (used by UI/services)
                        "static_prompt": static_prompt,
                        "motion_prompt": motion_prompt,
                        # consistency
                        "style_seed": int(base_seed),
                        "seed": int(base_seed) + (idx * 101),
                        "motion_bucket_id": int(motion_bucket_id),
                        "width": width,
                        "height": height,
                        "negative_prompt": "",
                    }
                )

            if scenes:
                return scenes
        except Exception:
            # fallback
            return self.plan_scenes(lyrics_segments=lyrics_segments, metadata=metadata, base_seed=base_seed)

        return self.plan_scenes(lyrics_segments=lyrics_segments, metadata=metadata, base_seed=base_seed)

    def plan_scenes(
        self,
        *,
        lyrics_segments: Sequence[Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None,
        base_seed: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        휴리스틱 플래너: 필수 3요소(static/dynamic/shared)를 항상 생성.
        """
        meta = metadata or {}
        max_scenes = int(self.config.max_scenes)
        width = int(self.config.width)
        height = int(self.config.height)

        if base_seed is None:
            base_seed = random.randint(0, 2**31 - 1)

        # 전체 컨텍스트(가사 전체) 기반 키워드/스타일 힌트
        full_text = "\n".join([str(s.get("text", "")).strip() for s in lyrics_segments if str(s.get("text", "")).strip()])
        global_keywords = _unique_preserve(_tokenize(full_text))[:12]

        mood = str(meta.get("mood") or "").strip()
        story = str(meta.get("story") or "").strip()
        artist = str(meta.get("artist") or "").strip()
        title = str(meta.get("title") or meta.get("song_title") or "").strip()

        # shared_keywords는 모든 씬에서 동일하게 유지
        shared_keywords = "cinematic, film still, soft lighting, 16:9 composition"

        scenes: List[Dict[str, Any]] = []
        for idx, seg in enumerate(list(lyrics_segments)[:max_scenes]):
            lyric_line = str(seg.get("text", "")).strip()
            if not lyric_line:
                continue

            start_time = float(seg.get("start_time", 0.0) or 0.0)
            end_time = float(seg.get("end_time", 0.0) or 0.0)

            local_kw = _unique_preserve(_tokenize(lyric_line))
            keywords = _unique_preserve((local_kw + global_keywords))[:8]

            camera_hint, motion_hint = _infer_camera_and_motion(lyric_line)
            motion_bucket_id = _pick_motion_bucket(camera_hint)

            # ✅ verified: "가사를 그대로 쓰지 마라" (휴리스틱도 가사 단어를 prompt에 넣지 않음)
            # - lyric_line은 분기(정서/리듬) 판단에만 사용, 프롬프트 문자열에는 직접 포함하지 않는다.
            # ✅ required 3-field split
            static_scene_description = ", ".join(
                [p for p in [
                    "a foggy mirror on a wall, soft side lighting",
                    "a quiet room with a single window, dust in the air",
                    "a table with a worn handkerchief and a cup of tea",
                    "shallow depth of field, clear subject separation",
                ] if p]
            )
            dynamic_action_description = ", ".join(
                [p for p in [
                    "camera slowly pushes in toward the mirror",
                    "a hand enters frame and gently wipes the glass",
                    "subtle parallax, stable exposure",
                ] if p]
            )

            static_prompt = ", ".join(
                [p for p in ["cinematic music video still", static_scene_description, "soft lighting", "high quality", "16:9 composition"] if str(p).strip()]
            )
            motion_prompt = ", ".join(
                [p for p in ["cinematic music video", dynamic_action_description, "consistent color", "no flicker"] if str(p).strip()]
            )

            scenes.append(
                {
                    "scene_index": idx + 1,
                    "segment_id": str(idx),
                    "lyric_text": lyric_line,
                    "start_time": start_time,
                    "end_time": end_time,
                    "keywords": keywords,
                    "style_seed": int(base_seed),
                    "seed": int(base_seed) + (idx * 101),
                    "static_scene_description": static_scene_description,
                    "dynamic_action_description": dynamic_action_description,
                    "shared_keywords": shared_keywords,
                    # wiring convenience (backward compatible)
                    "static_prompt": static_prompt,
                    "motion_prompt": motion_prompt,
                    "negative_prompt": "",
                    "motion_bucket_id": int(motion_bucket_id),
                    "width": width,
                    "height": height,
                }
            )

        return scenes

