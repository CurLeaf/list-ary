# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 打包配置 — Listary 个人自动化工具集
生成单文件 EXE：dist/listary_tools.exe
"""

import os

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None
ROOT = os.path.abspath('.')

# Rich 的 unicode 数据模块名称含版本号，PyInstaller 无法自动检测
rich_hidden = collect_submodules('rich._unicode_data')
rich_datas = collect_data_files('rich')

a = Analysis(
    ['hub.py'],
    pathex=[ROOT],
    binaries=[],
    datas=rich_datas + [
        # 看板 HTML 模板
        (os.path.join('dashboard', 'templates', 'panel.html'), os.path.join('dashboard', 'templates')),
        # 前端静态资源（离线可用）
        (os.path.join('dashboard', 'static'), os.path.join('dashboard', 'static')),
        # 上报脚本模板（用于注入到项目）
        (os.path.join('report', 'report.py'), 'report'),
        (os.path.join('report', 'report_config.json'), 'report'),
        # 默认配置
        ('servers.json', '.'),
        (os.path.join('assets', 'icon.ico'), 'assets'),
    ],
    hiddenimports=rich_hidden + [
        'uvicorn',
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        'uvicorn.lifespan.off',
        'fastapi',
        'starlette',
        'starlette.responses',
        'starlette.routing',
        'starlette.middleware',
        'starlette.templating',
        'jinja2',
        'httpx',
        'winotify',
        'psutil',
        'rich',
        'dashboard',
        'dashboard.server',
        'dashboard.models',
        'dashboard.session_manager',
        'dashboard.routers',
        'dashboard.routers.ports',
        'dashboard.routers.ssh',
        'dashboard.routers.windsurf',
        'dashboard.routers.sessions',
        'dashboard.routers.settings',
        'modules',
        'modules.kill_port',
        'modules.ssh_connect',
        'modules.ssh_manager',
        'modules.windsurf_setup',
        'modules.windsurf_open',
        'modules.ide_profiles',
        'modules.webhook',
        'modules.autostart',
        'config',
        'utils',
        'multipart',
        'python_multipart',
        'webview',
        'pystray',
        'PIL',
        'bottle',
        'clr_loader',
        'pythonnet',
        'tkinter',
        'tkinter.filedialog',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='listary_tools',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join('assets', 'icon.ico'),
)
