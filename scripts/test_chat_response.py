"""
Minimal chat probe: exercises AppChatReverse with an available token.

Usage:
  python scripts/test_chat_response.py
  (optional) TOKEN_POOL=ssoBasic|ssoSuper
"""

import asyncio
import importlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import config  # noqa: E402
from app.core.exceptions import UpstreamException  # noqa: E402
from app.services.reverse.app_chat import AppChatReverse  # noqa: E402
from app.services.token import get_token_manager  # noqa: E402


AsyncSession = importlib.import_module("curl_cffi.requests").AsyncSession


def _print_failure_details(details) -> None:
    if not isinstance(details, dict):
        print(f"Failure details: {details}")
        return

    status = details.get("status")
    if status is not None:
        print(f"Status: {status}")

    headers = details.get("headers")
    if headers:
        print("Headers:")
        for key, value in headers.items():
            print(f"  {key}: {value}")

    body = details.get("body")
    if body:
        print("Body:")
        print(body)


async def main() -> int:
    await config.load()
    token = None
    pool = os.getenv("TOKEN_POOL")
    manager = await get_token_manager()
    await manager.reload_if_stale()

    if pool:
        token = manager.get_token(pool_name=pool)
    else:
        token = manager.get_token(pool_name="ssoBasic") or manager.get_token(
            pool_name="ssoSuper"
        )

    if not token:
        token = os.getenv("GROK_TOKEN") or os.getenv("SSO_TOKEN") or os.getenv("TOKEN")
    if not token:
        print("Missing token. Ensure token pool is configured or set GROK_TOKEN.")
        return 2

    try:
        async with AsyncSession() as session:
            stream = await AppChatReverse.request(
                session=session,
                token=token,
                message="ping",
                model="grok-4",
            )
            # AppChatReverse.request returns an async generator (stream_response)
            first_line = None
            async for chunk in stream:
                if chunk:
                    first_line = chunk
                    break
    except UpstreamException as exc:
        print(f"Probe failed (UpstreamException): {exc}")
        _print_failure_details(getattr(exc, "details", None))
        return 4
    except Exception as exc:
        print(f"Probe failed ({type(exc).__name__}): {exc}")
        return 4

    if first_line is not None:
        print(f"First response chunk: {first_line!r}")
        return 0
    else:
        print("Stream yielded no data.")
        return 3


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
