import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ------------------------------------------------------------------
# [핵심 1] PyInstaller 및 경로 설정 (실행 파일 이동 대응)
# ------------------------------------------------------------------
if getattr(sys, 'frozen', False):
    # 1. 읽기 전용 (EXE 내부 압축 해제 경로: 코드, 템플릿 등)
    BASE_DIR = Path(sys._MEIPASS)
    
    # 2. 실행 파일 위치 (EXE 파일이 있는 실제 폴더)
    if sys.platform == 'darwin' and '.app' in sys.executable:
        # Mac App Bundle의 경우 .app 번들 폴더가 있는 위치를 기준으로 잡음
        EXEC_DIR = Path(sys.executable).parent.parent.parent.parent
    else:
        # Windows/Linux
        EXEC_DIR = Path(sys.executable).parent
    
    # 3. 데이터 저장 경로 (수정됨: 실행 파일 옆 'Data' 폴더 사용)
    # Documents 폴더 대신 실행 파일 옆에 저장하여 권한 문제 해결 및 경로 단순화
    DATA_DIR = EXEC_DIR / 'Data'
    DATA_DIR.mkdir(parents=True, exist_ok=True)
else:
    # 개발 환경
    BASE_DIR = Path(__file__).resolve().parent.parent
    EXEC_DIR = BASE_DIR
    DATA_DIR = BASE_DIR

# ------------------------------------------------------------------
# 기본 Django 설정
# ------------------------------------------------------------------
SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-key-dev')

DEBUG = True 

ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'clientapp', 
    'main',
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

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'], 
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'main.wsgi.application'

# ------------------------------------------------------------------
# Database (DATA_DIR에 저장)
# ------------------------------------------------------------------
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': DATA_DIR / 'db.sqlite3', 
    }
}

# ------------------------------------------------------------------
# Static Files
# ------------------------------------------------------------------
STATIC_URL = 'static/'

if getattr(sys, 'frozen', False):
    STATICFILES_DIRS = [EXEC_DIR / 'static']
else:
    STATICFILES_DIRS = [BASE_DIR / 'static']

STATIC_ROOT = BASE_DIR / 'staticfiles'

FRAMES_DIR = EXEC_DIR / 'static' / 'frames'
BACKGROUND_DIR = EXEC_DIR / 'static' / 'background'
STICKERS_DIR = EXEC_DIR / 'static' / 'stickers'

CAPTURE_DELAY_MS = 5000

# ------------------------------------------------------------------
# Media Files (촬영 사진 저장소)
# ------------------------------------------------------------------
MEDIA_URL = '/media/'
MEDIA_ROOT = DATA_DIR / 'media'

CAPTURE_DIR = MEDIA_ROOT / 'captures'
OUTPUT_DIR = MEDIA_ROOT / 'outputs' 

try:
    CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
except Exception as e:
    print(f"Media folder creation failed: {e}")

# ------------------------------------------------------------------
# 기타
# ------------------------------------------------------------------
LANGUAGE_CODE = 'ko-kr'
TIME_ZONE = 'Asia/Seoul'
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'