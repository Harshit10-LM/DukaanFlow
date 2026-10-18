import pytest
from app.services.elevenlabs_service import ElevenLabsService, MAX_TEXT_LENGTH


class MockAudioIterator:
    def __init__(self, chunks):
        self.chunks = chunks

    def __iter__(self):
        return iter(self.chunks)


class MockTTS:
    def __init__(self, chunks=None, error=None):
        self.chunks = chunks or [b'ID3', b'\x00\x00', b'audio-data']
        self.error = error
        self.last_call = None
        self.last_voice_id = None

    def convert(self, voice_id, **kwargs):
        self.last_voice_id = voice_id
        self.last_call = kwargs
        if self.error:
            raise self.error
        return MockAudioIterator(self.chunks)


class MockElevenLabsClient:
    def __init__(self, api_key=None, tts=None):
        self.api_key = api_key
        self.text_to_speech = tts or MockTTS()


# ── Service unit tests ──────────────────────────────────────────────────────

def test_successful_mocked_speech_generation():
    mock_tts = MockTTS([b'fake-mp3-bytes'])
    service = ElevenLabsService(
        {'ELEVENLABS_API_KEY': 'test-key', 'ELEVENLABS_VOICE_ID': 'test-voice', 'ELEVENLABS_MODEL_ID': 'eleven_multilingual_v2'},
        client_factory=lambda **_: MockElevenLabsClient(tts=mock_tts)
    )
    assert service.configured is True
    audio = service.speech('Thank you for your order! It will be delivered on Friday.')
    assert audio == b'fake-mp3-bytes'
    # voice_id is passed positionally — verify via last_voice_id
    assert mock_tts.last_voice_id == 'test-voice'
    assert mock_tts.last_call['model_id'] == 'eleven_multilingual_v2'
    assert mock_tts.last_call['output_format'] == 'mp3_44100_128'


def test_missing_credentials_raises_runtime_error():
    service = ElevenLabsService({'ELEVENLABS_API_KEY': None, 'ELEVENLABS_VOICE_ID': None})
    assert service.configured is False
    with pytest.raises(RuntimeError, match='not configured'):
        service.speech('Hello')


def test_missing_voice_id_not_configured():
    service = ElevenLabsService({'ELEVENLABS_API_KEY': 'sk-key', 'ELEVENLABS_VOICE_ID': None})
    assert service.configured is False
    with pytest.raises(RuntimeError, match='not configured'):
        service.speech('Hello')


def test_invalid_or_empty_text_raises_value_error():
    service = ElevenLabsService({'ELEVENLABS_API_KEY': 'k', 'ELEVENLABS_VOICE_ID': 'v'})
    with pytest.raises(ValueError, match='required'):
        service.speech('')
    with pytest.raises(ValueError, match='between 1 and'):
        service.speech('   ')
    with pytest.raises(ValueError, match='between 1 and'):
        service.speech('a' * (MAX_TEXT_LENGTH + 1))


def test_provider_401_auth_error_is_sanitized():
    class ApiAuthError(Exception):
        status_code = 401
    mock_tts = MockTTS(error=ApiAuthError('secret-token leaked here'))
    service = ElevenLabsService(
        {'ELEVENLABS_API_KEY': 'k', 'ELEVENLABS_VOICE_ID': 'v'},
        client_factory=lambda **_: MockElevenLabsClient(tts=mock_tts)
    )
    with pytest.raises(RuntimeError, match='authentication failed') as exc:
        service.speech('Hello')
    assert 'secret-token' not in str(exc.value)


def test_provider_404_voice_not_found():
    class ApiNotFoundError(Exception):
        status_code = 404
    mock_tts = MockTTS(error=ApiNotFoundError('voice not found'))
    service = ElevenLabsService(
        {'ELEVENLABS_API_KEY': 'k', 'ELEVENLABS_VOICE_ID': 'bad-voice'},
        client_factory=lambda **_: MockElevenLabsClient(tts=mock_tts)
    )
    with pytest.raises(RuntimeError, match='voice ID not found'):
        service.speech('Hello')


def test_provider_429_quota_error():
    class ApiQuotaError(Exception):
        status_code = 429
    mock_tts = MockTTS(error=ApiQuotaError('quota limit'))
    service = ElevenLabsService(
        {'ELEVENLABS_API_KEY': 'k', 'ELEVENLABS_VOICE_ID': 'v'},
        client_factory=lambda **_: MockElevenLabsClient(tts=mock_tts)
    )
    with pytest.raises(RuntimeError, match='quota or rate limit'):
        service.speech('Hello')


def test_provider_422_bad_request():
    class ApiUnprocessableError(Exception):
        status_code = 422
    mock_tts = MockTTS(error=ApiUnprocessableError('unprocessable entity'))
    service = ElevenLabsService(
        {'ELEVENLABS_API_KEY': 'k', 'ELEVENLABS_VOICE_ID': 'v'},
        client_factory=lambda **_: MockElevenLabsClient(tts=mock_tts)
    )
    with pytest.raises(RuntimeError, match='rejected the request'):
        service.speech('Hello')


def test_default_model_is_multilingual_v2():
    service = ElevenLabsService({'ELEVENLABS_API_KEY': 'k', 'ELEVENLABS_VOICE_ID': 'v'})
    assert service.model == 'eleven_multilingual_v2'


def test_model_override_from_config():
    service = ElevenLabsService(
        {'ELEVENLABS_API_KEY': 'k', 'ELEVENLABS_VOICE_ID': 'v', 'ELEVENLABS_MODEL_ID': 'eleven_v3'}
    )
    assert service.model == 'eleven_v3'


# ── Flask route integration tests ────────────────────────────────────────────

def _make_speak_factory(audio_bytes):
    """Return a client_factory that always returns good audio."""
    mock_tts = MockTTS(chunks=[audio_bytes])

    def factory(**_):
        return MockElevenLabsClient(tts=mock_tts)
    return factory


def test_speak_route_returns_json_for_xhr(client, app, monkeypatch):
    """POST /orders/<id>/speak with XHR header should return JSON {audio_url, download_url}."""
    from app.services.elevenlabs_service import ElevenLabsService

    def mock_speech(self, text):
        return b'FAKE-MP3'

    monkeypatch.setattr(ElevenLabsService, 'speech', mock_speech)

    # Patch configured so it doesn't raise credentials error
    monkeypatch.setattr(ElevenLabsService, 'configured', property(lambda self: True))

    from tests.test_app import login
    login(client)
    repo = app.extensions['repo']
    user = repo.by_email('demo@dukaanflow.test')
    order = repo.create_order(user['_id'], {
        'customer_name': 'Test',
        'items': [{'name': 'Item', 'quantity': 1, 'selling_price': '100.00'}],
        'reply_draft': 'Your order is confirmed!',
        'status': 'Draft',
    })
    order_id = str(order['_id'])

    r = client.post(
        f'/orders/{order_id}/speak',
        data={'reply_text': 'Your order is confirmed!', 'csrf_token': ''},
        headers={'X-Requested-With': 'XMLHttpRequest'},
    )
    assert r.status_code == 200
    body = r.get_json()
    assert 'audio_url' in body
    assert 'download_url' in body
    assert f'/orders/{order_id}/audio' in body['audio_url']


def test_speak_route_audio_endpoint_returns_mp3(client, app, monkeypatch):
    """GET /orders/<id>/audio should return audio/mpeg after a successful speak."""
    from app.services.elevenlabs_service import ElevenLabsService

    fake_bytes = b'FAKE-MP3-DATA'

    def mock_speech(self, text):
        return fake_bytes

    monkeypatch.setattr(ElevenLabsService, 'speech', mock_speech)
    monkeypatch.setattr(ElevenLabsService, 'configured', property(lambda self: True))

    from tests.test_app import login
    login(client)
    repo = app.extensions['repo']
    user = repo.by_email('demo@dukaanflow.test')
    order = repo.create_order(user['_id'], {
        'customer_name': 'Test2',
        'items': [{'name': 'Item', 'quantity': 1, 'selling_price': '200.00'}],
        'reply_draft': 'Ready for you!',
        'status': 'Draft',
    })
    order_id = str(order['_id'])

    # Trigger generation
    r_speak = client.post(
        f'/orders/{order_id}/speak',
        data={'reply_text': 'Ready for you!'},
        headers={'X-Requested-With': 'XMLHttpRequest'},
    )
    assert r_speak.status_code == 200

    # Fetch audio
    r_audio = client.get(f'/orders/{order_id}/audio')
    assert r_audio.status_code == 200
    assert r_audio.content_type == 'audio/mpeg'
    assert r_audio.data == fake_bytes


def test_speak_route_download_returns_attachment(client, app, monkeypatch):
    """GET /orders/<id>/audio/download should return Content-Disposition: attachment."""
    from app.services.elevenlabs_service import ElevenLabsService

    monkeypatch.setattr(ElevenLabsService, 'speech', lambda self, text: b'MP3')
    monkeypatch.setattr(ElevenLabsService, 'configured', property(lambda self: True))

    from tests.test_app import login
    login(client)
    repo = app.extensions['repo']
    user = repo.by_email('demo@dukaanflow.test')
    order = repo.create_order(user['_id'], {
        'customer_name': 'Test3',
        'items': [{'name': 'Item', 'quantity': 1, 'selling_price': '300.00'}],
        'reply_draft': 'Download me!',
        'status': 'Draft',
    })
    order_id = str(order['_id'])

    client.post(
        f'/orders/{order_id}/speak',
        data={'reply_text': 'Download me!'},
        headers={'X-Requested-With': 'XMLHttpRequest'},
    )
    r = client.get(f'/orders/{order_id}/audio/download')
    assert r.status_code == 200
    assert 'attachment' in r.headers.get('Content-Disposition', '')
    assert r.content_type == 'audio/mpeg'


def test_speak_route_cross_user_isolation(client, app, monkeypatch):
    """User B must not be able to generate or retrieve audio for User A's order."""
    from app.services.elevenlabs_service import ElevenLabsService
    monkeypatch.setattr(ElevenLabsService, 'speech', lambda self, text: b'MP3')
    monkeypatch.setattr(ElevenLabsService, 'configured', property(lambda self: True))

    from tests.test_app import login
    repo = app.extensions['repo']
    u1 = repo.create_user('speaker1@test.com', 'Pass12345', 'Speaker Shop 1')
    order = repo.create_order(u1['_id'], {
        'customer_name': 'Secret Buyer',
        'items': [{'name': 'Item', 'quantity': 1, 'selling_price': '100.00'}],
        'reply_draft': 'Secret reply',
        'status': 'Draft',
    })
    order_id = str(order['_id'])

    repo.create_user('speaker2@test.com', 'Pass12345', 'Speaker Shop 2')
    login(client, 'speaker2@test.com', 'Pass12345')

    # User 2 tries to POST speak on User 1's order
    r_speak = client.post(
        f'/orders/{order_id}/speak',
        data={'reply_text': 'Hacked!'},
        headers={'X-Requested-With': 'XMLHttpRequest'},
    )
    assert r_speak.status_code == 404

    # User 2 tries to GET audio
    r_audio = client.get(f'/orders/{order_id}/audio')
    assert r_audio.status_code == 404

    r_dl = client.get(f'/orders/{order_id}/audio/download')
    assert r_dl.status_code == 404


def test_speak_route_empty_text_returns_400(client, app):
    """POST /speak with blank reply_text and no stored draft should return 400."""
    from tests.test_app import login
    login(client)
    repo = app.extensions['repo']
    user = repo.by_email('demo@dukaanflow.test')
    order = repo.create_order(user['_id'], {
        'customer_name': 'Blank',
        'items': [{'name': 'Item', 'quantity': 1, 'selling_price': '100.00'}],
        'status': 'Draft',
    })
    order_id = str(order['_id'])

    r = client.post(
        f'/orders/{order_id}/speak',
        data={'reply_text': '   '},
        headers={'X-Requested-With': 'XMLHttpRequest'},
    )
    assert r.status_code == 400
    assert 'error' in r.get_json()


def test_speak_route_handles_unconfigured_voice_gracefully(client, app):
    """POST /speak when ElevenLabs not configured → JSON error, no crash."""
    from tests.test_app import login
    login(client)
    repo = app.extensions['repo']
    user = repo.by_email('demo@dukaanflow.test')
    order = repo.create_order(user['_id'], {
        'customer_name': 'Test User',
        'items': [{'name': 'Item 1', 'quantity': 1, 'selling_price': '100.00'}],
        'reply_draft': 'Hello customer',
        'status': 'Draft',
    })
    order_id = str(order['_id'])

    r = client.post(
        f'/orders/{order_id}/speak',
        data={'reply_text': 'Hello customer'},
        headers={'X-Requested-With': 'XMLHttpRequest'},
    )
    # Must not crash; when unconfigured the service raises RuntimeError → 503
    assert r.status_code in (400, 503)
    body = r.get_json()
    assert 'error' in body
    assert 'ElevenLabs' in body['error'] or 'configured' in body['error']
