import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# .env 로드
load_dotenv()

# ------------------------------------------------------------------
# [핵심 수정] PyInstaller 배포 시 경로 설정
# ------------------------------------------------------------------
# sys.frozen이 True면 exe로 실행 중인 상태입니다.
if getattr(sys, 'frozen', False):
    # 1. 읽기 전용 (템플릿, 정적파일 등 EXE 안에 압축된 파일들)
    # PyInstaller는 임시 폴더(_MEIPASS)에 파일들을 풉니다.
    BASE_DIR = Path(sys._MEIPASS)
    
    # 2. 쓰기 전용 (저장될 사진, DB 등)
    # EXE 파일이 위치한 실제 폴더 경로를 잡습니다. (데이터 보존용)
    DATA_DIR = Path(sys.executable).parent
else:
    # 일반 개발 환경 (python manage.py runserver)
    BASE_DIR = Path(__file__).resolve().parent.parent
    DATA_DIR = BASE_DIR

# ------------------------------------------------------------------

SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret')

# 배포 시엔 False 권장이지만, 로컬 EXE 단독 구동용이면 True도 괜찮습니다.
# False로 설정하면 run_app.py에서 --insecure 옵션이 필수입니다.
# DEBUG = os.getenv('DEBUG', 'True') == 'True'
DEBUG = True
# ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', '*').split(',')
ALLOWED_HOSTS = ['*']  # 혹은 ['localhost', '127.0.0.1']

# main/settings.py

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'clientapp',
    # 'sslserver',  # <--- [추가] 이거 한 줄만 넣으면 됩니다.
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'main.urls'

TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [BASE_DIR / 'clientapp' / 'templates'],
    'APP_DIRS': True,
    'OPTIONS': {'context_processors':[
        'django.template.context_processors.debug',
        'django.template.context_processors.request',
        'django.contrib.auth.context_processors.auth',
        'django.contrib.messages.context_processors.messages',
    ]},
}]

WSGI_APPLICATION = 'main.wsgi.application'

# ------------------------------------------------------------------
# Database
# ------------------------------------------------------------------
# DB는 EXE를 꺼도 데이터가 남아야 하므로 DATA_DIR(실제 폴더)에 저장
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': DATA_DIR / 'db.sqlite3', 
    }
}

# ------------------------------------------------------------------
# Static Files (CSS, JS, Images - 읽기 전용)
# ------------------------------------------------------------------
STATIC_URL = '/static/'

# 개발/배포 환경 모두 BASE_DIR(내부 압축 경로)를 바라보게 함
STATICFILES_DIRS = [BASE_DIR / 'clientapp' / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

# 프레임/배경/스티커 등 읽기 전용 리소스 경로
FRAMES_DIR = BASE_DIR / 'clientapp' / 'static' / 'frames'
BACKGROUND_DIR = BASE_DIR / 'clientapp' / 'static' / 'background'
STICKERS_DIR = BASE_DIR / 'clientapp' / 'static' / 'stickers'

# ------------------------------------------------------------------
# Media Files (Captures, Outputs - 쓰기 전용)
# ------------------------------------------------------------------
# ★중요★: 사진은 EXE를 종료해도 사라지면 안 되므로 DATA_DIR(실제 폴더)에 저장
MEDIA_URL = '/media/'
MEDIA_ROOT = DATA_DIR / 'media'

CAPTURE_DIR = MEDIA_ROOT / 'captures'
OUTPUT_DIR = MEDIA_ROOT / 'outputs'

# 폴더가 없으면 생성
CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ------------------------------------------------------------------
# 기타 설정
# ------------------------------------------------------------------
LANGUAGE_CODE = 'ko-kr'
TIME_ZONE = 'Asia/Seoul'
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# 캡처 딜레이 (중복 정의 제거함)
CAPTURE_DELAY_MS = int(os.getenv('CAPTURE_DELAY_MS', '5000'))