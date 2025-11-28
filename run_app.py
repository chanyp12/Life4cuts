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
        # [추가된 부분] 서버 시작 전 자동으로 DB 테이블 생성(Migration) 수행
        # ---------------------------------------------------------
        import django
        from django.core.management import call_command
        
        print("--> [System] Initializing Django...")
        django.setup() # 장고 설정 로드
        
        print("--> [System] Checking Database Migrations...")
        # DB가 비어있거나 변경사항이 있으면 자동으로 테이블 생성
        call_command('migrate', interactive=False)
        print("--> [System] Database ready.")
        # ---------------------------------------------------------

        print("--> [System] Starting Django Server...")
        # runserver 실행
        sys.argv = ['manage.py', 'runserver', '0.0.0.0:8000', '--noreload', '--insecure']
        execute_from_command_line(sys.argv)
        
    except Exception as e:
        print(f"--> [Error] Server Failed: {e}")

def start_app():
    # 1. 서버 스레드 시작
    t = threading.Thread(target=run_django)
    t.daemon = True
    t.start()

    # 2. 서버 부팅 및 마이그레이션 대기 (시간을 조금 넉넉히 줌)
    time.sleep(3)

    # 3. 앱 창 띄우기
    webview.create_window(
        title='인생네컷 Photo Booth',
        url='http://localhost:8000', 
        fullscreen=True,
        width=1080, height=1920,
        text_select=False,
        confirm_close=True
    )
    
    # debug=True 유지 (에러 확인용)
    webview.start(debug=False)

if __name__ == '__main__':
    # PyInstaller 환경에서 경로 보정
    if getattr(sys, 'frozen', False):
        sys.path.append(sys._MEIPASS)
        
    start_app()