import json
import os
import sys
import shutil
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

# 이미지 합성 함수
try:
    from utils.combine_photo_v2 import combine_with_frame
except ImportError:
    import sys
    sys.path.append(str(settings.BASE_DIR))
    from utils.combine_photo_v2 import combine_with_frame

# MoviePy 설정
MOVIEPY_AVAILABLE = False
try:
    from moviepy.editor import VideoFileClip, ImageClip, CompositeVideoClip
    MOVIEPY_AVAILABLE = True
except ImportError:
    print("🚨 'moviepy' 미설치")

# -----------------------
# 경로 및 로딩 헬퍼 함수
# -----------------------

def _get_base_path():
    if getattr(sys, 'frozen', False):
        if sys.platform == 'darwin' and '.app' in sys.executable:
            return Path(sys.executable).parent.parent.parent.parent
        return Path(sys.executable).parent
    else:
        return settings.BASE_DIR

def _get_frames_root():
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

def _clear_captures_in_session(request):
    request.session['captured_urls'] = []
    request.session['captured_videos'] = []
    request.session.modified = True

def _media_url_to_path(u: str):
    if not u: return None
    if u.startswith('file://'): return u[7:] if os.path.exists(u[7:]) else None
    
    # URL -> 로컬 경로 변환
    if u.startswith(settings.MEDIA_URL):
        rel = u[len(settings.MEDIA_URL):]
        fs_path = settings.MEDIA_ROOT / rel
        return str(fs_path) if fs_path.exists() else None
    
    if u.startswith(settings.TEMP_URL):
        rel = u[len(settings.TEMP_URL):]
        fs_path = settings.TEMP_ROOT / rel
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

# [수정] 비디오 합성 함수 (webm 코덱 사용)
def _generate_combined_video(frame_path, slots, video_paths, output_path):
    if not MOVIEPY_AVAILABLE:
        print(">> [Video Skip] MoviePy not installed.")
        return False
        
    try:
        print(f">> [Video Start] 합성 시작: {output_path}")
        
        frame_clip = ImageClip(frame_path)
        
        duration = 5 
        valid_videos = [v for v in video_paths if v and os.path.exists(v)]
        if valid_videos:
            try:
                temp = VideoFileClip(valid_videos[0])
                duration = temp.duration
                temp.close()
            except Exception as e:
                print(f"  - 원본 길이 확인 실패: {e}")
            
        frame_clip = frame_clip.set_duration(duration)
        clips = [frame_clip]
        
        added_count = 0
        for i, v_path in enumerate(video_paths):
            if v_path and os.path.exists(v_path) and i < len(slots):
                slot = slots[i]
                try:
                    video = VideoFileClip(v_path)
                    video = video.resize(newsize=(slot['w'], slot['h']))
                    video = video.set_position((slot['x'], slot['y']))
                    video = video.set_duration(duration)
                    clips.append(video)
                    added_count += 1
                except Exception as ve:
                    print(f"  - 비디오({i}) 로드 실패: {ve}")
        
        if added_count == 0:
            print(">> [Video Skip] 합성할 비디오가 없습니다.")
            return False

        final_video = CompositeVideoClip(clips, size=frame_clip.size)
        
        # [핵심] 출력 확장자가 .webm이면 libvpx 사용, mp4면 libx264 사용
        if output_path.endswith('.webm'):
            final_video.write_videofile(output_path, fps=24, codec='libvpx', audio_codec='libvorbis', logger=None)
        else:
            final_video.write_videofile(output_path, fps=24, codec='libx264', audio_codec='aac', logger=None)
        
        final_video.close()
        for c in clips:
            try: c.close()
            except: pass
            
        return True

    except Exception as e:
        print(f"!!! [Video Error] {e}")
        import traceback
        traceback.print_exc()
        return False

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
    mode = '3x1' if count == 3 else '4x1'

    request.session['shot_count'] = count
    request.session['mode'] = mode
    _clear_captures_in_session(request)

    themes = []
    frames_root = _get_frames_root()
    mode_dir = frames_root / mode
    
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
    
    return render(request, 'select_theme.html', {
        'themes': themes, 'count': count, 'mode': mode, 'debug_path': str(mode_dir)
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
    except Exception as e:
        print(f"[ERROR] Save failed: {e}")
        return JsonResponse({'saved': False}, status=500)

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
    
    today_str = _get_date_str()
    out_dir = settings.TEMP_ROOT / 'outputs' / today_str
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = f"base_{uuid.uuid4().hex[:8]}.jpg"
    out_path = out_dir / fname
    
    try:
        frame_png = _get_frames_root() / mode / theme / 'frame.png'
        combine_with_frame(str(frame_png), {**meta, 'stickers': []}, images_fs, str(out_path), [], None)
    except Exception as e: print(f"Base Compose Error: {e}")

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
        print(f"====== [Image Saved] {out_img_path} ======")
        
        # [수정] WebM으로 저장하도록 변경 (ffmpeg 의존성 문제 회피 가능성 높음)
        fname_video = f"{filename_base}.webm"
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
                else:
                    selected_video_paths.append(None)
            else:
                selected_video_paths.append(None)
        
        video_success = False
        if MOVIEPY_AVAILABLE:
            # .webm으로 합성 시도
            video_success = _generate_combined_video(str(frame_png), meta['slots'], selected_video_paths, str(out_video_path))
        
        if video_success:
            print(f"====== [Video Saved] {out_video_path} ======")
        else:
            print("====== [Video Backup] 합성 실패로 개별 파일 백업 ======")
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

# 관리자/인쇄 등 나머지 동일
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