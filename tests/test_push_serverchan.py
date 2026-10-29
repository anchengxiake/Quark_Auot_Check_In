import os
import tempfile
import unittest
from unittest import mock

import push_serverchan as ps


class EndpointTests(unittest.TestCase):
    def test_turbo_key_uses_sct_endpoint(self):
        self.assertEqual(
            ps.resolve_endpoint("SCT123456Tabcdef"),
            "https://sct.ftqq.com/SCT123456Tabcdef.send",
        )

    def test_sctp_key_uses_uid_subdomain(self):
        self.assertEqual(
            ps.resolve_endpoint("sctp777tAbCdEf"),
            "https://777.push.ft07.com/send/sctp777tAbCdEf.send",
        )

    def test_unknown_prefix_returns_none(self):
        self.assertIsNone(ps.resolve_endpoint("bogus-key"))

    def test_whitespace_is_trimmed(self):
        self.assertEqual(
            ps.resolve_endpoint("  SCT1Tk  "), "https://sct.ftqq.com/SCT1Tk.send"
        )


class SuccessDetectionTests(unittest.TestCase):
    def test_turbo_success_body(self):
        self.assertTrue(ps._is_success({"code": 0, "data": {"pushid": "1"}}, 200))

    def test_sctp_success_body(self):
        self.assertTrue(ps._is_success({"code": 0, "message": "", "data": None}, 200))

    def test_error_body_is_failure(self):
        self.assertFalse(ps._is_success({"code": 40001, "message": "bad key"}, 200))

    def test_non_json_body_falls_back_to_status(self):
        self.assertTrue(ps._is_success("ok", 200))
        self.assertFalse(ps._is_success("oops", 500))


class SendTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.marker = os.path.join(self.tmpdir, ".last_push_date")
        self.patch_marker = mock.patch.object(ps, "DAILY_MARKER", self.marker)
        self.patch_marker.start()
        self.addCleanup(self.patch_marker.stop)

    def test_missing_sendkey_returns_false(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(ps.send_serverchan("t", "m"))

    def test_successful_push_writes_daily_marker(self):
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b'{"code":0}'
        response.status = 200
        with mock.patch("urllib.request.urlopen", return_value=response):
            with mock.patch.dict(os.environ, {"PUSH_ONCE_DAILY": "1"}):
                self.assertTrue(ps.send_serverchan("t", "m", "SCT1Tk"))
        self.assertTrue(os.path.exists(self.marker))

    def test_daily_limit_skips_second_push(self):
        with open(self.marker, "w", encoding="utf-8") as handle:
            handle.write(ps._today_str())
        with mock.patch.dict(os.environ, {"PUSH_ONCE_DAILY": "1"}):
            with mock.patch("urllib.request.urlopen") as urlopen:
                self.assertTrue(ps.send_serverchan("t", "m", "SCT1Tk"))
                urlopen.assert_not_called()

    def test_force_push_ignores_daily_limit(self):
        with open(self.marker, "w", encoding="utf-8") as handle:
            handle.write(ps._today_str())
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b'{"code":0}'
        response.status = 200
        with mock.patch.dict(os.environ, {"PUSH_ONCE_DAILY": "1", "PUSH_FORCE": "1"}):
            with mock.patch("urllib.request.urlopen", return_value=response):
                self.assertTrue(ps.send_serverchan("t", "m", "SCT1Tk"))

    def test_network_error_returns_false_without_raising(self):
        with mock.patch("urllib.request.urlopen", side_effect=OSError("boom")):
            self.assertFalse(ps.send_serverchan("t", "m", "SCT1Tk"))

    def test_failure_body_does_not_write_marker(self):
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b'{"code":40001,"message":"bad"}'
        response.status = 200
        with mock.patch("urllib.request.urlopen", return_value=response):
            self.assertFalse(ps.send_serverchan("t", "m", "SCT1Tk"))
        self.assertFalse(os.path.exists(self.marker))


if __name__ == "__main__":
    unittest.main()
