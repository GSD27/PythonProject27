from django.db import models

class AudioBook(models.Model):
    title = models.CharField(max_length=200)
    audio_file = models.FileField(upload_to='audiobooks/')
    transcription = models.TextField(blank=True, null=True)
    translation = models.JSONField(default=dict, blank=True, null=True)  
    target_languages = models.CharField(max_length=200, default='en')  
    
    def __str__(self):
        return self.title
