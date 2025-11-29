import json
import os
import sys
import shutil
import base64
import uuid
import subprocess
from datetime import datetime
from pathlib import Path

from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.cache import never_cache
from django.conf import settings
from django.templatetags.static import static
from PIL import Image

# --- FFmpeg 경로 설정 ---
def get_ffmpeg_path():
    if getattr(sys, 'frozen', False):
        if hasattr(sys, '_MEIPASS'):
            path = os.path.join(sys._MEIPASS, 'ffmpeg')
            if os.path.exists(path): return path
        base_path = os.path.dirname(sys.executable)
        path = os.path.join(base_path, 'ffmpeg')
        if os.path.exists(path): return path
    if os.path.exists("ffmpeg"): return os.path.abspath("ffmpeg")
    return "ffmpeg"

os.environ["IMAGEIO_FFMPEG_EXE"] = get_ffmpeg_path()

# 이미지 합성 함수
try:
    from utils.combine_photo_v2 import combine_with_frame
except ImportError:
    import sys
    sys.path.append(str(settings.BASE_DIR))
    from utils.combine_photo_v2 import combine_with_frame

# -----------------------
# 경로 헬퍼
# -----------------------
def _get_base_path(): return settings.BASE_DIR
def _get_settings_path(): return _get_base_path() / 'Data' / 'settings.json'

def _load_global_settings():
    path = _get_settings_path()
    defaults = {
        'printer_enabled': True, 
        'print_duration_sec': 60, 
        'admin_password': '1234',
        'mirror_mode': False
    }
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding='utf-8'))
            for k,v in defaults.items(): 
                if k not in data: data[k] = v
            return data
    except: pass
    return defaults

def _save_global_settings(data):
    path = _get_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding='utf-8')

def _get_frames_root(): return _get_base_path() / 'static' / 'frames'
def _get_date_str(): return datetime.now().strftime("%Y%m%d")
def _get_time_str(): return datetime.now().strftime("%H%M%S")

def _get_output_paths():
    today = _get_date_str()
    base = _get_base_path() / 'Output' / today
    (base / 'img').mkdir(parents=True, exist_ok=True)
    (base / 'video').mkdir(parents=True, exist_ok=True)
    return base / 'img', base / 'video'

def _media_url_to_path(u: str):
    if not u: return None
    clean = u.replace('/media/', '').lstrip('/')
    return str(settings.BASE_DIR / clean)

def _common_stickers_dir(): return _get_frames_root() / 'stickers'
def _slots_path(mode, theme): return _get_frames_root() / mode / theme / 'slots.json'

def _load_meta(mode, theme):
    path = _slots_path(mode, theme)
    default = {'canvas': {'width': 1000, 'height': 1500}, 'slots': []}
    try:
        if path.exists():
            meta = json.loads(path.read_text(encoding='utf-8'))
            meta.setdefault('canvas', default['canvas'])
            return meta
    except: pass
    return default

def _save_meta(mode, theme, meta):
    path = _slots_path(mode, theme)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')

def _get_capture_delay(meta): return int(meta.get('capture_delay_ms', 5000))

# 세션 초기화
def _clear_session_data(request):
    request.session['captured_urls'] = []
    request.session['captured_videos'] = []
    request.session.modified = True

# 인쇄용 이미지 생성
def create_print_layout(source_path, save_path, mode):
    try:
        img = Image.open(source_path)
        if mode in ['3x1', '4x1']:
            strip_img = img.resize((600, 1800), Image.Resampling.LANCZOS)
            canvas = Image.new('RGB', (1200, 1800), 'white')
            canvas.paste(strip_img, (0, 0))
            canvas.paste(strip_img, (600, 0))
            canvas.save(save_path, quality=95)
        else:
            if img.width > img.height: canvas_size = (1800, 1200)
            else: canvas_size = (1200, 1800)
            full_img = img.resize(canvas_size, Image.Resampling.LANCZOS)
            full_img.save(save_path, quality=95)
    except: shutil.copy2(source_path, save_path)

# -----------------------
# Views
# -----------------------
def index(request): return redirect('startpage')

@ensure_csrf_cookie
def startpage(request):
    context = {'bg_url': static('background/sample-start.png')}
    return render(request, 'startpage.html', context)

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
    
    _clear_session_data(request)
    
    themes = []
    frames_root = _get_frames_root()
    mode_dir = frames_root / mode
    
    if mode_dir.exists():
        for tpath in sorted(mode_dir.iterdir()):
            if tpath.is_dir():
                p_url = ""
                if (tpath / 'layout' / 'preview.png').exists():
                    p_url = f"/static/frames/{mode}/{tpath.name}/layout/preview.png"
                elif (tpath / 'preview.png').exists():
                    p_url = f"/static/frames/{mode}/{tpath.name}/preview.png"
                elif (tpath / 'frame.png').exists():
                    p_url = f"/static/frames/{mode}/{tpath.name}/frame.png"
                
                if p_url:
                    themes.append({'name': tpath.name, 'thumb': p_url, 'mode': mode})

    return render(request, 'select_theme.html', {'themes': themes, 'count': count, 'mode': mode})

@ensure_csrf_cookie
@never_cache
def camera(request):
    mode = request.session.get('mode', '3x1')
    theme = request.GET.get('theme') or request.session.get('theme')
    if not theme: return redirect('select_theme')
    request.session['theme'] = theme

    _clear_session_data(request)

    meta = _load_meta(mode, theme)
    guide_ratio = 1.5
    if meta['slots']: 
        s = meta['slots'][0]
        if s['h'] > 0: guide_ratio = s['w'] / s['h']
    
    settings_data = _load_global_settings()

    return render(request, 'camera.html', {
        'count': request.session.get('shot_count', 3),
        'mode': mode, 'theme': theme,
        'guide_ratio': guide_ratio,
        'capture_delay_ms': _get_capture_delay(meta),
        'meta_json': json.dumps(meta),
        'mirror_mode': settings_data.get('mirror_mode', False)
    })

@require_POST
def upload_capture(request):
    data_url = request.POST.get('data_url')
    video_file = request.FILES.get('video')
    if not data_url: return JsonResponse({'saved':False}, status=400)
    
    today = _get_date_str()
    save_dir = settings.BASE_DIR / 'temp' / 'captures' / today
    save_dir.mkdir(parents=True, exist_ok=True)
    
    urls = request.session.get('captured_urls', [])
    v_urls = request.session.get('captured_videos', [])
    
    try:
        if ',' in data_url: b64 = data_url.split(',',1)[1]
        else: b64 = data_url
        fname = f"{uuid.uuid4().hex}.jpg"
        with open(save_dir/fname, 'wb') as f: f.write(base64.b64decode(b64))
        urls.append(f"/media/temp/captures/{today}/{fname}")
        
        if video_file:
            vname = f"{uuid.uuid4().hex}.webm"
            with open(save_dir/vname, 'wb+') as f:
                for c in video_file.chunks(): f.write(c)
            v_urls.append(f"/media/temp/captures/{today}/{vname}")
        else: v_urls.append(None)
        
        request.session['captured_urls'] = urls
        request.session['captured_videos'] = v_urls
        request.session.modified = True
        return JsonResponse({'saved':True, 'count':len(urls)})
    except: return JsonResponse({'saved':False}, status=500)

@ensure_csrf_cookie
def preview(request):
    mode = request.session.get('mode')
    theme = request.session.get('theme')
    meta = _load_meta(mode, theme)
    return render(request, 'preview.html', {
        'mode':mode, 'theme':theme,
        'captured_json': json.dumps(request.session.get('captured_urls', [])),
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
        return JsonResponse({'ok':True})
    except: return HttpResponseBadRequest('Error')

@ensure_csrf_cookie
def decorate(request):
    mode = request.session.get('mode')
    theme = request.session.get('theme')
    meta = _load_meta(mode, theme)
    mapping = request.session.get('mapping_urls', [])
    
    today = _get_date_str()
    out_dir = settings.BASE_DIR / 'temp' / 'outputs' / today
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = f"base_{uuid.uuid4().hex[:8]}.jpg"
    
    try:
        frame_p = _get_frames_root() / mode / theme / 'frame.png'
        imgs = []
        for u in mapping:
            # [핵심 수정] u가 None일 때 에러 방지
            if u:
                clean = u.replace('/media/', '').lstrip('/')
                imgs.append(str(settings.BASE_DIR / clean))
            else:
                imgs.append(None) # 빈 슬롯 처리
            
        from utils.combine_photo_v2 import combine_with_frame
        combine_with_frame(str(frame_p), {**meta, 'stickers':[]}, imgs, str(out_dir/fname), [], None)
    except Exception as e: print(f"Decorate Err: {e}")
    
    sdir = _common_stickers_dir()
    s_ids = [p.stem for p in sorted(sdir.glob('*.png'))] if sdir.exists() else []
    
    return render(request, 'decorate.html', {
        'mode':mode, 'theme':theme,
        'base_url': f"/media/temp/outputs/{today}/{fname}",
        'canvas_json': json.dumps(meta['canvas']),
        'sticker_ids_json': json.dumps(s_ids)
    })

@require_POST
def finalize(request):
    try:
        body = json.loads(request.body.decode('utf-8'))
        stickers = body.get('stickers', [])
        request.session['final_stickers'] = stickers
        
        mode = request.session.get('mode')
        theme = request.session.get('theme')
        count = request.session.get('shot_count', 4)
        mapping = request.session.get('mapping_urls', [])
        
        img_dir, vid_dir = _get_output_paths()
        today = _get_date_str()
        time = _get_time_str()
        base_name = f"{theme}_{count}cut_{today}_{time}"
        
        # 1. 이미지 합성
        out_img = img_dir / f"{base_name}.jpg"
        frame_p = _get_frames_root() / mode / theme / 'frame.png'
        
        imgs = []
        for u in mapping:
            # [핵심 수정] u가 None일 때 에러 방지
            if u:
                clean = u.replace('/media/', '').lstrip('/')
                imgs.append(str(settings.BASE_DIR / clean))
            else:
                imgs.append(None)

        s_dir = _common_stickers_dir()
        meta = _load_meta(mode, theme)
        from utils.combine_photo_v2 import combine_with_frame
        combine_with_frame(str(frame_p), meta, imgs, str(out_img), stickers, str(s_dir))
        
        # 2. 인쇄용 이미지
        print_img_path = img_dir / f"{base_name}_print.jpg"
        create_print_layout(str(out_img), str(print_img_path), mode)
        
        # 3. 동영상 백업 (선택된 것만)
        captures = request.session.get('captured_urls', [])
        c_vids = request.session.get('captured_videos', [])
        
        for i, m in enumerate(mapping):
            if m and m in captures:
                idx = captures.index(m)
                if idx < len(c_vids) and c_vids[idx]:
                    clean_v = c_vids[idx].replace('/media/', '').lstrip('/')
                    src_v = settings.BASE_DIR / clean_v
                    if src_v.exists():
                        shutil.copy2(src_v, vid_dir / f"{base_name}_shot{i+1}.webm")

        request.session['last_output_path'] = str(out_img)
        request.session['print_output_path'] = str(print_img_path)
        request.session.modified = True
        return JsonResponse({'saved': True})
    except: return JsonResponse({'saved': False}, status=500)

@ensure_csrf_cookie
def admin_mode(request):
    frames_root = _get_frames_root()
    mode_themes = {}
    if frames_root.exists():
        for md in sorted(frames_root.iterdir()):
            if not md.is_dir() or md.name == 'stickers': continue
            themes = []
            for td in sorted(md.iterdir()):
                if td.is_dir(): themes.append(td.name)
            if themes: mode_themes[md.name] = themes
            
    mode = request.GET.get('mode')
    if not mode or mode not in mode_themes: mode = next(iter(mode_themes)) if mode_themes else None
    theme = request.GET.get('theme')
    themes = mode_themes.get(mode, [])
    if not theme or theme not in themes: theme = themes[0] if themes else None

    meta = _load_meta(mode, theme) if mode and theme else {'canvas':{'width':0,'height':0},'slots':[]}
    
    frame_url = ""
    if mode and theme:
        t_path = frames_root / mode / theme
        if (t_path / 'layout' / 'preview.png').exists():
            frame_url = f"/static/frames/{mode}/{theme}/layout/preview.png"
        elif (t_path / 'preview.png').exists():
            frame_url = f"/static/frames/{mode}/{theme}/preview.png"
        else:
            frame_url = f"/static/frames/{mode}/{theme}/frame.png"
            
    return render(request, 'admin_mode.html', {
        'mode': mode, 'theme': theme, 'modes': list(mode_themes.keys()),
        'themes': themes,
        'frame_url': frame_url,
        'meta_json': json.dumps(meta),
        'capture_delay_ms': _get_capture_delay(meta),
        'global_settings': _load_global_settings()
    })

@require_POST
def admin_save_slots(request):
    try:
        body = json.loads(request.body.decode('utf-8'))
        if body.get('action') == 'save_global_settings':
            _save_global_settings({
                'printer_enabled': body.get('printer_enabled'),
                'print_duration_sec': body.get('print_duration_sec'),
                'admin_password': body.get('admin_password'),
                'mirror_mode': body.get('mirror_mode')
            })
            return JsonResponse({'saved':True})
            
        mode = body.get('mode')
        theme = body.get('theme')
        meta = _load_meta(mode, theme)
        meta['slots'] = body.get('slots')
        meta['capture_delay_ms'] = body.get('capture_delay_ms')
        _save_meta(mode, theme, meta)
        return JsonResponse({'saved': True})
    except: return JsonResponse({'saved':False}, status=500)

@ensure_csrf_cookie
def printing(request):
    mode = request.session.get('mode')
    theme = request.session.get('theme')
    meta = _load_meta(mode, theme)
    mapping = request.session.get('mapping_urls', [])
    captures = request.session.get('captured_urls', [])
    c_vids = request.session.get('captured_videos', [])
    
    mapped_vids = []
    for m in mapping:
        # [핵심 수정] m이 None(빈 슬롯)일 경우 처리
        if m and m in captures:
            idx = captures.index(m)
            if idx >= 0 and idx < len(c_vids): mapped_vids.append(c_vids[idx])
            else: mapped_vids.append(None)
        else:
            mapped_vids.append(None)
    
    layout_url = f"/static/frames/{mode}/{theme}/layout/layout.png"
    frame_url = f"/static/frames/{mode}/{theme}/frame.png"
    settings_data = _load_global_settings()

    return render(request, 'printing.html', {
        'frame_url': frame_url,
        'layout_url': layout_url,
        'meta_json': json.dumps(meta),
        'stickers_json': json.dumps(request.session.get('final_stickers', [])),
        'mapped_videos_json': json.dumps(mapped_vids),
        'print_duration': settings_data.get('print_duration_sec', 60),
        'mirror_mode': settings_data.get('mirror_mode', False)
    })

@require_POST
def print_action(request):
    try:
        sett = _load_global_settings()
        if not sett.get('printer_enabled', True):
            return JsonResponse({'status':'skipped'})
        path = request.session.get('print_output_path')
        if not path or not os.path.exists(path):
            path = request.session.get('last_output_path')
        if not path or not os.path.exists(path):
            return JsonResponse({'status':'error', 'message':'No file'})
        subprocess.run(['lpr', '-P', "Canon_SELPHY_CP1500", path], check=True)
        return JsonResponse({'status':'success'})
    except Exception as e: return JsonResponse({'status':'error', 'message':str(e)})