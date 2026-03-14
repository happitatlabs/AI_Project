"""
미디어 어댑터: 그림/동영상 연산·AI·업로드를 정책에 따라 분리.

- MediaComputeAdapter: 로컬 전용 (transcode_video, generate_thumbnail, merge_audio, extract_frames)
- MediaAIAdapter: 외부/모델 호출 (generate_image, generate_video, upscale, tts)
- MediaUploadAdapter: 외부 네트워크 (upload_youtube, upload_s3, upload_drive)
"""
from mellow_link.adapters.media.base import (
    MediaComputeAdapter,
    MediaAIAdapter,
    MediaUploadAdapter,
)
from mellow_link.adapters.media.factory import (
    get_media_compute,
    get_media_ai,
    get_media_uploader,
)

__all__ = [
    "MediaComputeAdapter",
    "MediaAIAdapter",
    "MediaUploadAdapter",
    "get_media_compute",
    "get_media_ai",
    "get_media_uploader",
]
