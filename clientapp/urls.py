from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('startpage', views.startpage, name='startpage'),
    path('select-shot', views.select_shot, name='select_shot'),
    path('select-theme', views.select_theme, name='select_theme'),
    path('camera', views.camera, name='camera'),

    path('preview', views.preview, name='preview'),
    path('prepare-decorate', views.prepare_decorate, name='prepare_decorate'),
    path('decorate', views.decorate, name='decorate'),
    path('finalize', views.finalize, name='finalize'),

    path('upload-capture', views.upload_capture, name='upload_capture'),

    path('admin-mode', views.admin_mode, name='admin_mode'),
    path('photo-admin/save-slots', views.admin_save_slots, name='admin_save_slots'),

    path('printing', views.printing, name='printing'),
]

# [핵심 수정] Static, Media, Temp 폴더 서빙 설정
if settings.DEBUG:
    # 정적 파일 (프레임 등)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    # 미디어 파일 (기존)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    # [추가] 임시 파일 (촬영된 사진 등) - 이걸 추가해야 사진이 보입니다!
    urlpatterns += static(settings.TEMP_URL, document_root=settings.TEMP_ROOT)