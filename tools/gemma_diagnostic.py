"""One-shot, safe Gemma connectivity diagnostic; never used by tests or routes."""
import os
import sys
from dotenv import load_dotenv

load_dotenv()
key=os.getenv('GEMMA_API_KEY')
model=os.getenv('GEMMA_MODEL','gemma-4-26b-a4b-it')
if not key:
    print('Gemma diagnostic: GEMMA_API_KEY is missing.')
    raise SystemExit(2)

try:
    from google import genai
    # Do not chain the temporary Client; the SDK may close it before send().
    client=genai.Client(api_key=key)
    response=client.models.generate_content(model=model,contents='Reply with exactly: OK')
    if not isinstance(getattr(response,'text',None),str) or not response.text.strip():
        print('Gemma diagnostic: request completed but returned no text.')
        raise SystemExit(1)
    print('Gemma diagnostic: minimal request succeeded for configured Gemma model.')
except Exception as exc:
    code=getattr(exc,'code',None)
    exception_name=exc.__class__.__name__.lower()
    if 'connect' in exception_name or 'network' in exception_name: category='network_connectivity'
    elif code in (401,403): category='authentication_or_permission'
    elif code==429: category='quota_or_rate_limit'
    elif code in (400,404): category='model_or_api_request'
    elif isinstance(code,int) and code>=500: category='provider_service'
    elif exception_name.find('timeout')>=0: category='timeout'
    else: category='unexpected_error'
    print(f'Gemma diagnostic: failed category={category} http_status={code if code is not None else "unknown"} exception_type={exc.__class__.__name__}.')
    raise SystemExit(1)
