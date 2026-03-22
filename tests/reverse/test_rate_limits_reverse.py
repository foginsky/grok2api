import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RATE_LIMITS_PATH = PROJECT_ROOT / "app/services/reverse/rate_limits.py"
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
    if "fastapi" not in sys.modules:
        fastapi_module = types.ModuleType("fastapi")
        setattr(fastapi_module, "Request", type("Request", (), {}))
        setattr(
            fastapi_module,
            "HTTPException",
            type(
                "HTTPException",
                (Exception,),
                {
                    "__init__": lambda self, status_code=500, detail="": (
                        setattr(self, "status_code", status_code),
                        setattr(self, "detail", detail),
                        Exception.__init__(self, detail),
                    )[-1]
                },
            ),
        )
        sys.modules["fastapi"] = fastapi_module

    if "fastapi.responses" not in sys.modules:
        responses_module = types.ModuleType("fastapi.responses")
        setattr(responses_module, "JSONResponse", type("JSONResponse", (), {}))
        sys.modules["fastapi.responses"] = responses_module

    if "fastapi.exceptions" not in sys.modules:
        exceptions_module = types.ModuleType("fastapi.exceptions")
        setattr(
            exceptions_module,
            "RequestValidationError",
            type("RequestValidationError", (Exception,), {}),
        )
        sys.modules["fastapi.exceptions"] = exceptions_module

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

    if "app.services.reverse.utils.headers" not in sys.modules:
        headers_module = types.ModuleType("app.services.reverse.utils.headers")
        setattr(headers_module, "build_headers", lambda **kwargs: {"x-test": "1"})
        sys.modules["app.services.reverse.utils.headers"] = headers_module

    if "app.services.reverse.utils.retry" not in sys.modules:
        retry_module = types.ModuleType("app.services.reverse.utils.retry")

        async def _retry_on_status(func):
            return await func()

        setattr(retry_module, "retry_on_status", _retry_on_status)
        sys.modules["app.services.reverse.utils.retry"] = retry_module

    if "curl_cffi.requests" not in sys.modules:
        curl_requests_module = types.ModuleType("curl_cffi.requests")
        setattr(curl_requests_module, "AsyncSession", type("AsyncSession", (), {}))
        sys.modules["curl_cffi.requests"] = curl_requests_module
        curl_module = types.ModuleType("curl_cffi")
        setattr(curl_module, "requests", curl_requests_module)
        sys.modules["curl_cffi"] = curl_module

    if "orjson" not in sys.modules:
        orjson_module = types.ModuleType("orjson")
        setattr(orjson_module, "dumps", lambda value: json.dumps(value).encode("utf-8"))
        sys.modules["orjson"] = orjson_module


def _load_rate_limits_module():
    for module_name in [
        "app.services.reverse.rate_limits",
        "app.services.reverse.utils.retry",
        "app.services.reverse.utils.headers",
        "app.services.reverse.utils",
        "app.services.reverse",
        "app.services",
        "app.core.exceptions",
        "app.core.config",
        "app.core.logger",
        "app.core",
        "app",
    ]:
        sys.modules.pop(module_name, None)

    _ensure_package("app", PROJECT_ROOT / "app")
    _ensure_package("app.core", PROJECT_ROOT / "app/core")
    _ensure_package("app.services", PROJECT_ROOT / "app/services")
    _ensure_package("app.services.reverse", PROJECT_ROOT / "app/services/reverse")
    _ensure_package(
        "app.services.reverse.utils", PROJECT_ROOT / "app/services/reverse/utils"
    )
    _install_dependency_stubs()

    exceptions_module = _load_module("app.core.exceptions", EXCEPTIONS_PATH)
    rate_limits_module = _load_module(
        "app.services.reverse.rate_limits", RATE_LIMITS_PATH
    )
    return rate_limits_module, exceptions_module.UpstreamException


class _FakeResponse:
    def __init__(self, status_code=200, text="", headers=None):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}


class _RecordingSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def post(self, *args, **kwargs):
        self.calls.append({"args": args, "kwargs": kwargs})
        return self.response


class RateLimitsReverseTest(unittest.IsolatedAsyncioTestCase):
    async def test_request_uses_configured_usage_model_name(self):
        rate_limits_module, _ = _load_rate_limits_module()
        session = _RecordingSession(_FakeResponse())
        values = {
            "proxy.base_proxy_url": "",
            "usage.timeout": 30,
            "proxy.browser": "chrome-test",
            "usage.model_name": "grok-4-custom",
        }

        with patch.object(
            rate_limits_module,
            "get_config",
            side_effect=lambda key, default=None: values.get(key, default),
        ):
            await rate_limits_module.RateLimitsReverse.request(session, "token=abc")

        payload = json.loads(session.calls[0]["kwargs"]["data"].decode("utf-8"))
        self.assertEqual(payload["modelName"], "grok-4-custom")

    async def test_request_passes_proxy_mapping_when_base_proxy_exists(self):
        rate_limits_module, _ = _load_rate_limits_module()
        session = _RecordingSession(_FakeResponse())
        values = {
            "proxy.base_proxy_url": "http://proxy.internal:8080",
            "usage.timeout": 30,
            "proxy.browser": "chrome-test",
        }

        with patch.object(
            rate_limits_module,
            "get_config",
            side_effect=lambda key, default=None: values.get(key, default),
        ):
            await rate_limits_module.RateLimitsReverse.request(session, "token=abc")

        kwargs = session.calls[0]["kwargs"]
        self.assertEqual(
            kwargs.get("proxies"),
            {
                "http": "http://proxy.internal:8080",
                "https": "http://proxy.internal:8080",
            },
        )

    async def test_request_includes_response_body_and_headers_in_upstream_exception(
        self,
    ):
        rate_limits_module, UpstreamException = _load_rate_limits_module()
        session = _RecordingSession(
            _FakeResponse(
                status_code=403,
                text="forbidden by upstream",
                headers={"cf-ray": "ray-123", "content-type": "text/plain"},
            )
        )
        values = {
            "proxy.base_proxy_url": "",
            "usage.timeout": 30,
            "proxy.browser": "chrome-test",
        }

        with (
            patch.object(
                rate_limits_module,
                "get_config",
                side_effect=lambda key, default=None: values.get(key, default),
            ),
            self.assertRaises(UpstreamException) as caught,
        ):
            await rate_limits_module.RateLimitsReverse.request(session, "token=abc")

        self.assertEqual(caught.exception.details["status"], 403)
        self.assertEqual(caught.exception.details["body"], "forbidden by upstream")
        self.assertEqual(
            caught.exception.details["headers"],
            {"cf-ray": "ray-123", "content-type": "text/plain"},
        )


if __name__ == "__main__":
    unittest.main()
