from google import genai
from flask import current_app


def generate_response(messages: list) -> str:
    """
    Generate a response from Google Gemini (free tier, no payment required).
    Uses the latest google-genai SDK.

    messages: list of dicts with 'role' (user/assistant) and 'content' keys.
    """
    api_key = current_app.config.get("GEMINI_API_KEY")
    if not api_key or api_key.strip() == "your-gemini-api-key":
        raise RuntimeError(
            "GEMINI_API_KEY not set. Please go to https://aistudio.google.com/app/apikey, "
            "create a free key, and add it to your .env file as GEMINI_API_KEY=..."
        )

    client = genai.Client(api_key=api_key)

    # Build history list in Gemini format (all except the last user message)
    history = []
    for msg in messages[:-1]:
        role = "user" if msg["role"] == "user" else "model"
        history.append(
            genai.types.Content(
                role=role,
                parts=[genai.types.Part(text=msg["content"])]
            )
        )

    # The final user message
    latest = messages[-1]["content"] if messages else ""

    chat = client.chats.create(
        model="gemini-flash-lite-latest",
        history=history
    )
    response = chat.send_message(latest)
    return response.text.strip()

def generate_response_stream(messages: list):
    api_key = current_app.config.get("GEMINI_API_KEY")
    if not api_key or api_key.strip() == "your-gemini-api-key":
        raise RuntimeError("GEMINI_API_KEY not set.")

    client = genai.Client(api_key=api_key)

    history = []
    for msg in messages[:-1]:
        role = "user" if msg["role"] == "user" else "model"
        history.append(
            genai.types.Content(
                role=role,
                parts=[genai.types.Part(text=msg["content"])]
            )
        )
    latest = messages[-1]["content"] if messages else ""

    chat = client.chats.create(
        model="gemini-flash-lite-latest",
        history=history
    )
    
    response = chat.send_message_stream(latest)
    for chunk in response:
        if chunk.text:
            yield chunk.text

