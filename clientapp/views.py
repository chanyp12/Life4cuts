import json
import os
import base64
import uuid
from urllib.parse import urlparse

from django.templatetags.static import static
from django.utils import timezone
from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import ensure_csrf_cookie
from django.conf import settings

# utils 폴더에 combine_photo_v2.py가 있다고 가정
from utils.combine_photo_v2 import combine_with_frame


# -----------------------
# Helpers
# -----------------------
def _clear_captures_in_session(request):
    request.session['captured_urls'] = []
    request.session['captured_videos'] = []
    request.session.modified = True

def _media_url_to_path(u: str):
    if not u: return None
    if u.startswith('file://'): return u[7:] if os.path.exists(u[7:]) else None
    if u.startswith('http') or u.startswith('/'):
        u_path = urlparse(u).path
        if u_path.startswith(settings.MEDIA_URL):
            rel = u_path[len(settings.MEDIA_URL):]
            fs_path = os.path.join(settings.MEDIA_ROOT, rel)
            return fs_path if os.path.exists(fs_path) else None
    return None

def _slots_path(mode: str, theme: str):
    return settings.FRAMES_DIR / mode / theme / 'slots.json'

def _common_stickers_dir():
    """
    [수정됨] 스티커는 공용 폴더 사용: /static/frames/stickers
    settings.FRAMES_DIR = BASE_DIR / 'static' / 'frames' 라고 가정
    """
    return settings.FRAMES_DIR / 'stickers'

def _load_meta(mode: str, theme: str) -> dict:
    path = _slots_path(mode, theme)
    default_meta = {'canvas': {'width': 1000, 'height': 1500}, 'slots': []}
    if not path.exists():
        return default_meta
    try:
        meta = json.loads(path.read_text(encoding='utf-8'))
        meta.setdefault('canvas', {'width': 1000, 'height': 1500})
        meta.setdefault('slots', [])
        return meta
    except:
        return default_meta

def _save_meta(mode: str, theme: str, meta: dict):
    path = _slots_path(mode, theme)
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

    mode = '3x1' if count == 3 else '4x4'
    request.session['shot_count'] = count
    _clear_captures_in_session(request)

    themes = []
    frame_root = settings.FRAMES_DIR / mode
    if frame_root.exists():
        for theme_dir in frame_root.iterdir():
            if theme_dir.is_dir() and (theme_dir / 'frame.png').exists():
                themes.append({
                    'name': theme_dir.name,
                    'thumb': f"/static/frames/{mode}/{theme_dir.name}/frame.png",
                    'mode': mode
                })

    return render(request, 'select_theme.html', {'themes': themes, 'count': count})

@ensure_csrf_cookie
def camera(request):
    count = int(request.session.get('shot_count', 3))
    mode = '3x1' if count == 3 else '4x4'
    theme = request.GET.get('theme') or request.session.get('theme')
    
    if not theme: return redirect('select_theme')

    request.session['theme'] = theme
    request.session['mode'] = mode
    _clear_captures_in_session(request)

    meta = _load_meta(mode, theme)
    capture_delay_ms = _get_capture_delay(meta)
    
    if meta['slots']:
        s0 = meta['slots'][0]
        guide_ratio = s0['w'] / s0['h']
    else:
        guide_ratio = 1.5 if count == 3 else 1.33

    return render(request, 'camera.html', {
        'count': count,
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

    if not data_url:
        return JsonResponse({'saved': False, 'reason': 'no_image'}, status=400)

    shot_total = int(request.session.get('shot_count', 4))
    urls = request.session.get('captured_urls', [])
    video_urls = request.session.get('captured_videos', [])

    if len(urls) >= shot_total:
        return JsonResponse({'saved': False, 'reason': 'limit', 'count': len(urls)})

    settings.CAPTURE_DIR.mkdir(parents=True, exist_ok=True)

    try:
        if ',' in data_url: header, b64data = data_url.split(',', 1)
        else: b64data = data_url
        
        fname_img = f"{uuid.uuid4().hex}.jpg"
        path_img = settings.CAPTURE_DIR / fname_img
        with open(path_img, 'wb') as f: f.write(base64.b64decode(b64data))
        
        urls.append(f"{settings.MEDIA_URL}captures/{fname_img}")
    except Exception as e:
        return JsonResponse({'saved': False}, status=500)

    if video_file:
        try:
            fname_vid = f"{uuid.uuid4().hex}.webm"
            path_vid = settings.CAPTURE_DIR / fname_vid
            with open(path_vid, 'wb+') as dest:
                for chunk in video_file.chunks(): dest.write(chunk)
            video_urls.append(f"{settings.MEDIA_URL}captures/{fname_vid}")
        except:
            video_urls.append(None)
    else:
        video_urls.append(None)

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
    except:
        return HttpResponseBadRequest('Error')

@ensure_csrf_cookie
def decorate(request):
    mode = request.session.get('mode')
    theme = request.session.get('theme')
    mapping_urls = request.session.get('mapping_urls', [])
    if not mode or not theme: return redirect('startpage')

    meta = _load_meta(mode, theme)
    
    images_fs = [_media_url_to_path(u) for u in mapping_urls]
    
    rel_dir = 'temp_outputs'
    out_dir = settings.MEDIA_ROOT / rel_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    
    fname = f"base_{uuid.uuid4().hex[:8]}.jpg"
    out_path = out_dir / fname
    
    frame_png = settings.FRAMES_DIR / mode / theme / 'frame.png'
    
    try:
        combine_with_frame(
            frame_png=str(frame_png),
            meta={**meta, 'stickers': []},
            images=images_fs,
            out_path=str(out_path),
            stickers=[], stickers_dir=None
        )
    except Exception as e:
        print(f"Base Compose Error: {e}")

    base_url = f"{settings.MEDIA_URL}{rel_dir}/{fname}"

    # [수정] 공용 스티커 폴더 스캔
    sticker_ids = []
    sdir = _common_stickers_dir()
    if sdir.exists():
        sticker_ids = [p.stem for p in sorted(sdir.glob('*.png'))]

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
        
        images_fs = [_media_url_to_path(u) for u in mapping]
        
        settings.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        fname = f"final_{uuid.uuid4().hex}.jpg"
        out_path = settings.OUTPUT_DIR / fname
        
        frame_png = settings.FRAMES_DIR / mode / theme / 'frame.png'
        sticker_dir = _common_stickers_dir() # [수정] 공용 폴더
        meta = _load_meta(mode, theme)
        
        combine_with_frame(
            frame_png=str(frame_png),
            meta=meta,
            images=images_fs,
            out_path=str(out_path),
            stickers=stickers,
            stickers_dir=str(sticker_dir)
        )
        
        request.session['last_output_path'] = str(out_path)
        request.session.modified = True
        
        return JsonResponse({'saved': True})
    except Exception as e:
        print(e)
        return JsonResponse({'saved': False}, status=500)

# ==========================================
# 관리자 모드 View
# ==========================================
@ensure_csrf_cookie
def admin_mode(request):
    frames_root = settings.FRAMES_DIR
    mode_themes = {}
    
    if frames_root.exists():
        # 1단계: 모드 폴더(3x1, 4x4) 스캔
        for mode_dir in frames_root.iterdir():
            if not mode_dir.is_dir(): continue
            if mode_dir.name == 'stickers': continue # 스티커 폴더 제외
            
            themes = []
            # 2단계: 테마 폴더 스캔
            for theme_dir in mode_dir.iterdir():
                if theme_dir.is_dir() and (theme_dir / 'frame.png').exists():
                    themes.append(theme_dir.name)
            
            if themes:
                mode_themes[mode_dir.name] = themes

    # 선택 로직
    mode = request.GET.get('mode')
    if not mode or mode not in mode_themes:
        mode = next(iter(mode_themes)) if mode_themes else None
        
    theme = request.GET.get('theme')
    themes = mode_themes.get(mode, [])
    if not theme or theme not in themes:
        theme = themes[0] if themes else None

    meta = _load_meta(mode, theme) if (mode and theme) else {'canvas':{'width':0,'height':0},'slots':[]}
    
    frame_url = f"/static/frames/{mode}/{theme}/frame.png" if (mode and theme) else ""
    layout_url = f"/static/frames/{mode}/{theme}/layout/layout.png" if (mode and theme) else ""

    return render(request, 'admin_mode.html', {
        'mode': mode,
        'theme': theme,
        'modes': list(mode_themes.keys()),
        'themes': themes,
        'frame_url': frame_url,
        'layout_url': layout_url,
        'meta_json': json.dumps(meta),
        'capture_delay_ms': _get_capture_delay(meta)
    })

@require_POST
def admin_save_slots(request):
    try:
        body = json.loads(request.body.decode('utf-8'))
        mode = body.get('mode')
        theme = body.get('theme')
        slots = body.get('slots')
        delay = body.get('capture_delay_ms')
        
        meta = _load_meta(mode, theme)
        meta['slots'] = slots
        meta['capture_delay_ms'] = delay
        _save_meta(mode, theme, meta)
        
        return JsonResponse({'saved': True})
    except Exception as e:
        return JsonResponse({'saved': False, 'error': str(e)}, status=500)

# ==========================================
# 인쇄 페이지 View
# ==========================================
@ensure_csrf_cookie
def printing(request):
    # 1. 최종 이미지 경로 (다운로드용)
    final_path = request.session.get('last_output_path')
    final_url = None
    if final_path:
        if str(settings.MEDIA_ROOT) in final_path:
            final_url = settings.MEDIA_URL + os.path.relpath(final_path, settings.MEDIA_ROOT).replace(os.sep, '/')

    # 2. 현재 모드/테마 정보
    mode = request.session.get('mode')
    theme = request.session.get('theme')
    
    # 3. 메타데이터 및 스티커 로드
    meta = _load_meta(mode, theme)
    stickers = request.session.get('final_stickers', [])
    
    # 4. 매핑된 데이터 로드 (사진, 비디오)
    mapping = request.session.get('mapping_urls', [])
    captures = request.session.get('captured_urls', [])
    videos = request.session.get('captured_videos', [])
    
    # 슬롯 순서대로 비디오 매핑
    mapped_videos = []
    for m_url in mapping:
        if m_url in captures:
            idx = captures.index(m_url)
            # 해당 인덱스에 비디오가 존재하면 추가
            if idx < len(videos) and videos[idx]:
                mapped_videos.append(videos[idx])
            else:
                mapped_videos.append(None)
        else:
            mapped_videos.append(None)

    # 5. 템플릿으로 데이터 전달
    return render(request, 'printing.html', {
        'final_url': final_url,
        'mode': mode,
        'theme': theme,
        'frame_url': f"/static/frames/{mode}/{theme}/frame.png",
        'layout_url': f"/static/frames/{mode}/{theme}/layout/layout.png", # [추가됨] 레이아웃 이미지
        'meta_json': json.dumps(meta),
        'stickers_json': json.dumps(stickers),
        'mapped_videos_json': json.dumps(mapped_videos)
    })