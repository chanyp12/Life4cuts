# clientapp/urls.py
from django.urls import path
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

    # 관리자 모드 화면
    path('admin-mode', views.admin_mode, name='admin_mode'),
    # Django 기본 /admin/ 과 안 겹치게 prefix 변경
    path('photo-admin/save-slots', views.admin_save_slots, name='admin_save_slots'),

    # 인쇄 중 화면
    path('printing', views.printing, name='printing'),
]
