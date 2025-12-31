import os
import urllib.request
import urllib.parse
import json
import datetime


def _today_str():
    return datetime.datetime.utcnow().date().isoformat()


def send_serverchan(title: str, message: str, sendkey: str = None) -> bool:
    """通过 Server 酱（SCT）发送推送，并支持每日限频。

    行为：
    - 优先使用传入的 `sendkey`，否则读取环境变量 `SENDKEY` 或 `SERVERCHAN_SENDKEY`。
    - 默认启用每日一次推送限制：若当天已经推送过，则跳过实际发送并返回 True（视为已处理）。
      可通过环境变量 `PUSH_ONCE_DAILY=0` 关闭此限制。
    - 可通过环境变量 `PUSH_FORCE=1` 强制发送并跳过限频检查。
    """
    sendkey = sendkey or os.getenv("SENDKEY") or os.getenv("SERVERCHAN_SENDKEY")
    if not sendkey:
        print("ServerChan: no sendkey configured")
        return False

    # 是否启用每日一次限制（默认开启）
    once_daily = os.getenv("PUSH_ONCE_DAILY", "1").lower() not in ("0", "false", "no")
    force_push = os.getenv("PUSH_FORCE", os.getenv("SERVERCHAN_FORCE_PUSH", "0")).lower() in ("1", "true", "yes")

    last_file = os.path.join(os.path.dirname(__file__), ".last_push_date")
    today = _today_str()

    if once_daily and not force_push:
        try:
            if os.path.exists(last_file):
                with open(last_file, "r", encoding="utf-8") as f:
                    last = f.read().strip()
                if last == today:
                    print("ServerChan: 今日已推送，跳过本次发送。")
                    return True
        except Exception as e:
            print(f"读取推送记录文件失败（忽略并继续）: {e}")

    desp = message.replace("\n", "\n\n")
    url = f"https://sctapi.ftqq.com/{sendkey}.send"
    data = {"title": title, "desp": desp}
    data_bytes = urllib.parse.urlencode(data).encode("utf-8")

    req = urllib.request.Request(url, data=data_bytes, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp_text = resp.read().decode("utf-8", errors="ignore")
            print(f"ServerChan response text: {resp_text}")
            try:
                body = json.loads(resp_text)
            except Exception:
                body = resp_text
            status = getattr(resp, 'status', None) or (resp.getcode() if hasattr(resp, 'getcode') else None)
            print(f"ServerChan push status: {status}, body: {body}")

            success = False
            if isinstance(body, dict):
                if body.get("code") == 0 or body.get("errno") == 0 or body.get("error") == 0:
                    success = True
                elif "data" in body:
                    success = True
                else:
                    msg = (body.get("message") or body.get("errmsg") or "").lower()
                    if msg in ("ok", "success", "success."):
                        success = True
                    if body.get("success") in (True, "true", "ok", "success"):
                        success = True
            else:
                if status and 200 <= int(status) < 300:
                    success = True

            if success:
                # 写入当天记录，忽略写入错误
                try:
                    with open(last_file, "w", encoding="utf-8") as f:
                        f.write(today)
                except Exception as e:
                    print(f"写入推送记录失败（忽略）: {e}")
                return True

            return False
    except Exception as e:
        print(f"ServerChan 推送异常: {e}")
        return False
