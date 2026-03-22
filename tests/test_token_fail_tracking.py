import unittest

from app.services.token.manager import TokenManager
from app.services.token.models import TokenInfo, TokenStatus
from app.services.token.pool import TokenPool


class TokenFailTrackingTests(unittest.TestCase):
    def test_record_401_fail_tracks_status_and_expires_at_threshold(self):
        token = TokenInfo(token="tok_401")

        token.record_fail(401, "app_chat_auth_failed", threshold=1)

        self.assertEqual(token.fail_count, 1)
        self.assertEqual(token.last_fail_status, 401)
        self.assertEqual(token.last_fail_reason, "app_chat_auth_failed")
        self.assertIsNotNone(token.last_fail_at)
        self.assertEqual(token.status, TokenStatus.EXPIRED)

    def test_record_403_fail_does_not_mark_invalid_auth_failure(self):
        token = TokenInfo(token="tok_403")

        token.record_fail(403, "assets_list_auth_failed")

        self.assertEqual(token.fail_count, 0)
        self.assertIsNone(token.last_fail_status)
        self.assertIsNone(token.last_fail_reason)
        self.assertIsNone(token.last_fail_at)
        self.assertEqual(token.status, TokenStatus.ACTIVE)

    def test_record_success_clears_last_auth_failure_markers(self):
        token = TokenInfo(
            token="tok_success",
            fail_count=1,
            last_fail_at=123,
            last_fail_reason="app_chat_auth_failed",
            last_fail_status=401,
        )

        token.record_success()

        self.assertEqual(token.fail_count, 0)
        self.assertIsNone(token.last_fail_at)
        self.assertIsNone(token.last_fail_reason)
        self.assertIsNone(token.last_fail_status)
        self.assertEqual(token.status, TokenStatus.ACTIVE)


class TokenManagerFailTrackingTests(unittest.IsolatedAsyncioTestCase):
    async def test_manager_ignores_403_for_invalid_cleanup_marking(self):
        manager = TokenManager()
        manager.pools = {"ssoBasic": TokenPool("ssoBasic")}
        token = TokenInfo(token="tok_mgr_403")
        manager.pools["ssoBasic"].add(token)
        manager._schedule_save = lambda: None

        result = await manager.record_fail(
            "tok_mgr_403", 403, "assets_list_auth_failed"
        )

        self.assertTrue(result)
        self.assertIsNone(token.last_fail_status)
        self.assertIsNone(token.last_fail_reason)
        self.assertEqual(token.fail_count, 0)
        self.assertIsNone(token.last_fail_at)
        self.assertEqual(token.status, TokenStatus.ACTIVE)


if __name__ == "__main__":
    unittest.main()
