# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: Akira.app (windowed onedir bundle)."""

from pathlib import Path
import sys

project_dir = Path(SPECPATH).resolve()
sys.path.insert(0, str(project_dir))
from tool_registry import TOOL_REGISTRY

icon_file = project_dir / "assets" / "akira.icns"
icon = str(icon_file) if icon_file.is_file() else None
block_cipher = None

a = Analysis(
    ['desktop.py'],
    pathex=[str(project_dir)],
    binaries=[],
    datas=[(str(project_dir / 'permissions.json'), '.'), (str(project_dir / 'assets' / 'core_atlas.png'), 'assets')],
    hiddenimports=sorted({tool.implementation_module for tool in TOOL_REGISTRY} | {"spotify_auth", "yt_dlp"}),
    hookspath=[str(project_dir / 'build' / 'hooks')] if (project_dir / 'build' / 'hooks').is_dir() else [],
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
    [],
    exclude_binaries=True,
    name='Akira',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Akira',
)
app = BUNDLE(
    coll,
    name='Akira.app',
    icon=icon,
    bundle_identifier='com.akira.desktop',
    info_plist={
        'CFBundleDisplayName': 'Akira',
        'CFBundleName': 'Akira',
        'CFBundleShortVersionString': '1.0.0',
        'CFBundleVersion': '1',
        'CFBundleIdentifier': 'com.akira.desktop',
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '12.0',
    },
)