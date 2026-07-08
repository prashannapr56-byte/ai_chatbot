from google import genai
from google.genai import types
from flask import current_app
import os
import time
from PIL import Image as PILImage

CHAT_MODEL = "gemini-2.5-flash"  # Use gemini-2.5-flash for higher quotas and better quality


def generate_response(messages: list, system_instruction: str = None, image_paths: list = None) -> str:
    """
    Generate a response from Google Gemini.
    Uses the latest google-genai SDK.

    messages: list of dicts with 'role' (user/assistant) and 'content' keys.
    system_instruction: Optional system prompt to instruct the AI.
    image_paths: Optional list of paths to local images to include in context.
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

    # Load image parts if any
    pil_images = []
    if image_paths:
        for path in image_paths:
            if os.path.exists(path):
                try:
                    pil_images.append(PILImage.open(path))
                except Exception as e:
                    current_app.logger.error(f"Error opening image {path}: {e}")

    # Build latest user parts (text prompt + images)
    latest_parts = []
    if messages:
        latest_parts.append(messages[-1]["content"])
    latest_parts.extend(pil_images)

    # Configure chat options (such as Claude-like system instructions)
    config_params = {}
    if system_instruction:
        config_params["system_instruction"] = system_instruction
    config = types.GenerateContentConfig(**config_params) if config_params else None

    chat = client.chats.create(
        model=CHAT_MODEL,
        history=history,
        config=config
    )
    # Retry on 503 (overload) and 429 (rate limits)
    for attempt in range(3):
        try:
            response = chat.send_message(latest_parts)
            return response.text.strip()
        except Exception as e:
            err_str = str(e)
            if attempt < 2 and ('503' in err_str or '429' in err_str or 'resource_exhausted' in err_str.lower()):
                sleep_time = 5
                # Try to parse retryDelay from error (e.g. 'retryDelay': '11s' or '11.25s')
                import re
                match = re.search(r"retryDelay':\s*'([\d\.]+)s'", err_str)
                if match:
                    try:
                        sleep_time = float(match.group(1)) + 0.5
                    except ValueError:
                        pass
                elif '429' in err_str:
                    sleep_time = 12
                time.sleep(sleep_time)
                continue
            raise


def generate_response_stream(messages: list, system_instruction: str = None, image_paths: list = None):
    """
    Generate a streaming response from Google Gemini.
    """
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

    # Load image parts if any
    pil_images = []
    if image_paths:
        for path in image_paths:
            if os.path.exists(path):
                try:
                    pil_images.append(PILImage.open(path))
                except Exception as e:
                    current_app.logger.error(f"Error opening image {path}: {e}")

    # Build latest user parts (text prompt + images)
    latest_parts = []
    if messages:
        latest_parts.append(messages[-1]["content"])
    latest_parts.extend(pil_images)

    # Configure chat options (such as Claude-like system instructions)
    config_params = {}
    if system_instruction:
        config_params["system_instruction"] = system_instruction
    config = types.GenerateContentConfig(**config_params) if config_params else None

    chat = client.chats.create(
        model=CHAT_MODEL,
        history=history,
        config=config
    )
    # Retry on 503 and 429
    for attempt in range(3):
        try:
            response = chat.send_message_stream(latest_parts)
            for chunk in response:
                if chunk.text:
                    yield chunk.text
            return
        except Exception as e:
            err_str = str(e)
            if attempt < 2 and ('503' in err_str or '429' in err_str or 'resource_exhausted' in err_str.lower()):
                sleep_time = 5
                import re
                match = re.search(r"retryDelay':\s*'([\d\.]+)s'", err_str)
                if match:
                    try:
                        sleep_time = float(match.group(1)) + 0.5
                    except ValueError:
                        pass
                elif '429' in err_str:
                    sleep_time = 12
                time.sleep(sleep_time)
                continue
            raise


def generate_image(prompt: str) -> bytes:
    """
    Generate an image using gemini-2.5-flash-image (confirmed available).
    Single API call, no fallback loop — avoids wasting credits.
    """
    api_key = current_app.config.get("GEMINI_API_KEY")
    if not api_key or api_key.strip() == "your-gemini-api-key":
        raise RuntimeError("GEMINI_API_KEY not set.")

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model="gemini-2.5-flash-image",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=["TEXT", "IMAGE"]
        )
    )
    for part in response.candidates[0].content.parts:
        if part.inline_data is not None:
            return part.inline_data.data
    raise RuntimeError("No image returned. Try rephrasing your prompt.")


def generate_image_edit(prompt: str, image_path: str) -> bytes:
    """
    Edit/modify an uploaded image using gemini-2.5-flash-image.
    Passes the image directly — no separate describe call, saves credits.
    """
    api_key = current_app.config.get("GEMINI_API_KEY")
    if not api_key or api_key.strip() == "your-gemini-api-key":
        raise RuntimeError("GEMINI_API_KEY not set.")

    client = genai.Client(api_key=api_key)
    pil_image = PILImage.open(image_path)
    response = client.models.generate_content(
        model="gemini-2.5-flash-image",
        contents=[prompt, pil_image],
        config=types.GenerateContentConfig(
            response_modalities=["TEXT", "IMAGE"]
        )
    )
    for part in response.candidates[0].content.parts:
        if part.inline_data is not None:
            return part.inline_data.data
    raise RuntimeError("No edited image returned. Try rephrasing your request.")


