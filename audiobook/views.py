from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponse, FileResponse
from django.views.decorators.csrf import csrf_exempt
from .models import AudioBook
import whisper
from googletrans import Translator
from gtts import gTTS
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from django.core.cache import cache
import time
import hashlib
from pathlib import Path
import re


_whisper_model = None

def get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        _whisper_model = whisper.load_model("tiny")  
    return _whisper_model

def split_into_sentences(text):
    """Split text into sentences for better TTS processing"""
    
    sentences = re.split(r'(?<=[.!?])\s+', text)
    return [s.strip() for s in sentences if s.strip()]

def chunk_text_for_display(text, max_chars=300):
    """Split text into readable paragraphs"""
    sentences = split_into_sentences(text)
    paragraphs = []
    current_paragraph = []
    current_length = 0
    
    for sentence in sentences:
        if current_length + len(sentence) > max_chars and current_paragraph:
            paragraphs.append(' '.join(current_paragraph))
            current_paragraph = [sentence]
            current_length = len(sentence)
        else:
            current_paragraph.append(sentence)
            current_length += len(sentence)
    
    if current_paragraph:
        paragraphs.append(' '.join(current_paragraph))
    
    return paragraphs

def chunk_text(text, chunk_size=1000):
    """Split text into smaller chunks for translation"""
    sentences = split_into_sentences(text)
    chunks = []
    current_chunk = []
    current_size = 0
    
    for sentence in sentences:
        if current_size + len(sentence) > chunk_size and current_chunk:
            chunks.append(' '.join(current_chunk))
            current_chunk = [sentence]
            current_size = len(sentence)
        else:
            current_chunk.append(sentence)
            current_size += len(sentence)
    
    if current_chunk:
        chunks.append(' '.join(current_chunk))
    
    return chunks

def translate_text(text, lang, translator):
    cache_key = f"translation_{hashlib.md5(text.encode()).hexdigest()}_{lang}"
    cached_translation = cache.get(cache_key)
    if cached_translation:
        return lang, cached_translation
    
    # Add a small delay between translations to avoid rate limiting
    time.sleep(0.2)  # Reduced delay
    try:
        translation = translator.translate(text, dest=lang)
        cache.set(cache_key, translation.text, timeout=86400)  # Cache for 24 hours
        return lang, translation.text
    except Exception as e:
        return lang, str(e)

def get_tts_audio_path(text, lang):
    """Get path for TTS audio file"""
    text_hash = hashlib.md5(text.encode()).hexdigest()
    audio_dir = Path('media/tts_audio')
    audio_dir.mkdir(parents=True, exist_ok=True)
    return audio_dir / f"{text_hash}_{lang}.mp3"

@csrf_exempt
def text_to_speech(request, audiobook_id, lang_code):
    """Generate or retrieve cached TTS audio"""
    try:
        audiobook = get_object_or_404(AudioBook, id=audiobook_id)
        text = audiobook.translation.get(lang_code, '')
        if not text:
            return JsonResponse({'error': 'Translation not found'}, status=404)

        # Create media directory if it doesn't exist
        media_dir = Path('media/tts_audio')
        media_dir.mkdir(parents=True, exist_ok=True)

        # Generate unique filename based on content hash
        file_hash = hashlib.md5(text.encode()).hexdigest()
        audio_path = media_dir / f"{file_hash}_{lang_code}.mp3"

        # Generate audio file if it doesn't exist
        if not audio_path.exists():
            tts = gTTS(text=text, lang=lang_code, slow=False)
            tts.save(str(audio_path))

        return FileResponse(open(audio_path, 'rb'), content_type='audio/mpeg')
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

def index(request):
    audiobooks = AudioBook.objects.all()
    languages = {
        'en': 'English',
        'es': 'Spanish',
        'fr': 'French',
        'de': 'German',
        'it': 'Italian',
        'pt': 'Portuguese',
        'ru': 'Russian',
        'ja': 'Japanese',
        'ko': 'Korean',
        'zh-cn': 'Chinese (Simplified)',
        'ta': 'Tamil',
        'te': 'Telugu',
        'kn': 'Kannada'
    }
    
    # Format translations for display
    formatted_audiobooks = []
    for book in audiobooks:
        formatted_book = {
            'id': book.id,
            'title': book.title,
            'audio_file': book.audio_file,
            'transcription': book.transcription,
            'translations': book.translation if book.translation else {}
        }
        formatted_audiobooks.append(formatted_book)
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'audiobooks': formatted_audiobooks})
    
    return render(request, 'audiobook/index.html', {
        'audiobooks': formatted_audiobooks,
        'languages': languages
    })

@csrf_exempt
def upload_audiobook(request):
    if request.method == 'POST':
        title = request.POST.get('title')
        audio_file = request.FILES.get('audio_file')
        target_language = request.POST.get('target_languages')  # Changed from getlist to get
        
        if not target_language:  # Check for single language
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'status': 'error', 'message': 'Please select a target language'})
            return redirect('audiobook:index')
        
        if title and audio_file:
            audiobook = AudioBook.objects.create(
                title=title,
                audio_file=audio_file,
                target_languages=target_language  # Store single language
            )
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'status': 'success', 'id': audiobook.id})
            return redirect('audiobook:index')
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'status': 'error', 'message': 'Invalid request'})
    return redirect('audiobook:index')

@csrf_exempt
def process_audiobook(request, audiobook_id):
    audiobook = get_object_or_404(AudioBook, id=audiobook_id)
    
    try:
        # Transcribe if not already done
        if not audiobook.transcription:
            model = get_whisper_model()
            result = model.transcribe(
                audiobook.audio_file.path,
                initial_prompt="This is an audiobook transcription.",
                fp16=False  # Disable half-precision for better compatibility
            )
            audiobook.transcription = result["text"]
            audiobook.save()
        
        # Translate to the selected language
        translator = Translator()
        translations = {}
        target_language = audiobook.target_languages  # Now a single language
        
        # Handle English separately
        if target_language == 'en':
            translations['en'] = audiobook.transcription
        else:
            try:
                translation = translator.translate(audiobook.transcription, dest=target_language)
                translations[target_language] = translation.text
            except Exception as e:
                translations[target_language] = f"Translation failed: {str(e)}"
        
        audiobook.translation = translations
        audiobook.save()
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'status': 'success',
                'transcription': audiobook.transcription,
                'translations': translations
            })
        return redirect('audiobook:index')
        
    except Exception as e:
        error_message = str(e)
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'status': 'error',
                'message': error_message
            })
        return redirect('audiobook:index')

@csrf_exempt
def delete_audiobook(request, audiobook_id):
    try:
        audiobook = get_object_or_404(AudioBook, id=audiobook_id)
        
        # Delete the audio file from storage
        if audiobook.audio_file:
            if os.path.exists(audiobook.audio_file.path):
                os.remove(audiobook.audio_file.path)
        
        # Delete any TTS audio files
        if audiobook.translation:
            for lang_code in audiobook.translation.keys():
                text = audiobook.translation[lang_code]
                text_hash = hashlib.md5(text.encode()).hexdigest()
                tts_path = Path('media/tts_audio') / f"{text_hash}_{lang_code}.mp3"
                if tts_path.exists():
                    os.remove(tts_path)
        
        # Delete the database record
        audiobook.delete()
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'status': 'success'})
        return redirect('audiobook:index')
        
    except Exception as e:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'status': 'error', 'message': str(e)})
        return redirect('audiobook:index')
