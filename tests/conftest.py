import pytest
from app import create_app
@pytest.fixture
def app(): return create_app({'TESTING':True,'WTF_CSRF_ENABLED':False,'SECRET_KEY':'test','MONGODB_URI':None})
@pytest.fixture
def client(app): return app.test_client()
def login(client): return client.post('/login',data={'email':'demo@dukaanflow.test','password':'DemoPass123'},follow_redirects=True)
