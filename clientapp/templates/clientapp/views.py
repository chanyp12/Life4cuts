import json
import os
import sys
import shutil
import base64
import uuid
import subprocess
from datetime import datetime
from pathlib import Path

from django.templatetags.static import static
from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import ensure_csrf_cookie
from django.conf import settings

# 이미지 합성 함수
try:
    from utils.combine_photo_v2 import combine_with_frame
except ImportError:
    import sys
    sys.path.append(str(settings.BASE_DIR))
    from utils.combine_photo_v2 import combine_with_frame

# MoviePy 설정 (환경변수 강제 주입)
MOVIEPY_AVAILABLE = False
try:
    # Mac, PyInstaller 환경 등에서 ffmpeg 경로 명시
    # 로컬 개발 환경의 ffmpeg 경로 또는 내장된 경로를 지정
    os.environ["IMAGEIO_FFMPEG_EXE"] = "/opt/homebrew/bin/ffmpeg" 
    from moviepy.editor import VideoFileClip, ImageClip, CompositeVideoClip
    MOVIEPY_AVAILABLE = True
except ImportError:
    print("🚨 'moviepy' 로드 실패")

# -----------------------
# [핵심 수정] 경로 헬퍼 함수
# -----------------------

def _get_base_path():
    """
    PyInstaller 실행 환경에 따라 기본 경로(인생네컷 배포 폴더)를 반환
    """
    if getattr(sys, 'frozen', False):
        # Mac .app 번들 실행 시: .../Life4Cut.app/Contents/MacOS/Life4Cut
        # 우리가 필요한 static 폴더는 Life4Cut.app과 같은 위치에 있음
        if sys.platform == 'darwin' and '.app' in sys.executable:
            # .parent를 4번 해서 앱 번들 밖으로 나감
            return Path(sys.executable).parent.parent.parent.parent
        
        # 윈도우나 일반 바이너리
        return Path(sys.executable).parent
    else:
        # 개발 환경 (python manage.py runserver)
        return settings.BASE_DIR

def _get_settings_path():
    return _get_base_path() / 'Data' / 'settings.json'

def _load_global_settings():
    path = _get_settings_path()
    defaults = {'printer_enabled': True, 'print_duration_sec': 60}
    if not path.exists(): return defaults
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        for k, v in defaults.items():
            if k not in data: data[k] = v
        return data
    except: return defaults

def _save_global_settings(data):
    path = _get_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding='utf-8')

def _get_frames_root():
    # '인생네컷 배포/static/frames' 경로 반환
    return _get_base_path() / 'static' / 'frames'

def _get_date_str():
    return datetime.now().strftime("%Y%m%d")

def _get_time_str():
    return datetime.now().strftime("%H%M%S")

def _get_output_paths():
    today_str = _get_date_str()
    base_output = _get_base_path() / 'Output' / today_str
    img_dir = base_output / 'img'
    video_dir = base_output / 'video'
    img_dir.mkdir(parents=True, exist_ok=True)
    video_dir.mkdir(parents=True, exist_ok=True)
    return img_dir, video_dir

def _media_url_to_path(u: str):
    if not u: return None
    if u.startswith(settings.MEDIA_URL):
        rel = u[len(settings.MEDIA_URL):]
        # 배포 환경에서는 Data/media 등을 사용할 수 있음
        fs_path = settings.MEDIA_ROOT / rel
        return str(fs_path)
    if u.startswith(settings.TEMP_URL):
        rel = u[len(settings.TEMP_URL):]
        fs_path = settings.TEMP_ROOT / rel
        return str(fs_path)
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

# 동영상 합성 함수 (안정적인 mp4 저장)
def _generate_combined_video(frame_path, slots, video_paths, output_path):
    if not MOVIEPY_AVAILABLE:
        print(">> [Video Skip] MoviePy missing.")
        return False
    try:
        print(f">> [Video Start] {output_path}")
        if not os.path.exists(frame_path):
            print(f"   ! Frame missing: {frame_path}")
            return False
            
        frame_clip = ImageClip(str(frame_path)).convert_alpha()
        duration = 10 
        valid_videos = [v for v in video_paths if v and os.path.exists(v)]
        if valid_videos:
            try:
                temp = VideoFileClip(valid_videos[0])
                duration = temp.duration
                temp.close()
            except: pass
            
        frame_clip = frame_clip.set_duration(duration)
        clips_layer = [] 
        added_count = 0
        
        for i, v_path in enumerate(video_paths):
            if v_path and os.path.exists(v_path) and i < len(slots):
                slot = slots[i]
                try:
                    video = VideoFileClip(v_path, audio=False)
                    video = video.resize(newsize=(slot['w'], slot['h']))
                    video = video.set_position((slot['x'], slot['y']))
                    video = video.set_duration(duration)
                    clips_layer.append(video)
                    added_count += 1
                except: pass
        
        if added_count == 0: return False

        clips_layer.append(frame_clip) # 프레임을 맨 위로
        final_video = CompositeVideoClip(clips_layer, size=frame_clip.size)
        
        final_video.write_videofile(
            output_path, fps=24, codec='libx264', audio=False, 
            logger=None, preset='ultrafast'
        )
        final_video.close()
        for c in clips_layer: 
            try: c.close() 
            except: pass
        return True
    except Exception as e:
        print(f"!!! [Video Error] {e}")
        return False

# -----------------------
# Views
# -----------------------

def index(request): return redirect('startpage')

@ensure_csrf_cookie
def startpage(request):
    return render(request, 'startpage.html')

@ensure_csrf_cookie
def select_shot(request):
    return render(request, 'select_shot.html')

@ensure_csrf_cookie
def select_theme(request):
    try: count = int(request.GET.get('count', '3'))
    except: count = 3
    if count not in (3, 4): count = 3
    mode = '3x1' if count == 3 else '4x1'

    request.session['shot_count'] = count
    request.session['mode'] = mode
    
    themes = []
    frames_root = _get_frames_root()
    mode_dir = frames_root / mode
    
    # 디버깅용: 경로 출력
    print(f"DEBUG: Looking for frames in {mode_dir}")

    if mode_dir.exists():
        for theme_path in sorted(mode_dir.iterdir()):
            if theme_path.is_dir():
                preview_file = theme_path / 'preview.png'
                frame_file = theme_path / 'frame.png'
                
                thumb_url = ""
                # 정적 파일 URL 생성 시 /static/... 경로 사용
                if preview_file.exists():
                    thumb_url = f"/static/frames/{mode}/{theme_path.name}/preview.png"
                elif frame_file.exists():
                    thumb_url = f"/static/frames/{mode}/{theme_path.name}/frame.png"
                
                if thumb_url:
                    themes.append({'name': theme_path.name, 'thumb': thumb_url, 'mode': mode})
    else:
        print("DEBUG: Mode directory not found!")

    return render(request, 'select_theme.html', {'themes': themes, 'count': count, 'mode': mode})

@ensure_csrf_cookie
def camera(request):
    mode = request.session.get('mode', '3x1')
    theme = request.GET.get('theme') or request.session.get('theme')
    if not theme: return redirect('select_theme')
    request.session['theme'] = theme

    meta = _load_meta(mode, theme)
    capture_delay_ms = _get_capture_delay(meta)
    
    # 가이드 비율 설정
    guide_ratio = 1.5 if '3x1' in mode else 1.33
    if meta['slots']:
        s0 = meta['slots'][0]
        if s0['h'] > 0: guide_ratio = s0['w'] / s0['h']

    return render(request, 'camera.html', {
        'count': request.session.get('shot_count', 3),
        'mode': mode, 'theme': theme,
        'guide_ratio': guide_ratio,
        'capture_delay_ms': capture_delay_ms,
        'meta_json': json.dumps(meta),
    })

@require_POST
def upload_capture(request):
    data_url = request.POST.get('data_url')
    video_file = request.FILES.get('video')
    if not data_url: return JsonResponse({'saved': False}, status=400)

    today_str = _get_date_str()
    save_dir = settings.TEMP_ROOT / 'captures' / today_str
    save_dir.mkdir(parents=True, exist_ok=True)
    
    urls = request.session.get('captured_urls', [])
    video_urls = request.session.get('captured_videos', [])

    try:
        if ',' in data_url: header, b64data = data_url.split(',', 1)
        else: b64data = data_url
        fname_img = f"{uuid.uuid4().hex}.jpg"
        with open(save_dir / fname_img, 'wb') as f: f.write(base64.b64decode(b64data))
        urls.append(f"{settings.TEMP_URL}captures/{today_str}/{fname_img}")
    except: return JsonResponse({'saved': False}, status=500)

    if video_file:
        try:
            fname_vid = f"{uuid.uuid4().hex}.webm"
            with open(save_dir / fname_vid, 'wb+') as dest:
                for chunk in video_file.chunks(): dest.write(chunk)
            video_urls.append(f"{settings.TEMP_URL}captures/{today_str}/{fname_vid}")
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
    
    meta = _load_meta(mode, theme)
    images_fs = [_media_url_to_path(u) for u in mapping_urls]
    
    today_str = _get_date_str()
    out_dir = settings.TEMP_ROOT / 'outputs' / today_str
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = f"base_{uuid.uuid4().hex[:8]}.jpg"
    out_path = out_dir / fname
    
    try:
        frame_png = _get_frames_root() / mode / theme / 'frame.png'
        combine_with_frame(str(frame_png), {**meta, 'stickers': []}, images_fs, str(out_path), [], None)
    except: pass

    base_url = f"{settings.TEMP_URL}outputs/{today_str}/{fname}"
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
        shot_count = request.session.get('shot_count', 4)
        mapping = request.session.get('mapping_urls', [])
        
        img_dir, video_dir = _get_output_paths()
        today_str = _get_date_str()
        time_str = _get_time_str()
        filename_base = f"{theme}_{shot_count}cut_{today_str}_{time_str}"
        
        fname_img = f"{filename_base}.jpg"
        out_img_path = img_dir / fname_img
        
        images_fs = [_media_url_to_path(u) for u in mapping]
        frame_png = _get_frames_root() / mode / theme / 'frame.png'
        sticker_dir = _common_stickers_dir()
        meta = _load_meta(mode, theme)
        
        combine_with_frame(str(frame_png), meta, images_fs, str(out_img_path), stickers, str(sticker_dir))
        
        fname_video = f"{filename_base}.mp4" 
        out_video_path = video_dir / fname_video
        
        captured_videos = request.session.get('captured_videos', [])
        captured_urls = request.session.get('captured_urls', [])
        
        selected_video_paths = []
        for m_url in mapping:
            if m_url in captured_urls:
                idx = captured_urls.index(m_url)
                if idx < len(captured_videos) and captured_videos[idx]:
                    v_path = _media_url_to_path(captured_videos[idx])
                    selected_video_paths.append(v_path)
                else: selected_video_paths.append(None)
            else: selected_video_paths.append(None)
        
        video_success = False
        if MOVIEPY_AVAILABLE:
            video_success = _generate_combined_video(str(frame_png), meta['slots'], selected_video_paths, str(out_video_path))
        
        if not video_success:
            for i, v_path in enumerate(selected_video_paths):
                if v_path and os.path.exists(v_path):
                    ext = os.path.splitext(v_path)[1]
                    bk_name = f"{filename_base}_shot{i+1}{ext}"
                    try: shutil.copy2(v_path, video_dir / bk_name)
                    except: pass

        request.session['last_output_path'] = str(out_img_path)
        request.session.modified = True
        return JsonResponse({'saved': True})
    except Exception as e:
        print(f"Finalize Error: {e}")
        return JsonResponse({'saved': False}, status=500)

@ensure_csrf_cookie
def admin_mode(request):
    frames_root = _get_frames_root()
    mode_themes = {}
    
    # 디버깅: 경로 확인
    print(f"DEBUG Admin: Frames Root is {frames_root}")

    if frames_root.exists():
        for mode_dir in sorted(frames_root.iterdir()):
            if not mode_dir.is_dir() or mode_dir.name == 'stickers': continue
            themes = []
            for theme_dir in sorted(mode_dir.iterdir()):
                if theme_dir.is_dir():
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
    
    global_settings = _load_global_settings()

    return render(request, 'admin_mode.html', {
        'mode': mode, 'theme': theme, 'modes': list(mode_themes.keys()),
        'themes': themes, 'frame_url': frame_url, 'layout_url': layout_url,
        'meta_json': json.dumps(meta), 'capture_delay_ms': _get_capture_delay(meta),
        'global_settings': global_settings
    })

@require_POST
def admin_save_slots(request):
    try:
        body = json.loads(request.body.decode('utf-8'))
        action = body.get('action')

        if action == 'save_global_settings':
            settings_data = {
                'printer_enabled': body.get('printer_enabled', True),
                'print_duration_sec': int(body.get('print_duration_sec', 60))
            }
            _save_global_settings(settings_data)
            return JsonResponse({'saved': True})

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

    global_settings = _load_global_settings()

    return render(request, 'printing.html', {
        'final_url': final_url, 'mode': mode, 'theme': theme,
        'frame_url': f"/static/frames/{mode}/{theme}/frame.png",
        'layout_url': f"/static/frames/{mode}/{theme}/layout/layout.png",
        'meta_json': json.dumps(meta), 'stickers_json': json.dumps(stickers),
        'mapped_videos_json': json.dumps(mapped_videos),
        'print_duration': global_settings.get('print_duration_sec', 60)
    })

@require_POST
def print_action(request):
    try:
        global_settings = _load_global_settings()
        if not global_settings.get('printer_enabled', True):
            return JsonResponse({'status': 'skipped', 'message': 'Printer OFF'})

        image_path = request.session.get('last_output_path')
        if not image_path or not os.path.exists(image_path):
            return JsonResponse({'status': 'error', 'message': 'No image'})

        printer_name = "Canon_SELPHY_CP1500" 
        command = ['lpr', '-P', printer_name, image_path]
        subprocess.run(command, check=True)
        return JsonResponse({'status': 'success', 'message': 'Printing'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)