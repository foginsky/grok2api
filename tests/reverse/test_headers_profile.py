import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[2]
HEADERS_PATH = PROJECT_ROOT / "app/services/reverse/utils/headers.py"
STATSIG_PATH = PROJECT_ROOT / "app/services/reverse/utils/statsig.py"


def _ensure_package(name: str, path: Path) -> None:
    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
        module.__path__ = [str(path)]
        sys.modules[name] = module


def _install_dependency_stubs() -> None:
    if "loguru" not in sys.modules:

        class _DummyLogger:
            def __getattr__(self, _name):
                return lambda *args, **kwargs: None

        loguru_module = types.ModuleType("loguru")
        setattr(loguru_module, "logger", _DummyLogger())
        sys.modules["loguru"] = loguru_module

    if "orjson" not in sys.modules:
        orjson_module = types.ModuleType("orjson")
        setattr(
            orjson_module,
            "dumps",
            lambda value: json.dumps(value).encode("utf-8"),
        )
        sys.modules["orjson"] = orjson_module


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_reverse_utils_modules():
    for module_name in [
        "app.services.reverse.utils.headers",
        "app.services.reverse.utils.statsig",
        "app.services.reverse.utils",
        "app.services.reverse",
        "app.services",
        "app",
    ]:
        sys.modules.pop(module_name, None)

    _ensure_package("app", PROJECT_ROOT / "app")
    _ensure_package("app.services", PROJECT_ROOT / "app/services")
    _ensure_package("app.services.reverse", PROJECT_ROOT / "app/services/reverse")
    _ensure_package(
        "app.services.reverse.utils", PROJECT_ROOT / "app/services/reverse/utils"
    )
    _install_dependency_stubs()

    statsig_module = _load_module("app.services.reverse.utils.statsig", STATSIG_PATH)
    headers_module = _load_module("app.services.reverse.utils.headers", HEADERS_PATH)
    return headers_module, statsig_module


class ReverseHeaderProfileTest(unittest.TestCase):
    def test_build_headers_omits_sentry_headers_when_sentry_release_missing(self):
        headers_module, _ = _load_reverse_utils_modules()
        values = {
            "app.sentry_release": "",
            "proxy.user_agent": "",
            "proxy.cf_cookies": "",
            "proxy.cf_clearance": "",
            "proxy.enabled": False,
        }

        with (
            patch.object(
                headers_module,
                "get_config",
                side_effect=lambda key, default=None: values.get(key, default),
            ),
            patch.object(
                headers_module.StatsigGenerator,
                "gen_id",
                return_value="statsig-fixed",
            ),
        ):
            headers = headers_module.build_headers("sso=test")

        self.assertNotIn("Baggage", headers)
        self.assertNotIn("Sentry-Trace", headers)
        self.assertNotIn("Traceparent", headers)

    def test_statsig_generator_uses_config_override_before_existing_behavior(self):
        _, statsig_module = _load_reverse_utils_modules()
        values = {
            "app.statsig_override": "statsig-override",
            "app.dynamic_statsig": False,
        }

        with patch.object(
            statsig_module,
            "get_config",
            side_effect=lambda key, default=None: values.get(key, default),
        ):
            self.assertEqual(
                statsig_module.StatsigGenerator.gen_id(), "statsig-override"
            )


if __name__ == "__main__":
    unittest.main()
