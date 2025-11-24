# 인생네컷 (Life4Cuts) — 브라우저 웹캠 캡처 버전

## 설치
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

## 특징
- 브라우저 getUserMedia로 영상 표시 + 캡처 (OpenCV/Channels 불필요)
- 캡처 이미지는 BASE64로 서버 업로드 → 세션에 경로 저장 → 미리보기/합성

## 사용 흐름
1. `clientapp/static/background/`에 시작 배경 이미지를 넣습니다.
2. `clientapp/static/frames/{3x1|4x4}/{테마}/frame.png`와 `slots.json`을 추가합니다.
3. 앱에서 3장/4장 선택 → 테마 선택 → 촬영(캡처 버튼) → 미리보기/매핑 → 저장.

