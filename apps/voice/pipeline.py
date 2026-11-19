from apps.channels.models import OutboxMessage
from apps.jobs.queue import handler

from .tts import speak


@handler("voice.tts_for_message")
def tts_for_message(payload: dict) -> dict:
    msg = OutboxMessage.objects.get(pk=payload["message_id"])
    clip = speak(msg.body, msg.language)
    msg.audio_url = clip.audio.url
    msg.save(update_fields=["audio_url"])
    return {"clip": clip.pk}
