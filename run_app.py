import os
import sys
import threading
import time
import webview
from django.core.management import execute_from_command_line

# -------------------------------------------------------------------
# [중요] PyInstaller 경로 설정 함수
# -------------------------------------------------------------------
def resource_path(relative_path):
    """ PyInstaller 임시 폴더(_MEIPASS) 또는 현재 폴더 절대 경로 반환 """
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

# Django 설정 모듈 지정
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'main.settings')

def run_django():
    try:
        # PyInstaller 환경에서는 manage.py 파일이 없으므로 sys.argv를 직접 구성해야 함
        # runserver 구동
        print("--> [System] Starting Django Server...")
        
        # 0.0.0.0으로 열어야 외부 접속 차단 문제를 덜 겪음 (내부적으로는 localhost로 접속)
        # --insecure: DEBUG=False 상태에서도 static 파일 서빙
        sys.argv = ['manage.py', 'runserver', '0.0.0.0:8000', '--noreload', '--insecure']
        
        execute_from_command_line(sys.argv)
    except Exception as e:
        print(f"--> [Error] Django Server Failed: {e}")

def start_app():
    # 1. 별도 스레드에서 장고 서버 실행
    t = threading.Thread(target=run_django)
    t.daemon = True
    t.start()

    # 2. 서버 부팅 대기 (여유 있게)
    time.sleep(2)

    # 3. pywebview 창 띄우기
    # macOS에서는 localhost HTTP 접속 시에도 카메라 권한이 필요함
    webview.create_window(
        title='인생네컷 Photo Booth',
        url='http://localhost:8000/startpage', # settings.py 포트와 일치시킬 것
        fullscreen=True,
        width=1080, height=1920,
        text_select=False,
        confirm_close=True
    )
    
    # debug=True: 개발자 도구(F12) 활성화 (배포 시 False 권장하나 에러 확인용으로 True 유지)
    webview.start(debug=True)

if __name__ == '__main__':
    # [중요] PyInstaller 실행 시 경로 보정
    if getattr(sys, 'frozen', False):
        # 템플릿/스태틱 파일을 찾기 위해 _MEIPASS를 기본 경로로 인식시킴
        sys.path.append(sys._MEIPASS)
        # DB 저장 등을 위해 실행 파일 위치로 작업 디렉토리 변경 (선택 사항)
        # os.chdir(os.path.dirname(sys.executable)) 
    
    start_app()