from django.db import models


class TtsClip(models.Model):
    """Cached text-to-speech audio, keyed by sha256(text + voice + model)."""

    key = models.CharField(max_length=64, unique=True)
    text = models.TextField()
    voice_id = models.CharField(max_length=64)
    model_id = models.CharField(max_length=64)
    audio = models.FileField(upload_to="tts/")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.text[:40]
