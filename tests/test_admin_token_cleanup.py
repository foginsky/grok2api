import asyncio
import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import ANY, AsyncMock, patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANAGER_PATH = PROJECT_ROOT / "app/services/token/manager.py"
MODELS_PATH = PROJECT_ROOT / "app/services/token/models.py"
POOL_PATH = PROJECT_ROOT / "app/services/token/pool.py"
CHAT_SERVICE_PATH = PROJECT_ROOT / "app/services/grok/services/chat.py"
ADMIN_TOKEN_PATH = PROJECT_ROOT / "app/api/v1/admin_api/token.py"
BATCH_PATH = PROJECT_ROOT / "app/core/batch.py"
AUTH_PATH = PROJECT_ROOT / "app/core/auth.py"
EXCEPTIONS_PATH = PROJECT_ROOT / "app/core/exceptions.py"


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

        def _get_config(key, default=None):
            if key == "usage.model_name":
                return "grok-4.1-fast"
            return default

        setattr(config_module, "get_config", _get_config)
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

    if "app.services.grok.batch_services.usage" not in sys.modules:
        usage_module = types.ModuleType("app.services.grok.batch_services.usage")

        class UsageService:
            async def get(self, _token, disable_retry: bool = False):
                return None

        setattr(usage_module, "UsageService", UsageService)
        sys.modules["app.services.grok.batch_services.usage"] = usage_module

    if "app.services.grok.batch_services.cleanup_probe" not in sys.modules:
        cleanup_probe_module = types.ModuleType(
            "app.services.grok.batch_services.cleanup_probe"
        )

        class CleanupProbeService:
            async def probe(
                self, _token, probe_model: str, disable_retry: bool = False
            ):
                return None

        setattr(cleanup_probe_module, "CleanupProbeService", CleanupProbeService)
        sys.modules["app.services.grok.batch_services.cleanup_probe"] = (
            cleanup_probe_module
        )

    if "app.services.grok.batch_services.nsfw" not in sys.modules:
        nsfw_module = types.ModuleType("app.services.grok.batch_services.nsfw")

        class NSFWService:
            @staticmethod
            async def batch(*_args, **_kwargs):
                return {}

        setattr(nsfw_module, "NSFWService", NSFWService)
        sys.modules["app.services.grok.batch_services.nsfw"] = nsfw_module

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

    if "app.services.reverse.utils.session" not in sys.modules:
        session_module = types.ModuleType("app.services.reverse.utils.session")

        class ResettableSession:
            def __init__(self, *_args, **_kwargs):
                pass

            async def close(self):
                return None

        setattr(session_module, "ResettableSession", ResettableSession)
        sys.modules["app.services.reverse.utils.session"] = session_module

    if "app.services.grok.services.model" not in sys.modules:
        model_module = types.ModuleType("app.services.grok.services.model")

        class ModelService:
            @staticmethod
            def get(_model):
                return None

            @staticmethod
            def to_grok(model_id):
                return model_id, None

        setattr(model_module, "ModelService", ModelService)
        sys.modules["app.services.grok.services.model"] = model_module

    if "app.services.grok.utils.upload" not in sys.modules:
        upload_module = types.ModuleType("app.services.grok.utils.upload")

        class UploadService:
            async def upload_file(self, *_args, **_kwargs):
                return "file-id", {}

            async def close(self):
                return None

        setattr(upload_module, "UploadService", UploadService)
        sys.modules["app.services.grok.utils.upload"] = upload_module

    if "app.services.grok.utils.process" not in sys.modules:
        process_module = types.ModuleType("app.services.grok.utils.process")

        class BaseProcessor:
            def __init__(self, model: str, token: str = ""):
                self.model = model
                self.token = token
                self.created = 0

            async def close(self):
                return None

            def _get_dl(self):
                return types.SimpleNamespace(
                    render_image=AsyncMock(return_value="![image](https://example.com)")
                )

        setattr(process_module, "BaseProcessor", BaseProcessor)
        sys.modules["app.services.grok.utils.process"] = process_module

    if "app.services.grok.utils.retry" not in sys.modules:
        grok_retry_module = types.ModuleType("app.services.grok.utils.retry")
        setattr(grok_retry_module, "pick_token", lambda *_args, **_kwargs: None)
        setattr(grok_retry_module, "rate_limited", lambda *_args, **_kwargs: False)
        sys.modules["app.services.grok.utils.retry"] = grok_retry_module

    if "app.services.grok.utils.stream" not in sys.modules:
        stream_module = types.ModuleType("app.services.grok.utils.stream")
        setattr(
            stream_module, "wrap_stream_with_usage", lambda stream, *_a, **_k: stream
        )
        sys.modules["app.services.grok.utils.stream"] = stream_module

    if "app.services.grok.utils.tool_call" not in sys.modules:
        tool_call_module = types.ModuleType("app.services.grok.utils.tool_call")
        setattr(tool_call_module, "build_tool_prompt", lambda *_args, **_kwargs: "")
        setattr(tool_call_module, "parse_tool_calls", lambda *_args, **_kwargs: [])
        setattr(
            tool_call_module, "parse_tool_call_block", lambda *_args, **_kwargs: None
        )
        setattr(tool_call_module, "format_tool_history", lambda messages: messages)
        sys.modules["app.services.grok.utils.tool_call"] = tool_call_module

    token_pkg = sys.modules.get("app.services.token")
    if token_pkg is not None:
        setattr(token_pkg, "get_token_manager", AsyncMock(return_value=None))

        class EffortType:
            LOW = "low"

        setattr(token_pkg, "EffortType", EffortType)

    if "orjson" not in sys.modules:
        orjson_module = types.ModuleType("orjson")
        setattr(orjson_module, "dumps", lambda value: json.dumps(value).encode("utf-8"))
        setattr(orjson_module, "loads", lambda value: json.loads(value))
        setattr(orjson_module, "JSONDecodeError", json.JSONDecodeError)
        sys.modules["orjson"] = orjson_module

    if "curl_cffi.requests.errors" not in sys.modules:
        curl_module = types.ModuleType("curl_cffi")
        requests_module = types.ModuleType("curl_cffi.requests")
        errors_module = types.ModuleType("curl_cffi.requests.errors")

        class RequestsError(Exception):
            pass

        setattr(errors_module, "RequestsError", RequestsError)
        sys.modules["curl_cffi"] = curl_module
        sys.modules["curl_cffi.requests"] = requests_module
        sys.modules["curl_cffi.requests.errors"] = errors_module


def _load_test_modules():
    for module_name in [
        "app.api.v1.admin_api.token",
        "app.api.v1.admin_api",
        "app.api.v1",
        "app.api",
        "app.services.token.manager",
        "app.services.token.pool",
        "app.services.token.models",
        "app.services.grok.batch_services.usage",
        "app.services.grok.batch_services.cleanup_probe",
        "app.services.grok.batch_services.nsfw",
        "app.services.grok.batch_services",
        "app.services.grok",
        "app.services.grok.services.chat",
        "app.services.grok.services.model",
        "app.services.grok.services",
        "app.services.grok.utils.upload",
        "app.services.grok.utils.process",
        "app.services.grok.utils.retry",
        "app.services.grok.utils.stream",
        "app.services.grok.utils.tool_call",
        "app.services.grok.utils",
        "app.services.reverse.app_chat",
        "app.services.reverse.utils.retry",
        "app.services.reverse.utils.session",
        "app.services.reverse.utils.headers",
        "app.services.reverse.utils",
        "app.services.reverse",
        "app.services.token",
        "app.services",
        "app.core.batch",
        "app.core.auth",
        "app.core.exceptions",
        "app.core.storage",
        "app.core.config",
        "app.core.logger",
        "app.core",
        "app",
        "orjson",
    ]:
        sys.modules.pop(module_name, None)

    _ensure_package("app", PROJECT_ROOT / "app")
    _ensure_package("app.core", PROJECT_ROOT / "app/core")
    _ensure_package("app.services", PROJECT_ROOT / "app/services")
    _ensure_package("app.services.token", PROJECT_ROOT / "app/services/token")
    _ensure_package("app.services.grok", PROJECT_ROOT / "app/services/grok")
    _ensure_package(
        "app.services.grok.services", PROJECT_ROOT / "app/services/grok/services"
    )
    _ensure_package("app.services.grok.utils", PROJECT_ROOT / "app/services/grok/utils")
    _ensure_package("app.services.reverse", PROJECT_ROOT / "app/services/reverse")
    _ensure_package(
        "app.services.reverse.utils", PROJECT_ROOT / "app/services/reverse/utils"
    )
    _ensure_package(
        "app.services.grok.batch_services",
        PROJECT_ROOT / "app/services/grok/batch_services",
    )
    _ensure_package("app.api", PROJECT_ROOT / "app/api")
    _ensure_package("app.api.v1", PROJECT_ROOT / "app/api/v1")
    _ensure_package("app.api.v1.admin_api", PROJECT_ROOT / "app/api/v1/admin_api")
    _install_dependency_stubs()

    models_module = _load_module("app.services.token.models", MODELS_PATH)
    pool_module = _load_module("app.services.token.pool", POOL_PATH)
    manager_module = _load_module("app.services.token.manager", MANAGER_PATH)
    batch_module = _load_module("app.core.batch", BATCH_PATH)
    _load_module("app.core.auth", AUTH_PATH)
    _load_module("app.core.exceptions", EXCEPTIONS_PATH)
    admin_token_module = _load_module("app.api.v1.admin_api.token", ADMIN_TOKEN_PATH)
    return models_module, pool_module, manager_module, batch_module, admin_token_module


class _FakeUsageService:
    def __init__(self, responses):
        self._responses = responses

    async def get(self, token: str, disable_retry: bool = False):
        result = self._responses[token]
        if isinstance(result, Exception):
            raise result
        return result


class _FakeCleanupProbeService:
    def __init__(self, responses, calls=None):
        self._responses = responses
        self._calls = calls if calls is not None else []

    async def probe(self, token: str, probe_model: str, disable_retry: bool = False):
        self._calls.append((token, probe_model, disable_retry))
        result = self._responses[token]
        if isinstance(result, Exception):
            raise result
        return result


class _FakeProbeResponse:
    def __init__(self, status_code=200, lines=None, body="", headers=None):
        self.status_code = status_code
        self._lines = list(lines or [])
        self._body = body
        self.headers = headers or {}
        self.closed = False

    async def text(self):
        return self._body

    async def aiter_lines(self):
        for line in self._lines:
            yield line

    async def aclose(self):
        self.closed = True


class CleanupProbeServiceStreamTests(unittest.IsolatedAsyncioTestCase):
    async def test_probe_raises_when_first_stream_event_contains_error(self):
        cleanup_probe_module = _load_module(
            "app.services.grok.batch_services.cleanup_probe",
            PROJECT_ROOT / "app/services/grok/batch_services/cleanup_probe.py",
        )

        error_line = json.dumps(
            {
                "result": {
                    "error": {
                        "status": 404,
                        "message": "model route missing",
                    }
                }
            }
        )

        request_calls = []

        async def _fake_stream():
            try:
                request_calls.append(("stream_yielded", None))
                yield f"data: {error_line}"
            finally:
                request_calls.append(("stream_closed", None))

        class _FakeChatService:
            async def chat(self, **kwargs):
                request_calls.append(("chat", kwargs))
                return _fake_stream()

        with (
            patch.object(
                cleanup_probe_module,
                "_get_chat_service_cls",
                lambda: _FakeChatService,
                create=True,
            ),
            patch.object(
                cleanup_probe_module,
                "_get_model_service",
                lambda: types.SimpleNamespace(
                    to_grok=lambda _model_id: (
                        "grok-4-1-thinking-1129",
                        "MODEL_MODE_FAST",
                    )
                ),
            ),
            patch.object(
                cleanup_probe_module,
                "_get_app_chat_helpers",
                side_effect=AssertionError(
                    "cleanup probe should use GrokChatService.chat"
                ),
                create=True,
            ),
            patch.object(
                cleanup_probe_module,
                "logger",
                types.SimpleNamespace(
                    info=lambda *a, **k: None,
                    error=lambda *a, **k: None,
                    warning=lambda *a, **k: None,
                ),
            ),
        ):
            with self.assertRaises(cleanup_probe_module.UpstreamException) as ctx:
                await cleanup_probe_module.CleanupProbeService().probe(
                    "token-1", "grok-4.1-fast", disable_retry=True
                )

        self.assertEqual(ctx.exception.details["status"], 404)
        self.assertEqual(request_calls[0][0], "chat")
        self.assertEqual(
            request_calls[0][1],
            {
                "token": "token-1",
                "message": "hi",
                "model": "grok-4-1-thinking-1129",
                "requested_model": "grok-4.1-fast",
                "mode": "MODEL_MODE_FAST",
                "image_generation_count": 1,
                "disable_retry": True,
                "record_auth_failures": False,
            },
        )
        self.assertIn(("stream_yielded", None), request_calls)
        self.assertIn(("stream_closed", None), request_calls)

    async def test_probe_uses_real_request_path_without_retry_or_fail_tracking(self):
        cleanup_probe_module = _load_module(
            "app.services.grok.batch_services.cleanup_probe",
            PROJECT_ROOT / "app/services/grok/batch_services/cleanup_probe.py",
        )
        chat_module = _load_module("app.services.grok.services.chat", CHAT_SERVICE_PATH)
        app_chat_module = sys.modules["app.services.reverse.app_chat"]

        response = _FakeProbeResponse(
            403,
            body="forbidden by upstream",
            headers={"cf-ray": "ray-cleanup-403"},
        )
        record_fail = AsyncMock(return_value=True)

        class _RecordingSession:
            def __init__(self, *_args, **_kwargs):
                self.calls = []
                self.closed = False

            async def post(self, *args, **kwargs):
                self.calls.append({"args": args, "kwargs": kwargs})
                return response

            async def close(self):
                self.closed = True

        values = {
            "proxy.base_proxy_url": "",
            "chat.timeout": 30,
            "chat.concurrent": 1,
            "video.timeout": 30,
            "image.timeout": 30,
            "chat.connect_timeout": 5,
            "proxy.browser": "chrome-test",
            "app.disable_memory": True,
            "app.temporary": True,
        }

        async def _fail_if_retry_used(*_args, **_kwargs):
            raise AssertionError("cleanup probe should not invoke retry_on_status")

        fake_session = _RecordingSession()

        with (
            patch.object(
                cleanup_probe_module,
                "_get_chat_service_cls",
                lambda: chat_module.GrokChatService,
                create=True,
            ),
            patch.object(
                cleanup_probe_module,
                "_get_model_service",
                lambda: types.SimpleNamespace(
                    to_grok=lambda _model_id: ("grok-4", "MODEL_MODE_FAST")
                ),
            ),
            patch.object(
                cleanup_probe_module,
                "_get_app_chat_helpers",
                side_effect=AssertionError(
                    "cleanup probe should route through GrokChatService.chat"
                ),
                create=True,
            ),
            patch.object(
                cleanup_probe_module,
                "logger",
                types.SimpleNamespace(
                    info=lambda *a, **k: None,
                    error=lambda *a, **k: None,
                    warning=lambda *a, **k: None,
                ),
            ),
            patch.object(
                chat_module,
                "ResettableSession",
                lambda *_args, **_kwargs: fake_session,
            ),
            patch.object(
                app_chat_module,
                "get_config",
                side_effect=lambda key, default=None: values.get(key, default),
            ),
            patch.object(
                chat_module,
                "get_config",
                side_effect=lambda key, default=None: values.get(key, default),
            ),
            patch.object(app_chat_module.TokenService, "record_fail", new=record_fail),
            patch.object(app_chat_module, "retry_on_status", new=_fail_if_retry_used),
        ):
            with self.assertRaises(cleanup_probe_module.UpstreamException) as ctx:
                await cleanup_probe_module.CleanupProbeService().probe(
                    "cleanup-token", "grok-4.1-fast", disable_retry=True
                )

        self.assertEqual(ctx.exception.details["status"], 403)
        record_fail.assert_not_awaited()
        self.assertEqual(len(fake_session.calls), 1)
        payload = json.loads(fake_session.calls[0]["kwargs"]["data"].decode("utf-8"))
        self.assertEqual(payload["modelName"], "grok-4")
        self.assertEqual(payload["modelMode"], "MODEL_MODE_FAST")
        self.assertEqual(payload["message"], "hi")
        self.assertTrue(fake_session.closed)


def _build_manager(manager_module):
    manager = manager_module.TokenManager()
    basic_pool = manager_module.TokenPool("ssoBasic")
    super_pool = manager_module.TokenPool("ssoSuper")

    basic_pool.add(
        manager_module.TokenInfo(token="remove-401", last_fail_status=403, fail_count=1)
    )
    basic_pool.add(
        manager_module.TokenInfo(token="keep-500", last_fail_status=401, fail_count=4)
    )
    super_pool.add(
        manager_module.TokenInfo(token="keep-403", last_fail_status=401, fail_count=3)
    )
    super_pool.add(manager_module.TokenInfo(token="keep-ok"))
    super_pool.add(
        manager_module.TokenInfo(
            token="already-disabled", status=manager_module.TokenStatus.DISABLED
        )
    )

    manager.pools = {
        "ssoBasic": basic_pool,
        "ssoSuper": super_pool,
    }
    manager._save = AsyncMock()
    return manager


class ActiveInvalidTokenCleanupTests(unittest.IsolatedAsyncioTestCase):
    async def test_cleanup_removes_401_and_disables_400_403_404(self):
        _, _, manager_module, _, _ = _load_test_modules()
        manager = _build_manager(manager_module)
        manager.pools["ssoBasic"].add(manager_module.TokenInfo(token="disable-400"))
        manager.pools["ssoSuper"].add(manager_module.TokenInfo(token="disable-404"))
        responses = {
            "remove-401": manager_module.UpstreamException(
                "unauthorized", details={"status": 401}
            ),
            "disable-400": manager_module.UpstreamException(
                "bad-request", details={"status": 400}
            ),
            "keep-403": manager_module.UpstreamException(
                "forbidden", details={"status": 403}
            ),
            "disable-404": manager_module.UpstreamException(
                "not-found", details={"status": 404}
            ),
            "keep-500": manager_module.UpstreamException(
                "server-error", details={"status": 500}
            ),
            "keep-ok": {"remainingTokens": 12},
        }

        with patch.object(
            manager_module,
            "CleanupProbeService",
            lambda: _FakeCleanupProbeService(responses),
        ):
            result = await manager.cleanup_invalid_tokens()

        by_token = result["results"]

        self.assertIsNone(manager.pools["ssoBasic"].get("remove-401"))
        self.assertEqual(
            manager.pools["ssoBasic"].get("disable-400").status,
            manager_module.TokenStatus.DISABLED,
        )
        self.assertIsNotNone(manager.pools["ssoSuper"].get("keep-403"))
        self.assertEqual(
            manager.pools["ssoSuper"].get("keep-403").status,
            manager_module.TokenStatus.DISABLED,
        )
        self.assertEqual(
            manager.pools["ssoSuper"].get("disable-404").status,
            manager_module.TokenStatus.DISABLED,
        )
        self.assertIsNotNone(manager.pools["ssoBasic"].get("keep-500"))
        self.assertIsNotNone(manager.pools["ssoSuper"].get("keep-ok"))
        manager._save.assert_awaited_once()

        self.assertEqual(result["summary"]["total"], 6)
        self.assertEqual(result["summary"]["removed"], 1)
        self.assertEqual(result["summary"]["deleted"], 1)
        self.assertEqual(result["summary"]["disabled"], 3)
        self.assertEqual(result["summary"]["kept"], 2)

        self.assertTrue(by_token["remove-401"]["removed"])
        self.assertEqual(by_token["remove-401"]["probe_status"], 401)
        self.assertFalse(by_token["disable-400"]["removed"])
        self.assertTrue(by_token["disable-400"]["disabled"])
        self.assertEqual(by_token["disable-400"]["probe_status"], 400)
        self.assertFalse(by_token["keep-403"]["removed"])
        self.assertTrue(by_token["keep-403"]["disabled"])
        self.assertEqual(by_token["keep-403"]["probe_status"], 403)
        self.assertFalse(by_token["disable-404"]["removed"])
        self.assertTrue(by_token["disable-404"]["disabled"])
        self.assertEqual(by_token["disable-404"]["probe_status"], 404)
        self.assertFalse(by_token["keep-500"]["removed"])
        self.assertFalse(by_token["keep-500"].get("disabled", False))
        self.assertEqual(by_token["keep-500"]["probe_status"], 500)
        self.assertFalse(by_token["keep-ok"]["removed"])
        self.assertFalse(by_token["keep-ok"].get("disabled", False))
        self.assertIsNone(by_token["keep-ok"]["probe_status"])
        self.assertNotIn("already-disabled", by_token)

    async def test_cleanup_removes_token_when_401_is_on_status_code_field(self):
        _, _, manager_module, _, _ = _load_test_modules()
        manager = _build_manager(manager_module)
        responses = {
            "remove-401": manager_module.UpstreamException(
                "unauthorized", details={"body": "expired"}, status_code=401
            ),
            "keep-403": manager_module.UpstreamException(
                "forbidden", details={"status": 403}
            ),
            "keep-500": manager_module.UpstreamException(
                "server-error", details={"status": 500}
            ),
            "keep-ok": {"remainingTokens": 12},
        }

        with patch.object(
            manager_module,
            "CleanupProbeService",
            lambda: _FakeCleanupProbeService(responses),
        ):
            result = await manager.cleanup_invalid_tokens()

        self.assertIsNone(manager.pools["ssoBasic"].get("remove-401"))
        self.assertEqual(result["summary"]["removed"], 1)
        self.assertEqual(result["results"]["remove-401"]["probe_status"], 401)
        self.assertTrue(result["results"]["remove-401"]["removed"])

    async def test_cleanup_uses_single_probe_mode_for_active_tokens(self):
        _, _, manager_module, _, _ = _load_test_modules()
        manager = _build_manager(manager_module)
        calls = []

        with patch.object(
            manager_module,
            "CleanupProbeService",
            lambda: _FakeCleanupProbeService(
                {
                    "remove-401": {"remainingTokens": 1},
                    "keep-500": {"remainingTokens": 1},
                    "keep-403": {"remainingTokens": 1},
                    "keep-ok": {"remainingTokens": 1},
                },
                calls=calls,
            ),
        ):
            await manager.cleanup_invalid_tokens()

        self.assertEqual(
            calls,
            [
                ("remove-401", "grok-4.1-fast", True),
                ("keep-500", "grok-4.1-fast", True),
                ("keep-403", "grok-4.1-fast", True),
                ("keep-ok", "grok-4.1-fast", True),
            ],
        )


class AdminTokenCleanupAsyncApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_async_cleanup_endpoint_finishes_batch_with_summary_results(self):
        _, _, manager_module, batch_module, admin_token_module = _load_test_modules()
        manager = _build_manager(manager_module)
        manager.pools["ssoBasic"].add(manager_module.TokenInfo(token="disable-400"))
        manager.pools["ssoSuper"].add(manager_module.TokenInfo(token="disable-404"))
        responses = {
            "remove-401": manager_module.UpstreamException(
                "unauthorized", details={"status": 401}
            ),
            "disable-400": manager_module.UpstreamException(
                "bad-request", details={"status": 400}
            ),
            "keep-403": manager_module.UpstreamException(
                "forbidden", details={"status": 403}
            ),
            "disable-404": manager_module.UpstreamException(
                "not-found", details={"status": 404}
            ),
            "keep-500": manager_module.UpstreamException(
                "server-error", details={"status": 500}
            ),
            "keep-ok": {"remainingTokens": 12},
        }

        async def _expire_task(*_args, **_kwargs):
            return None

        with (
            patch.object(
                manager_module,
                "CleanupProbeService",
                lambda: _FakeCleanupProbeService(responses),
            ),
            patch.object(
                admin_token_module,
                "get_token_manager",
                AsyncMock(return_value=manager),
            ),
            patch.object(admin_token_module, "expire_task", _expire_task),
        ):
            response = await admin_token_module.cleanup_invalid_tokens_async({})
            task = batch_module.get_task(response["task_id"])

            final_event = None
            for _ in range(50):
                await asyncio.sleep(0)
                final_event = task.final_event() if task else None
                if final_event is not None:
                    break

        self.assertIsNotNone(task)
        self.assertEqual(response["status"], "success")
        self.assertEqual(response["total"], 6)
        self.assertIsNotNone(final_event)
        assert final_event is not None
        self.assertEqual(final_event["type"], "done")
        self.assertEqual(final_event["processed"], 6)
        self.assertEqual(final_event["ok"], 6)
        self.assertEqual(final_event["fail"], 0)

        result = final_event["result"]
        assert result is not None
        by_token = result["results"]
        self.assertEqual(result["summary"]["removed"], 1)
        self.assertEqual(result["summary"]["deleted"], 1)
        self.assertEqual(result["summary"]["disabled"], 3)
        self.assertEqual(result["summary"]["kept"], 2)
        self.assertTrue(by_token["remove-401"]["removed"])
        self.assertTrue(by_token["disable-400"]["disabled"])
        self.assertFalse(by_token["keep-403"]["removed"])
        self.assertTrue(by_token["keep-403"]["disabled"])
        self.assertTrue(by_token["disable-404"]["disabled"])
        self.assertFalse(by_token["keep-500"]["removed"])
        self.assertNotIn("already-disabled", by_token)


if __name__ == "__main__":
    unittest.main()
