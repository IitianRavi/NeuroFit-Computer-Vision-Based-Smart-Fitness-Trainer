from io import BytesIO
from gtts import gTTS


VOICE_LANGUAGES = {
    "Hindi / Hinglish": ("hi", "Hindi, using natural Hinglish gym terms"),
    "English": ("en", "English"),
    "Marathi": ("mr", "Marathi"),
    "Bengali": ("bn", "Bengali"),
    "Tamil": ("ta", "Tamil"),
    "Telugu": ("te", "Telugu"),
    "Kannada": ("kn", "Kannada"),
    "Malayalam": ("ml", "Malayalam"),
    "Gujarati": ("gu", "Gujarati"),
    "Punjabi": ("pa", "Punjabi"),
}


class TextToSpeech:
    def speak(self, text, lang="hi"):
        cleaned = (text or "").strip()

        if not cleaned:
            return
        
        buffer = BytesIO()

        gTTS(text=cleaned, lang=lang).write_to_fp(buffer)

        buffer.seek(0)

        return buffer.read()
    
