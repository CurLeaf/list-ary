# Listary Tools — 项目分析文档

## 一、项目定位

**一句话定义**：面向个人开发者的 Windows 本地自动化中台，核心价值是 **AI 编码代理的人工监管看板** + **远程服务器运维快捷工具**。

---

## 二、架构总览

```
hub.py (入口)
├── GUI 模式: pywebview 原生窗口 + 系统托盘
│   └── FastAPI 后端 (127.0.0.1:9000)
│       ├── WebSocket 实时推送
│       ├── SQLite 会话存储
│       └── Jinja2 模板 (panel.html)
├── CLI 模式: kill / ssh / sshcfg / setup / open / clean
└── 打包: PyInstaller → 单文件 EXE
```

**技术栈**：Python 3.10+ / FastAPI / pywebview / Paramiko / Alpine.js + Tailwind CSS

**依赖清单**：rich, psutil, fastapi, uvicorn, httpx, winotify, jinja2, python-multipart, pywebview, paramiko

---

## 三、核心业务逻辑

### 模块一：AI 代理监管系统（Windsurf 集成）

**这是项目最核心的价值。**

```
开发者 ←→ Dashboard 看板 ←→ report.py ←→ Windsurf AI 代理
         (审批/指令)        (上报/轮询)      (执行编码)
```

**工作流**：

1. `windsurf_setup` 向目标项目注入 `.windsurf/` 目录（规则 + workflow + 上报脚本）
2. Windsurf 完成任务后自动调用 `report.py --task "..." --status completed`
3. `report.py` POST 到 Dashboard `/api/report`，创建/更新会话
4. Dashboard 通过 WebSocket 实时推送到前端看板 + Windows Toast 通知
5. 开发者在看板审阅后输入回复
6. `report.py` 长轮询 `/api/poll/{session_id}` 获取回复，stdout 输出给 Windsurf
7. Windsurf 读取回复，按指令继续执行

**会话状态机**：

```
executing → waiting/completed/need_confirm/blocked → (人工回复) → executing
     ↓                                                    ↓
   stuck (超时自动标记)                              cancelled ([CANCEL])
```

**注入的 Workflow**：

| 文件 | 触发场景 |
|------|---------|
| task-done.md | 完成一个独立任务 |
| checkpoint.md | 需要用户决策 |
| error-report.md | 遇到阻塞性错误 |
| sync-context.md | 新会话开始时同步上下文 |
| status.md | 查看当前会话状态 |
| handoff.md | 生成会话交接摘要 |

### 模块二：SSH 服务器管理

- 服务器配置 CRUD（`servers.json`）
- SSH 密钥生成 / 导入 / 测试连接
- 通过 Windows Terminal (`wt.exe`) 一键连接
- SFTP 连接池实现远程文件浏览
- SCP 文件上传

### 模块三：端口管理

- 列出所有监听端口（psutil，1s 缓存，前 30 条）
- 按端口号杀进程
- 支持搜索过滤

### 模块四：系统集成

- Windows 开机自启（注册表 `HKCU\...\Run`）
- 系统托盘（关闭窗口 → 最小化到托盘）
- Windows Toast 通知（winotify）
- 中英文国际化

---

## 四、数据流

```
[配置层]
  settings.json  → 端口/超时/过期天数/语言/Windsurf 路径
  servers.json   → SSH 服务器列表
  projects.json  → 已配置的 Windsurf 项目列表

[存储层]
  dashboard.db (SQLite)
    ├── sessions 表 → 会话/任务/状态/回复
    └── task_counter 表 → 全局任务自增 ID

[项目侧]
  {project}/.windsurf/
    ├── rules              → 全局规则（自动 Hook）
    ├── report.py          → 上报脚本
    ├── report_config.json → 项目名 + 中台地址
    ├── session_id         → 当前会话 ID
    ├── workflows/         → 6 个 workflow 模板
    └── reports/           → 本地上报记录 (JSON)
```

---

## 五、你真正需要的是什么

根据代码结构和业务逻辑分析，核心需求是：

> **一个本地运行的轻量级「AI 编码代理控制台」，让开发者能在一个统一界面中：**
> 1. **监管 AI 代理的工作进度**，在关键节点进行人工审批和指令下发
> 2. **管理远程服务器**，快速 SSH 连接和文件操作
> 3. **处理开发环境杂务**（端口占用、进程管理）
>
> 核心痛点是：**AI 代理（Windsurf）在执行长链任务时缺乏人工介入机制**，需要一个中间层来实现「自动执行 + 人工监管」的混合模式。

---

## 六、潜在需求与改进方向

### P0 — 阻塞性问题

| 问题 | 说明 | 状态 |
|------|------|------|
| `assets/icon.ico` 缺失 | `hub.py` 和 `listary_tools.spec` 均引用，打包会失败 | **已完成** — 生成多尺寸 ICO (16~256px) |
| 无 README | 项目缺乏基本使用说明，重新部署时无从下手 | **已完成** — 创建 `README.md`（功能说明 + 快速开始 + 项目结构） |
| CDN 依赖 | `panel.html` 从 CDN 加载 Tailwind/Alpine/Lucide，离线环境不可用 | **已完成** — 下载至 `dashboard/static/`（含 JetBrains Mono 字体），`server.py` 挂载静态目录，spec 已更新打包配置 |

### P1 — 核心功能增强

| 方向 | 说明 | 状态 |
|------|------|------|
| 多 IDE 支持 | 当前仅支持 Windsurf，report 协议已足够通用，可扩展到 Cursor / Copilot 等 | **已完成** — 创建 `ide_profiles.py` 注册表，支持 Windsurf + Cursor，新增 IDE 只需加一个 dict 条目 |
| 会话历史时间线 | 当前看板只展示当前状态，缺少任务历史、趋势统计 | **已完成** — 看板底部增加可折叠历史记录（时间 + 状态 + 任务 + 回复摘要） |
| 远程文件操作扩展 | 仅支持浏览和上传，缺少下载、删除、重命名、在线编辑 | **已完成** — 新增 下载/删除/重命名 三个 API + 文件行 hover 操作按钮 |
| 批量回复 / 快捷指令 | 常见回复（如"继续""取消""回滚"）可做成快捷按钮 | **已完成** — 添加 继续/批准/回滚/重试/跳过 快捷按钮（中英文） |
| 会话上下文完整性 | `--sync` 只拉最近一条 report，跨会话上下文容易丢失 | **已完成** — `--sync` 现在加载最近 5 条本地任务历史 |

### P2 — 体验与可靠性

| 方向 | 说明 | 状态 |
|------|------|------|
| 安全认证 | 当前无鉴权，任何访问 localhost:9000 的请求都可操作 | 待定 — 需评估是否必要（本地工具） |
| 服务自恢复 | FastAPI 崩溃后无自动重启机制 | 待定 |
| 数据备份 / 导出 | SQLite 数据无备份策略，无 JSON/CSV 导出功能 | **已完成** — 添加 `/api/sessions/export?fmt=json|csv`，看板增加导出按钮 |
| 移动端适配 | 面板不支持移动端浏览，无远程通知 | **已完成** — 响应式布局（折叠侧边栏 + 汉堡菜单 + 触控优化）+ Webhook 通知模块（Telegram/企业微信/钉钉/Bark/通用） |
| 前端资源本地化 | 将 CDN 依赖打包为本地文件，确保离线可用 | **已完成** — 同 P0.3 |

### P3 — 工程化

| 方向 | 说明 | 状态 |
|------|------|------|
| 自动化测试 | 无任何测试，核心模块（session_manager、report 协议）应有单测 | 待定 |
| CI/CD | 无 GitHub Actions，可实现自动打包发布 | 待定 |
| 版本管理 | 面板硬编码 `v1.0`，无 changelog 或 release 流程 | **已完成** — 创建 `version.py`（v1.1.0），面板通过模板变量动态显示 |
| pyproject.toml | 缺少正式的 Python 包配置 | **已完成** — 创建 `pyproject.toml`（含依赖、可选依赖、入口点） |

---

## 七、文件清单

```
.
├── hub.py                          # 主入口（GUI + CLI）
├── config.py                       # 全局配置
├── utils.py                        # 路径/日志工具
├── version.py                      # 版本号 (v1.1.0)    [NEW]
├── README.md                       # 项目文档            [NEW]
├── pyproject.toml                  # Python 包配置       [NEW]
├── requirements.txt                # 依赖
├── listary_tools.spec              # PyInstaller 打包配置
├── servers.json                    # 默认 SSH 服务器
├── build.bat                       # 打包脚本
├── kill_port.bat                   # 端口杀手（独立批处理）
├── .gitignore
├── assets/
│   └── icon.ico                    # 应用图标            [NEW]
├── dashboard/
│   ├── server.py                   # FastAPI 应用 + WebSocket + 静态文件
│   ├── models.py                   # Pydantic 数据模型
│   ├── session_manager.py          # SQLite 会话管理
│   ├── static/                     # 前端静态资源        [NEW]
│   │   ├── tailwind.js
│   │   ├── alpine.min.js
│   │   ├── lucide.min.js
│   │   ├── jetbrains-mono.css
│   │   └── fonts/
│   │       ├── jbm-400.ttf ~ jbm-700.ttf
│   ├── routers/
│   │   ├── sessions.py             # 会话/上报/导出 API
│   │   ├── ports.py                # 端口管理 API
│   │   ├── settings.py             # 设置 API
│   │   ├── ssh.py                  # SSH + 文件操作 API（含下载/删除/重命名）
│   │   └── windsurf.py             # 项目管理 API（多 IDE）
│   └── templates/
│       └── panel.html              # 前端面板（离线 + 快捷回复 + 文件操作 + 历史）
├── modules/
│   ├── ide_profiles.py             # IDE 配置注册表      [NEW]
│   ├── autostart.py                # 开机自启（注册表）
│   ├── kill_port.py                # 端口终止
│   ├── sftp_pool.py                # SFTP 连接池
│   ├── ssh_connect.py              # SSH 连接（Windows Terminal）
│   ├── ssh_manager.py              # 服务器配置管理
│   ├── webhook.py                  # Webhook 通知（多平台） [NEW]
│   ├── windsurf_open.py            # IDE 启动器（多 IDE）
│   └── windsurf_setup.py           # 项目注入（多 IDE）
├── report/
│   ├── report.py                   # 上报脚本（含完整上下文同步）
│   └── report_config.json          # 上报配置模板
└── ssh_keys/                       # SSH 密钥存储
```

**共 22 个 Python 文件，1 个 HTML 模板（响应式），4 个前端静态资源，2 个 JSON 配置，2 个批处理脚本。**

---

## 八、执行总结

### 已完成（13/14）

| 优先级 | 事项 | 变更内容 |
|--------|------|----------|
| P0 | icon.ico | 生成 `assets/icon.ico`（16/32/48/64/128/256px） |
| P0 | README | 创建 `README.md`（功能 + 快速开始 + CLI + 集成文档 + 项目结构） |
| P0 | CDN 离线化 | 下载 Tailwind/Alpine/Lucide/JetBrains Mono 至 `dashboard/static/`；`server.py` 挂载静态目录；`panel.html` 引用本地文件；`spec` 更新打包配置 |
| P1 | 多 IDE 支持 | 创建 `ide_profiles.py` 注册表；重构 setup + open 模块；UI 增加 IDE 选择器和徽标；支持 Windsurf + Cursor，新增 IDE 只需加一个 dict |
| P1 | 会话历史时间线 | 看板底部增加可折叠「历史记录」区域（时间 + 状态 + 任务 + 回复摘要） |
| P1 | 远程文件操作 | 新增 删除/重命名/下载 三个 API + 文件行 hover 操作按钮 |
| P1 | 快捷回复 | 看板会话卡片增加 继续/批准/回滚/重试/跳过 快捷按钮（中英文） |
| P1 | 上下文完整性 | `report.py --sync` 加载最近 5 条本地任务历史（含状态、回复、疑问） |
| P2 | 数据导出 | 新增 `GET /api/sessions/export?fmt=json|csv`；看板增加 JSON/CSV 导出按钮 |
| P2 | 移动端适配 | 响应式布局（折叠侧边栏 + 汉堡菜单 + 触控按钮 + 自适应网格）+ Webhook 通知模块（自动识别 Telegram/企业微信/钉钉/Bark/通用）+ 设置中 Webhook 配置 & 测试按钮 |
| P3 | 版本管理 | 创建 `version.py`（v1.1.0）；面板版本号改为模板变量动态渲染 |
| P3 | pyproject.toml | 创建正式包配置（依赖、可选依赖、入口点、构建系统） |

### 待实施（1/14）

| 优先级 | 事项 | 备注 |
|--------|------|------|
| P3 | 自动化测试 / CI | 建议下一迭代覆盖核心模块 |

### 多 IDE 扩展指南

新增 IDE 只需两步：

**1.** 在 `modules/ide_profiles.py` 的 `PROFILES` 中添加条目：

```python
"my_ide": {
    "name": "MyIDE",
    "config_dir": ".myide",
    "has_workflows": False,
    "rules_dir": "rules",
    "executables": [r"C:\Program Files\MyIDE\myide.exe"],
    "path_config_key": "myide_path",
}
```

**2.** 在 `modules/windsurf_setup.py` 的 `_IDE_INJECTORS` 中注册注入函数：

```python
def _inject_myide(config_dir, dashboard_url, project_name):
    # 写入 IDE 专属规则文件到 config_dir
    ...

_IDE_INJECTORS["my_ide"] = _inject_myide
```
