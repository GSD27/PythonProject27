from django.urls import path
from . import views
from django.conf import settings
from django.conf.urls.static import static

app_name = 'audiobook'

urlpatterns = [
    path('', views.index, name='index'),
    path('upload/', views.upload_audiobook, name='upload_audiobook'),
    path('process/<int:audiobook_id>/', views.process_audiobook, name='process_audiobook'),
    path('tts/<int:audiobook_id>/<str:lang_code>/', views.text_to_speech, name='text_to_speech'),
    path('delete/<int:audiobook_id>/', views.delete_audiobook, name='delete_audiobook'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT) 