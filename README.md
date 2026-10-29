# ⭐️ 夸克网盘自动签到

![GitHub stars](https://img.shields.io/github/stars/Liu8Can/Quark_Auto_Check_In) ![GitHub forks](https://img.shields.io/github/forks/Liu8Can/Quark_Auto_Check_In) ![License](https://img.shields.io/github/license/Liu8Can/Quark_Auto_Check_In) ![Last Commit](https://img.shields.io/github/last-commit/Liu8Can/Quark_Auto_Check_In) ![GitHub Actions](https://github.com/Liu8Can/Quark_Auto_Check_In/actions/workflows/quark_signin.yml/badge.svg)

🎉 通过 GitHub Actions 每天自动完成夸克网盘签到，领取签到奖励空间。

> 🛑 **警告**：本项目遵循 [MIT 协议](https://opensource.org/licenses/MIT)。任何对项目的修改和发布必须保留原作者署名。
>
> **本项目禁止传播，有缘人自会看到。给个星标再 fork 吧，求求了**
>
> 本仓库严厉谴责 [2pacJay/Quark_Auot_Check_In](https://github.com/2pacJay/Quark_Auot_Check_In) 仓库 **抹除原作者署名权的行为**，该行为严重违反 MIT 协议，侵害开源精神！

---

## 🚀 功能

- **每日自动签到**：北京时间约 09:00 执行，13:00 再进行一次失败兜底。
- **两种账号格式**：既支持老的 `kps / sign / vcode` 手填，也支持直接粘贴新版抓包的完整 URL（脚本自动提取参数）。
- **多账号隔离**：按账号逐个执行，某个账号失败不会影响其他账号；只要有账号失败，工作流整体返回失败，从而保留 13:00 的补签机会。
- **当日去重**：所有账号成功后写入「当天日期」的 Actions 缓存，重复触发会直接跳过，不会重复签到。
- **推送可选**：配置 Server 酱即可在签到后收到微信推送，未配置则只打印控制台日志。
- **凭证体检**：手动触发时可选 `dry_run`，只校验凭证与签到状态、不真正提交签到。
- **保活**：每月在独立的 `heartbeat` 孤儿分支生成一条空提交，不污染 `main` 历史。

**致谢**：本项目基于 [BNDou/Auto_Check_In](https://github.com/BNDou/Auto_Check_In) 中夸克网盘签到子功能修改而来，感谢 [Spectrollay](https://github.com/Spectrollay) 与 [haozihong](https://github.com/haozihong) 对工作流的优化。

---

## 📋 使用指南

### 1️⃣ Fork 项目

点击右上角的 `Fork` 按钮，将本项目复制到自己的 GitHub 仓库。

### 2️⃣ 获取签到参数

推荐使用 **MuMu 模拟器 + Root + ProxyPin** 抓包（新版夸克 App 对用户证书校验较严，实体机通常需要 Root 才能解密 HTTPS）：

1. MuMu 设置中开启 Root，安装夸克 App 与 [ProxyPin](https://github.com/wanghongenpin/proxypin)。
2. 把 ProxyPin 的 CA 证书安装为 Android **系统证书**。
3. 打开夸克网盘的签到页，在 ProxyPin 中筛选域名 `drive-m.quark.cn`。
4. 找到类似 `https://drive-m.quark.cn/1/clouddrive/act/growth/reward?...` 的请求，**原样复制完整 URL**（不要手动改动其中的 `+`、`=`、`%xx`）。
5. 按下面任一格式整理账号信息：

   ```text
   # 推荐：直接贴完整 URL
   user=张三; url=https://drive-m.quark.cn/1/clouddrive/act/growth/reward?...;

   # 兼容：手动填参数
   user=张三; kps=abcdefg; sign=hijklmn; vcode=111111111;
   ```

   > `user` 只是显示用昵称，可随意填写。多个账户用**换行**或 `&&` 分隔，空行会被忽略。

### 3️⃣ 添加 GitHub Secret

进入 **Settings → Secrets and variables → Actions → New repository secret**：

| Secret 名称 | 是否必填 | 说明 |
| --- | --- | --- |
| `COOKIE_QUARK` | 必填 | 上一步整理好的账号信息，多账号用换行或 `&&` 分隔 |
| `SENDKEY` | 可选 | Server 酱 SendKey，支持 Turbo（`SCT` 开头）与 Server酱³（`sctp` 开头） |
| `SERVERCHAN_SENDKEY` | 可选 | 同上，`SENDKEY` 未配置时的备用名 |

### 4️⃣ 启用 GitHub Actions

1. 打开 **Actions**，若顶部有黄色提示条，点击 **I understand my workflows, go ahead and enable them**。
2. 签到工作流只使用 `contents: read` 权限，**不需要**把仓库的 Workflow permissions 改成读写；只有保活工作流需要 `contents: write`。
3. 工作流会在北京时间每天约 09:00 自动运行。

### 5️⃣ 手动测试

**Actions → 夸克网盘每日签到 → Run workflow**：

- 直接运行：真实执行签到。
- 勾选 `dry_run`：只校验凭证与签到状态，不提交签到，也不会占用当天的成功标记。

---

## 🔁 执行与重试逻辑

1. 按北京时间生成当天日期，作为缓存 key：`quark-signed-<YYYY-MM-DD>`。
2. 缓存命中说明今天所有账号都已成功，直接跳过；否则逐个处理 `COOKIE_QUARK` 中的账号。
3. 全部账号成功 → 写入当天成功标记 → 13:00 的那次任务直接跳过。
4. 任一账号配置错误、凭证失效或接口异常 → 工作流返回失败且**不写标记** → 13:00 自动重试一次。

退出码约定（`python checkIn_Quark.py`）：

| 退出码 | 含义 |
| --- | --- |
| `0` | 全部账号成功（含「今日已签到」） |
| `1` | 至少一个账号失败，其余账号已尽力执行 |
| `2` | `COOKIE_QUARK` 未配置或整体为空 |

---

## 📨 可选：Server 酱推送

脚本内已内置最小实现（[push_serverchan.py](push_serverchan.py)），只依赖标准库：

- `SCT...` 开头的 Turbo key → `https://sct.ftqq.com/{key}.send`
- `sctp{uid}t...` 开头的 Server酱³ key → `https://{uid}.push.ft07.com/send/{key}.send`

本地测试：

```bash
export SENDKEY='SCT你的SendKey'
python push_serverchan.py
```

可选环境变量：

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `PUSH_ONCE_DAILY` | `0` | 设为 `1` 时每天只推送一次（以 `.last_push_date` 记录） |
| `PUSH_FORCE` | `0` | 设为 `1` 时忽略上面的每日限制 |
| `PUSH_TIMEOUT` | `10` | 推送请求超时秒数 |

推送失败只会回退到控制台日志，不影响签到结果。

---

## ⚙️ 环境变量

| 变量 | 说明 |
| --- | --- |
| `COOKIE_QUARK` | 账号信息，必填 |
| `DRY_RUN` | 设为 `1` 时只校验凭证，不提交签到 |
| `SENDKEY` / `SERVERCHAN_SENDKEY` | Server 酱推送 key，可选 |

---

## ❓ 常见问题

1. **提示「缺少必要参数」**
   - 检查每个账号是否都含 `kps`、`sign`、`vcode`，或完整 URL 是否确实带有这三个查询参数。
   - 注意 URL 里的 `+` 必须原样保留，脚本已按「只做百分号解码」的方式解析，不会把 `+` 当空格。
2. **提示「获取成长信息失败」或「凭证失效」**
   - 通常是抓到的参数已过期（有效期约两个月）或不完整，重新抓包并更新 `COOKIE_QUARK`。
   - 接口临时异常也会让工作流失败，但不会写入当日成功缓存，因此仍有 13:00 的第二次机会。
3. **单账号正常，多账号失败**
   - 确认账号之间用换行或 `&&` 分隔，每个账号都是一套完整参数；日志里会明确指出失败的是第几个账号。
4. **定时任务没有准点运行**
   - GitHub Actions 的 schedule 天然会有数分钟到数十分钟延迟，脚本还会额外随机延迟最多 60 秒（13:00 那轮再多等 2 分钟以错开抖动）。
5. **保活分支为什么每月被强制更新**
   - `heartbeat` 是专门的孤儿分支，每月只保留最新一条空提交，用于避免长期无活动的 Fork 被 GitHub 停用定时任务，不会改动 `main`。

---

## 🧪 本地开发

```bash
python -m pip install -r requirements.txt -r requirements-dev.txt
python -m unittest discover -s tests -v
```

CI（[ci.yml](.github/workflows/ci.yml)）会做语法检查、单元测试，并校验「未配置凭证时退出码为 2」。

---

## ⚠️ 注意事项

- 本项目仅供学习交流，请勿用于非法用途。
- 若夸克更新接口，通常只需调整 `checkIn_Quark.py`，工作流一般无需改动。
- 频繁手动触发可能被目标服务限制，请谨慎操作。
- 本项目基于 BNDou/Auto_Check_In 的夸克签到功能修改而来。

---

## 📜 免责声明

本项目为开源项目，作者不对任何因使用本项目产生的后果负责。

---

### 🛡️ 防盗声明

本项目严格遵守 MIT 协议，修改和分发时必须保留原作者署名及协议声明。
若发现违反行为，请通过以下方式联系：
📧 Email: [liucan01234@gmail.com](mailto:liucan01234@gmail.com)

---

🎉 **欢迎提交 PR 和 Star 支持项目发展！**
