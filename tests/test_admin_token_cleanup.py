import asyncio
import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANAGER_PATH = PROJECT_ROOT / "app/services/token/manager.py"
MODELS_PATH = PROJECT_ROOT / "app/services/token/models.py"
POOL_PATH = PROJECT_ROOT / "app/services/token/pool.py"
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

    if "app.services.grok.batch_services.usage" not in sys.modules:
        usage_module = types.ModuleType("app.services.grok.batch_services.usage")

        class UsageService:
            async def get(self, _token):
                return None

        setattr(usage_module, "UsageService", UsageService)
        sys.modules["app.services.grok.batch_services.usage"] = usage_module

    if "app.services.grok.batch_services.nsfw" not in sys.modules:
        nsfw_module = types.ModuleType("app.services.grok.batch_services.nsfw")

        class NSFWService:
            @staticmethod
            async def batch(*_args, **_kwargs):
                return {}

        setattr(nsfw_module, "NSFWService", NSFWService)
        sys.modules["app.services.grok.batch_services.nsfw"] = nsfw_module

    if "orjson" not in sys.modules:
        orjson_module = types.ModuleType("orjson")
        setattr(orjson_module, "dumps", lambda value: json.dumps(value).encode("utf-8"))
        sys.modules["orjson"] = orjson_module


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
        "app.services.grok.batch_services.nsfw",
        "app.services.grok.batch_services",
        "app.services.grok",
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

    async def get(self, token: str):
        result = self._responses[token]
        if isinstance(result, Exception):
            raise result
        return result


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

    manager.pools = {
        "ssoBasic": basic_pool,
        "ssoSuper": super_pool,
    }
    manager._save = AsyncMock()
    return manager


class ActiveInvalidTokenCleanupTests(unittest.IsolatedAsyncioTestCase):
    async def test_cleanup_removes_401_and_disables_403(self):
        _, _, manager_module, _, _ = _load_test_modules()
        manager = _build_manager(manager_module)
        responses = {
            "remove-401": manager_module.UpstreamException(
                "unauthorized", details={"status": 401}
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
            "UsageService",
            lambda: _FakeUsageService(responses),
        ):
            result = await manager.cleanup_invalid_tokens()

        by_token = result["results"]

        self.assertIsNone(manager.pools["ssoBasic"].get("remove-401"))
        self.assertIsNotNone(manager.pools["ssoSuper"].get("keep-403"))
        self.assertEqual(
            manager.pools["ssoSuper"].get("keep-403").status,
            manager_module.TokenStatus.DISABLED,
        )
        self.assertIsNotNone(manager.pools["ssoBasic"].get("keep-500"))
        self.assertIsNotNone(manager.pools["ssoSuper"].get("keep-ok"))
        manager._save.assert_awaited_once()

        self.assertEqual(result["summary"]["total"], 4)
        self.assertEqual(result["summary"]["removed"], 1)
        self.assertEqual(result["summary"]["deleted"], 1)
        self.assertEqual(result["summary"]["disabled"], 1)
        self.assertEqual(result["summary"]["kept"], 2)

        self.assertTrue(by_token["remove-401"]["removed"])
        self.assertEqual(by_token["remove-401"]["probe_status"], 401)
        self.assertFalse(by_token["keep-403"]["removed"])
        self.assertTrue(by_token["keep-403"]["disabled"])
        self.assertEqual(by_token["keep-403"]["probe_status"], 403)
        self.assertFalse(by_token["keep-500"]["removed"])
        self.assertFalse(by_token["keep-500"].get("disabled", False))
        self.assertEqual(by_token["keep-500"]["probe_status"], 500)
        self.assertFalse(by_token["keep-ok"]["removed"])
        self.assertFalse(by_token["keep-ok"].get("disabled", False))
        self.assertIsNone(by_token["keep-ok"]["probe_status"])

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
            "UsageService",
            lambda: _FakeUsageService(responses),
        ):
            result = await manager.cleanup_invalid_tokens()

        self.assertIsNone(manager.pools["ssoBasic"].get("remove-401"))
        self.assertEqual(result["summary"]["removed"], 1)
        self.assertEqual(result["results"]["remove-401"]["probe_status"], 401)
        self.assertTrue(result["results"]["remove-401"]["removed"])


class AdminTokenCleanupAsyncApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_async_cleanup_endpoint_finishes_batch_with_summary_results(self):
        _, _, manager_module, batch_module, admin_token_module = _load_test_modules()
        manager = _build_manager(manager_module)
        responses = {
            "remove-401": manager_module.UpstreamException(
                "unauthorized", details={"status": 401}
            ),
            "keep-403": manager_module.UpstreamException(
                "forbidden", details={"status": 403}
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
                "UsageService",
                lambda: _FakeUsageService(responses),
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
        self.assertEqual(response["total"], 4)
        self.assertIsNotNone(final_event)
        assert final_event is not None
        self.assertEqual(final_event["type"], "done")
        self.assertEqual(final_event["processed"], 4)
        self.assertEqual(final_event["ok"], 4)
        self.assertEqual(final_event["fail"], 0)

        result = final_event["result"]
        assert result is not None
        by_token = result["results"]
        self.assertEqual(result["summary"]["removed"], 1)
        self.assertEqual(result["summary"]["deleted"], 1)
        self.assertEqual(result["summary"]["disabled"], 1)
        self.assertEqual(result["summary"]["kept"], 2)
        self.assertTrue(by_token["remove-401"]["removed"])
        self.assertFalse(by_token["keep-403"]["removed"])
        self.assertTrue(by_token["keep-403"]["disabled"])
        self.assertFalse(by_token["keep-500"]["removed"])


if __name__ == "__main__":
    unittest.main()
