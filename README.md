# 魔方财务云服务器监控（Python + 网页 + Azure Functions）

参照 [loqwe/heyun-zjmf-worker-monitor](https://github.com/loqwe/heyun-zjmf-worker-monitor)
的思路用 Python 重写：带**状态页**和**管理后台**的可视化监控，检测到服务器关机/异常时
自动开机或硬重启，token 失效（401/403/405/含“未登录”提示）会**自动重新登录**继续监控。

支持两种运行方式：

1. **本地独立运行**：`heyun.py`，改好配置直接 `python heyun.py` 长期跑。
2. **Azure Functions 部署**：定时触发器周期检测 + HTTP 触发器提供网页与 API，
   无需自建服务器，配置和状态保存在 Azure Blob 存储中。

## 目录结构

```
monitor_core.py            # 核心：API 客户端 + 监控引擎（5 状态机）
state_store.py             # 配置/状态持久化（Azure Blob，本地回退 JSON 文件）
webui.py                   # 状态页与管理后台 HTML
function_app.py            # Azure Functions 入口（Timer + HTTP）
heyun.py                   # 本地独立运行版
host.json                  # Functions 主机配置（routePrefix 置空以支持网页路由）
requirements.txt           # 依赖
local.settings.json.example  # 本地/云端环境变量样例
```

## 核心机制

- **自动重新登录**：任意接口返回 401/403/405，或响应正文含“未登录/请登录/登录失效”等
  提示时，自动调用登录接口刷新 JWT 并重试一次；JWT 超过约 100 分钟也会提前续期。
- **5 状态机**：`healthy → suspect → down → rebooting → recovering → healthy`
  - 首次异常进入 `suspect`，连续 `suspect_threshold` 次才确认 `down`，避免误判。
  - 确认 `down` 后执行动作（开机或硬重启），进入 `recovering` 等待恢复。
- **安全护栏**：动作冷却（`reboot_cooldown`）、单位时间动作次数上限（`reboot_limit`）、
  恢复超时重判（`recover_timeout`）、`dry_run` 只检测不执行。

## 方式一：本地运行

```bash
pip install requests
```

编辑 `heyun.py` 顶部的 `BASE_URL / ACCOUNT / API_KEY`，需要指定服务器时填 `SERVER_IDS`
（留空自动发现账户下全部服务器），然后：

```bash
python heyun.py          # 持续监控
python heyun.py --once   # 只跑一轮
```

## 方式二：部署到 Azure Functions

### 前置

- 一个 Azure 订阅、一个存储账户（用于 `AzureWebJobsStorage` 和保存配置）。
- 本机安装 [Azure Functions Core Tools v4](https://learn.microsoft.com/azure/azure-functions/functions-run-local)
  和 [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli)、Python 3.10+。

### 本地调试

```bash
copy local.settings.json.example local.settings.json   # Windows
# 编辑 local.settings.json，填入 ADMIN_TOKEN 和 ZJMF_ACCOUNT / ZJMF_API_KEY

python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

func start
```

启动后访问：

- 状态页：`http://localhost:7071/`
- 管理后台：`http://localhost:7071/admin`（用 `ADMIN_TOKEN` 登录）
- 状态 API：`http://localhost:7071/api/status`

> 本地若未连真实存储，配置会自动落到当前目录 `monitor_data.json`。

### 部署到云端

```bash
az login

# 创建资源（名称需全局唯一，自行替换）
az group create -n heyun-rg -l eastasia
az storage account create -n heyunstore123 -g heyun-rg -l eastasia --sku Standard_LRS
az functionapp create -n heyun-monitor-app -g heyun-rg \
  --storage-account heyunstore123 --consumption-plan-location eastasia \
  --runtime python --runtime-version 3.11 --functions-version 4 --os-type Linux

# 配置应用设置（等价于 local.settings.json 里的 Values）
az functionapp config appsettings set -n heyun-monitor-app -g heyun-rg --settings \
  ADMIN_TOKEN="你的后台密码" \
  ZJMF_ACCOUNT="你的账号" \
  ZJMF_API_KEY="你的API密钥" \
  ZJMF_ACTION="on" \
  ZJMF_CRON="0 */10 * * * *"

# 发布代码
func azure functionapp publish heyun-monitor-app
```

发布完成后：

- 状态页：`https://heyun-monitor-app.azurewebsites.net/`
- 管理后台：`https://heyun-monitor-app.azurewebsites.net/admin`

### 环境变量说明

| 变量 | 说明 | 默认 |
|---|---|---|
| `ADMIN_TOKEN` | 管理后台登录密码（必填） | admin |
| `ZJMF_BASE_URL` | 魔方财务 API 地址 | https://www.heyunidc.cn |
| `ZJMF_ACCOUNT` | 账号（手机号/邮箱） | - |
| `ZJMF_API_KEY` | API 密钥 | - |
| `ZJMF_ACTION` | `on` 开机 / `hard_reboot` 硬重启 | on |
| `ZJMF_CRON` | 定时表达式（NCRONTAB，6 段） | 0 */10 * * * * |
| `ZJMF_SUSPECT_THRESHOLD` | 连续异常几次判宕机 | 3 |
| `ZJMF_REBOOT_COOLDOWN` | 动作冷却（秒） | 600 |
| `ZJMF_RECOVER_TIMEOUT` | 恢复超时（秒） | 300 |
| `ZJMF_REBOOT_LIMIT` | 时间窗内动作次数上限（0=不限） | 5 |
| `ZJMF_REBOOT_LIMIT_WINDOW` | `hour` / `day` | hour |
| `ZJMF_DRY_RUN` | `true` 只检测不执行 | false |
| `ZJMF_WEBHOOK_TYPE` | `custom` / `pushplus` | custom |
| `ZJMF_WEBHOOK_URL` | 通知 Webhook 地址或 PushPlus Token | - |

> 大部分设置也可在**管理后台**里在线修改并持久化（保存到 Blob）。

## 安全提示

- `ADMIN_TOKEN` 用于保护管理后台与所有写接口，务必设置为强密码。
- `local.settings.json` 与 `monitor_data.json` 已加入 `.gitignore`，不要提交到仓库。
- 管理后台默认对公网可访问（仅靠 ADMIN_TOKEN 保护）。如需更强隔离，可在 Azure 上
  配置访问限制（IP 白名单）或前置身份验证（Easy Auth）。
