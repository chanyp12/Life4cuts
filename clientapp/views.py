import json
import os
import sys
import base64
import uuid
from urllib.parse import urlparse
from datetime import datetime
from pathlib import Path

from django.templatetags.static import static
from django.utils import timezone
from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import ensure_csrf_cookie
from django.conf import settings

# 이미지 합성 함수 가져오기
try:
    from utils.combine_photo_v2 import combine_with_frame
except ImportError:
    import sys
    sys.path.append(str(settings.BASE_DIR))
    from utils.combine_photo_v2 import combine_with_frame

# -----------------------
# 경로 및 로딩 헬퍼 함수 (앱 패키지 대응 버전)
# -----------------------

def _get_base_path():
    """
    [핵심 수정] 실행 환경에 따른 최상위 루트 경로 반환
    """
    if getattr(sys, 'frozen', False):
        # 실행 파일 경로: .../Life4Cut.app/Contents/MacOS/Life4Cut
        executable_path = Path(sys.executable)
        
        # Case 1: Mac App Bundle (.app) 실행 중일 때
        # .app 폴더와 나란히 있는 static을 찾으려면 4단계 위로 올라가야 함
        # .parent(MacOS) -> .parent(Contents) -> .parent(AppBundle) -> .parent(Root)
        mac_app_root = executable_path.parent.parent.parent.parent
        if (mac_app_root / 'static').exists():
            return mac_app_root
            
        # Case 2: 일반 PyInstaller OneDir/OneFile 실행 (Unix Executable)
        # 실행 파일 바로 옆을 가리킴
        return executable_path.parent
    else:
        # 개발 환경 (python manage.py runserver)
        return settings.BASE_DIR

def _get_frames_root():
    """static/frames 폴더의 절대 경로"""
    return _get_base_path() / 'static' / 'frames'

def _get_output_paths():
    """결과물 저장 경로 (Output/YYYYMMDD/img)"""
    today_str = datetime.now().strftime("%Y%m%d")
    
    # 앱 패키지 밖(사용자가 보는 폴더)에 Output 폴더 생성
    base_output = _get_base_path() / 'Output' / today_str
    img_dir = base_output / 'img'
    video_dir = base_output / 'video'
    
    img_dir.mkdir(parents=True, exist_ok=True)
    video_dir.mkdir(parents=True, exist_ok=True)
    
    return img_dir, video_dir

def _clear_captures_in_session(request):
    request.session['captured_urls'] = []
    request.session['captured_videos'] = []
    request.session.modified = True

def _media_url_to_path(u: str):
    if not u: return None
    if u.startswith('file://'): return u[7:] if os.path.exists(u[7:]) else None
    
    if u.startswith(settings.MEDIA_URL):
        rel = u[len(settings.MEDIA_URL):]
        fs_path = settings.MEDIA_ROOT / rel
        return str(fs_path) if fs_path.exists() else None
    return None

def _common_stickers_dir():
    return _get_frames_root() / 'stickers'

def _slots_path(mode: str, theme: str):
    return _get_frames_root() / mode / theme / 'slots.json'

def _load_meta(mode: str, theme: str) -> dict:
    path = _slots_path(mode, theme)
    default_meta = {'canvas': {'width': 1000, 'height': 1500}, 'slots': []}
    if not path.exists(): return default_meta
    try:
        meta = json.loads(path.read_text(encoding='utf-8'))
        meta.setdefault('canvas', {'width': 1000, 'height': 1500})
        meta.setdefault('slots', [])
        return meta
    except: return default_meta

def _save_meta(mode: str, theme: str, meta: dict):
    path = _slots_path(mode, theme)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')

def _get_capture_delay(meta: dict) -> int:
    default = getattr(settings, 'CAPTURE_DELAY_MS', 5000)
    return int(meta.get('capture_delay_ms', default))

# -----------------------
# Views
# -----------------------
def index(request):
    return redirect('startpage')

@ensure_csrf_cookie
def startpage(request):
    base_url = static('background/sample-start.png')
    return render(request, 'startpage.html', {'bg_url': base_url})

@ensure_csrf_cookie
def select_shot(request):
    return render(request, 'select_shot.html')

@ensure_csrf_cookie
def select_theme(request):
    try: count = int(request.GET.get('count', '3'))
    except: count = 3
    if count not in (3, 4): count = 3

    # [확인] 4컷 -> 4x1 사용
    mode = '3x1' if count == 3 else '4x1'

    request.session['shot_count'] = count
    request.session['mode'] = mode
    _clear_captures_in_session(request)

    themes = []
    frames_root = _get_frames_root()
    mode_dir = frames_root / mode
    
    # 디버깅 로그 (서버 콘솔 확인용)
    print(f"\n[DEBUG] select_theme - 현재 탐색 경로: {mode_dir}")

    if mode_dir.exists():
        for theme_path in sorted(mode_dir.iterdir()):
            if theme_path.is_dir():
                frame_file = theme_path / 'frame.png'
                if frame_file.exists():
                    themes.append({
                        'name': theme_path.name,
                        'thumb': f"/static/frames/{mode}/{theme_path.name}/frame.png",
                        'mode': mode
                    })
                else:
                    print(f"[SKIP] frame.png 없음: {theme_path.name}")
    else:
        print(f"[ERROR] 경로가 존재하지 않음: {mode_dir}")

    # 만약 여전히 못 찾을 경우를 대비해, 템플릿에 현재 탐색 중인 경로를 보여줌
    return render(request, 'select_theme.html', {
        'themes': themes, 
        'count': count, 
        'mode': mode,
        'debug_path': str(mode_dir) 
    })

@ensure_csrf_cookie
def camera(request):
    mode = request.session.get('mode', '3x1')
    theme = request.GET.get('theme') or request.session.get('theme')
    if not theme: return redirect('select_theme')

    request.session['theme'] = theme
    _clear_captures_in_session(request)

    meta = _load_meta(mode, theme)
    capture_delay_ms = _get_capture_delay(meta)
    
    if meta['slots']:
        s0 = meta['slots'][0]
        guide_ratio = s0['w'] / s0['h']
    else:
        guide_ratio = 1.5 if '3x1' in mode else 1.33

    return render(request, 'camera.html', {
        'count': request.session.get('shot_count', 3),
        'mode': mode,
        'theme': theme,
        'guide_ratio': guide_ratio,
        'capture_delay_ms': capture_delay_ms,
        'meta_json': json.dumps(meta),
    })

@require_POST
def upload_capture(request):
    data_url = request.POST.get('data_url')
    video_file = request.FILES.get('video')
    if not data_url: return JsonResponse({'saved': False}, status=400)

    # 임시 캡처도 앱 패키지 밖(또는 실행 위치) 기준으로 저장
    base_path = _get_base_path()
    # settings.MEDIA_ROOT가 절대 경로가 아니면 base_path와 결합
    # 여기서는 간단하게 base_path 아래 'captures' 생성
    save_dir = base_path / 'temp_captures'
    
    save_dir.mkdir(parents=True, exist_ok=True)
    
    urls = request.session.get('captured_urls', [])
    video_urls = request.session.get('captured_videos', [])

    try:
        if ',' in data_url: header, b64data = data_url.split(',', 1)
        else: b64data = data_url
        fname_img = f"{uuid.uuid4().hex}.jpg"
        with open(save_dir / fname_img, 'wb') as f: f.write(base64.b64decode(b64data))
        # 웹 서빙을 위해 MEDIA_URL 매핑이 필요하지만, 일단은 파일 저장 성공 여부 확인
        # 실제 서빙은 Django runserver의 static/media 설정을 따름
        # 임시 방편: settings.MEDIA_URL 사용
        urls.append(f"{settings.MEDIA_URL}captures/{fname_img}")
    except Exception as e:
        print(f"Save Error: {e}")
        return JsonResponse({'saved': False}, status=500)

    if video_file:
        try:
            fname_vid = f"{uuid.uuid4().hex}.webm"
            with open(save_dir / fname_vid, 'wb+') as dest:
                for chunk in video_file.chunks(): dest.write(chunk)
            video_urls.append(f"{settings.MEDIA_URL}captures/{fname_vid}")
        except: video_urls.append(None)
    else: video_urls.append(None)

    request.session['captured_urls'] = urls
    request.session['captured_videos'] = video_urls
    request.session.modified = True
    return JsonResponse({'saved': True, 'count': len(urls)})

@ensure_csrf_cookie
def preview(request):
    mode = request.session.get('mode')
    theme = request.session.get('theme')
    if not mode or not theme: return redirect('startpage')
    meta = _load_meta(mode, theme)
    captured = request.session.get('captured_urls', [])
    return render(request, 'preview.html', {
        'mode': mode, 'theme': theme,
        'captured_json': json.dumps(captured),
        'frame_url': f"/static/frames/{mode}/{theme}/frame.png",
        'layout_url': f"/static/frames/{mode}/{theme}/layout/layout.png",
        'meta_json': json.dumps(meta)
    })

@require_POST
def prepare_decorate(request):
    try:
        body = json.loads(request.body.decode('utf-8'))
        request.session['mapping_urls'] = body.get('mapping', [])
        request.session.modified = True
        return JsonResponse({'ok': True})
    except: return HttpResponseBadRequest('Error')

@ensure_csrf_cookie
def decorate(request):
    mode = request.session.get('mode')
    theme = request.session.get('theme')
    mapping_urls = request.session.get('mapping_urls', [])
    if not mode or not theme: return redirect('startpage')

    meta = _load_meta(mode, theme)
    images_fs = [_media_url_to_path(u) for u in mapping_urls]
    
    # 임시 합성 결과
    out_dir = _get_base_path() / 'temp_outputs'
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = f"base_{uuid.uuid4().hex[:8]}.jpg"
    out_path = out_dir / fname
    
    try:
        frame_png = _get_frames_root() / mode / theme / 'frame.png'
        combine_with_frame(str(frame_png), {**meta, 'stickers': []}, images_fs, str(out_path), [], None)
    except Exception as e: print(f"Base Compose Error: {e}")

    base_url = f"{settings.MEDIA_URL}temp_outputs/{fname}" # URL 매핑 주의
    
    sticker_ids = []
    sdir = _common_stickers_dir()
    if sdir.exists(): sticker_ids = [p.stem for p in sorted(sdir.glob('*.png'))]

    return render(request, 'decorate.html', {
        'mode': mode, 'theme': theme,
        'base_url': base_url,
        'canvas_json': json.dumps(meta['canvas']),
        'sticker_ids_json': json.dumps(sticker_ids)
    })

@require_POST
def finalize(request):
    try:
        body = json.loads(request.body.decode('utf-8'))
        stickers = body.get('stickers', [])
        request.session['final_stickers'] = stickers
        
        mode = request.session.get('mode')
        theme = request.session.get('theme')
        mapping = request.session.get('mapping_urls', [])
        
        # [핵심] 저장 경로 자동 탐색된 위치 사용
        img_dir, video_dir = _get_output_paths()
        
        timestamp = datetime.now().strftime("%H%M%S")
        unique_id = uuid.uuid4().hex[:6]
        fname_img = f"final_{timestamp}_{unique_id}.jpg"
        out_path = img_dir / fname_img
        
        images_fs = [_media_url_to_path(u) for u in mapping]
        frame_png = _get_frames_root() / mode / theme / 'frame.png'
        sticker_dir = _common_stickers_dir()
        meta = _load_meta(mode, theme)
        
        combine_with_frame(str(frame_png), meta, images_fs, str(out_path), stickers, str(sticker_dir))
        
        print(f"====== [저장 성공] 파일 위치: {out_path} ======")
        request.session['last_output_path'] = str(out_path)
        request.session.modified = True
        return JsonResponse({'saved': True})
    except Exception as e:
        print(f"Finalize Error: {e}")
        return JsonResponse({'saved': False}, status=500)

# 관리자/인쇄 페이지
@ensure_csrf_cookie
def admin_mode(request):
    frames_root = _get_frames_root()
    mode_themes = {}
    if frames_root.exists():
        for mode_dir in sorted(frames_root.iterdir()):
            if not mode_dir.is_dir() or mode_dir.name == 'stickers': continue
            themes = []
            for theme_dir in sorted(mode_dir.iterdir()):
                if theme_dir.is_dir() and (theme_dir / 'frame.png').exists():
                    themes.append(theme_dir.name)
            if themes: mode_themes[mode_dir.name] = themes

    mode = request.GET.get('mode')
    if not mode or mode not in mode_themes: mode = next(iter(mode_themes)) if mode_themes else None
    theme = request.GET.get('theme')
    themes = mode_themes.get(mode, [])
    if not theme or theme not in themes: theme = themes[0] if themes else None

    meta = _load_meta(mode, theme) if (mode and theme) else {'canvas':{'width':0,'height':0},'slots':[]}
    frame_url = f"/static/frames/{mode}/{theme}/frame.png" if (mode and theme) else ""
    layout_url = f"/static/frames/{mode}/{theme}/layout/layout.png" if (mode and theme) else ""

    return render(request, 'admin_mode.html', {
        'mode': mode, 'theme': theme, 'modes': list(mode_themes.keys()),
        'themes': themes, 'frame_url': frame_url, 'layout_url': layout_url,
        'meta_json': json.dumps(meta), 'capture_delay_ms': _get_capture_delay(meta)
    })

@require_POST
def admin_save_slots(request):
    try:
        body = json.loads(request.body.decode('utf-8'))
        mode = body.get('mode'); theme = body.get('theme')
        meta = _load_meta(mode, theme)
        meta['slots'] = body.get('slots')
        meta['capture_delay_ms'] = body.get('capture_delay_ms')
        _save_meta(mode, theme, meta)
        return JsonResponse({'saved': True})
    except Exception as e: return JsonResponse({'saved': False, 'error': str(e)}, status=500)

@ensure_csrf_cookie
def printing(request):
    final_path = request.session.get('last_output_path')
    final_url = None
    if final_path and str(settings.MEDIA_ROOT) in final_path:
        final_url = settings.MEDIA_URL + os.path.relpath(final_path, settings.MEDIA_ROOT).replace(os.sep, '/')

    mode = request.session.get('mode')
    theme = request.session.get('theme')
    meta = _load_meta(mode, theme)
    stickers = request.session.get('final_stickers', [])
    
    mapping = request.session.get('mapping_urls', [])
    captures = request.session.get('captured_urls', [])
    videos = request.session.get('captured_videos', [])
    
    mapped_videos = []
    for m_url in mapping:
        idx = captures.index(m_url) if m_url in captures else -1
        mapped_videos.append(videos[idx] if idx >= 0 and idx < len(videos) else None)

    return render(request, 'printing.html', {
        'final_url': final_url, 'mode': mode, 'theme': theme,
        'frame_url': f"/static/frames/{mode}/{theme}/frame.png",
        'layout_url': f"/static/frames/{mode}/{theme}/layout/layout.png",
        'meta_json': json.dumps(meta), 'stickers_json': json.dumps(stickers),
        'mapped_videos_json': json.dumps(mapped_videos)
    })