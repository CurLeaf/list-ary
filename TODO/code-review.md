# 代码审查报告

> 审查范围：全量源码  |  日期：2026-03-01  |  修复完成：2026-03-01

---

## 🔴 系统故障风险（可能崩溃 / 数据丢失）

### 1. ✅ SQLite 无 WAL 模式 + 并发写锁死
**文件：** `dashboard/session_manager.py`

`asyncio.to_thread` 会并发执行多个线程，多个写操作同时命中 SQLite 默认的 journal 模式会触发 `database is locked` 错误，导致接口报 500。

**修复方案：** 建库时执行 `conn.execute("PRAGMA journal_mode=WAL")`

**已修复：** 在 `_get_conn()` 和 `init_db()` 中均添加 `PRAGMA journal_mode=WAL`。

---

### 2. ✅ `ws_clients` 并发修改导致运行时异常
**文件：** `dashboard/server.py`

`broadcast_ws` 在 `await ws.send_json()` 让出控制权期间，`websocket_endpoint` 协程可能同时执行 `ws_clients.remove(websocket)`，两处都调用 `remove()` 操作同一个列表，重复删除时抛 `ValueError`。

**修复方案：** 改用 `set` 或在 remove 前二次检查

**已修复：** `ws_clients` 改为 `set`，使用 `add()` / `discard()`；`broadcast_ws` 中使用 `list(ws_clients)` 快照迭代，避免迭代期间修改。

---

### 3. ✅ `_reply_events` 跨线程竞争
**文件：** `dashboard/session_manager.py`

`clean_all_sessions()` 经 `asyncio.to_thread` 在工作线程里执行 `_reply_events.clear()`，同时事件循环线程可能在 `get_reply_event()` 中写入该字典，产生真正的多线程竞争。

**修复方案：** 加 `threading.Lock`

**已修复：** 新增 `_reply_events_lock = threading.Lock()`，所有对 `_reply_events` 的读写操作（`get_reply_event`、`notify_reply`、`clear_reply_event`、`remove_reply_event`、`clean_all_sessions`、`clean_expired_sessions`）均在锁保护下执行。

---

### 4. ✅ `os._exit(0)` 跳过所有清理
**文件：** `hub.py`

`webview.start()` 返回后调用 `os._exit(0)` 直接强杀进程，SQLite 未提交的事务会丢失，atexit 和 `__del__` 均不执行。

**修复方案：** 改为 `sys.exit(0)`

**已修复：** `launch_gui()` 末尾和托盘 `on_quit` 回调均改为 `sys.exit(0)`。

---

### 5. ✅ Tkinter 在非主线程崩溃
**文件：** `dashboard/routers/windsurf.py`

`_pick()` 通过 `asyncio.to_thread` 在工作线程中创建 `tk.Tk()`，Tkinter 在 Windows 上**只允许在主线程使用**，偶现崩溃，表现为整个 FastAPI 进程挂起。

**修复方案：** 用 PowerShell 调用系统对话框

**已修复：** Windows 下改用 PowerShell 的 `System.Windows.Forms.FolderBrowserDialog`，非 Windows 平台保留 Tkinter 回退。

---

## 🟠 安全隐患

### 6. ✅ SSH 远程命令 Shell 注入
**文件：** `dashboard/routers/ssh.py`

`ls -1pA '{target}'` 和 `cd '{target}' && exec $SHELL` 中用单引号包裹路径。`_validate_subpath` 只检查 `..`，**不过滤单引号和分号**。

攻击示例：`subpath=a'; rm -rf ~; echo '` → 注入任意命令。

**修复方案：** 用 `shlex.quote(target)` 包裹路径

**已修复：** 导入 `shlex`，`ssh_connect`（line 146）和 `list_remote_files`（line 286）中的路径拼接均改用 `shlex.quote(target)`。

---

### 7. ✅ 任意文件读取接口
**文件：** `dashboard/routers/ssh.py`

`GET /api/ssh-key/read?path=C:/Windows/System32/config/SAM`，`path` 参数无任何路径限制，可读取系统任意文件。

**修复方案：** 校验路径必须在 `ssh_keys/` 目录内

**已修复：** 使用 `os.path.realpath()` 规范化后，检查路径是否在 `ssh_keys/` 目录下，不在则返回 403。

---

### 8. ✅ StrictHostKeyChecking=no（MITM 风险）
**文件：** `dashboard/routers/ssh.py`

所有 SSH / SCP 操作均关闭主机指纹验证，中间人攻击无感知。

**修复方案：** 首次连接时记录指纹，后续使用 `StrictHostKeyChecking=yes`

**已修复：** 新增 `_known_hosts_path()` 返回 `ssh_keys/known_hosts` 路径，所有 SSH/SCP 命令改用 `StrictHostKeyChecking=accept-new` + `UserKnownHostsFile` — 首次连接自动记录指纹，后续连接严格校验。

---

## 🟡 性能隐患

### 9. ✅ 缓存返回可变对象引用（缓存污染）
**文件：** `modules/ssh_manager.py`、`config.py`

`load_servers()` 和 `load_settings()` 直接返回缓存字典/列表本身，调用方修改后直接污染缓存。

**修复方案：** `return copy.deepcopy(_servers_cache["data"])`

**已修复：** `load_servers()` 和 `load_settings()` 均导入 `copy` 模块，返回 `copy.deepcopy()` 副本。

---

### 10. ✅ SSH 文件浏览每次重建连接
**文件：** `dashboard/routers/ssh.py`、`modules/sftp_pool.py`（新建）

每次点击目录都 `subprocess.run ssh ls`，即新建 SSH TCP 握手 + 认证，慢网络下每次操作需 1-5 秒。

**修复方案：** 改用 `paramiko` 的 `SFTPClient`（复用连接）

**已修复：** 新建 `modules/sftp_pool.py` SFTP 连接池（带 120s TTL 自动过期），`list_remote_files` 优先走 paramiko SFTP 复用连接，失败自动 fallback 到原有 subprocess 方式。进程退出时通过 lifespan 关闭所有连接。`requirements.txt` 新增 `paramiko>=3.0`。

---

### 11. ✅ `stuck_checker` 广播全量 sessions
**文件：** `dashboard/server.py`、`dashboard/session_manager.py`、`dashboard/templates/panel.html`

每分钟一次的定时器检测到任何卡死会话后，用 `async_get_all_sessions()` 取出**所有**会话再整体广播。

**修复方案：** 只广播变更的会话 ID，由前端按需拉取详情

**已修复：** stuck 检测改为逐个发送 `session_updated` 消息（复用前端已有逻辑）；过期清理改为发送 `sessions_deleted` 消息（携带 ID 列表），前端按 ID 批量移除。`clean_expired_sessions` 返回 `(count, expired_ids)` 元组。

---

### 12. ✅ `poll` 接口 timeout 无上限
**文件：** `dashboard/routers/sessions.py`

`GET /api/poll/{id}?timeout=999999`，客户端可设置极大 timeout，协程永久挂起不释放。

**修复方案：** `timeout = min(timeout, 60)`

**已修复：** 在 `poll()` 函数入口添加 `timeout = min(timeout, 60)`。

---

## ⚪ 代码质量 / 小隐患

### 13. ✅ CLI `connect()` 路径无引号
**文件：** `modules/ssh_connect.py`

`remote_cmd = f"cd {server['path']} && exec $SHELL"` 路径含空格时必然报错。

**已修复：** 导入 `shlex`，改为 `f"cd {shlex.quote(server['path'])} && exec $SHELL"`。

---

### 14. ✅ 设置保存无类型校验
**文件：** `dashboard/routers/settings.py`

`port` 可被存为字符串 `"abc"`，下游 `find_free_port(get_port())` 直接传入时崩溃。

**已修复：** 保存前对 `port`、`stuck_timeout`、`session_expire_days` 强制 `int()` 转换并校验正整数，非法值返回 400。

---

### 15. ✅ SQLite 连接不显式关闭（文件描述符泄漏）
**文件：** `dashboard/session_manager.py`

`_get_conn()` 在 `threading.local` 中存储连接，线程池线程被回收时连接依赖 GC 关闭。

**已修复：** 新增 `_all_conns` 列表跟踪所有创建的连接，注册 `atexit.register(_close_all_conns)` 在进程退出时显式关闭。

---

### 16. ✅ `server.py __main__` 绑定 0.0.0.0
**文件：** `dashboard/server.py`

直接 `python server.py` 会绑定 `0.0.0.0:9000`，将管理面板暴露到局域网。

**已修复：** 改为 `host="127.0.0.1"`，与 `hub.py` 安全策略一致。

---

## 修复总结

| 编号 | 项目 | 状态 | 修复内容 |
|------|------|------|----------|
| #1 | SQLite WAL 模式 | ✅ 已修复 | `PRAGMA journal_mode=WAL` |
| #2 | ws_clients 并发 | ✅ 已修复 | `list` → `set` + 快照迭代 |
| #3 | _reply_events 竞争 | ✅ 已修复 | `threading.Lock` 保护 |
| #4 | os._exit | ✅ 已修复 | → `sys.exit(0)` |
| #5 | Tkinter 非主线程 | ✅ 已修复 | PowerShell 对话框替代 |
| #6 | Shell 注入 | ✅ 已修复 | `shlex.quote()` |
| #7 | 任意文件读取 | ✅ 已修复 | 路径限制 `ssh_keys/` |
| #8 | StrictHostKeyChecking | ✅ 已修复 | `accept-new` + `UserKnownHostsFile` |
| #9 | 缓存可变引用 | ✅ 已修复 | `copy.deepcopy()` |
| #10 | SSH 连接复用 | ✅ 已修复 | paramiko SFTP 连接池 + fallback |
| #11 | stuck_checker 增量广播 | ✅ 已修复 | 逐个 `session_updated` + `sessions_deleted` |
| #12 | poll timeout 上限 | ✅ 已修复 | `min(timeout, 60)` |
| #13 | CLI 路径引号 | ✅ 已修复 | `shlex.quote()` |
| #14 | 设置类型校验 | ✅ 已修复 | `int()` + 正整数校验 |
| #15 | SQLite 连接关闭 | ✅ 已修复 | `atexit` 关闭所有连接 |
| #16 | 绑定 127.0.0.1 | ✅ 已修复 | `0.0.0.0` → `127.0.0.1` |

**已修复：16/16** — 所有问题均已修复
