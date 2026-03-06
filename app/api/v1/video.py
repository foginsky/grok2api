"""
???? API ??
"""

import re
import time
import uuid
from typing import Any, Dict, Optional, Tuple

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.core.exceptions import UpstreamException, ValidationException
from app.services.grok.services.model import ModelService
from app.services.grok.services.video import VideoService


router = APIRouter(tags=["Videos"])

VIDEO_MODEL_ID = "grok-imagine-1.0-video"
SIZE_TO_ASPECT = {
    "1280x720": "16:9",
    "720x1280": "9:16",
    "1792x1024": "3:2",
    "1024x1792": "2:3",
    "1024x1024": "1:1",
}
QUALITY_TO_RESOLUTION = {
    "standard": "480p",
    "high": "720p",
}


class VideoCreateRequest(BaseModel):
    """OpenAI ??????????"""

    model_config = ConfigDict(extra="ignore")

    prompt: str = Field(..., description="?????")
    model: Optional[str] = Field(VIDEO_MODEL_ID, description="????")
    size: Optional[str] = Field("1792x1024", description="????")
    seconds: Optional[int] = Field(6, description="???????")
    quality: Optional[str] = Field("standard", description="?????standard/high")


def _normalize_model(model: Optional[str]) -> str:
    requested = (model or VIDEO_MODEL_ID).strip()
    if requested != VIDEO_MODEL_ID:
        raise ValidationException(
            message=f"The model `{VIDEO_MODEL_ID}` is required for video generation.",
            param="model",
            code="model_not_supported",
        )
    model_info = ModelService.get(requested)
    if not model_info or not model_info.is_video:
        raise ValidationException(
            message=f"The model `{requested}` is not supported for video generation.",
            param="model",
            code="model_not_supported",
        )
    return requested


def _normalize_size(size: Optional[str]) -> Tuple[str, str]:
    value = (size or "1792x1024").strip()
    aspect_ratio = SIZE_TO_ASPECT.get(value)
    if not aspect_ratio:
        raise ValidationException(
            message=f"size must be one of {sorted(SIZE_TO_ASPECT.keys())}",
            param="size",
            code="invalid_size",
        )
    return value, aspect_ratio


def _normalize_quality(quality: Optional[str]) -> Tuple[str, str]:
    value = (quality or "standard").strip().lower()
    resolution = QUALITY_TO_RESOLUTION.get(value)
    if not resolution:
        raise ValidationException(
            message=f"quality must be one of {sorted(QUALITY_TO_RESOLUTION.keys())}",
            param="quality",
            code="invalid_quality",
        )
    return value, resolution


def _normalize_seconds(seconds: Optional[int]) -> int:
    value = int(seconds or 6)
    if value < 6 or value > 30:
        raise ValidationException(
            message="seconds must be between 6 and 30",
            param="seconds",
            code="invalid_seconds",
        )
    return value


def _extract_video_url(content: str) -> str:
    if not isinstance(content, str) or not content.strip():
        return ""

    markdown_match = re.search(r"\[video\]\(([^)\s]+)\)", content)
    if markdown_match:
        return markdown_match.group(1).strip()

    html_match = re.search(r"""<source[^>]+src=["']([^"']+)["']""", content)
    if html_match:
        return html_match.group(1).strip()

    url_match = re.search(r"""https?://[^\s"'<>]+""", content)
    if url_match:
        return url_match.group(0).strip().rstrip(".,)")

    return ""


def _build_create_response(
    *,
    model: str,
    prompt: str,
    size: str,
    seconds: int,
    quality: str,
    url: str,
) -> Dict[str, Any]:
    ts = int(time.time())
    return {
        "id": f"video_{uuid.uuid4().hex[:24]}",
        "object": "video",
        "created_at": ts,
        "completed_at": ts,
        "status": "completed",
        "model": model,
        "prompt": prompt,
        "size": size,
        "seconds": str(seconds),
        "quality": quality,
        "url": url,
    }


@router.post("/videos")
async def create_video(request: VideoCreateRequest):
    """????????????"""
    prompt = (request.prompt or "").strip()
    if not prompt:
        raise ValidationException(
            message="prompt is required",
            param="prompt",
            code="invalid_request_error",
        )

    model = _normalize_model(request.model)
    size, aspect_ratio = _normalize_size(request.size)
    quality, resolution = _normalize_quality(request.quality)
    seconds = _normalize_seconds(request.seconds)

    result = await VideoService.completions(
        model=model,
        messages=[{"role": "user", "content": [{"type": "text", "text": prompt}]}],
        stream=False,
        reasoning_effort=None,
        aspect_ratio=aspect_ratio,
        video_length=seconds,
        resolution=resolution,
        preset="custom",
    )

    choices = result.get("choices") if isinstance(result, dict) else None
    if not isinstance(choices, list) or not choices:
        raise UpstreamException("Video generation failed: empty result")

    message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
    rendered = message.get("content", "") if isinstance(message, dict) else ""
    video_url = _extract_video_url(rendered)
    if not video_url:
        raise UpstreamException("Video generation failed: missing video URL")

    return JSONResponse(
        content=_build_create_response(
            model=model,
            prompt=prompt,
            size=size,
            seconds=seconds,
            quality=quality,
            url=video_url,
        )
    )


__all__ = ["router"]
