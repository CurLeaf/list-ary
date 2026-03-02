# Listary Tools

面向个人开发者的 Windows 本地自动化中台 — **AI 编码代理监管看板** + **远程服务器运维工具**。

## 功能

- **AI 代理看板** — 监管 Windsurf/Cursor 等 AI 编码代理的任务进度，在关键节点审批和下发指令
- **SSH 管理** — 服务器配置、密钥管理、一键连接（Windows Terminal）、SFTP 文件浏览/上传
- **端口管理** — 查看监听端口、一键终止占用进程
- **系统集成** — 开机自启、系统托盘、Windows Toast 通知、中英文切换

## 快速开始

### 从源码运行

```bash
pip install -r requirements.txt
python hub.py
```

### CLI 命令

```bash
python hub.py kill 3000          # 杀端口
python hub.py ssh 1              # 连接第 1 台服务器
python hub.py sshcfg             # 管理 SSH 配置
python hub.py setup <项目路径>    # 配置 Windsurf 项目
python hub.py open <项目路径>     # 用 Windsurf 打开项目
python hub.py clean              # 清理历史会话
```

### 打包为 EXE

```bash
build.bat
```

生成 `dist/listary_tools.exe`，双击启动 GUI 面板。

## AI 代理集成

### 工作原理

```
开发者 ←→ Dashboard 看板 ←→ report.py ←→ AI 代理 (Windsurf)
         (审批/指令)        (上报/轮询)     (执行编码)
```

### 配置项目

1. 启动 Listary Tools（GUI 或 `python hub.py`）
2. 进入 **WINDSURF** 页签，点击 **+ 配置**
3. 选择项目文件夹，填写项目名
4. 工具会自动注入 `.windsurf/` 目录（规则 + workflow + 上报脚本）

### 注入的 Workflow

| Workflow | 触发场景 |
|----------|---------|
| `/task-done` | AI 完成一个独立任务后上报 |
| `/checkpoint` | 遇到需要人工决策的问题 |
| `/error-report` | 遇到无法自行解决的错误 |
| `/sync-context` | 新会话开始时同步上下文 |
| `/status` | 查看当前会话状态 |
| `/handoff` | 生成会话交接摘要 |

## 项目结构

```
hub.py                    # 主入口（GUI + CLI）
config.py                 # 全局配置
utils.py                  # 路径/日志工具
version.py                # 版本号
dashboard/
  server.py               # FastAPI 应用
  models.py               # 数据模型
  session_manager.py      # SQLite 会话管理
  static/                 # 前端静态资源
  templates/panel.html    # 前端面板
  routers/                # API 路由
modules/
  ssh_manager.py          # SSH 服务器配置
  ssh_connect.py          # SSH 连接
  sftp_pool.py            # SFTP 连接池
  kill_port.py            # 端口终止
  windsurf_setup.py       # Windsurf 项目注入
  windsurf_open.py        # Windsurf 启动器
  autostart.py            # 开机自启
report/
  report.py               # 上报脚本（注入到项目中）
```

## 技术栈

Python 3.10+ / FastAPI / pywebview / Paramiko / Alpine.js / Tailwind CSS

## License

MIT
