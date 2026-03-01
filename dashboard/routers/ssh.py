"""SSH 连接 + 配置 + 密钥管理 API 路由"""

import asyncio
import os
import sys

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from dashboard.models import ServerConfig

router = APIRouter(tags=["ssh"])


@router.get("/servers")
async def list_servers():
    """获取 SSH 服务器列表"""
    from modules.ssh_manager import load_servers
    return load_servers()


@router.post("/servers")
async def add_server(req: ServerConfig):
    """添加 SSH 服务器"""
    from modules.ssh_manager import load_servers, save_servers
    servers = load_servers()
    servers.append(req.model_dump())
    save_servers(servers)
    return {"ok": True, "servers": servers}


@router.put("/servers/{index}")
async def update_server(index: int, req: ServerConfig):
    """更新 SSH 服务器"""
    from modules.ssh_manager import load_servers, save_servers
    servers = load_servers()
    if not (0 <= index < len(servers)):
        return JSONResponse(status_code=404, content={"error": "服务器不存在"})
    servers[index] = req.model_dump()
    save_servers(servers)
    return {"ok": True, "servers": servers}


@router.delete("/servers/{index}")
async def remove_server(index: int):
    """删除 SSH 服务器"""
    from modules.ssh_manager import load_servers, save_servers
    servers = load_servers()
    if not (0 <= index < len(servers)):
        return JSONResponse(status_code=404, content={"error": "服务器不存在"})
    removed = servers.pop(index)
    save_servers(servers)
    return {"ok": True, "removed": removed["name"], "servers": servers}


@router.get("/servers/ping")
async def ping_servers():
    """探测所有 SSH 服务器在线状态（并发）"""
    from modules.ssh_manager import load_servers
    from config import SSH_PING_TIMEOUT
    servers = load_servers()

    async def ping_one(host: str, port: int) -> bool:
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=SSH_PING_TIMEOUT)
            writer.close()
            await writer.wait_closed()
            return True
        except Exception:
            return False

    tasks = [
        ping_one(s.get("host", "").split("@")[-1], s.get("port", 22))
        for s in servers
    ]
    results = await asyncio.gather(*tasks) if tasks else []
    return {"status": list(results)}


@router.post("/ssh-connect/{index}")
async def ssh_connect(index: int):
    """连接到 SSH 服务器"""
    import subprocess, shutil
    from modules.ssh_manager import load_servers, save_servers, save_key_content_to_file
    servers = load_servers()
    if not (0 <= index < len(servers)):
        return JSONResponse(status_code=404, content={"error": "服务器不存在"})
    server = servers[index]

    ssh_cmd = ["ssh", "-t"]
    if server.get("port") and server["port"] != 22:
        ssh_cmd += ["-p", str(server["port"])]
    if server.get("key"):
        key_val = server["key"]
        if "PRIVATE KEY" in key_val:
            key_path = save_key_content_to_file(server.get("name", "default"), key_val)
            servers[index]["key"] = key_path
            save_servers(servers)
        else:
            key_path = os.path.expanduser(key_val)
        ssh_cmd += ["-i", key_path]
    ssh_cmd.append(server["host"])
    if server.get("path"):
        ssh_cmd.append(f"cd {server['path']} && exec $SHELL")

    wt = shutil.which("wt") or shutil.which("wt.exe")
    try:
        if wt:
            subprocess.Popen([wt, "new-tab", "--title", server["name"]] + ssh_cmd)
        else:
            subprocess.Popen(["cmd", "/c", "start"] + ssh_cmd)
        return {"ok": True, "server": server["name"]}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/ssh-key/ensure")
async def ensure_ssh_key(req: dict):
    """检查本地是否已有密钥对，没有则自动生成。返回私钥路径和公钥内容"""
    import subprocess
    from utils import get_data_dir
    server_name = req.get("server_name", "default").strip() or "default"
    keys_dir = os.path.join(get_data_dir(), "ssh_keys")
    os.makedirs(keys_dir, exist_ok=True)

    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in server_name)
    key_path = os.path.join(keys_dir, f"{safe_name}_key")
    pub_path = key_path + ".pub"
    generated = False

    # 已有密钥对 → 直接返回
    if os.path.exists(key_path) and os.path.exists(pub_path):
        with open(pub_path, "r", encoding="utf-8") as f:
            public_key = f.read().strip()
        return {"ok": True, "path": key_path, "public_key": public_key, "generated": False}

    # 不存在 → 生成
    try:
        result = await asyncio.to_thread(
            subprocess.run,
            ["ssh-keygen", "-t", "ed25519", "-f", key_path, "-N", "", "-C", server_name],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            return JSONResponse(status_code=500, content={"error": result.stderr.strip() or "生成密钥失败"})

        with open(pub_path, "r", encoding="utf-8") as f:
            public_key = f.read().strip()

        return {"ok": True, "path": key_path, "public_key": public_key, "generated": True}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/ssh-test")
async def test_ssh_connection(req: dict):
    """测试 SSH 连接是否能通过密钥认证"""
    import subprocess
    host = req.get("host", "").strip()
    port = req.get("port", 22)
    key_path = req.get("key", "").strip()
    if not host:
        return JSONResponse(status_code=400, content={"error": "缺少主机地址"})

    ssh_cmd = [
        "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
        "-o", "StrictHostKeyChecking=no",
    ]
    if port and port != 22:
        ssh_cmd += ["-p", str(port)]
    if key_path:
        ssh_cmd += ["-i", os.path.expanduser(key_path)]
    ssh_cmd += [host, "echo OK"]

    try:
        result = await asyncio.to_thread(
            subprocess.run, ssh_cmd,
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return {"ok": True, "connected": True}
        else:
            return {"ok": True, "connected": False, "error": result.stderr.strip()}
    except subprocess.TimeoutExpired:
        return {"ok": True, "connected": False, "error": "连接超时"}
    except Exception as e:
        return {"ok": True, "connected": False, "error": str(e)}


@router.post("/ssh-key/save")
async def save_ssh_key(req: dict):
    """将用户粘贴的 SSH 密钥内容保存为文件，返回文件路径"""
    from modules.ssh_manager import save_key_content_to_file
    key_content = req.get("key_content", "").strip()
    server_name = req.get("server_name", "default").strip()
    if not key_content:
        return JSONResponse(status_code=400, content={"error": "密钥内容不能为空"})
    if "PRIVATE KEY" not in key_content:
        return JSONResponse(status_code=400, content={"error": "无效的密钥内容，缺少 PRIVATE KEY 标记"})

    try:
        key_path = save_key_content_to_file(server_name, key_content)
        return {"ok": True, "path": key_path}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"保存密钥失败: {e}"})


@router.get("/ssh-key/read")
async def read_ssh_key(path: str = ""):
    """读取 SSH 密钥文件内容"""
    if not path:
        return JSONResponse(status_code=400, content={"error": "路径不能为空"})
    expanded = os.path.expanduser(path)
    if not os.path.isfile(expanded):
        return JSONResponse(status_code=404, content={"error": "文件不存在"})
    try:
        with open(expanded, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return {"ok": True, "content": content}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/servers/{index}/files")
async def list_remote_files(index: int):
    """通过 SSH 列出远程服务器目录下的文件"""
    import subprocess
    from modules.ssh_manager import load_servers
    servers = load_servers()
    if not (0 <= index < len(servers)):
        return JSONResponse(status_code=404, content={"error": "服务器不存在"})
    server = servers[index]
    remote_path = server.get("path", "").strip()
    if not remote_path:
        return {"ok": True, "files": [], "path": ""}

    # 构建 ssh 命令: ls -1pA (一行一个, 目录加/, 不显示 . ..)
    ssh_cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", "-o", "StrictHostKeyChecking=no"]
    if server.get("port") and server["port"] != 22:
        ssh_cmd += ["-p", str(server["port"])]
    if server.get("key"):
        key_val = server["key"]
        if "PRIVATE KEY" not in key_val:
            key_path = os.path.expanduser(key_val)
            ssh_cmd += ["-i", key_path]
    ssh_cmd.append(server["host"])
    ssh_cmd.append(f"ls -1pA {remote_path}")

    try:
        result = await asyncio.to_thread(
            subprocess.run, ssh_cmd,
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return JSONResponse(status_code=500, content={"error": result.stderr.strip() or "SSH 连接失败"})

        files = []
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            if line.endswith("/"):
                files.append({"name": line[:-1], "type": "dir"})
            else:
                files.append({"name": line, "type": "file"})
        return {"ok": True, "files": files, "path": remote_path}
    except subprocess.TimeoutExpired:
        return JSONResponse(status_code=504, content={"error": "SSH 连接超时"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/ssh-key/open-dir")
async def open_ssh_key_dir():
    """在文件资源管理器中打开 SSH 密钥所在目录"""
    import subprocess
    from utils import get_data_dir
    keys_dir = os.path.join(get_data_dir(), "ssh_keys")
    os.makedirs(keys_dir, exist_ok=True)
    try:
        if sys.platform == "win32":
            subprocess.Popen(["explorer", keys_dir])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", keys_dir])
        else:
            subprocess.Popen(["xdg-open", keys_dir])
        return {"ok": True, "path": keys_dir}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
