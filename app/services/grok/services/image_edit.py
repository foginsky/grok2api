"""
Grok image edit service.
"""

import asyncio
import re
import time
from dataclasses import dataclass
from typing import AsyncGenerator, AsyncIterable, Dict, List, Union, Any, Callable

import orjson
from curl_cffi.requests.errors import RequestsError

from app.core.config import get_config
from app.core.exceptions import (
    AppException,
    ErrorType,
    UpstreamException,
    StreamIdleTimeoutError,
)
from app.core.logger import logger
from app.services.grok.utils.process import (
    BaseProcessor,
    _with_idle_timeout,
    _normalize_line,
    _collect_images,
    _is_http2_error,
)
from app.services.grok.utils.upload import UploadService
from app.services.grok.utils.retry import pick_token, rate_limited
from app.services.grok.services.chat import GrokChatService
from app.services.grok.services.video import VideoService
from app.services.grok.utils.stream import wrap_stream_with_usage
from app.services.token import EffortType

_EDIT_UPSTREAM_MODEL = "grok-4"
_EDIT_UPSTREAM_MODE = "MODEL_MODE_AUTO"


@dataclass
class ImageEditResult:
    stream: bool
    data: Union[AsyncGenerator[str, None], List[str]]


def _is_upload_rejected_error(exc: Exception) -> bool:
    """判断是否为上游审核导致的上传拒绝。"""
    msg = str(exc or "").lower()
    if "content moderated" in msg or "content-moderated" in msg:
        return True
    if '"code":3' in msg or "'code': 3" in msg:
        return True

    details = getattr(exc, "details", None)
    if isinstance(details, dict):
        status = details.get("status")
        body = str(details.get("body") or "").lower()
        err = str(details.get("error") or "").lower()
        if "content moderated" in body or "content-moderated" in body:
            return True
        if '"code":3' in body or "'code': 3" in body:
            return True
        # 某些链路只返回 400 + '"code"' 关键词，按拒绝处理。
        if status == 400 and ('"code"' in err or "moderated" in err):
            return True

    return False


def _is_upload_network_error(exc: Exception) -> bool:
    """判断是否为网络连通/网关挑战类上传失败。"""
    msg = str(exc or "").lower()
    if (
        "tls connect error" in msg
        or "timed out" in msg
        or "timeout" in msg
        or "connection" in msg
        or "proxy" in msg
        or "curl: (35)" in msg
    ):
        return True

    details = getattr(exc, "details", None)
    if isinstance(details, dict):
        status = details.get("status")
        body = str(details.get("body") or "").lower()
        if status == 403 and ("just a moment" in body or "cloudflare" in body):
            return True
        if "tls connect error" in body or "timed out" in body:
            return True

    return False


def _normalize_fallback_image_url(url: str) -> str:
    """下载失败时的兜底 URL 规范化。"""
    raw = str(url or "").strip()
    if not raw:
        return ""
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    if raw.startswith("/"):
        return f"https://assets.grok.com{raw}"
    return f"https://assets.grok.com/{raw}"


def _append_unique_urls(target: List[str], values: List[str]) -> None:
    for value in values:
        text = str(value or "").strip()
        if text and text not in target:
            target.append(text)


def _extract_urls_from_card_json(card_data: Any) -> List[str]:
    urls: List[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                key_lower = str(key or "").lower()
                if (
                    key_lower in {"imageurl", "original", "url", "sourceurl"}
                    and isinstance(value, str)
                    and value.strip().startswith(("http://", "https://"))
                ):
                    _append_unique_urls(urls, [value.strip()])
                    continue
                walk(value)
            return
        if isinstance(node, list):
            for item in node:
                walk(item)

    walk(card_data)
    return urls


def _extract_card_attachment_urls(resp: Dict[str, Any]) -> List[str]:
    urls: List[str] = []

    card = resp.get("cardAttachment")
    if isinstance(card, dict):
        raw_json = card.get("jsonData")
        if isinstance(raw_json, str) and raw_json.strip():
            try:
                card_data = orjson.loads(raw_json)
            except orjson.JSONDecodeError:
                card_data = None
            if card_data is not None:
                _append_unique_urls(urls, _extract_urls_from_card_json(card_data))

    model_response = resp.get("modelResponse")
    if isinstance(model_response, dict):
        for raw in model_response.get("cardAttachmentsJson") or []:
            if not isinstance(raw, str) or not raw.strip():
                continue
            try:
                card_data = orjson.loads(raw)
            except orjson.JSONDecodeError:
                continue
            _append_unique_urls(urls, _extract_urls_from_card_json(card_data))

    return urls


class ImageEditService:
    """Image edit orchestration service."""

    @staticmethod
    def _build_request_overrides(n: int) -> Dict[str, Any]:
        return {"imageGenerationCount": max(1, int(n or 1))}

    async def _emit_progress(
        self,
        progress_cb: Callable[[str, dict], Any] | None,
        event: str,
        progress: int,
        message: str,
        **extra: Any,
    ) -> None:
        if not progress_cb:
            return
        payload = {"progress": int(progress), "message": message}
        if extra:
            payload.update(extra)
        try:
            result = progress_cb(event, payload)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            logger.debug(f"Image edit progress callback ignored: {e}")

    async def edit(
        self,
        *,
        token_mgr: Any,
        token: str,
        model_info: Any,
        prompt: str,
        images: List[str],
        n: int,
        response_format: str,
        stream: bool,
        return_all_images: bool = False,
        progress_cb: Callable[[str, dict], Any] | None = None,
    ) -> ImageEditResult:
        max_token_retries = int(get_config("retry.max_retry"))
        tried_tokens: set[str] = set()
        last_error: Exception | None = None

        for attempt in range(max_token_retries):
            preferred = token if attempt == 0 else None
            current_token = await pick_token(
                token_mgr, model_info.model_id, tried_tokens, preferred=preferred
            )
            if not current_token:
                if last_error:
                    raise last_error
                raise AppException(
                    message="No available tokens. Please try again later.",
                    error_type=ErrorType.RATE_LIMIT.value,
                    code="rate_limit_exceeded",
                    status_code=429,
                )

            tried_tokens.add(current_token)
            await self._emit_progress(
                progress_cb,
                "token_selected",
                8,
                "已匹配编辑令牌",
            )
            try:
                await self._emit_progress(
                    progress_cb,
                    "upload_start",
                    16,
                    "正在上传输入图片",
                )
                file_attachments = await self._upload_images(images, current_token)
                await self._emit_progress(
                    progress_cb,
                    "upload_done",
                    30,
                    f"图片上传完成，共 {len(file_attachments)} 张",
                    count=len(file_attachments),
                )
                tool_overrides: Dict[str, Any] | None = None
                request_overrides = self._build_request_overrides(n)

                if stream:
                    response = await GrokChatService().chat(
                        token=current_token,
                        message=prompt,
                        model=_EDIT_UPSTREAM_MODEL,
                        mode=_EDIT_UPSTREAM_MODE,
                        stream=True,
                        file_attachments=file_attachments,
                        tool_overrides=tool_overrides,
                        request_overrides=request_overrides,
                    )
                    processor = ImageStreamProcessor(
                        model_info.model_id,
                        current_token,
                        n=n,
                        response_format=response_format,
                    )
                    return ImageEditResult(
                        stream=True,
                        data=wrap_stream_with_usage(
                            processor.process(response),
                            token_mgr,
                            current_token,
                            model_info.model_id,
                        ),
                    )

                await self._emit_progress(
                    progress_cb,
                    "chat_request_start",
                    48,
                    "已提交编辑请求",
                )
                images_out = await self._collect_images(
                    token=current_token,
                    prompt=prompt,
                    response_format=response_format,
                    file_attachments=file_attachments,
                    tool_overrides=tool_overrides,
                    request_overrides=request_overrides,
                    return_all_images=return_all_images,
                    progress_cb=progress_cb,
                )
                await self._emit_progress(
                    progress_cb,
                    "collect_done",
                    92,
                    f"已收到 {len(images_out)} 张结果",
                )
                try:
                    effort = (
                        EffortType.HIGH
                        if (model_info and model_info.cost.value == "high")
                        else EffortType.LOW
                    )
                    await token_mgr.consume(current_token, effort)
                    logger.debug(
                        f"Image edit completed, recorded usage (effort={effort.value})"
                    )
                except Exception as e:
                    logger.warning(f"Failed to record image edit usage: {e}")
                return ImageEditResult(stream=False, data=images_out)

            except UpstreamException as e:
                last_error = e
                if rate_limited(e):
                    await token_mgr.mark_rate_limited(current_token)
                    await self._emit_progress(
                        progress_cb,
                        "rate_limited",
                        16,
                        "令牌限流，正在切换重试",
                    )
                    logger.warning(
                        f"Token {current_token[:10]}... rate limited (429), "
                        f"trying next token (attempt {attempt + 1}/{max_token_retries})"
                    )
                    continue
                raise

        if last_error:
            raise last_error
        raise AppException(
            message="No available tokens. Please try again later.",
            error_type=ErrorType.RATE_LIMIT.value,
            code="rate_limit_exceeded",
            status_code=429,
        )

    async def edit_with_parent_post(
        self,
        *,
        token_mgr: Any,
        token: str,
        model_info: Any,
        prompt: str,
        parent_post_id: str,
        source_image_url: str,
        response_format: str,
        stream: bool,
        return_all_images: bool = False,
        progress_cb: Callable[[str, dict], Any] | None = None,
    ) -> ImageEditResult:
        """基于 parentPostId 进行编辑，不上传图片。"""
        max_token_retries = int(get_config("retry.max_retry"))
        tried_tokens: set[str] = set()
        last_error: Exception | None = None

        for attempt in range(max_token_retries):
            preferred = token if attempt == 0 else None
            current_token = await pick_token(
                token_mgr, model_info.model_id, tried_tokens, preferred=preferred
            )
            if not current_token:
                if last_error:
                    raise last_error
                raise AppException(
                    message="No available tokens. Please try again later.",
                    error_type=ErrorType.RATE_LIMIT.value,
                    code="rate_limit_exceeded",
                    status_code=429,
                )

            tried_tokens.add(current_token)
            await self._emit_progress(
                progress_cb,
                "token_selected",
                8,
                "已匹配编辑令牌",
            )
            try:
                image_ref = (source_image_url or "").strip()
                if not image_ref:
                    image_ref = f"https://imagine-public.x.ai/imagine-public/images/{parent_post_id}.jpg"
                effective_parent_post_id = parent_post_id
                await self._emit_progress(
                    progress_cb,
                    "pre_create_start",
                    18,
                    "正在创建媒体帖子",
                    parent_post_id=parent_post_id,
                )
                try:
                    # 与 nsfw 的 parentPostId 链路保持一致：先预创建 media post
                    # 这样上游在 imagine-image-edit 校验 parentPostId 时更稳定。
                    image_post_id = await VideoService().create_image_post(
                        current_token, image_ref
                    )
                    if image_post_id:
                        effective_parent_post_id = image_post_id
                    logger.info(
                        "Image edit(parentPostId) pre-create media post done: "
                        f"parent_post_id={parent_post_id}, "
                        f"image_post_id={effective_parent_post_id}, media_url={image_ref}"
                    )
                    await self._emit_progress(
                        progress_cb,
                        "pre_create_done",
                        34,
                        "媒体帖子创建完成",
                        image_post_id=effective_parent_post_id,
                    )
                except Exception as e:
                    logger.warning(
                        "Image edit(parentPostId) pre-create media post failed, continue anyway: "
                        f"parent_post_id={parent_post_id}, media_url={image_ref}, error={e}"
                    )
                    await self._emit_progress(
                        progress_cb,
                        "pre_create_failed",
                        28,
                        "媒体帖子创建失败，继续请求",
                    )

                model_config_override = {
                    "modelMap": {
                        "imageEditModel": "imagine",
                        "imageEditModelConfig": {
                            "imageReferences": [image_ref],
                            "parentPostId": effective_parent_post_id,
                        },
                    }
                }
                tool_overrides = {"imageGen": True}

                if stream:
                    response = await GrokChatService().chat(
                        token=current_token,
                        message=prompt,
                        model=model_info.grok_model,
                        mode=None,
                        stream=True,
                        tool_overrides=tool_overrides,
                        model_config_override=model_config_override,
                        image_generation_count=1,
                    )
                    processor = ImageStreamProcessor(
                        model_info.model_id,
                        current_token,
                        n=1,
                        response_format=response_format,
                    )
                    return ImageEditResult(
                        stream=True,
                        data=wrap_stream_with_usage(
                            processor.process(response),
                            token_mgr,
                            current_token,
                            model_info.model_id,
                        ),
                    )

                await self._emit_progress(
                    progress_cb,
                    "chat_request_start",
                    48,
                    "已提交编辑请求",
                    parent_post_id=effective_parent_post_id,
                )
                images_out = await self._collect_images(
                    token=current_token,
                    prompt=prompt,
                    response_format=response_format,
                    file_attachments=[],
                    tool_overrides=tool_overrides,
                    request_overrides={"imageGenerationCount": 1},
                    return_all_images=return_all_images,
                    progress_cb=progress_cb,
                )
                await self._emit_progress(
                    progress_cb,
                    "collect_done",
                    92,
                    f"已收到 {len(images_out)} 张结果",
                )
                try:
                    effort = (
                        EffortType.HIGH
                        if (model_info and model_info.cost.value == "high")
                        else EffortType.LOW
                    )
                    await token_mgr.consume(current_token, effort)
                    logger.debug(
                        "Image edit(parentPostId) completed, "
                        f"recorded usage (effort={effort.value})"
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to record image edit(parentPostId) usage: {e}"
                    )
                return ImageEditResult(stream=False, data=images_out)

            except UpstreamException as e:
                last_error = e
                if rate_limited(e):
                    await token_mgr.mark_rate_limited(current_token)
                    await self._emit_progress(
                        progress_cb,
                        "rate_limited",
                        16,
                        "令牌限流，正在切换重试",
                    )
                    logger.warning(
                        f"Token {current_token[:10]}... rate limited (429), "
                        f"trying next token (attempt {attempt + 1}/{max_token_retries})"
                    )
                    continue
                raise

        if last_error:
            raise last_error
        raise AppException(
            message="No available tokens. Please try again later.",
            error_type=ErrorType.RATE_LIMIT.value,
            code="rate_limit_exceeded",
            status_code=429,
        )

    async def _upload_images(self, images: List[str], token: str) -> List[str]:
        file_attachments: List[str] = []
        upload_service = UploadService()
        try:
            for image in images:
                file_id, _ = await upload_service.upload_file(image, token)
                if file_id:
                    file_attachments.append(file_id)
        except Exception as e:
            if _is_upload_rejected_error(e):
                raise AppException(
                    message="图片上传被拒绝，请更换图片后重试",
                    error_type=ErrorType.INVALID_REQUEST.value,
                    code="upload_rejected",
                    status_code=400,
                )
            if _is_upload_network_error(e):
                raise AppException(
                    message="图片上传失败：网络连接异常，请稍后重试",
                    error_type=ErrorType.SERVER.value,
                    code="upload_network_error",
                    status_code=502,
                )
            raise AppException(
                message="图片上传失败，请稍后重试",
                error_type=ErrorType.SERVER.value,
                code="upload_failed",
                status_code=502,
            )
        finally:
            await upload_service.close()

        if not file_attachments:
            raise AppException(
                message="Image upload failed",
                error_type=ErrorType.SERVER.value,
                code="upload_failed",
            )

        return file_attachments

    async def _collect_images(
        self,
        *,
        token: str,
        prompt: str,
        response_format: str,
        file_attachments: List[str],
        tool_overrides: dict,
        request_overrides: dict,
        return_all_images: bool = False,
        progress_cb: Callable[[str, dict], Any] | None = None,
    ) -> List[str]:
        async def _call_edit():
            response = await GrokChatService().chat(
                token=token,
                message=prompt,
                model=_EDIT_UPSTREAM_MODEL,
                mode=_EDIT_UPSTREAM_MODE,
                stream=True,
                file_attachments=file_attachments,
                tool_overrides=tool_overrides,
                request_overrides=request_overrides,
            )
            processor = ImageCollectProcessor(
                "grok-imagine-1.0-edit",
                token,
                response_format=response_format,
                progress_cb=progress_cb,
            )
            return await processor.process(response)

        all_images = await _call_edit()

        if not all_images:
            raise UpstreamException(
                "Image edit returned no results", details={"error": "empty_result"}
            )
        if return_all_images:
            return all_images
        return [all_images[0]]


class ImageStreamProcessor(BaseProcessor):
    """HTTP image stream processor."""

    def __init__(
        self,
        model: str,
        token: str = "",
        n: int = 1,
        response_format: str = "b64_json",
        chat_format: bool = True,
    ):
        super().__init__(model, token)
        self.partial_index = 0
        self.n = n
        self.target_index = 0 if n == 1 else None
        self._image_ids: Dict[int, str] = {}
        self.chat_format = chat_format
        self.response_format = response_format
        if response_format == "url":
            self.response_field = "url"
        elif response_format == "base64":
            self.response_field = "base64"
        else:
            self.response_field = "b64_json"

    def _get_image_id(self, image_index: int) -> str:
        if image_index not in self._image_ids:
            self._image_ids[image_index] = (
                f"app-chat-{int(time.time() * 1000)}-{image_index}"
            )
        return self._image_ids[image_index]

    def _sse(self, event: str, data: dict) -> str:
        """Build SSE response."""
        return f"event: {event}\ndata: {orjson.dumps(data).decode()}\n\n"

    async def process(
        self, response: AsyncIterable[bytes]
    ) -> AsyncGenerator[str, None]:
        """Process stream response."""
        final_images = []
        idle_timeout = get_config("image.stream_timeout")

        try:
            async for line in _with_idle_timeout(response, idle_timeout, self.model):
                line = _normalize_line(line)
                if not line:
                    continue
                try:
                    data = orjson.loads(line)
                except orjson.JSONDecodeError:
                    continue

                resp = data.get("result", {}).get("response", {})

                # Image generation progress
                if img := resp.get("streamingImageGenerationResponse"):
                    image_index = img.get("imageIndex", 0)
                    progress = img.get("progress", 0)

                    if self.n == 1 and image_index != self.target_index:
                        continue

                    out_index = 0 if self.n == 1 else image_index

                    image_id = self._get_image_id(image_index)
                    yield self._sse(
                        "image_generation.partial_image",
                        {
                            "type": "image_generation.partial_image",
                            self.response_field: "",
                            "index": out_index,
                            "progress": progress,
                            "image_id": image_id,
                        },
                    )
                    continue

                extracted_urls: List[str] = []
                if mr := resp.get("modelResponse"):
                    _append_unique_urls(extracted_urls, _collect_images(mr))
                _append_unique_urls(extracted_urls, _extract_card_attachment_urls(resp))

                if extracted_urls:
                    for url in extracted_urls:
                        if self.response_format == "url":
                            try:
                                processed = await self.process_url(url, "image")
                            except Exception as e:
                                logger.warning(
                                    "Image stream URL resolve failed, fallback to raw URL: "
                                    f"error={e}"
                                )
                                processed = _normalize_fallback_image_url(url)
                            if processed:
                                final_images.append(processed)
                            continue
                        try:
                            dl_service = self._get_dl()
                            base64_data = await dl_service.parse_b64(
                                url, self.token, "image"
                            )
                            if base64_data:
                                if "," in base64_data:
                                    b64 = base64_data.split(",", 1)[1]
                                else:
                                    b64 = base64_data
                                final_images.append(b64)
                        except Exception as e:
                            logger.warning(
                                f"Failed to convert image to base64, falling back to URL: {e}"
                            )
                            processed = await self.process_url(url, "image")
                            if processed:
                                final_images.append(processed)
                    continue

            for index, b64 in enumerate(final_images):
                if self.n == 1:
                    if index != self.target_index:
                        continue
                    out_index = 0
                else:
                    out_index = index

                yield self._sse(
                    "image_generation.completed",
                    {
                        "type": "image_generation.completed",
                        self.response_field: b64,
                        "index": out_index,
                        "image_id": self._get_image_id(out_index),
                        "stage": "final",
                        "usage": {
                            "total_tokens": 0,
                            "input_tokens": 0,
                            "output_tokens": 0,
                            "input_tokens_details": {
                                "text_tokens": 0,
                                "image_tokens": 0,
                            },
                        },
                    },
                )
        except asyncio.CancelledError:
            logger.debug("Image stream cancelled by client")
        except StreamIdleTimeoutError as e:
            raise UpstreamException(
                message=f"Image stream idle timeout after {e.idle_seconds}s",
                status_code=504,
                details={
                    "error": str(e),
                    "type": "stream_idle_timeout",
                    "idle_seconds": e.idle_seconds,
                },
            )
        except RequestsError as e:
            if _is_http2_error(e):
                logger.warning(f"HTTP/2 stream error in image: {e}")
                raise UpstreamException(
                    message="Upstream connection closed unexpectedly",
                    status_code=502,
                    details={"error": str(e), "type": "http2_stream_error"},
                )
            logger.error(f"Image stream request error: {e}")
            raise UpstreamException(
                message=f"Upstream request failed: {e}",
                status_code=502,
                details={"error": str(e)},
            )
        except Exception as e:
            logger.error(
                f"Image stream processing error: {e}",
                extra={"error_type": type(e).__name__},
            )
            raise
        finally:
            await self.close()


class ImageCollectProcessor(BaseProcessor):
    """HTTP image non-stream processor."""

    def __init__(
        self,
        model: str,
        token: str = "",
        response_format: str = "b64_json",
        progress_cb: Callable[[str, dict], Any] | None = None,
    ):
        if response_format == "base64":
            response_format = "b64_json"
        super().__init__(model, token)
        self.response_format = response_format
        self.progress_cb = progress_cb

    async def _emit_progress(
        self, event: str, progress: int, message: str, **extra: Any
    ) -> None:
        if not self.progress_cb:
            return
        payload = {"progress": int(progress), "message": message}
        if extra:
            payload.update(extra)
        try:
            result = self.progress_cb(event, payload)
            if asyncio.iscoroutine(result):
                await result
        except Exception:
            pass

    async def process(self, response: AsyncIterable[bytes]) -> List[str]:
        """Process and collect images."""
        images = []
        idle_timeout = get_config("image.stream_timeout")
        chat_connected_emitted = False

        try:
            async for line in _with_idle_timeout(response, idle_timeout, self.model):
                line = _normalize_line(line)
                if not line:
                    continue
                try:
                    data = orjson.loads(line)
                except orjson.JSONDecodeError:
                    continue

                resp = data.get("result", {}).get("response", {})
                if not chat_connected_emitted and resp:
                    chat_connected_emitted = True
                    await self._emit_progress(
                        "chat_connected",
                        60,
                        "模型连接成功，正在生成图片",
                    )

                extracted_urls: List[str] = []
                if mr := resp.get("modelResponse"):
                    _append_unique_urls(extracted_urls, _collect_images(mr))
                _append_unique_urls(extracted_urls, _extract_card_attachment_urls(resp))

                if extracted_urls:
                    for url in extracted_urls:
                        if self.response_format == "url":
                            try:
                                processed = await self.process_url(url, "image")
                            except Exception as e:
                                logger.warning(
                                    "Image collect URL resolve failed, fallback to raw URL: "
                                    f"error={e}"
                                )
                                processed = _normalize_fallback_image_url(url)
                            if processed:
                                images.append(processed)
                                progress = min(90, 64 + len(images) * 12)
                                await self._emit_progress(
                                    "image_downloaded",
                                    progress,
                                    f"已下载第 {len(images)} 张图片",
                                    count=len(images),
                                )
                            continue
                        try:
                            dl_service = self._get_dl()
                            base64_data = await dl_service.parse_b64(
                                url, self.token, "image"
                            )
                            if base64_data:
                                if "," in base64_data:
                                    b64 = base64_data.split(",", 1)[1]
                                else:
                                    b64 = base64_data
                                images.append(b64)
                                progress = min(90, 64 + len(images) * 12)
                                await self._emit_progress(
                                    "image_downloaded",
                                    progress,
                                    f"已下载第 {len(images)} 张图片",
                                    count=len(images),
                                )
                        except Exception as e:
                            logger.warning(
                                f"Failed to convert image to base64, falling back to URL: {e}"
                            )
                            processed = await self.process_url(url, "image")
                            if processed:
                                images.append(processed)
                                progress = min(90, 64 + len(images) * 12)
                                await self._emit_progress(
                                    "image_downloaded",
                                    progress,
                                    f"已下载第 {len(images)} 张图片",
                                    count=len(images),
                                )

        except asyncio.CancelledError:
            logger.debug("Image collect cancelled by client")
        except StreamIdleTimeoutError as e:
            logger.warning(f"Image collect idle timeout: {e}")
        except RequestsError as e:
            if _is_http2_error(e):
                logger.warning(f"HTTP/2 stream error in image collect: {e}")
            else:
                logger.error(f"Image collect request error: {e}")
        except Exception as e:
            logger.error(
                f"Image collect processing error: {e}",
                extra={"error_type": type(e).__name__},
            )
        finally:
            await self.close()

        return images


__all__ = ["ImageEditService", "ImageEditResult"]
