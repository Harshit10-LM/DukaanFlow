import json
import pytest
from app.services.gemma_service import GemmaError, GemmaNotConfiguredError, GemmaResponseError, GemmaService

VALID_SINGLE = {
    "customer_name": "Asha",
    "customer_contact": None,
    "items": [{"product_name": "Navy Kurti", "variant": "M", "quantity": 1, "quoted_unit_price": 650, "price_needs_verification": True}],
    "delivery_request_text": "by Friday",
    "delivery_address": None,
    "payment_terms": "half now",
    "stated_advance_amount": 650,
    "notes": None,
    "missing_fields": ["delivery address"],
    "ambiguous_fields": ["Friday date"],
    "clarification_questions": ["What address should we use?"],
    "customer_reply_draft": "Please share your address."
}

VALID_MULTI_VARIANT = {
    "customer_name": None,
    "customer_contact": None,
    "items": [
        {"product_name": "Navy Kurti", "variant": "Medium", "quantity": 1, "quoted_unit_price": 650, "price_needs_verification": True},
        {"product_name": "Navy Kurti", "variant": "Large", "quantity": 1, "quoted_unit_price": 650, "price_needs_verification": True}
    ],
    "delivery_request_text": "by Friday",
    "delivery_address": None,
    "payment_terms": "half advance",
    "stated_advance_amount": None,
    "notes": None,
    "missing_fields": ["customer_name", "delivery_address"],
    "ambiguous_fields": ["Friday delivery date"],
    "clarification_questions": ["What is your name and delivery address?"],
    "customer_reply_draft": "Hi! Thanks for ordering 2 Navy Kurtis (Medium & Large). Please share your delivery address."
}

class Response:
    def __init__(self, text):
        self.text = text

class Models:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.called = None
    def generate_content(self, **kwargs):
        self.called = kwargs
        if self.error:
            raise self.error
        return self.response

class Client:
    def __init__(self, models):
        self.models = models

def service(response=None, error=None):
    models = Models(response, error)
    return GemmaService({'GEMMA_API_KEY': 'test-key', 'GEMMA_MODEL': 'gemma-4-26b-a4b-it'}, lambda **_: Client(models)), models

def test_successful_multi_variant_extraction():
    s, models = service(Response(json.dumps(VALID_MULTI_VARIANT)))
    result = s.extract("Hi, I need two navy kurtis, one medium and one large.", [{'name': 'Navy Kurti', 'price': '650'}])
    assert len(result['items']) == 2
    assert result['items'][0]['product_name'] == 'Navy Kurti'
    assert result['items'][0]['variant'] == 'Medium'
    assert result['items'][0]['quantity'] == 1
    assert result['items'][0]['quoted_unit_price'] == '650.00'
    assert result['items'][1]['product_name'] == 'Navy Kurti'
    assert result['items'][1]['variant'] == 'Large'
    assert result['items'][1]['quantity'] == 1
    assert result['items'][1]['quoted_unit_price'] == '650.00'
    assert models.called['model'] == 'gemma-4-26b-a4b-it'
    assert 'CRITICAL MULTI-ITEM AND VARIANT RULE' in models.called['config'].system_instruction

def test_malformed_json_is_a_safe_response_error():
    s, _ = service(Response('{not-json'))
    with pytest.raises(GemmaResponseError, match='invalid order draft'):
        s.extract('hello', [])

def test_empty_message_rejected():
    s, _ = service(Response('{}'))
    with pytest.raises(GemmaResponseError, match='Paste a customer message'):
        s.extract('', [])

def test_missing_credentials_keeps_manual_workflow_available():
    with pytest.raises(GemmaNotConfiguredError, match='manually'):
        GemmaService({'GEMMA_API_KEY': None}).extract('hello', [])

def test_provider_error_is_safe_and_does_not_leak_details():
    s, _ = service(error=Exception('quota internal credential details'))
    with pytest.raises(GemmaError, match='could not process') as exc:
        s.extract('hello', [])
    assert 'credential details' not in str(exc.value)

def test_markdown_fenced_json_is_accepted():
    s, _ = service(Response('```json\n' + json.dumps(VALID_SINGLE) + '\n```'))
    assert s.extract('hello', [])['customer_name'] == 'Asha'

def test_quota_error_has_a_useful_safe_message():
    class ProviderError(Exception):
        code = 429
    s, _ = service(error=ProviderError('quota exceeded'))
    with pytest.raises(GemmaError, match='rate limit or quota') as exc:
        s.extract('hello', [])
    assert 'quota exceeded' not in str(exc.value)

def test_auth_error_has_safe_message():
    class AuthError(Exception):
        code = 401
    s, _ = service(error=AuthError('invalid key'))
    with pytest.raises(GemmaError, match='authentication or permission') as exc:
        s.extract('hello', [])
    assert 'invalid key' not in str(exc.value)

def test_timeout_error_is_distinguished():
    class TimeoutException(Exception):
        pass
    TimeoutException.__name__ = 'GatewayTimeout'
    s, _ = service(error=TimeoutException('timed out waiting for response'))
    with pytest.raises(GemmaError, match='timed out') as exc:
        s.extract('hello', [])
    assert 'waiting for response' not in str(exc.value)

def test_connectivity_error_is_distinguished_from_provider_rejection():
    class ConnectError(Exception):
        pass
    s, _ = service(error=ConnectError('network internals'))
    with pytest.raises(GemmaError, match='could not be reached') as exc:
        s.extract('hello', [])
    assert 'network internals' not in str(exc.value)

def test_invalid_quantity_is_rejected():
    payload = {**VALID_SINGLE, 'items': [dict(VALID_SINGLE['items'][0], quantity=-2)]}
    s, _ = service(Response(json.dumps(payload)))
    with pytest.raises(GemmaResponseError):
        s.extract('hello', [])
