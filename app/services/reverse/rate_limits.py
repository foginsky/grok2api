"""
Reverse interface: rate limits.
"""

import importlib
from typing import Any

from app.core.config import get_config
from app.core.exceptions import UpstreamException
from app.services.reverse.utils.headers import build_headers
from app.services.reverse.utils.retry import retry_on_status


orjson = importlib.import_module("orjson")
logger = importlib.import_module("app.core.logger").logger

RATE_LIMITS_API = "https://grok.com/rest/rate-limits"


class RateLimitsReverse:
    """/rest/rate-limits reverse interface."""

    @staticmethod
    async def request(session: Any, token: str, disable_retry: bool = False) -> Any:
        """Fetch rate limits from Grok.

        Args:
            session: AsyncSession, the session to use for the request.
            token: str, the SSO token.

        Returns:
            Any: The response from the request.
        """
        try:
            # Get proxy
            base_proxy = str(get_config("proxy.base_proxy_url") or "").strip() or None
            proxies = {"http": base_proxy, "https": base_proxy} if base_proxy else None

            # Build headers
            headers = build_headers(
                cookie_token=token,
                content_type="application/json",
                origin="https://grok.com",
                referer="https://grok.com/",
            )

            # Build payload
            payload = {
                "requestKind": "DEFAULT",
                "modelName": get_config("usage.model_name") or "grok-4-1-thinking-1129",
            }

            # Curl Config
            timeout = get_config("usage.timeout")
            browser = get_config("proxy.browser")

            async def _do_request():
                response = await session.post(
                    RATE_LIMITS_API,
                    headers=headers,
                    data=orjson.dumps(payload),
                    timeout=timeout,
                    proxies=proxies,
                    impersonate=browser,
                )

                if response.status_code != 200:
                    try:
                        body = response.text
                    except Exception:
                        body = None

                    try:
                        headers_summary = dict(response.headers)
                    except Exception:
                        headers_summary = None

                    logger.error(
                        f"RateLimitsReverse: Request failed, {response.status_code}",
                        extra={"error_type": "UpstreamException"},
                    )
                    raise UpstreamException(
                        message=f"RateLimitsReverse: Request failed, {response.status_code}",
                        details={
                            "status": response.status_code,
                            "body": body,
                            "headers": headers_summary,
                        },
                    )

                return response

            if disable_retry:
                return await _do_request()

            return await retry_on_status(_do_request)

        except Exception as e:
            # Handle upstream exception
            if isinstance(e, UpstreamException):
                raise

            # Handle other non-upstream exceptions
            logger.error(
                f"RateLimitsReverse: Request failed, {str(e)}",
                extra={"error_type": type(e).__name__},
            )
            raise UpstreamException(
                message=f"RateLimitsReverse: Request failed, {str(e)}",
                details={"status": 502, "error": str(e)},
            )


__all__ = ["RateLimitsReverse"]
