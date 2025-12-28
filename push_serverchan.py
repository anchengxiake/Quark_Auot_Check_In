import os
import urllib.request
import urllib.parse
import json


def send_serverchan(title: str, message: str, sendkey: str = None) -> bool:
    """通过 Server 酱（SCT）发送推送（仅使用标准库）。

    优先使用传入的 sendkey，若没有则尝试从环境变量中读取 `SENDKEY` 或 `SERVERCHAN_SENDKEY`。
    返回 True 表示请求已发送并且 API 返回成功，否则返回 False。
    """
    sendkey = sendkey or os.getenv("SENDKEY") or os.getenv("SERVERCHAN_SENDKEY")
    if not sendkey:
        print("ServerChan: no sendkey configured")
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
            # 打印完整返回，便于调试不同版本的 Server 酱
            print(f"ServerChan response text: {resp_text}")
            try:
                body = json.loads(resp_text)
            except Exception:
                body = resp_text
            # 尝试获取状态码（兼容不同 Python 版本的 HTTPResponse 接口）
            status = getattr(resp, 'status', None) or (resp.getcode() if hasattr(resp, 'getcode') else None)
            print(f"ServerChan push status: {status}, body: {body}")

            # 根据返回内容判断是否成功（支持多种 Server 酱/第三方实现）
            if isinstance(body, dict):
                # 常见成功标志： code/errno/error 为 0
                if body.get("code") == 0 or body.get("errno") == 0 or body.get("error") == 0:
                    return True
                # 部分实现返回 data 键（即使为空），视为请求已被接受
                if "data" in body:
                    return True
                # 检查常见的 message/errmsg 字段
                msg = (body.get("message") or body.get("errmsg") or "").lower()
                if msg in ("ok", "success", "success."):
                    return True
                # 检查 success 字段
                if body.get("success") in (True, "true", "ok", "success"):
                    return True

                # 以上条件都不满足则视为失败
                return False

            # 非 JSON 返回时，只要是 2xx 状态码就认为已发送
            if status and 200 <= int(status) < 300:
                return True

            return False
    except Exception as e:
        print(f"ServerChan 推送异常: {e}")
        return False
