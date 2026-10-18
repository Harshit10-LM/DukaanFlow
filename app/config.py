import os
from dotenv import load_dotenv
load_dotenv()
class Config:
    SECRET_KEY=os.getenv('SECRET_KEY')
    ENVIRONMENT=os.getenv('FLASK_ENV','development')
    MONGODB_URI=os.getenv('MONGODB_URI')
    MONGODB_DB=os.getenv('MONGODB_DB','dukaanflow')
    GEMMA_API_KEY=os.getenv('GEMMA_API_KEY')
    GEMMA_MODEL=os.getenv('GEMMA_MODEL','gemma-4-26b-a4b-it')
    ELEVENLABS_API_KEY=os.getenv('ELEVENLABS_API_KEY')
    ELEVENLABS_VOICE_ID=os.getenv('ELEVENLABS_VOICE_ID')
    ELEVENLABS_MODEL_ID=os.getenv('ELEVENLABS_MODEL_ID','eleven_multilingual_v2')

    MAX_CONTENT_LENGTH=512*1024
    SESSION_COOKIE_HTTPONLY=True
    SESSION_COOKIE_SAMESITE='Lax'
    SESSION_COOKIE_SECURE=ENVIRONMENT=='production'
    WTF_CSRF_TIME_LIMIT=3600
