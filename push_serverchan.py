"""Server 酱（ServerChan）推送的最小实现。

同时兼容两代 SendKey：

* Server 酱 Turbo：``SCT...``，推送到 ``https://sct.ftqq.com/{key}.send``
* Server 酱³：``sctp{uid}t...``，推送到 ``https://{uid}.push.ft07.com/send/{key}.send``

只依赖标准库，避免在 GitHub Actions 里多装一个包。
"""

from __future__ import annotations

import datetime
import json
import os
import re
import urllib.parse
import urllib.request

TURBO_ENDPOINT = "https://sct.ftqq.com/{sendkey}.send"
SCTP_ENDPOINT = "https://{uid}.push.ft07.com/send/{sendkey}.send"
SCTP_UID_PATTERN = re.compile(r"^sctp(\d+)t")
DAILY_MARKER = ".last_push_date"


def _today_str() -> str:
    """返回北京时间的日期字符串（GitHub runner 默认是 UTC）。"""

    try:
        from zoneinfo import ZoneInfo

        now = datetime.datetime.now(ZoneInfo("Asia/Shanghai"))
    except Exception:  # 极老版本或缺少 tzdata 时退化为固定 UTC+8
        now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
    return now.date().isoformat()


def resolve_endpoint(sendkey: str) -> str | None:
    """根据 SendKey 前缀选择推送地址。"""

    sendkey = sendkey.strip()
    if match := SCTP_UID_PATTERN.match(sendkey):
        return SCTP_ENDPOINT.format(uid=match.group(1), sendkey=sendkey)
    if sendkey.startswith("SCT"):
        return TURBO_ENDPOINT.format(sendkey=sendkey)
    # 未知前缀时不猜，交给调用方回退到控制台
    return None


def _env_flag(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


def send_serverchan(title: str, message: str, sendkey: str | None = None) -> bool:
    """通过 Server 酱推送消息，成功返回 True。

    环境变量：
    * ``SENDKEY`` / ``SERVERCHAN_SENDKEY``：SendKey，优先级低于入参。
    * ``PUSH_ONCE_DAILY=1``：启用每日一次限制（默认关闭，是否跳过重复推送
      由 workflow 的日期缓存负责）。
    * ``PUSH_FORCE=1``：忽略每日限制强制推送。
    * ``PUSH_TIMEOUT``：HTTP 超时秒数，默认 10。
    """

    sendkey = (sendkey or os.getenv("SENDKEY") or os.getenv("SERVERCHAN_SENDKEY") or "").strip()
    if not sendkey:
        print("ServerChan: 未配置 SendKey")
        return False

    endpoint = resolve_endpoint(sendkey)
    if endpoint is None:
        print("ServerChan: SendKey 格式无法识别（应以 SCT 或 sctp 开头）")
        return False

    once_daily = _env_flag("PUSH_ONCE_DAILY")
    force_push = _env_flag("PUSH_FORCE") or _env_flag("SERVERCHAN_FORCE_PUSH")
    marker_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), DAILY_MARKER)
    today = _today_str()

    if once_daily and not force_push:
        try:
            if os.path.exists(marker_path):
                with open(marker_path, "r", encoding="utf-8") as handle:
                    if handle.read().strip() == today:
                        print("ServerChan: 今日已推送，跳过本次发送。")
                        return True
        except OSError as exc:
            print(f"ServerChan: 读取推送记录失败（忽略并继续）：{exc}")

    payload = urllib.parse.urlencode(
        {"title": title, "desp": message.replace("\n", "\n\n")}
    ).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Quark_Auto_Check_In/2 (+https://github.com/Liu8Can/Quark_Auto_Check_In)",
        },
    )

    try:
        timeout = float(os.getenv("PUSH_TIMEOUT", "10"))
    except ValueError:
        timeout = 10.0

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body_text = response.read().decode("utf-8", "ignore")
            status = response.status
    except Exception as exc:
        print(f"ServerChan: 推送异常：{exc}")
        return False

    try:
        body = json.loads(body_text)
    except ValueError:
        body = body_text

    success = _is_success(body, status)
    print(f"ServerChan: HTTP {status}，{'推送成功' if success else '推送失败'}")
    if not success:
        print(f"ServerChan: 响应内容 {body_text[:300]}")

    if success and once_daily:
        try:
            with open(marker_path, "w", encoding="utf-8") as handle:
                handle.write(today)
        except OSError as exc:
            print(f"ServerChan: 写入推送记录失败（忽略）：{exc}")

    return success


def _is_success(body, status: int) -> bool:
    """兼容 Turbo 的 ``{"code":0}`` 与 v3 的 ``{"code":0,"data":{...}}``。"""

    if isinstance(body, dict):
        if body.get("code") in (0, "0"):
            return True
        for key in ("errno", "error"):
            if body.get(key) in (0, "0"):
                return True
        if isinstance(body.get("data"), dict):
            return True
        if body.get("success") in (True, "true", "ok", "success"):
            return True
        message = str(body.get("message") or body.get("errmsg") or "").strip().lower()
        return message in ("ok", "success", "success.")
    return 200 <= status < 300


if __name__ == "__main__":
    import sys

    sys.exit(0 if send_serverchan("测试推送", "来自 Quark_Auto_Check_In 的测试消息") else 1)
