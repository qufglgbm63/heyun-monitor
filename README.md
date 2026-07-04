# 魔方财务云服务器监控（Python）

参照 [loqwe/heyun-zjmf-worker-monitor](https://github.com/loqwe/heyun-zjmf-worker-monitor)
用 Python 重写：检测服务器关机/异常时自动开机或硬重启；token 失效
（HTTP 401/403/405 或返回“未登录”）会**自动重新登录**继续监控。

状态判定分三种：

- **在线**：正常，什么都不做；
- **关机**：按配置执行动作（默认开机 `on`，也可设成硬重启）；
- **状态未知**（接口返回识别不出来）：**一律硬重启**，把机器从不确定的状态里拽回来。

关机/未知都要连续命中 `SUSPECT_THRESHOLD` 次才会动手，避免偶发抖动误触发。

## 先看这里：两种用法，二选一

| | 用法一：本地运行 | 用法二：部署到 Azure |
|---|---|---|
| 适合谁 | 自己有电脑/服务器能一直开着 | 想放云端 24 小时托管，不想自己开机器 |
| 需要什么 | **只要装了 Python 就行** | 需要 Azure 账号 + 微软的命令行工具 |
| 有没有网页 | **有**，本地 `http://localhost:8000` | 有，云端网址 |
| 怎么跑 | `python heyun.py` | 见下面「用法二」 |

两种用法都带网页界面。如果你只是想让服务器掉线自动开机，**用法一就够了，不用碰 Azure**。

---

## 用法一：本地运行（最简单，自带网页）

你的电脑只要装了 Python 3.10+ 就能跑，**不需要安装任何额外的库，也不需要 Azure、不需要 func 工具、不需要虚拟环境。**

1. 打开 `heyun.py`，改最上面这几行：

   ```python
   ACCOUNT = "你的账号(手机号或邮箱)"
   API_KEY = "你的API密钥"
   # 想固定监控某几台就填 ID，留空 [] 则自动监控账户下全部服务器
   SERVER_IDS = ["4075", "4076"]
   ADMIN_PASSWORD = "admin"   # 管理后台密码，建议改掉
   ```

2. 在这个文件夹里打开命令行，运行：

   ```
   python heyun.py
   ```

3. 程序会一边后台自动监控（发现关机就自动开机），一边开一个本地网页。
   浏览器打开：

   - 状态页：`http://localhost:8000/`
   - 管理后台：`http://localhost:8000/manage`（用上面的 `ADMIN_PASSWORD` 登录）

   窗口一直开着就会每隔一段时间检测一次。想只测一次看看效果、不开网页，
   就用 `python heyun.py --once`。

就这么简单。下面的「用法二」跟本地运行没关系，不看也行。

---

## 用法二：部署到 Azure Functions（想要网页版才需要）

这套是放到微软 Azure 云上 24 小时自动跑，还带一个网页状态页和管理后台。
**只有走这条路才需要装下面这些微软的工具**，本地运行（用法一）完全用不到。

需要准备：

- 一个 Azure 账号（订阅）。
- [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli)（命令 `az`）。
- [Azure Functions Core Tools v4](https://learn.microsoft.com/azure/azure-functions/functions-run-local)（命令 `func`，用来把代码传到 Azure）。

### 直接部署到云端

```
az login

# 1. 创建资源（名字要全球唯一，自己换）
az group create -n heyun-rg -l eastasia
az storage account create -n heyunstore123 -g heyun-rg -l eastasia --sku Standard_LRS
az functionapp create -n heyunjiankong -g heyun-rg `
  --storage-account heyunstore123 --consumption-plan-location eastasia `
  --runtime python --runtime-version 3.11 --functions-version 4 --os-type Linux

# 2. 填入你的账号密钥等配置
az functionapp config appsettings set -n heyunjiankong -g heyun-rg --settings `
  ADMIN_TOKEN="你的后台密码" `
  ZJMF_ACCOUNT="你的账号" `
  ZJMF_API_KEY="你的API密钥" `
  ZJMF_ACTION="on" `
  ZJMF_CRON="0 */10 * * * *"

# 3. 上传代码
func azure functionapp publish heyunjiankong
```

部署完访问：

- 状态页：`https://heyunjiankong.azurewebsites.net/`
- 管理后台：`https://heyunjiankong.azurewebsites.net/manage`（用 `ADMIN_TOKEN` 登录）

> 核心逻辑只用 Python 标准库（`urllib`），不依赖 `requests`，即使远程构建异常也不会因
> 缺包 503。`azure-storage-blob` 是**可选**的，只用来持久化状态；装不上会自动回退到本地文件。

### 状态存哪儿（Serverless 关键）

Serverless 实例随时被回收、本地文件系统随时清空，所以状态不能只写本地文件。程序会自动挑后端：

1. 设了 `MONITOR_DATA_FILE` → 用这个本地文件（本地运行走这条）；
2. 有存储连接串（Azure 上的 `AzureWebJobsStorage` 天然就有）→ 存到 **Azure Blob**，实例回收也不丢；
3. 都没有 → 回退到 `$HOME/data/monitor_data.json`。

Blob 相关可选变量：`MONITOR_BLOB_CONNECTION`（不填则复用 `AzureWebJobsStorage`）、
`MONITOR_BLOB_CONTAINER`（默认 `monitor`）、`MONITOR_BLOB_NAME`（默认 `monitor_data.json`）。

### （可选）在自己电脑上预览 Azure 网页版

如果你想部署前先在本机看看网页长什么样，才需要下面这几步（装了 `func` 工具才行）；
不想折腾就跳过，直接部署到云端即可。

```
copy local.settings.json.example local.settings.json
# 编辑 local.settings.json，填 ADMIN_TOKEN / ZJMF_ACCOUNT / ZJMF_API_KEY

func start
```

然后浏览器打开 `http://localhost:7071/` 看状态页，`http://localhost:7071/manage` 看管理后台。

### Azure 环境变量说明

| 变量 | 说明 | 默认 |
|---|---|---|
| `ADMIN_TOKEN` | 管理后台登录密码（必填） | admin |
| `ZJMF_BASE_URL` | 魔方财务 API 地址 | https://www.heyunidc.cn |
| `ZJMF_ACCOUNT` | 账号（手机号/邮箱） | - |
| `ZJMF_API_KEY` | API 密钥 | - |
| `ZJMF_ACTION` | `on` 开机 / `hard_reboot` 硬重启 | on |
| `ZJMF_CRON` | 定时表达式（NCRONTAB，6 段，注意不是 5 段） | 0 */10 * * * * |
| `ZJMF_SUSPECT_THRESHOLD` | 连续异常几次判宕机 | 3 |
| `ZJMF_REBOOT_COOLDOWN` | 动作冷却（秒） | 600 |
| `ZJMF_RECOVER_TIMEOUT` | 恢复超时（秒） | 300 |
| `ZJMF_REBOOT_LIMIT` | 时间窗内动作次数上限（0=不限） | 5 |
| `ZJMF_REBOOT_LIMIT_WINDOW` | `hour` / `day` | hour |
| `ZJMF_DRY_RUN` | `true` 只检测不执行 | false |
| `ZJMF_WEBHOOK_TYPE` | `custom` / `pushplus` | custom |
| `ZJMF_WEBHOOK_URL` | 通知地址或 PushPlus Token | - |

> 这些设置大部分也能在网页「管理后台」里在线改，改完会存进上面选中的存储后端。

---

## 用法三：部署到其他 Serverless（GCP / Vercel / AWS）

`web_handler.py` 里导出了标准的 WSGI 可调用对象（`wsgi_app`，也叫 `application`），
多数平台都能直接挂：

- **Google Cloud Functions**：`functions-framework` 支持 WSGI app；
- **Vercel（Python）**：把 `application` 暴露成入口即可；
- **AWS Lambda**：套一层 `apig-wsgi` / `aws-wsgi` 适配器。

定时检测这块，用平台自带的定时器（Cloud Scheduler / Vercel Cron / EventBridge）
定时 `POST /api/admin/run`（带 `X-Admin-Token`），或直接调用 `web_handler.run_monitor_once()`。

状态持久化设 `MONITOR_BLOB_CONNECTION` 指向一个 Azure 存储账户即可跨平台复用；其他对象存储
可按 `state_store.py` 里 `_BlobStore` 的样子照葫芦画瓢加一个后端。

---

## 各文件是干嘛的

```
heyun.py             本地运行版（用法一）：后台监控 + 本地网页
monitor_core.py      核心逻辑：API 调用 + 监控引擎（两种用法共用）
web_handler.py       网页/接口的处理逻辑（本地版和 Azure 版共用）
webui.py             网页界面 HTML（状态页 + 管理后台）
function_app.py      Azure 入口：定时任务 + 网页（用法二才用到）
state_store.py       配置和状态的读写（本地文件 / Azure Blob 自动切换）
host.json            Azure Functions 配置
requirements.txt     依赖清单（azure-functions + 可选的 azure-storage-blob）
local.settings.json.example  Azure 本地预览用的配置样例
```

## 安全提示

- 别把真实账号密钥提交到公开仓库；本地运行建议改 `heyun.py`，或用环境变量
  `ZJMF_ACCOUNT` / `ZJMF_API_KEY`。
- `ADMIN_TOKEN` 是管理后台的密码，务必设强一点。
- `local.settings.json`、`monitor_data.json` 已在 `.gitignore` 里，不会被提交。
