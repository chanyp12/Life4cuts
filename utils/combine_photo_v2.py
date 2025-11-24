from pathlib import Path
from PIL import Image


def combine_with_frame(
    frame_png: str,
    meta: dict,
    images: list,
    out_path: str,
    stickers=None,
    stickers_dir: str | None = None,
):
    """
    frame_png 위에 meta 정보(canvas + slots)에 따라 사진들을 합성해서 out_path로 저장.

    meta 예시:
    {
      "canvas": { "width": 1200, "height": 1800 },
      "slots": [
        { "x": 100, "y": 200, "w": 300, "h": 400 },
        ...
      ],
      "stickers": [
        { "id": "heart", "x": 100, "y": 200, "w": 300, "h": 300, "angle": 0 },
        ...
      ]
    }

    images: 슬롯 순서에 맞는 파일 경로 리스트 (없으면 None)

    stickers: meta['stickers'] 같은 리스트 (옵션, 주어지면 이 값을 우선 사용)
    stickers_dir: 스티커 PNG들이 들어 있는 디렉터리 경로
    """

    canvas_w = meta['canvas']['width']
    canvas_h = meta['canvas']['height']

    frame_path = Path(frame_png)

    # 프레임 PNG
    frame = Image.open(frame_path).convert('RGBA')
    frame_w, frame_h = frame.size

    # slots.json의 canvas 크기와 실제 프레임 PNG 크기가 다를 수 있으므로 스케일 계수 계산
    if (canvas_w, canvas_h) != (frame_w, frame_h):
        scale_x = frame_w / canvas_w
        scale_y = frame_h / canvas_h
    else:
        scale_x = scale_y = 1.0

    # base를 프레임 복사본으로 사용 (배경)
    base = frame.copy()

    # 1) 슬롯에 촬영 사진 합성
    for idx, slot in enumerate(meta['slots']):
        if idx >= len(images) or not images[idx]:
            continue

        img_path = images[idx]
        im = Image.open(img_path).convert('RGBA')

        # 슬롯 비율에 맞춰 중앙 크롭
        target_ratio = slot['w'] / slot['h']
        w, h = im.size
        src_ratio = w / h

        if src_ratio > target_ratio:
            new_w = int(h * target_ratio)
            x0 = (w - new_w) // 2
            im = im.crop((x0, 0, x0 + new_w, h))
        elif src_ratio < target_ratio:
            new_h = int(w / target_ratio)
            y0 = (h - new_h) // 2
            im = im.crop((0, y0, w, y0 + new_h))

        dst_w = int(slot['w'] * scale_x)
        dst_h = int(slot['h'] * scale_y)
        dst_x = int(slot['x'] * scale_x)
        dst_y = int(slot['y'] * scale_y)

        im = im.resize((dst_w, dst_h), Image.LANCZOS)
        base.alpha_composite(im, (dst_x, dst_y))

    # 1.5) layout 합성 (있으면) — frame과 동일 사이즈 PNG
    layout_path = frame_path.parent / 'layout' / 'layout.png'
    if layout_path.exists():
        layout = Image.open(layout_path).convert('RGBA')
        if layout.size != (frame_w, frame_h):
            layout = layout.resize((frame_w, frame_h), Image.LANCZOS)
        # frame + 사진 위에 layout을 올림
        base.alpha_composite(layout, (0, 0))

    # 2) 스티커 합성 (있으면)
    stickers = stickers if stickers is not None else meta.get('stickers', [])
    if stickers and stickers_dir:
        stickers_dir = Path(stickers_dir)
        for st in stickers:
            sid = st.get('id')
            if not sid:
                continue
            sticker_path = stickers_dir / f"{sid}.png"
            if not sticker_path.exists():
                continue

            sim = Image.open(sticker_path).convert('RGBA')

            sw = float(st.get('w', 0))
            sh = float(st.get('h', 0))
            sx = float(st.get('x', 0))
            sy = float(st.get('y', 0))
            angle = float(st.get('angle', 0.0))

            # 프레임 픽셀 좌표계로 변환 (회전 전 기준 bounding box)
            dst_w = max(1, int(sw * scale_x))
            dst_h = max(1, int(sh * scale_y))
            dst_x = sx * scale_x
            dst_y = sy * scale_y

            # bounding box 중심
            cx = dst_x + dst_w / 2.0
            cy = dst_y + dst_h / 2.0

            sim = sim.resize((dst_w, dst_h), Image.LANCZOS)

            if angle != 0:
                sim = sim.rotate(angle, expand=True, resample=Image.BICUBIC)

            rw, rh = sim.size
            ox = int(cx - rw / 2.0)
            oy = int(cy - rh / 2.0)

            base.alpha_composite(sim, (ox, oy))

    # 최종 RGB로 저장
    result = base.convert('RGB')
    result.save(out_path, quality=95)
