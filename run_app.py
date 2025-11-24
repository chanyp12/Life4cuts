import os
import sys
import threading
import time
import webview
from django.core.management import execute_from_command_line

# 설정 파일 경로 지정
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'main.settings')

def run_django():
    """Django 서버 실행 및 DB 초기화"""
    try:
        import django
        from django.core.management import call_command
        
        print("--> [System] Initializing Django...")
        django.setup() 
        
        print("--> [System] Checking Database Migrations...")
        # DB 테이블 자동 생성
        call_command('migrate', interactive=False)
        
        print("--> [System] Starting Django Server...")
        # 디버그 모드여도 --insecure로 정적파일 서빙 보장
        sys.argv = ['manage.py', 'runserver', '0.0.0.0:8000', '--noreload', '--insecure']
        execute_from_command_line(sys.argv)
        
    except Exception as e:
        print(f"--> [Error] Server Failed: {e}")

def start_app():
    # 1. 서버 스레드 시작
    t = threading.Thread(target=run_django)
    t.daemon = True
    t.start()

    # 2. 서버 부팅 대기 (2초)
    time.sleep(2)

    # 3. 앱 창 띄우기
    window = webview.create_window(
        title='인생네컷 Photo Booth',
        url='http://localhost:8000', 
        fullscreen=True,
        width=1080, height=1920,
        text_select=False,
        confirm_close=True
    )
    
    # [수정] debug=False로 설정하여 우측 개발자 도구 제거
    webview.start(debug=False)

if __name__ == '__main__':
    # PyInstaller 환경 경로 보정
    if getattr(sys, 'frozen', False):
        sys.path.append(sys._MEIPASS)
        
    start_app()