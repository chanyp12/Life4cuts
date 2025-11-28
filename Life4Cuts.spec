# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['run_app.py'],
    pathex=[],
    binaries=[],
    datas=[
        # 템플릿과 스태틱 파일을 EXE 안에 포함
        ('clientapp/templates', 'clientapp/templates'),
        ('clientapp/static', 'clientapp/static'),
    ],
    hiddenimports=[],
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
    console=False, # 터미널 창 숨기기
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Life4Cut',
)

# ★ [중요] Mac 앱 권한 설정 ★
app = BUNDLE(
    coll,
    name='Life4Cut.app',
    icon=None,
    bundle_identifier='com.chanyp12.life4cut',
    info_plist={
        'NSCameraUsageDescription': '사진 촬영을 위해 카메라 접근이 필요합니다.',
        'NSMicrophoneUsageDescription': '영상 녹화를 위해 마이크 접근이 필요합니다.',
        'NSHighResolutionCapable': 'True',
        'NSAppTransportSecurity': {
            'NSAllowsArbitraryLoads': True # 로컬호스트 HTTP 허용
        }
    },
)