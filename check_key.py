from dotenv import load_dotenv
import os

load_dotenv()
key = os.environ.get("GEMINI_API_KEY", "NOT FOUND")
if key != "NOT FOUND":
    print("KEY FOUND:", key[:25] + "...")
else:
    print("KEY NOT FOUND in .env")
