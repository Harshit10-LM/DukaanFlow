import logging

logger = logging.getLogger(__name__)

# Supported text-to-speech model IDs (verified against ElevenLabs API, 2025-10)
# eleven_multilingual_v2 : 29 languages incl. English + Hindi, up to 10 000 chars — recommended default
# eleven_v3              : 70+ languages, up to 5 000 chars, more expressive
# eleven_flash_v2_5      : ultra-low-latency, real-time streaming only
DEFAULT_MODEL = 'eleven_multilingual_v2'
MAX_TEXT_LENGTH = 5000   # safe for both multilingual_v2 (10k) and v3 (5k)

class ElevenLabsService:
    def __init__(self, cfg, client_factory=None):
        self.key = cfg.get('ELEVENLABS_API_KEY')
        self.voice = cfg.get('ELEVENLABS_VOICE_ID')
        self.model = cfg.get('ELEVENLABS_MODEL_ID') or DEFAULT_MODEL
        self.client_factory = client_factory

    @property
    def configured(self):
        return bool(self.key and self.voice)

    def speech(self, text):
        """Generate MP3 audio bytes from *text* using the configured ElevenLabs voice.

        Raises:
            RuntimeError: credentials missing, auth failure, quota exceeded, or provider error.
            ValueError:   text is empty, not a string, or exceeds MAX_TEXT_LENGTH.
        """
        if not self.configured:
            raise RuntimeError('ElevenLabs is not configured. Set ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID.')
        if not text or not isinstance(text, str):
            raise ValueError('Approved customer reply text is required for audio generation.')
        cleaned = text.strip()
        if len(cleaned) < 1:
            raise ValueError('Approved reply must be between 1 and %d characters.' % MAX_TEXT_LENGTH)
        if len(cleaned) > MAX_TEXT_LENGTH:
            raise ValueError('Approved reply must be between 1 and %d characters.' % MAX_TEXT_LENGTH)

        try:
            if self.client_factory:
                client = self.client_factory(api_key=self.key)
            else:
                from elevenlabs.client import ElevenLabs
                client = ElevenLabs(api_key=self.key)

            # voice_id is the first positional argument in SDK >= 1.0
            audio_iter = client.text_to_speech.convert(
                self.voice,
                text=cleaned,
                model_id=self.model,
                output_format='mp3_44100_128',
            )
            return b''.join(audio_iter)
        except (ValueError, RuntimeError):
            raise
        except Exception as exc:
            status_code = getattr(exc, 'status_code', None)
            # Log only metadata — never the exception message which may contain key or text
            logger.warning(
                'ElevenLabs speech error: status=%s type=%s',
                status_code, exc.__class__.__name__
            )
            if status_code in (401, 403):
                raise RuntimeError('ElevenLabs authentication failed. Please verify your API key.') from exc
            elif status_code == 404:
                raise RuntimeError(
                    'ElevenLabs voice ID not found. Verify ELEVENLABS_VOICE_ID in your environment.'
                ) from exc
            elif status_code == 422:
                raise RuntimeError(
                    'ElevenLabs rejected the request — check ELEVENLABS_MODEL_ID and voice plan access.'
                ) from exc
            elif status_code == 429:
                raise RuntimeError('ElevenLabs quota or rate limit exceeded. Please wait or upgrade your plan.') from exc
            raise RuntimeError('ElevenLabs could not generate audio. Please try again later.') from exc

