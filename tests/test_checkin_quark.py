import io
import unittest
from contextlib import redirect_stdout

from checkIn_Quark import (
    ConfigError,
    Quark,
    QuarkAPIError,
    extract_params,
    main,
    parse_account,
    split_account_entries,
)


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise QuarkAPIError(f"HTTP {self.status_code}")

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)


GROWTH_UNSIGNED = {
    "data": {
        "88VIP": True,
        "total_capacity": 2048,
        "cap_composition": {},
        "cap_sign": {"sign_daily": False, "sign_progress": 2, "sign_target": 7},
    }
}

GROWTH_SIGNED = {
    "data": {
        "88VIP": False,
        "total_capacity": 1024,
        "cap_composition": {"sign_reward": 512},
        "cap_sign": {
            "sign_daily": True,
            "sign_daily_reward": 256,
            "sign_progress": 2,
            "sign_target": 7,
        },
    }
}


class ParsingTests(unittest.TestCase):
    def test_split_accounts_supports_newlines_crlf_and_double_ampersand(self):
        entries = split_account_entries(" one \r\n\r\n two && three ")
        self.assertEqual(entries, ["one", "two", "three"])

    def test_split_accounts_rejects_empty_value(self):
        for raw in (None, "", "   \n  "):
            with self.subTest(raw=raw), self.assertRaises(ConfigError):
                split_account_entries(raw)

    def test_extract_params_from_captured_url(self):
        params = extract_params(
            "https://drive-m.quark.cn/path?foo=1&kps=a%2Bb&sign=s&vcode=v"
        )
        self.assertEqual(params, {"kps": "a+b", "sign": "s", "vcode": "v"})

    def test_extract_params_preserves_literal_plus_in_new_captured_url(self):
        params = extract_params(
            "https://drive-m.quark.cn/1/clouddrive/act/growth/reward"
            "?mt=token+part&kps=AASx+abc%2Bencoded%3D"
            "&sign=AAQH+sig%2Bencoded%3D&vcode=1790667254217&app=clouddrive"
        )
        self.assertEqual(params["kps"], "AASx+abc+encoded=")
        self.assertEqual(params["sign"], "AAQH+sig+encoded=")
        self.assertEqual(params["vcode"], "1790667254217")

    def test_extract_params_ignores_fragment(self):
        params = extract_params(
            "https://drive-m.quark.cn/x?kps=k&sign=s&vcode=v#/share?kps=bad"
        )
        self.assertEqual(params["kps"], "k")

    def test_parse_account_supports_legacy_format(self):
        account = parse_account("user=张三; kps=k; sign=s; vcode=v;", 1)
        self.assertEqual(account["user"], "张三")
        self.assertEqual(account["kps"], "k")

    def test_parse_account_supports_captured_url_format(self):
        account = parse_account(
            "user=李四; url=https://example.test/reward?kps=k&sign=s&vcode=v;", 1
        )
        self.assertEqual(account["sign"], "s")

    def test_parse_account_prefers_explicit_params_over_url(self):
        account = parse_account(
            "user=李四; kps=manual; url=https://example.test/reward?kps=fromurl&sign=s&vcode=v;",
            1,
        )
        self.assertEqual(account["kps"], "manual")

    def test_parse_account_reports_missing_parameters(self):
        with self.assertRaisesRegex(ConfigError, "sign, vcode"):
            parse_account("user=张三; kps=k;", 1)

    def test_parse_account_rejects_field_without_equals(self):
        with self.assertRaisesRegex(ConfigError, "无效字段"):
            parse_account("user=张三; kps=k; sign; vcode=v;", 1)

    def test_parse_account_defaults_user_name(self):
        self.assertEqual(parse_account("kps=k; sign=s; vcode=v;", 3)["user"], "账号3")


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.account = {"user": "测试", "kps": "k", "sign": "s", "vcode": "v"}

    def test_already_signed_is_successful(self):
        session = FakeSession([FakeResponse(GROWTH_SIGNED)])
        result = Quark(self.account, session=session).do_sign()
        self.assertIn("今日已签到", result)
        self.assertEqual(len(session.calls), 1)

    def test_unsigned_account_posts_sign_request(self):
        session = FakeSession(
            [
                FakeResponse(GROWTH_UNSIGNED),
                FakeResponse({"data": {"sign_daily_reward": 1024}}),
            ]
        )
        result = Quark(self.account, session=session).do_sign()
        self.assertIn("签到成功", result)
        self.assertEqual([call[0] for call in session.calls], ["GET", "POST"])

    def test_api_error_is_not_treated_as_success(self):
        session = FakeSession([FakeResponse({"code": 401, "message": "凭证失效"})])
        with self.assertRaisesRegex(QuarkAPIError, "凭证失效"):
            Quark(self.account, session=session).do_sign()

    def test_dry_run_never_posts(self):
        session = FakeSession([FakeResponse(GROWTH_UNSIGNED)])
        result = Quark(self.account, session=session, dry_run=True).do_sign()
        self.assertIn("DRY_RUN", result)
        self.assertEqual([call[0] for call in session.calls], ["GET"])

    def test_sign_already_done_message_is_treated_as_success(self):
        session = FakeSession(
            [
                FakeResponse(GROWTH_UNSIGNED),
                FakeResponse({"code": 23008, "message": "今天已经签到过了"}),
            ]
        )
        result = Quark(self.account, session=session).do_sign()
        self.assertIn("今日已签到", result)

    def test_unknown_sign_response_raises(self):
        session = FakeSession(
            [FakeResponse(GROWTH_UNSIGNED), FakeResponse({"code": 500, "msg": "服务异常"})]
        )
        with self.assertRaisesRegex(QuarkAPIError, "服务异常"):
            Quark(self.account, session=session).do_sign()

    def test_missing_cap_sign_raises(self):
        session = FakeSession([FakeResponse({"data": {"88VIP": False}})])
        with self.assertRaisesRegex(QuarkAPIError, "cap_sign"):
            Quark(self.account, session=session).do_sign()

    def test_params_include_required_credentials(self):
        quark = Quark(self.account)
        params = quark._params()
        self.assertEqual(params["pr"], "ucpro")
        self.assertEqual(params["fr"], "android")
        self.assertEqual(params["kps"], "k")

    def test_convert_bytes_formats_units(self):
        self.assertEqual(Quark.convert_bytes(0), "0.00 B")
        self.assertEqual(Quark.convert_bytes(1536), "1.50 KB")
        self.assertEqual(Quark.convert_bytes(1024**3), "1.00 GB")


class MainTests(unittest.TestCase):
    def test_multi_account_continues_after_one_failure_and_returns_nonzero(self):
        seen = []

        class StubQuark:
            def __init__(self, account):
                self.account = account

            def do_sign(self):
                seen.append(self.account["user"])
                if self.account["user"] == "坏账号":
                    raise QuarkAPIError("凭证失效")
                return "✅ 签到成功"

        raw = "user=坏账号;kps=1;sign=1;vcode=1;\nuser=好账号;kps=2;sign=2;vcode=2;"
        with redirect_stdout(io.StringIO()):
            exit_code = main(raw, quark_factory=StubQuark)

        self.assertEqual(exit_code, 1)
        self.assertEqual(seen, ["坏账号", "好账号"])

    def test_all_accounts_success_returns_zero(self):
        class StubQuark:
            def __init__(self, account):
                self.account = account

            def do_sign(self):
                return "✅ 签到成功"

        with redirect_stdout(io.StringIO()):
            exit_code = main("user=账号;kps=1;sign=1;vcode=1;", quark_factory=StubQuark)
        self.assertEqual(exit_code, 0)

    def test_malformed_account_does_not_block_others(self):
        seen = []

        class StubQuark:
            def __init__(self, account):
                self.account = account

            def do_sign(self):
                seen.append(self.account["user"])
                return "✅ 签到成功"

        raw = "user=坏;kps=1;\nuser=好;kps=2;sign=2;vcode=2;"
        with redirect_stdout(io.StringIO()):
            exit_code = main(raw, quark_factory=StubQuark)
        self.assertEqual(exit_code, 1)
        self.assertEqual(seen, ["好"])

    def test_missing_environment_returns_configuration_error(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(""), 2)


if __name__ == "__main__":
    unittest.main()
