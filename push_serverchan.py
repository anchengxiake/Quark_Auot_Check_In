import os
import urllib.request
import urllib.parse
import json


def send_serverchan(title: str, message: str, sendkey: str = None) -> bool:
    """通过 Server 酱（SCT）发送推送（仅使用标准库）。

    优先使用传入的 sendkey，若没有则尝试从环境变量中读取 `SENDKEY` 或 `SERVERCHAN_SENDKEY`。
    返回 True 表示请求已发送（服务器返回响应），False 表示未发送或发生异常。
    """
    sendkey = sendkey or os.getenv("SENDKEY") or os.getenv("SERVERCHAN_SENDKEY")
    if not sendkey:
        return False

    desp = message.replace("\n", "\n\n")
    url = f"https://sctapi.ftqq.com/{sendkey}.send"
    data = {"title": title, "desp": desp}
    data_bytes = urllib.parse.urlencode(data).encode("utf-8")

    req = urllib.request.Request(url, data=data_bytes, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp_text = resp.read().decode("utf-8", errors="ignore")
            try:
                body = json.loads(resp_text)
            except Exception:
                body = resp_text
            print(f"ServerChan push status: {resp.status}, body: {body}")
            return True
    except Exception as e:
        print(f"ServerChan 推送异常: {e}")
        return False
