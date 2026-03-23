from __future__ import annotations

import importlib
from typing import Any, Dict

import orjson

from app.core.config import get_config
from app.core.exceptions import UpstreamException
from app.core.logger import logger


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


def _get_headers_builder():
    return importlib.import_module("app.services.reverse.utils.headers").build_headers


def _get_app_chat_helpers():
    module = importlib.import_module("app.services.reverse.app_chat")
    return module.AppChatReverse, module.CHAT_API, module._is_transient_network_error


def _get_requests_error_cls():
    return importlib.import_module("curl_cffi.requests.errors").RequestsError


class CleanupProbeService:
    """Real model-request probe used by admin cleanup."""

    async def probe(
        self,
        token: str,
        probe_model: str,
        disable_retry: bool = True,
    ) -> Dict[str, Any]:
        ModelService = _get_model_service()
        ResettableSession = _get_session_cls()
        build_headers = _get_headers_builder()
        AppChatReverse, CHAT_API, is_transient_network_error = _get_app_chat_helpers()
        RequestsError = _get_requests_error_cls()

        resolved_model_id = str(probe_model or "").strip() or "grok-3-mini"
        model_name, model_mode = ModelService.to_grok(resolved_model_id)

        base_proxy = get_config("proxy.base_proxy_url")
        proxies = {"http": base_proxy, "https": base_proxy} if base_proxy else None
        browser = get_config("proxy.browser")
        base_timeout = max(
            float(get_config("chat.timeout") or 60.0),
            float(get_config("video.timeout") or 60.0),
            float(get_config("image.timeout") or 60.0),
        )
        connect_timeout = float(
            get_config("chat.connect_timeout") or min(max(base_timeout, 1.0), 12.0)
        )
        timeout = (connect_timeout, base_timeout)

        headers = build_headers(
            cookie_token=token,
            content_type="application/json",
            origin="https://grok.com",
            referer="https://grok.com/",
        )
        payload = AppChatReverse.build_payload(
            message="hi",
            model=model_name,
            mode=model_mode,
            image_generation_count=1,
        )

        logger.info(
            "Cleanup probe prepared: "
            f"probe_model={probe_model or resolved_model_id}, "
            f"resolved_model={resolved_model_id}, upstream_model={model_name}, mode={model_mode}"
        )

        async with ResettableSession(impersonate=browser) as session:
            try:
                response = await session.post(
                    CHAT_API,
                    headers=headers,
                    data=orjson.dumps(payload),
                    timeout=timeout,
                    stream=True,
                    proxies=proxies,
                    impersonate=browser,
                )
            except RequestsError as exc:
                status = 599 if is_transient_network_error(exc) else 502
                logger.error(
                    f"Cleanup probe request failure: {status}",
                    extra={"error_type": "UpstreamException"},
                )
                raise UpstreamException(
                    message=f"CleanupProbeService: Probe failed, {exc}",
                    details={"status": status, "error": str(exc)},
                    status_code=status,
                ) from exc
            except Exception as exc:
                logger.error(
                    "Cleanup probe request failure: 502",
                    extra={"error_type": "UpstreamException"},
                )
                raise UpstreamException(
                    message=f"CleanupProbeService: Probe failed, {exc}",
                    details={"status": 502, "error": str(exc)},
                    status_code=502,
                ) from exc

            if response.status_code != 200:
                content = ""
                try:
                    content = await response.text()
                except Exception:
                    pass
                logger.error(
                    f"Cleanup probe HTTP failure: {response.status_code}",
                    extra={"error_type": "UpstreamException"},
                )
                raise UpstreamException(
                    message=f"CleanupProbeService: Probe failed, {response.status_code}",
                    details={"status": response.status_code, "body": content},
                    status_code=response.status_code,
                )

            stream_error_status = None
            stream_error_body = None
            saw_success_event = False
            try:
                async for raw_line in response.aiter_lines():
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
                            stream_error_status = int(error.get("status"))
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
                    close_fn = getattr(response, "aclose", None)
                    if callable(close_fn):
                        result = close_fn()
                        if hasattr(result, "__await__"):
                            await result
                    else:
                        close_fn = getattr(response, "close", None)
                        if callable(close_fn):
                            result = close_fn()
                            if hasattr(result, "__await__"):
                                await result
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
