# Life4Cuts.spec

# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['run_app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('clientapp/templates', 'clientapp/templates'),
        ('clientapp/static', 'clientapp/static'),
        # 만약 db.sqlite3도 포함해서 배포하려면 아래 주석 해제 (선택사항)
        # ('db.sqlite3', '.'),
    ],
    hiddenimports=[
        'django.contrib.admin',
        'django.contrib.auth',
        'django.contrib.contenttypes',
        'django.contrib.sessions',
        'django.contrib.messages',
        'django.contrib.staticfiles',
        'clientapp',
        'sslserver'  # <--- [추가] 여기에 꼭 적어주세요!
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
    name='Life4Cut',
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
)

# [여기가 핵심] macOS 앱 번들 설정 및 카메라 권한 설명 추가
app = BUNDLE(
    exe,
    name='Life4Cut.app',
    icon=None,
    bundle_identifier='com.myname.life4cut', # 고유 ID 아무거나
    info_plist={
        'NSCameraUsageDescription': '사진 촬영을 위해 카메라 접근 권한이 필요합니다.',
        'NSMicrophoneUsageDescription': '영상 촬영을 위해 마이크 접근 권한이 필요합니다.',
        'NSHighResolutionCapable': 'True'
    },
)