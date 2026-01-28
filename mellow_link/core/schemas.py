from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

# ... (다른 클래스들은 그대로 두고, ImageRequest만 수정) ...

class ImageRequest(BaseModel):
    """
    이미지 생성 요청 스키마
    """
    prompt: str = Field(..., description="생성할 이미지에 대한 텍스트 설명")
    negative_prompt: Optional[str] = Field(None, description="제외할 요소")
    width: int = Field(1024, description="이미지 너비")
    height: int = Field(1024, description="이미지 높이")
    steps: int = Field(20, description="디노이징 스텝 수")
    cfg_scale: float = Field(7.0, description="CFG 스케일")
    seed: int = Field(-1, description="시드 값 (-1은 랜덤)")
    batch_size: int = Field(1, description="한 번에 생성할 매수")
    model: Optional[str] = Field(None, description="사용할 모델 파일명")
    
    # [▼ 여기가 핵심! 이 줄이 없어서 에러가 났던 거야]
    workflow: Optional[str] = Field(None, description="사용할 워크플로우 JSON 파일명 (예: flux_dev_api.json)")
    # [▼ 이 3줄을 추가해!]
    sampler_name: str = Field("euler", description="샘플러 (예: euler, dpmpp_2m)")
    scheduler: str = Field("normal", description="스케줄러 (예: normal, karras)")
    denoise: float = Field(1.0, description="디노이징 강도 (1.0 = 완전 새로 그리기)")