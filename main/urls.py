from django.contrib import admin
from django.urls import path, re_path
from django.conf import settings
from django.views.static import serve 
from clientapp import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.index, name='index'),
    path('start/', views.startpage, name='startpage'),
    path('select_shot/', views.select_shot, name='select_shot'),
    path('select_theme/', views.select_theme, name='select_theme'),
    path('camera/', views.camera, name='camera'),
    path('upload_capture/', views.upload_capture, name='upload_capture'),
    path('preview/', views.preview, name='preview'),
    path('prepare_decorate/', views.prepare_decorate, name='prepare_decorate'),
    path('decorate/', views.decorate, name='decorate'),
    path('finalize/', views.finalize, name='finalize'),
    path('printing/', views.printing, name='printing'),
    path('print_action/', views.print_action, name='print_action'),
    
    path('admin_mode/', views.admin_mode, name='admin_mode'),
    path('admin_save_slots/', views.admin_save_slots, name='admin_save_slots'),

    # [핵심] 외부 static 폴더 및 media(Output) 폴더 강제 서빙
    # 이렇게 해야 배포 후 외부 폴더의 이미지를 불러올 수 있음
    re_path(r'^static/(?P<path>.*)$', serve, {'document_root': settings.BASE_DIR / 'static'}),
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
]