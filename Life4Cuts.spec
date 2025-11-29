# -*- mode: python ; coding: utf-8 -*-
import sys
import os
from PyInstaller.utils.hooks import collect_all

block_cipher = None

# [1] Hidden Imports
hiddenimports = [
    'PIL', 
    'PIL.Image',
    'clientapp',
    'clientapp.apps',
    'clientapp.urls',
    'clientapp.views',
    'main',
    'main.settings',
    'main.urls',
    'main.wsgi',
    'django.contrib.admin.apps',
    'django.contrib.auth.apps',
    'django.contrib.contenttypes.apps',
    'django.contrib.messages.apps',
    'django.contrib.staticfiles.apps',
    'django.contrib.sessions.apps',
    'django.core.management',
]

datas = []
binaries = []

# [2] 내장할 파일 (templates, db)
added_files = [
    ('clientapp/templates', 'clientapp/templates'),
    ('db.sqlite3', '.'), 
]
datas += added_files

a = Analysis(
    ['run_app.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
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
    [],
    exclude_binaries=True,
    name='Life4Cut',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False, 
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    
    # [핵심 수정] 권한 설정 파일 연결 (이게 없으면 매번 물어봅니다)
    entitlements_file='entitlements.plist', 
)

app = BUNDLE(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    name='Life4Cut.app',
    # [핵심 수정] 아이콘 파일 연결
    icon='life4cuts_icon.icns', 
    bundle_identifier='com.life4cut.webcam',
    info_plist={
        'NSCameraUsageDescription': 'Camera Access Required',
        'NSMicrophoneUsageDescription': 'Microphone Access Required',
        'NSHighResolutionCapable': 'True',
        'LSBackgroundOnly': 'False'
    },
)