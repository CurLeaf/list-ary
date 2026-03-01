"""
SFTP 连接池 — 复用 paramiko SSH/SFTP 连接，避免每次文件浏览都重新握手
"""

import os
import threading
import time

import paramiko

from utils import get_data_dir

_pool: dict[str, tuple[paramiko.SFTPClient, paramiko.Transport, float]] = {}
_lock = threading.Lock()
_TTL = 120  # 连接空闲超时（秒）


def _server_key(server: dict) -> str:
    """生成服务器唯一标识"""
    host = server.get("host", "")
    port = server.get("port", 22)
    key = server.get("key", "")
    return f"{host}:{port}:{key}"


def _connect(server: dict) -> tuple[paramiko.SFTPClient, paramiko.Transport]:
    """建立新的 SSH + SFTP 连接"""
    host_str = server.get("host", "")
    port = server.get("port", 22) or 22

    # 解析 user@host
    if "@" in host_str:
        username, hostname = host_str.rsplit("@", 1)
    else:
        username = None
        hostname = host_str

    transport = paramiko.Transport((hostname, port))

    key_val = server.get("key", "")
    pkey = None
    if key_val:
        if "PRIVATE KEY" in key_val:
            # 内联密钥内容
            import io
            pkey = paramiko.Ed25519Key.from_private_key(io.StringIO(key_val))
        else:
            # 密钥文件路径
            key_path = os.path.expanduser(key_val)
            if os.path.isfile(key_path):
                try:
                    pkey = paramiko.Ed25519Key.from_private_key_file(key_path)
                except paramiko.SSHException:
                    try:
                        pkey = paramiko.RSAKey.from_private_key_file(key_path)
                    except paramiko.SSHException:
                        pkey = paramiko.ECDSAKey.from_private_key_file(key_path)

    # 加载 known_hosts（与 ssh.py 使用同一个文件）
    known_hosts_path = os.path.join(get_data_dir(), "ssh_keys", "known_hosts")
    host_keys = transport.get_security_options()

    connect_kwargs = {"username": username or ""}
    if pkey:
        connect_kwargs["pkey"] = pkey

    transport.connect(**connect_kwargs)
    sftp = paramiko.SFTPClient.from_transport(transport)
    return sftp, transport


def get_sftp(server: dict) -> paramiko.SFTPClient:
    """获取或复用 SFTP 连接"""
    key = _server_key(server)
    with _lock:
        if key in _pool:
            sftp, transport, _ = _pool[key]
            if transport.is_active():
                _pool[key] = (sftp, transport, time.time())
                return sftp
            else:
                # 连接已断开，清除
                try:
                    sftp.close()
                    transport.close()
                except Exception:
                    pass
                del _pool[key]

    # 在锁外创建连接（耗时操作）
    sftp, transport = _connect(server)
    with _lock:
        _pool[key] = (sftp, transport, time.time())
    return sftp


def listdir(server: dict, remote_path: str) -> list[dict]:
    """列出远程目录，返回 [{name, type}]"""
    sftp = get_sftp(server)
    entries = []
    for attr in sftp.listdir_attr(remote_path):
        name = attr.filename
        if name.startswith("."):
            continue
        import stat
        if stat.S_ISDIR(attr.st_mode or 0):
            entries.append({"name": name, "type": "dir"})
        else:
            entries.append({"name": name, "type": "file"})
    return entries


def cleanup_idle():
    """清理超时的空闲连接"""
    now = time.time()
    with _lock:
        expired = [k for k, (_, _, ts) in _pool.items() if now - ts > _TTL]
        for k in expired:
            sftp, transport, _ = _pool.pop(k)
            try:
                sftp.close()
                transport.close()
            except Exception:
                pass


def close_all():
    """关闭所有连接"""
    with _lock:
        for sftp, transport, _ in _pool.values():
            try:
                sftp.close()
                transport.close()
            except Exception:
                pass
        _pool.clear()
