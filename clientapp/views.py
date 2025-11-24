import os
import json
import base64
from datetime import datetime
from PIL import Image

from django.shortcuts import render, redirect
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

# ------------------------------------------------------------------
# [1] 파일 저장 및 공통 로직
# ------------------------------------------------------------------
def save_final_output(image_obj, video_file=None):
    """최종 합성본 및 동영상을 Output/{날짜} 폴더에 저장"""
    today_str = datetime.now().strftime("%Y%m%d")
    base_output_dir = settings.DATA_DIR / 'Output' / today_str
    
    img_dir = base_output_dir / 'img'
    vid_dir = base_output_dir / 'video'
    os.makedirs(img_dir, exist_ok=True)
    os.makedirs(vid_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%H%M%S_%f")
    
    # 이미지 저장
    img_filename = f"photo_{timestamp}.jpg"
    img_save_path = img_dir / img_filename
    image_obj.save(img_save_path, "JPEG", quality=95)
    print(f"--> [Saved] Image: {img_save_path}")

    # 동영상 저장
    if video_file:
        vid_filename = f"video_{timestamp}.mp4"
        vid_save_path = vid_dir / vid_filename
        with open(vid_save_path, 'wb+') as dest:
            for chunk in video_file.chunks():
                dest.write(chunk)
        print(f"--> [Saved] Video: {vid_save_path}")

    return str(img_filename)

def get_slots_meta(count):
    """컷 수에 따른 좌표 반환 (600x1800 캔버스 기준)"""
    # 4컷 (세로)
    if count == 4:
        return [
            {"x": 25, "y": 25,   "w": 550, "h": 400},
            {"x": 25, "y": 450,  "w": 550, "h": 400},
            {"x": 25, "y": 875,  "w": 550, "h": 400},
            {"x": 25, "y": 1300, "w": 550, "h": 400},
        ]
    # 3컷 (예시 - 필요시 좌표 수정)
    elif count == 3:
        return [
            {"x": 25, "y": 50,   "w": 550, "h": 500},
            {"x": 25, "y": 600,  "w": 550, "h": 500},
            {"x": 25, "y": 1150, "w": 550, "h": 500},
        ]
    return []

# ------------------------------------------------------------------
# [2] 뷰 함수들
# ------------------------------------------------------------------

def start_page(request):
    request.session.flush()
    # [수정] 배경 이미지 전달 (없으면 검은화면만 나옴)
    context = {
        'bg_url': f"{settings.STATIC_URL}background/sample-start.png" 
    }
    return render(request, 'start.html', context)

def select_shot(request):
    return render(request, 'select_shot.html')

def select_theme(request):
    count = request.GET.get('count', 4)
    request.session['shot_count'] = int(count)
    return render(request, 'select_theme.html', {'count': count})

def camera(request):
    count = request.session.get('shot_count', 4)
    theme = request.GET.get('theme', 'basic')
    request.session['theme'] = theme
    return render(request, 'camera.html', {'count': count, 'theme': theme})

@csrf_exempt
def upload_capture(request):
    if request.method == 'POST':
        data_url = request.POST.get('data_url')
        if not data_url:
            return JsonResponse({'status': 'fail'}, status=400)
            
        format, imgstr = data_url.split(';base64,') 
        ext = format.split('/')[-1] 
        data = base64.b64decode(imgstr)
        
        filename = f"{datetime.now().strftime('%H%M%S_%f')}.{ext}"
        save_path = settings.CAPTURE_DIR / filename
        with open(save_path, 'wb') as f:
            f.write(data)
            
        captures = request.session.get('captures', [])
        captures.append(str(filename))
        request.session['captures'] = captures
        request.session.modified = True
        
        return JsonResponse({'status': 'ok', 'count': len(captures)})
    return JsonResponse({'status': 'fail'}, status=400)

# ------------------------------------------------------------------
# [3] Preview (GET): 화면 표시
# ------------------------------------------------------------------
def preview(request):
    captures = request.session.get('captures', [])
    if not captures:
        return redirect('start_page')
    
    count = request.session.get('shot_count', 4)
    theme = request.session.get('theme', 'basic') # 기본값 basic

    # 1. 좌표 및 캔버스 크기 가져오기
    slots_meta = get_slots_meta(count)
    canvas_meta = {"width": 600, "height": 1800}

    # 2. 이미지 URL 리스트
    captured_urls = [f"{settings.MEDIA_URL}captures/{fname}" for fname in captures]

    # 3. 프레임/레이아웃 경로 설정 (동적)
    # 예: static/frames/4x4/hamzzi/frame.png
    frame_folder = f"{count}x{count}/{theme}"
    frame_url = f"{settings.STATIC_URL}frames/{frame_folder}/frame.png"
    layout_url = f"{settings.STATIC_URL}frames/{frame_folder}/layout.png"

    context = {
        'captured_json': json.dumps(captured_urls),
        'meta_json': json.dumps({'slots': slots_meta, 'canvas': canvas_meta}),
        'frame_url': frame_url,
        'layout_url': layout_url,
    }
    return render(request, 'preview.html', context)


# ------------------------------------------------------------------
# [4] Prepare Decorate (POST): 합성 및 저장
# ------------------------------------------------------------------
@csrf_exempt
def prepare_decorate(request):
    if request.method == 'POST':
        try:
            body = json.loads(request.body)
            mapping = body.get('mapping', []) 
            
            count = request.session.get('shot_count', 4)
            theme = request.session.get('theme', 'basic')

            # 1. 캔버스 생성 (Preview와 동일 크기)
            canvas_w, canvas_h = 600, 1800
            final_image = Image.new('RGB', (canvas_w, canvas_h), (255, 255, 255))
            
            # 2. 프레임 로드 (동적 경로)
            frame_subpath = f"{count}x{count}/{theme}/frame.png"
            frame_path = settings.FRAMES_DIR / frame_subpath
            
            if os.path.exists(frame_path):
                frame_img = Image.open(frame_path).convert("RGBA")
                canvas_w, canvas_h = frame_img.size
                final_image = Image.new('RGB', (canvas_w, canvas_h), (255, 255, 255))
            else:
                frame_img = None
                print(f"Warning: Frame not found at {frame_path}")

            # 3. 좌표 가져오기
            slots_meta = get_slots_meta(count)

            # 4. 사진 합성
            for i, url in enumerate(mapping):
                if url and i < len(slots_meta):
                    filename = url.split('/')[-1]
                    img_path = settings.CAPTURE_DIR / filename
                    
                    if os.path.exists(img_path):
                        photo = Image.open(img_path)
                        slot = slots_meta[i]
                        
                        # 리사이즈
                        photo = photo.resize((slot['w'], slot['h']))
                        
                        # 붙여넣기
                        final_image.paste(photo, (slot['x'], slot['y']))

            # 5. 프레임 덮기
            if frame_img:
                final_image.paste(frame_img, (0, 0), frame_img)

            # 6. 저장 (Output 폴더)
            save_final_output(final_image, video_file=None)

            # 7. 화면 표시용 임시 저장
            display_filename = f"merged_{datetime.now().strftime('%H%M%S')}.jpg"
            final_image.save(settings.OUTPUT_DIR / display_filename)
            
            request.session['merged_image_url'] = f"{settings.MEDIA_URL}outputs/{display_filename}"

            return JsonResponse({'ok': True})
            
        except Exception as e:
            print(f"Error in prepare_decorate: {e}")
            return JsonResponse({'ok': False, 'error': str(e)})

    return JsonResponse({'ok': False})


def decorate(request):
    merged_url = request.session.get('merged_image_url')
    # decorate.html이 없으면 preview.html 재사용 (결과만 보여줌)
    # 하지만 님 코드를 보니 preview.html은 선택용이라, 결과 확인용 템플릿을 따로 만들거나
    # 간단히 렌더링해야 합니다. 여기서는 result_view.html을 가정하거나 
    # 간단한 결과 페이지를 렌더링합니다.
    
    # 임시: 결과 이미지만 보여주는 간단한 페이지
    return render(request, 'base.html', {'content': f"""
        <div style="width:100%; height:100%; background:#000; display:flex; justify-content:center; align-items:center; flex-direction:column;">
            <img src="{merged_url}" style="height:80vh; border:10px solid #fff;">
            <div style="margin-top:20px;">
                <button onclick="window.print()" style="padding:15px 30px; border-radius:30px; border:none; background:#00d1b2; color:white; font-size:20px; font-weight:bold;">🖨 인쇄하기</button>
                <button onclick="location.href='/'" style="padding:15px 30px; border-radius:30px; border:none; background:#ff6b6b; color:white; font-size:20px; font-weight:bold;">🏠 처음으로</button>
            </div>
        </div>
    """})