# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: Akira.app (windowed onedir bundle)."""

block_cipher = None

a = Analysis(
    ['desktop.py'],
    pathex=['/Users/wonde/Akira'],
    binaries=[],
    datas=[],
    hiddenimports=[
        'webrtcvad',
        'sounddevice',
        'soundfile',
        'numpy',
        'groq',
        'capabilities.observe',
        'capabilities.apps',
        'capabilities.filesystem',
        'capabilities.shell',
        'capabilities.wait',
        'capabilities.key',
        'capabilities.gui',
        'capabilities.task',
    ],
    hookspath=['/Users/wonde/Akira/build/hooks'],
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
    icon='/tmp/akira.icns',
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
    icon='/tmp/akira.icns',
    bundle_identifier='com.akira.desktop',
    info_plist={
        'CFBundleDisplayName': 'Akira',
        'CFBundleName': 'Akira',
        'CFBundleShortVersionString': '1.0.0',
        'CFBundleVersion': '1',
        'CFBundleIdentifier': 'com.akira.desktop',
        'NSMicrophoneUsageDescription': (
            'Акира использует микрофон для распознавания речи, '
            'голосовых команд и диалога.'
        ),
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '12.0',
    },
)