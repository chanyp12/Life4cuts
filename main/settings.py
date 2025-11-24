import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ------------------------------------------------------------------
# [핵심 1] PyInstaller 및 경로 설정
# ------------------------------------------------------------------
if getattr(sys, 'frozen', False):
    # 1. 읽기 전용 (EXE 내부 압축 해제 경로: 템플릿, 코드, 정적파일)
    BASE_DIR = Path(sys._MEIPASS)
    
    # 2. 쓰기 전용 (실제 맥 문서 폴더: DB, 촬영된 사진 저장)
    # Mac 앱 내부는 읽기 전용이거나 서명 문제로 쓰기가 막힐 수 있어 Documents 폴더 사용 권장
    DATA_DIR = Path(os.path.expanduser("~/Documents/Life4Cut_Data"))
    DATA_DIR.mkdir(parents=True, exist_ok=True)
else:
    # 개발 환경 (python manage.py runserver)
    BASE_DIR = Path(__file__).resolve().parent.parent
    DATA_DIR = BASE_DIR

# ------------------------------------------------------------------
# 기본 Django 설정
# ------------------------------------------------------------------
SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-key-dev')

# EXE 단독 실행 시 정적 파일(CSS/JS) 서빙을 위해 True 필수
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
        'DIRS': [BASE_DIR / 'clientapp' / 'templates'], # BASE_DIR 기준
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
# Static Files (읽기 전용 - BASE_DIR)
# ------------------------------------------------------------------
STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'clientapp' / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

# ★ [수정] 여기가 없어서 에러가 났었습니다. 추가 완료! ★
FRAMES_DIR = BASE_DIR / 'clientapp' / 'static' / 'frames'
BACKGROUND_DIR = BASE_DIR / 'clientapp' / 'static' / 'background'
STICKERS_DIR = BASE_DIR / 'clientapp' / 'static' / 'stickers'

# 캡처 설정
CAPTURE_DELAY_MS = 5000

# ------------------------------------------------------------------
# Media Files (쓰기 전용 - DATA_DIR)
# ------------------------------------------------------------------
MEDIA_URL = '/media/'
MEDIA_ROOT = DATA_DIR / 'media'

CAPTURE_DIR = MEDIA_ROOT / 'captures'
OUTPUT_DIR = MEDIA_ROOT / 'outputs'

# 폴더 자동 생성
CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ------------------------------------------------------------------
# 기타
# ------------------------------------------------------------------
LANGUAGE_CODE = 'ko-kr'
TIME_ZONE = 'Asia/Seoul'
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'