from google import genai
import os
from dotenv import load_dotenv

load_dotenv()
client = genai.Client(api_key=os.environ.get('GEMINI_API_KEY'))

for model in ['gemini-2.5-flash', 'gemini-3.1-flash-lite', 'gemini-3.5-flash', 'gemini-flash-latest']:
    try:
        response = client.chats.create(model=model).send_message('hello')
        print(f'SUCCESS with {model}: {response.text}')
        break
    except Exception as e:
        print(f'FAILED with {model}: {e}')
