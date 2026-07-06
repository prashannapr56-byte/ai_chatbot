from google import genai
import os
from dotenv import load_dotenv

load_dotenv()
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

try:
    response = client.chats.create(model="gemini-2.0-flash-lite").send_message("hello")
    print("SUCCESS with gemini-2.0-flash-lite:", response.text)
except Exception as e:
    print("FAILED with gemini-2.0-flash-lite:", e)
