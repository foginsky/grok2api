from __future__ import annotations

import inspect
import importlib
from typing import Any, Dict

from app.core.exceptions import UpstreamException


orjson = importlib.import_module("orjson")
logger = importlib.import_module("app.core.logger").logger


def _normalize_line(line: Any) -> str | None:
    if line is None:
        return None
    if isinstance(line, (bytes, bytearray)):
        text = line.decode("utf-8", errors="ignore")
    else:
        text = str(line)
    text = text.strip()
    if not text:
        return None
    if text.startswith("data:"):
        text = text[5:].strip()
    if text == "[DONE]":
        return None
    return text


def _get_model_service():
    return importlib.import_module("app.services.grok.services.model").ModelService


def _get_session_cls():
    return importlib.import_module(
        "app.services.reverse.utils.session"
    ).ResettableSession


def _get_chat_service_cls():
    return importlib.import_module("app.services.grok.services.chat").GrokChatService


class CleanupProbeService:
    """Real model-request probe used by admin cleanup."""

    async def probe(
        self,
        token: str,
        probe_model: str,
        disable_retry: bool = True,
    ) -> Dict[str, Any]:
        ModelService = _get_model_service()
        GrokChatService = _get_chat_service_cls()

        resolved_model_id = str(probe_model or "").strip() or "grok-3-mini"
        model_name, model_mode = ModelService.to_grok(resolved_model_id)

        logger.info(
            "Cleanup probe prepared: "
            f"probe_model={probe_model or resolved_model_id}, "
            f"resolved_model={resolved_model_id}, upstream_model={model_name}, mode={model_mode}"
        )

        try:
            stream = await GrokChatService().chat(
                token=token,
                message="hi",
                model=model_name,
                requested_model=resolved_model_id,
                mode=model_mode,
                image_generation_count=1,
                disable_retry=disable_retry,
                record_auth_failures=False,
            )
        except Exception as exc:
            if isinstance(exc, UpstreamException):
                raise
            logger.error(
                "Cleanup probe request failure: 502",
                extra={"error_type": "UpstreamException"},
            )
            raise UpstreamException(
                message=f"CleanupProbeService: Probe failed, {exc}",
                details={"status": 502, "error": str(exc)},
                status_code=502,
            ) from exc

        stream_error_status = None
        stream_error_body = None
        saw_success_event = False
        try:
            async for raw_line in stream:
                line = _normalize_line(raw_line)
                if not line:
                    continue
                try:
                    data = orjson.loads(line)
                except orjson.JSONDecodeError:
                    continue

                result = data.get("result") if isinstance(data, dict) else None
                if not isinstance(result, dict):
                    continue

                error = result.get("error")
                if isinstance(error, dict):
                    try:
                        raw_status = error.get("status")
                        if raw_status is None:
                            raise TypeError("missing_status")
                        stream_error_status = int(raw_status)
                    except (TypeError, ValueError):
                        stream_error_status = 502
                    stream_error_body = error
                    break

                response_obj = result.get("response")
                if isinstance(response_obj, dict) and response_obj:
                    saw_success_event = True
                    break
        finally:
            try:
                close_fn = getattr(stream, "aclose", None)
                if callable(close_fn):
                    close_result = close_fn()
                    if inspect.isawaitable(close_result):
                        await close_result
                else:
                    close_fn = getattr(stream, "close", None)
                    if callable(close_fn):
                        close_result = close_fn()
                        if inspect.isawaitable(close_result):
                            await close_result
            except Exception:
                pass

        if stream_error_status is not None:
            logger.error(
                f"Cleanup probe stream failure: {stream_error_status}",
                extra={"error_type": "UpstreamException"},
            )
            raise UpstreamException(
                message=f"CleanupProbeService: Probe stream failed, {stream_error_status}",
                details={"status": stream_error_status, "body": stream_error_body},
                status_code=stream_error_status,
            )

        if not saw_success_event:
            logger.error(
                "Cleanup probe stream ended without usable success event",
                extra={"error_type": "UpstreamException"},
            )
            raise UpstreamException(
                message="CleanupProbeService: Probe stream ended without usable event",
                details={"status": 502, "error": "empty_or_unusable_stream"},
                status_code=502,
            )

        return {
            "status": 200,
            "resolved_model": resolved_model_id,
            "disable_retry": disable_retry,
        }


__all__ = ["CleanupProbeService"]
