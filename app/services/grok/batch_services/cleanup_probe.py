from __future__ import annotations

import importlib
from typing import Any, Dict

from app.core.config import get_config
from app.core.exceptions import UpstreamException


class CleanupProbeService:
    """Real model-request probe used by admin cleanup."""

    async def probe(
        self,
        token: str,
        probe_model: str,
        disable_retry: bool = True,
    ) -> Dict[str, Any]:
        app_chat_module = importlib.import_module("app.services.reverse.app_chat")
        model_module = importlib.import_module("app.services.grok.services.model")
        session_module = importlib.import_module("app.services.reverse.utils.session")
        headers_module = importlib.import_module("app.services.reverse.utils.headers")
        logger = importlib.import_module("app.core.logger").logger
        orjson = importlib.import_module("orjson")
        requests_error = importlib.import_module(
            "curl_cffi.requests.errors"
        ).RequestsError

        ModelService = model_module.ModelService
        ResettableSession = session_module.ResettableSession
        build_headers = headers_module.build_headers
        AppChatReverse = app_chat_module.AppChatReverse
        CHAT_API = app_chat_module.CHAT_API
        is_transient = app_chat_module._is_transient_network_error

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
            except requests_error as exc:
                status = 599 if is_transient(exc) else 502
                raise UpstreamException(
                    message=f"CleanupProbeService: Probe failed, {exc}",
                    details={"status": status, "error": str(exc)},
                    status_code=status,
                ) from exc
            except Exception as exc:
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
                raise UpstreamException(
                    message=f"CleanupProbeService: Probe failed, {response.status_code}",
                    details={"status": response.status_code, "body": content},
                    status_code=response.status_code,
                )

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

            return {
                "status": 200,
                "resolved_model": resolved_model_id,
                "disable_retry": disable_retry,
            }


__all__ = ["CleanupProbeService"]
