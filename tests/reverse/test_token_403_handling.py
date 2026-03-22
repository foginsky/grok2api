import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MANAGER_PATH = PROJECT_ROOT / "app/services/token/manager.py"
MODELS_PATH = PROJECT_ROOT / "app/services/token/models.py"
POOL_PATH = PROJECT_ROOT / "app/services/token/pool.py"
SERVICE_PATH = PROJECT_ROOT / "app/services/token/service.py"
APP_CHAT_PATH = PROJECT_ROOT / "app/services/reverse/app_chat.py"


def _ensure_package(name: str, path: Path) -> None:
    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
        module.__path__ = [str(path)]
        sys.modules[name] = module


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _install_dependency_stubs() -> None:
    if "app.core.logger" not in sys.modules:

        class _DummyLogger:
            def __getattr__(self, _name):
                return lambda *args, **kwargs: None

        logger_module = types.ModuleType("app.core.logger")
        setattr(logger_module, "logger", _DummyLogger())
        sys.modules["app.core.logger"] = logger_module

    if "app.core.config" not in sys.modules:
        config_module = types.ModuleType("app.core.config")
        setattr(config_module, "get_config", lambda key, default=None: default)
        sys.modules["app.core.config"] = config_module

    if "app.core.storage" not in sys.modules:

        class _DummyLock:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

        class _DummyStorage:
            async def load_tokens(self):
                return {}

            async def save_tokens(self, _data):
                return None

            def acquire_lock(self, *_args, **_kwargs):
                return _DummyLock()

        storage_module = types.ModuleType("app.core.storage")
        setattr(storage_module, "get_storage", lambda: _DummyStorage())
        setattr(storage_module, "LocalStorage", _DummyStorage)
        sys.modules["app.core.storage"] = storage_module

    if "app.core.exceptions" not in sys.modules:
        exceptions_module = types.ModuleType("app.core.exceptions")

        class UpstreamException(Exception):
            def __init__(self, message: str, details=None, status_code: int = 502):
                self.message = message
                self.details = details
                self.status_code = status_code
                super().__init__(message)

        setattr(exceptions_module, "UpstreamException", UpstreamException)
        sys.modules["app.core.exceptions"] = exceptions_module

    if "app.services.grok.batch_services.usage" not in sys.modules:
        usage_module = types.ModuleType("app.services.grok.batch_services.usage")

        class UsageService:
            async def get(self, _token_str):
                return None

        setattr(usage_module, "UsageService", UsageService)
        sys.modules["app.services.grok.batch_services.usage"] = usage_module

    if "app.services.reverse.utils.headers" not in sys.modules:
        headers_module = types.ModuleType("app.services.reverse.utils.headers")
        setattr(headers_module, "build_headers", lambda **kwargs: {"x-test": "1"})
        sys.modules["app.services.reverse.utils.headers"] = headers_module

    if "app.services.reverse.utils.retry" not in sys.modules:
        retry_module = types.ModuleType("app.services.reverse.utils.retry")

        async def _retry_on_status(func, **_kwargs):
            return await func()

        setattr(retry_module, "retry_on_status", _retry_on_status)
        sys.modules["app.services.reverse.utils.retry"] = retry_module

    if "curl_cffi.requests.errors" not in sys.modules:
        errors_module = types.ModuleType("curl_cffi.requests.errors")
        setattr(errors_module, "RequestsError", type("RequestsError", (Exception,), {}))
        sys.modules["curl_cffi.requests.errors"] = errors_module

    if "curl_cffi.requests" not in sys.modules:
        curl_requests_module = types.ModuleType("curl_cffi.requests")
        setattr(curl_requests_module, "AsyncSession", type("AsyncSession", (), {}))
        sys.modules["curl_cffi.requests"] = curl_requests_module

    if "curl_cffi" not in sys.modules:
        curl_module = types.ModuleType("curl_cffi")
        setattr(curl_module, "requests", sys.modules["curl_cffi.requests"])
        sys.modules["curl_cffi"] = curl_module

    if "orjson" not in sys.modules:
        orjson_module = types.ModuleType("orjson")
        setattr(orjson_module, "dumps", lambda value: json.dumps(value).encode("utf-8"))
        sys.modules["orjson"] = orjson_module


def _load_test_modules():
    for module_name in [
        "app.services.reverse.app_chat",
        "app.services.token.manager",
        "app.services.token.service",
        "app.services.token.pool",
        "app.services.token.models",
        "app.services.reverse.utils.retry",
        "app.services.reverse.utils.headers",
        "app.services.reverse.utils",
        "app.services.reverse",
        "app.services.grok.batch_services.usage",
        "app.services.grok.batch_services",
        "app.services.grok",
        "app.services.token",
        "app.services",
        "app.core.exceptions",
        "app.core.storage",
        "app.core.config",
        "app.core.logger",
        "app.core",
        "app",
        "curl_cffi.requests.errors",
        "curl_cffi.requests",
        "curl_cffi",
        "orjson",
    ]:
        sys.modules.pop(module_name, None)

    _ensure_package("app", PROJECT_ROOT / "app")
    _ensure_package("app.core", PROJECT_ROOT / "app/core")
    _ensure_package("app.services", PROJECT_ROOT / "app/services")
    _ensure_package("app.services.token", PROJECT_ROOT / "app/services/token")
    _ensure_package("app.services.reverse", PROJECT_ROOT / "app/services/reverse")
    _ensure_package(
        "app.services.reverse.utils", PROJECT_ROOT / "app/services/reverse/utils"
    )
    _ensure_package("app.services.grok", PROJECT_ROOT / "app/services/grok")
    _ensure_package(
        "app.services.grok.batch_services",
        PROJECT_ROOT / "app/services/grok/batch_services",
    )
    _install_dependency_stubs()

    _load_module("app.services.token.models", MODELS_PATH)
    _load_module("app.services.token.pool", POOL_PATH)
    _load_module("app.services.token.service", SERVICE_PATH)
    manager_module = _load_module("app.services.token.manager", MANAGER_PATH)
    app_chat_module = _load_module("app.services.reverse.app_chat", APP_CHAT_PATH)
    return manager_module, app_chat_module


class _ForbiddenUsageService:
    def __init__(self, module):
        self.module = module

    async def get(self, _token_str):
        raise self.module.UpstreamException(
            "forbidden",
            details={"status": 403},
        )


class _FakeErrorResponse:
    def __init__(self, status_code=403, body="forbidden", headers=None):
        self.status_code = status_code
        self._body = body
        self.headers = headers or {}

    async def text(self):
        return self._body


class _RecordingSession:
    def __init__(self, response):
        self.response = response

    async def post(self, *args, **kwargs):
        return self.response


class Token403HandlingTest(unittest.IsolatedAsyncioTestCase):
    async def test_sync_usage_records_403_as_auth_failure(self):
        manager_module, _ = _load_test_modules()
        manager = manager_module.TokenManager()
        manager._schedule_save = lambda: None

        pool = manager_module.TokenPool("ssoBasic")
        token = manager_module.TokenInfo(token="bad-token")
        pool.add(token)
        manager.pools = {"ssoBasic": pool}

        values = {
            "token.fail_threshold": 1,
            "token.auth_failure_status_codes": [401, 403],
        }

        with (
            patch.object(
                manager_module,
                "get_config",
                side_effect=lambda key, default=None: values.get(key, default),
            ),
            patch.object(
                manager_module,
                "UsageService",
                lambda: _ForbiddenUsageService(manager_module),
            ),
        ):
            result = await manager.sync_usage("bad-token", consume_on_fail=False)

        self.assertFalse(result)
        self.assertEqual(token.fail_count, 1)
        self.assertEqual(token.status, manager_module.TokenStatus.EXPIRED)
        self.assertEqual(token.last_fail_reason, "rate_limits_auth_failed")

    async def test_app_chat_request_records_403_auth_like_failure(self):
        _, app_chat_module = _load_test_modules()
        session = _RecordingSession(
            _FakeErrorResponse(
                status_code=403,
                body="forbidden by upstream",
                headers={"cf-ray": "ray-403"},
            )
        )
        values = {
            "proxy.base_proxy_url": "",
            "chat.timeout": 30,
            "video.timeout": 30,
            "image.timeout": 30,
            "chat.connect_timeout": 5,
            "proxy.browser": "chrome-test",
            "app.disable_memory": True,
            "app.temporary": True,
        }
        record_fail = AsyncMock(return_value=True)

        with (
            patch.object(
                app_chat_module,
                "get_config",
                side_effect=lambda key, default=None: values.get(key, default),
            ),
            patch.object(app_chat_module.TokenService, "record_fail", new=record_fail),
            self.assertRaises(app_chat_module.UpstreamException) as caught,
        ):
            await app_chat_module.AppChatReverse.request(
                session=session,
                token="bad-token",
                message="hello",
                model="grok-4",
            )

        record_fail.assert_awaited_once_with("bad-token", 403, "app_chat_auth_failed")
        self.assertEqual(caught.exception.details["status"], 403)


if __name__ == "__main__":
    unittest.main()
