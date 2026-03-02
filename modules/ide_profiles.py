"""
IDE 配置档案注册表 — 定义各 IDE 的目录结构、规则格式、可执行文件路径。
新增 IDE 只需在 PROFILES 中添加一个条目。
"""

import os


def _expand(paths: list[str]) -> list[str]:
    return [os.path.expandvars(p) for p in paths]


PROFILES: dict[str, dict] = {
    "windsurf": {
        "name": "Windsurf",
        "config_dir": ".windsurf",
        "has_workflows": True,
        "workflows_dir": "workflows",
        "rules_file": "rules",
        "executables": _expand([
            r"D:\Program Files\Windsurf Next\Windsurf - Next.exe",
            r"D:\Program Files\Windsurf\Windsurf.exe",
            r"C:\Program Files\Windsurf Next\Windsurf - Next.exe",
            r"C:\Program Files\Windsurf\Windsurf.exe",
            r"%LOCALAPPDATA%\Programs\Windsurf\Windsurf.exe",
            r"%LOCALAPPDATA%\Programs\Windsurf Next\Windsurf - Next.exe",
        ]),
        "path_config_key": "windsurf_path",
    },
    "cursor": {
        "name": "Cursor",
        "config_dir": ".cursor",
        "has_workflows": False,
        "rules_dir": "rules",
        "rules_format": "mdc",
        "executables": _expand([
            r"D:\Program Files\Cursor\Cursor.exe",
            r"C:\Program Files\Cursor\Cursor.exe",
            r"%LOCALAPPDATA%\Programs\cursor\Cursor.exe",
            r"%LOCALAPPDATA%\cursor\Cursor.exe",
        ]),
        "path_config_key": "cursor_path",
    },
}

IDE_CHOICES = list(PROFILES.keys())


def get_profile(ide: str) -> dict:
    """获取 IDE 配置档案，不存在时抛出 KeyError"""
    if ide not in PROFILES:
        raise KeyError(f"未知 IDE: {ide}，可选: {', '.join(IDE_CHOICES)}")
    return PROFILES[ide]


def get_config_dir_name(ide: str) -> str:
    return get_profile(ide)["config_dir"]


def find_executable(ide: str) -> str | None:
    """查找 IDE 可执行文件路径（优先用户配置，其次常见路径）"""
    from utils import get_data_dir

    profile = get_profile(ide)
    config_key = profile["path_config_key"]

    saved_path = os.path.join(get_data_dir(), f"{config_key}.txt")
    if os.path.exists(saved_path):
        with open(saved_path, "r", encoding="utf-8") as f:
            path = f.read().strip()
            if path and os.path.exists(path):
                return path

    for path in profile["executables"]:
        if os.path.exists(path):
            return path

    return None


def save_executable_path(ide: str, path: str):
    """保存用户指定的 IDE 路径"""
    from utils import get_data_dir

    profile = get_profile(ide)
    config_key = profile["path_config_key"]
    config_path = os.path.join(get_data_dir(), f"{config_key}.txt")
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        f.write(path)


def get_project_config_dir(project_path: str, ide: str) -> str:
    """获取项目中 IDE 配置目录的完整路径"""
    return os.path.join(project_path, get_config_dir_name(ide))


def is_project_configured(project_path: str, ide: str) -> bool:
    """检测项目是否已注入指定 IDE 的配置"""
    return os.path.isdir(get_project_config_dir(project_path, ide))
