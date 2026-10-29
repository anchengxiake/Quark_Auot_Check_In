"""夸克网盘每日签到（自动领取签到奖励空间）。

账号配置来自环境变量 ``COOKIE_QUARK``，支持两种写法：

旧版（手动拆参数）::

    user=张三; kps=xxx; sign=yyy; vcode=zzz;

新版（抓包完整 URL，脚本自动从中提取 kps/sign/vcode）::

    user=张三; url=https://drive-m.quark.cn/1/clouddrive/act/growth/reward?...#...

多个账号可用换行或 ``&&`` 分隔，空行会被忽略。
脚本按账号逐个执行：单个账号失败不会中断其余账号；只要有账号失败，
进程退出码即为非 0，便于 GitHub Actions 判定失败并触发 13:00 的补签。
"""

from __future__ import annotations

import os
import random
import re
import sys
import time
from typing import Callable
from urllib.parse import unquote, urlparse

import requests

INFO_URL = "https://drive-m.quark.cn/1/clouddrive/capacity/growth/info"
SIGN_URL = "https://drive-m.quark.cn/1/clouddrive/capacity/growth/sign"
REQUIRED_PARAMS = ("kps", "sign", "vcode")

DEFAULT_TIMEOUT = 15
RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})
MAX_GET_ATTEMPTS = 3

# 接口在“今天已经签过”时会返回业务错误码，这种提示要当作成功处理
ALREADY_SIGNED_PATTERN = re.compile(r"已经签|已签到|重复签|already\s*signed", re.I)


class ConfigError(ValueError):
    """COOKIE_QUARK 缺失或格式不正确。"""


class QuarkAPIError(RuntimeError):
    """夸克接口无法完成签到操作。"""


def send(title: str, message: str) -> None:
    """输出签到结果；配置了 Server 酱时同时推送。"""

    sendkey = os.getenv("SENDKEY") or os.getenv("SERVERCHAN_SENDKEY")
    if sendkey:
        try:
            from push_serverchan import send_serverchan

            if send_serverchan(title, message, sendkey):
                print(f"{title}:\n{message}")
                return
        except Exception as exc:  # 推送失败不能影响签到结果
            print(f"⚠️ 推送异常，回退到控制台输出：{exc}")
    print(f"{title}:\n{message}")


def split_account_entries(raw_value: str | None) -> list[str]:
    """把 COOKIE_QUARK 拆成多个账号条目，忽略空行。"""

    if not raw_value or not raw_value.strip():
        raise ConfigError("未配置 COOKIE_QUARK，或变量内容为空")

    entries = [entry.strip() for entry in re.split(r"\r?\n|&&", raw_value)]
    entries = [entry for entry in entries if entry]
    if not entries:
        raise ConfigError("COOKIE_QUARK 中没有可用的账号配置")
    return entries


def extract_params(url: str) -> dict[str, str]:
    """从抓包 URL 中提取 kps/sign/vcode。

    夸克凭证里可能包含字面量 ``+``，而 ``parse_qs`` 会按
    ``application/x-www-form-urlencoded`` 语义把 ``+`` 当空格，导致新版
    抓包 URL 解析出的凭证失效。这里自行切分 query，只做百分号解码。
    """

    query: dict[str, str] = {}
    for part in urlparse(url.strip()).query.split("&"):
        if not part:
            continue
        key, separator, value = part.partition("=")
        if not separator:
            value = ""
        key = unquote(key)
        if key not in query:  # 同名参数取第一个，与浏览器行为一致
            query[key] = unquote(value)

    return {name: query.get(name, "") for name in REQUIRED_PARAMS}


def parse_account(entry: str, index: int) -> dict[str, str]:
    """解析并校验单个账号条目。"""

    account: dict[str, str] = {}
    for field in entry.split(";"):
        field = field.strip()
        if not field:
            continue
        if "=" not in field:
            raise ConfigError(f"第 {index} 个账号存在无效字段：{field}")
        key, value = field.split("=", 1)
        key = key.strip()
        if not key:
            raise ConfigError(f"第 {index} 个账号存在空字段名")
        account[key] = value.strip()

    if "url" in account:
        for key, value in extract_params(account["url"]).items():
            account.setdefault(key, value)

    missing = [key for key in REQUIRED_PARAMS if not account.get(key)]
    if missing:
        raise ConfigError(f"第 {index} 个账号缺少必要参数：{', '.join(missing)}")

    account.setdefault("user", f"账号{index}")
    return account


def _api_error_message(payload: dict, fallback: str) -> str:
    message = payload.get("message") or payload.get("msg")
    code = payload.get("code")
    if message:
        return str(message)
    if code is not None:
        return f"{fallback}（code={code}）"
    return fallback


class Quark:
    """夸克移动端成长接口的最小封装。"""

    def __init__(
        self,
        account: dict[str, str],
        session: requests.Session | None = None,
        timeout: int = DEFAULT_TIMEOUT,
        dry_run: bool = False,
    ) -> None:
        self.account = account
        self.session = session or requests.Session()
        self.timeout = timeout
        self.dry_run = dry_run

    @staticmethod
    def convert_bytes(value: int | float) -> str:
        units = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
        size = float(value)
        unit_index = 0
        while size >= 1024 and unit_index < len(units) - 1:
            size /= 1024
            unit_index += 1
        return f"{size:.2f} {units[unit_index]}"

    def _params(self) -> dict[str, str]:
        return {
            "pr": "ucpro",
            "fr": "android",
            **{key: self.account[key] for key in REQUIRED_PARAMS},
        }

    def _request(self, method: str, url: str, **kwargs) -> dict:
        stage = "查询签到状态" if method == "GET" else "提交签到"
        attempts = MAX_GET_ATTEMPTS if method == "GET" else 1

        for attempt in range(1, attempts + 1):
            started = time.monotonic()
            try:
                response = self.session.request(
                    method, url, timeout=self.timeout, **kwargs
                )
                response.raise_for_status()
                payload = response.json()
            except (requests.Timeout, requests.ConnectionError) as exc:
                elapsed = time.monotonic() - started
                print(
                    f"⚠️ {stage}第 {attempt}/{attempts} 次网络失败："
                    f"{type(exc).__name__}（{elapsed:.1f}s）"
                )
                if attempt >= attempts:
                    raise QuarkAPIError(
                        f"{stage}网络失败（{type(exc).__name__}）"
                    ) from exc
                time.sleep(2 ** (attempt - 1) + random.uniform(0, 1))
                continue
            except requests.RequestException as exc:
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if attempt < attempts and status in RETRYABLE_STATUS:
                    print(f"⚠️ {stage}返回 HTTP {status}，第 {attempt} 次重试")
                    time.sleep(2 ** (attempt - 1) + random.uniform(0, 1))
                    continue
                raise QuarkAPIError(f"{stage}请求失败（HTTP {status or 'unknown'}）") from exc
            except ValueError as exc:  # response.json() 解析失败
                raise QuarkAPIError(f"{stage}返回了无法解析的数据") from exc

            if not isinstance(payload, dict):
                raise QuarkAPIError(f"{stage}返回格式异常")
            return payload

        raise QuarkAPIError(f"{stage}重试次数已用尽")

    def get_growth_info(self) -> dict:
        payload = self._request("GET", INFO_URL, params=self._params())
        data = payload.get("data")
        if not isinstance(data, dict):
            raise QuarkAPIError(_api_error_message(payload, "获取成长信息失败"))
        return data

    def get_growth_sign(self) -> int | float | None:
        """提交签到；返回奖励字节数，接口提示“今天已签过”时返回 None。"""

        payload = self._request(
            "POST", SIGN_URL, params=self._params(), json={"sign_cyclic": True}
        )
        data = payload.get("data")
        if isinstance(data, dict) and "sign_daily_reward" in data:
            return data["sign_daily_reward"]

        message = _api_error_message(payload, "签到失败")
        # 接口幂等：并发/重复调用时可能直接返回“已经签到”，这同样是成功
        if ALREADY_SIGNED_PATTERN.search(message):
            print(f"ℹ️ 接口提示：{message}")
            return None
        raise QuarkAPIError(message)

    def do_sign(self) -> str:
        growth_info = self.get_growth_info()
        cap_sign = growth_info.get("cap_sign")
        if not isinstance(cap_sign, dict):
            raise QuarkAPIError("成长信息中缺少 cap_sign 字段")

        user = self.account["user"]
        vip_label = "88VIP" if growth_info.get("88VIP") else "普通用户"
        composition = growth_info.get("cap_composition") or {}
        progress = cap_sign.get("sign_progress", "?")
        target = cap_sign.get("sign_target", "?")

        lines = [
            f"🙍🏻‍♂️ {vip_label} {user}",
            f"💾 网盘总容量：{self.convert_bytes(growth_info.get('total_capacity', 0))}，"
            f"签到累计容量：{self.convert_bytes(composition.get('sign_reward', 0))}",
        ]

        if cap_sign.get("sign_daily"):
            lines.append(
                f"✅ 今日已签到 +{self.convert_bytes(cap_sign.get('sign_daily_reward', 0))}，"
                f"连签进度（{progress}/{target}）"
            )
            return "\n".join(lines)

        if self.dry_run:
            lines.append("🧪 DRY_RUN：凭证有效，今日尚未签到（已跳过实际签到）")
            return "\n".join(lines)

        try:
            reward = self.get_growth_sign()
        except QuarkAPIError as exc:
            if "网络失败" not in str(exc):
                raise
            # POST 已经发出但结果未知，复查一次状态，避免重复签到或误报失败
            print("⚠️ 签到结果不确定，重新查询签到状态")
            verified = self.get_growth_info().get("cap_sign") or {}
            if not verified.get("sign_daily"):
                raise QuarkAPIError("未确认签到成功，等待下一次定时补签") from exc
            lines.append(
                f"✅ 复查确认今日已签到 +{self.convert_bytes(verified.get('sign_daily_reward', 0))}"
            )
            return "\n".join(lines)

        next_progress = progress + 1 if isinstance(progress, int) else "?"
        if reward is None:
            lines.append(f"✅ 今日已签到（接口提示重复签到），连签进度（{progress}/{target}）")
        else:
            lines.append(
                f"✅ 签到成功 +{self.convert_bytes(reward)}，"
                f"连签进度（{next_progress}/{target}）"
            )
        return "\n".join(lines)


def main(
    cookie_value: str | None = None,
    quark_factory: Callable[[dict[str, str]], Quark] | None = None,
) -> int:
    """依次执行所有账号，返回进程退出码（0 全部成功 / 1 有失败 / 2 配置错误）。"""

    print("----------夸克网盘开始签到----------", flush=True)
    if cookie_value is None:
        cookie_value = os.getenv("COOKIE_QUARK")

    dry_run = os.getenv("DRY_RUN", "").lower() in ("1", "true", "yes")
    if quark_factory is None:
        quark_factory = lambda account: Quark(account, dry_run=dry_run)  # noqa: E731

    try:
        entries = split_account_entries(cookie_value)
    except ConfigError as exc:
        print(f"❌ {exc}")
        send("夸克自动签到", f"❌ {exc}")
        return 2

    print(f"✅ 检测到共 {len(entries)} 个夸克账号\n", flush=True)

    results: list[str] = []
    failures = 0

    for index, entry in enumerate(entries, start=1):
        try:
            account = parse_account(entry, index)
            results.append(quark_factory(account).do_sign())
        except (ConfigError, QuarkAPIError, KeyError, TypeError, ValueError) as exc:
            failures += 1
            results.append(f"🙍🏻‍♂️ 第 {index} 个账号\n❌ {exc}")
        except Exception as exc:  # 兜底：保证后续账号继续执行
            failures += 1
            results.append(f"🙍🏻‍♂️ 第 {index} 个账号\n❌ 未知错误：{type(exc).__name__}: {exc}")

    succeeded = len(entries) - failures
    summary = "\n\n".join(results)
    print("\n" + summary + "\n")
    send("夸克自动签到", summary)
    print(
        f"----------执行完毕：成功 {succeeded}，失败 {failures}----------",
        flush=True,
    )
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
