from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, current_app, Response, stream_with_context
import json
from flask_login import login_required, current_user
from app import db
from app.models.chat import Chat, Message, MessageRole, ChatStatus
from app.models.file import File, FileType, FileStatus
from app.utils.s3_helper import upload_file_to_s3
from app.utils.gemini_client import generate_response as gemini_response
import datetime
import uuid
import os
from werkzeug.utils import secure_filename

chat_bp = Blueprint('chat', __name__)


def extract_text_from_file(filepath, file_type):
    from app.models.file import FileType
    if file_type == FileType.PDF:
        try:
            import pdfplumber
            with pdfplumber.open(filepath) as pdf:
                text_pages = []
                for page in pdf.pages:
                    t = page.extract_text()
                    if t:
                        text_pages.append(t)
                return "\n".join(text_pages).strip()
        except Exception as e:
            current_app.logger.error(f"Error reading PDF {filepath}: {e}")
            return None
    elif file_type == FileType.DOCX:
        try:
            import docx
            doc = docx.Document(filepath)
            text_runs = []
            for p in doc.paragraphs:
                if p.text:
                    text_runs.append(p.text)
            return "\n".join(text_runs).strip()
        except Exception as e:
            current_app.logger.error(f"Error reading Word doc {filepath}: {e}")
            return None
    elif file_type in (FileType.TXT, FileType.CSV):
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read().strip()
        except Exception as e:
            current_app.logger.error(f"Error reading text file {filepath}: {e}")
            return None
    return None


def get_file_type(filename):
    ext = os.path.splitext(filename)[1].lower()
    if ext in ['.png', '.jpg', '.jpeg', '.gif']:
        return FileType.IMAGE
    elif ext == '.pdf':
        return FileType.PDF
    elif ext in ['.docx', '.doc']:
        return FileType.DOCX
    elif ext == '.txt':
        return FileType.TXT
    elif ext == '.csv':
        return FileType.CSV
    else:
        return FileType.OTHER


@chat_bp.route('/')
@login_required
def index():
    chats = Chat.query.filter_by(user_id=current_user.id, status=ChatStatus.ACTIVE).order_by(Chat.updated_at.desc()).all()
    return render_template('chat/index.html', chats=chats)


@chat_bp.route('/new', methods=['POST'])
@login_required
def new_chat():
    chat = Chat(user_id=current_user.id, title="New Chat")
    db.session.add(chat)
    db.session.commit()
    return redirect(url_for('chat.view', chat_id=chat.id))


@chat_bp.route('/<chat_id>')
@login_required
def view(chat_id):
    chat = Chat.query.filter_by(id=chat_id, user_id=current_user.id).first_or_404()
    chats = Chat.query.filter_by(user_id=current_user.id, status=ChatStatus.ACTIVE).order_by(Chat.updated_at.desc()).all()
    messages = Message.query.filter_by(chat_id=chat.id).order_by(Message.created_at.asc()).all()
    return render_template('chat/view.html', chat=chat, chats=chats, messages=messages)


def get_chat_files(chat_id):
    messages_with_files = Message.query.filter(Message.chat_id == chat_id, Message.file_id.isnot(None)).all()
    file_ids = [m.file_id for m in messages_with_files]
    if not file_ids:
        return []
    from app.models.file import File
    return File.query.filter(File.id.in_(file_ids)).all()


def build_system_instruction(chat_id):
    system_prompt = (
        "You are a helpful, high-quality AI assistant similar to Claude. "
        "Provide clearly structured, highly detailed, and extremely useful answers. "
        "Use Markdown formatting (such as bolding, lists, tables, and headers) where appropriate to make your response structured and clean.\n\n"
    )
    
    files = get_chat_files(chat_id)
    doc_contexts = []
    from app.models.file import FileType
    for f in files:
        if f.file_type in (FileType.PDF, FileType.DOCX, FileType.TXT, FileType.CSV) and f.extracted_text:
            doc_contexts.append(f"--- DOCUMENT: {f.original_filename} ---\n{f.extracted_text}\n--------------------")
            
    if doc_contexts:
        system_prompt += (
            "The user has uploaded the following documents in this chat. "
            "Use their contents to answer any questions or analyze the text as requested:\n\n"
            + "\n\n".join(doc_contexts)
        )
        
    return system_prompt


def should_generate_image(prompt: str) -> bool:
    prompt_lower = prompt.lower().strip()
    keywords = [
        "generate image", "create image", "generate an image", "create an image",
        "generate a picture", "create a picture", "draw a picture of", "draw an image of",
        "make an image of", "make a picture of", "generate a drawing", "create a drawing",
        "generate a painting", "create a painting", "/image", "/draw"
    ]
    return any(kw in prompt_lower for kw in keywords)


def should_edit_image(prompt: str, has_images: bool) -> bool:
    if not has_images:
        return False
    prompt_lower = prompt.lower().strip()
    keywords = [
        "edit this image", "modify this image", "edit the image", "modify the image",
        "edit the picture", "modify the picture", "change this image", "change the image",
        "make this image", "make a version of this image", "transform this image",
        "edit uploaded image", "change this uploaded image", "edit it", "modify it", "change it"
    ]
    return any(kw in prompt_lower for kw in keywords)


@chat_bp.route('/<chat_id>/send', methods=['POST'])
@login_required
def send_message(chat_id):
    chat = Chat.query.filter_by(id=chat_id, user_id=current_user.id).first_or_404()
    data = request.get_json()
    content = data.get('message', '').strip()

    if not content:
        return jsonify({'error': 'Message cannot be empty'}), 400

    chat_files = get_chat_files(chat.id)
    image_files = [f for f in chat_files if f.file_type == FileType.IMAGE]

    # 1. Handle image creation / generation
    if should_generate_image(content):
        try:
            from app.utils.gemini_client import generate_image
            image_bytes = generate_image(content)
            
            unique_filename = f"{uuid.uuid4()}_generated.jpg"
            uploads_dir = os.path.join(current_app.root_path, 'static', 'uploads')
            os.makedirs(uploads_dir, exist_ok=True)
            filepath = os.path.join(uploads_dir, unique_filename)
            with open(filepath, 'wb') as f:
                f.write(image_bytes)
                
            file_record = File(
                user_id=current_user.id,
                original_filename="Generated Image.jpg",
                storage_filename=unique_filename,
                file_type=FileType.IMAGE,
                file_size=len(image_bytes),
                status=FileStatus.PROCESSED
            )
            db.session.add(file_record)
            db.session.commit()
            
            image_url = url_for('static', filename=f'uploads/{unique_filename}', _external=True)
            ai_reply = f"Here is the image you requested based on '{content}':<br><img src=\"{image_url}\" alt=\"Generated Image\" />"
            
            user_msg = Message(chat_id=chat.id, role=MessageRole.USER, content=content)
            ai_msg = Message(chat_id=chat.id, role=MessageRole.ASSISTANT, content=ai_reply, model_used="imagen-3.0-generate-002", file_id=file_record.id)
            db.session.add(user_msg)
            db.session.add(ai_msg)
            
            if chat.title == "New Chat":
                chat.title = content[:50]
            chat.updated_at = datetime.datetime.utcnow()
            db.session.commit()
            
            return jsonify({
                'user_message': {'id': user_msg.id, 'content': user_msg.content, 'role': 'user'},
                'ai_message': {'id': ai_msg.id, 'content': ai_msg.content, 'role': 'assistant'}
            })
        except Exception as e:
            current_app.logger.error(f"Image generation error: {e}")
            return jsonify({'error': f"Failed to generate image: {str(e)}"}), 500

    # 2. Handle image editing / modification
    if len(image_files) > 0 and should_edit_image(content, True):
        try:
            last_img = image_files[-1]
            img_path = os.path.join(current_app.root_path, 'static', 'uploads', last_img.storage_filename)
            
            desc_prompt = "Describe this image in detail. Focus on style, objects, lighting, and composition so that it can be recreated."
            from app.utils.gemini_client import generate_response, generate_image
            img_description = generate_response([{"role": "user", "content": desc_prompt}], image_paths=[img_path])
            
            combined_prompt = f"Create a new image based on this description: {img_description}. Modify it according to this request: {content}"
            image_bytes = generate_image(combined_prompt)
            
            unique_filename = f"{uuid.uuid4()}_edited.jpg"
            uploads_dir = os.path.join(current_app.root_path, 'static', 'uploads')
            os.makedirs(uploads_dir, exist_ok=True)
            filepath = os.path.join(uploads_dir, unique_filename)
            with open(filepath, 'wb') as f:
                f.write(image_bytes)
                
            file_record = File(
                user_id=current_user.id,
                original_filename="Edited Image.jpg",
                storage_filename=unique_filename,
                file_type=FileType.IMAGE,
                file_size=len(image_bytes),
                status=FileStatus.PROCESSED
            )
            db.session.add(file_record)
            db.session.commit()
            
            image_url = url_for('static', filename=f'uploads/{unique_filename}', _external=True)
            ai_reply = f"Here is the edited image based on your request:<br><img src=\"{image_url}\" alt=\"Edited Image\" />"
            
            user_msg = Message(chat_id=chat.id, role=MessageRole.USER, content=content)
            ai_msg = Message(chat_id=chat.id, role=MessageRole.ASSISTANT, content=ai_reply, model_used="imagen-3.0-generate-002", file_id=file_record.id)
            db.session.add(user_msg)
            db.session.add(ai_msg)
            
            if chat.title == "New Chat":
                chat.title = content[:50]
            chat.updated_at = datetime.datetime.utcnow()
            db.session.commit()
            
            return jsonify({
                'user_message': {'id': user_msg.id, 'content': user_msg.content, 'role': 'user'},
                'ai_message': {'id': ai_msg.id, 'content': ai_msg.content, 'role': 'assistant'}
            })
        except Exception as e:
            current_app.logger.error(f"Image edit error: {e}")
            return jsonify({'error': f"Failed to edit image: {str(e)}"}), 500

    # 3. Standard text message flow
    user_msg = Message(
        chat_id=chat.id,
        role=MessageRole.USER,
        content=content
    )
    db.session.add(user_msg)

    try:
        history = Message.query.filter_by(chat_id=chat.id).order_by(Message.created_at.asc()).all()
        messages_for_ai = []
        for msg in history:
            if msg.role not in (MessageRole.SYSTEM,):
                messages_for_ai.append({
                    "role": msg.role.value.lower(),
                    "content": msg.content
                })
        
        # Add current user message if it's not already in history
        if not messages_for_ai or messages_for_ai[-1]["content"] != content:
            messages_for_ai.append({"role": "user", "content": content})
        
        system_instruction = build_system_instruction(chat.id)
        image_paths = []
        for img in image_files:
            path = os.path.join(current_app.root_path, 'static', 'uploads', img.storage_filename)
            if os.path.exists(path):
                image_paths.append(path)

        ai_reply = gemini_response(messages_for_ai, system_instruction=system_instruction, image_paths=image_paths)
        model_used = "gemini-2.5-flash"
    except Exception as e:
        current_app.logger.error(f"Gemini API Error: {e}")
        ai_reply = f"Error communicating with Gemini: {str(e)}"
        model_used = "error"

    ai_msg = Message(
        chat_id=chat.id,
        role=MessageRole.ASSISTANT,
        content=ai_reply,
        model_used=model_used
    )
    db.session.add(ai_msg)

    if chat.title == "New Chat":
        chat.title = content[:50]

    chat.updated_at = datetime.datetime.utcnow()
    db.session.commit()

    return jsonify({
        'user_message': {'id': user_msg.id, 'content': user_msg.content, 'role': 'user'},
        'ai_message': {'id': ai_msg.id, 'content': ai_msg.content, 'role': 'assistant'}
    })


@chat_bp.route('/<chat_id>/send_stream', methods=['POST'])
@login_required
def send_message_stream(chat_id):
    chat = Chat.query.filter_by(id=chat_id, user_id=current_user.id).first_or_404()
    data = request.get_json()
    content = data.get('message', '').strip()

    if not content:
        return jsonify({'error': 'Message cannot be empty'}), 400

    chat_files = get_chat_files(chat.id)
    image_files = [f for f in chat_files if f.file_type == FileType.IMAGE]

    user_msg = Message(
        chat_id=chat.id,
        role=MessageRole.USER,
        content=content
    )
    db.session.add(user_msg)
    
    if chat.title == "New Chat":
        chat.title = content[:50]
        
    chat.updated_at = datetime.datetime.utcnow()
    db.session.commit()

    # If image generation or edit request, handle one-shot inside stream
    if should_generate_image(content) or (len(image_files) > 0 and should_edit_image(content, True)):
        @stream_with_context
        def generate_image_stream():
            try:
                yield f"data: {json.dumps({'chunk': '🖌️ *Generating/editing image... please wait...*<br>'})}\n\n"
                
                from app.utils.gemini_client import generate_image
                import uuid
                
                if should_generate_image(content):
                    image_bytes = generate_image(content)
                    orig_filename = "Generated Image.jpg"
                else:
                    last_img = image_files[-1]
                    img_path = os.path.join(current_app.root_path, 'static', 'uploads', last_img.storage_filename)
                    from app.utils.gemini_client import generate_image_edit
                    image_bytes = generate_image_edit(content, img_path)
                    orig_filename = "Edited Image.jpg"

                unique_filename = f"{uuid.uuid4()}_streamed.jpg"
                uploads_dir = os.path.join(current_app.root_path, 'static', 'uploads')
                os.makedirs(uploads_dir, exist_ok=True)
                filepath = os.path.join(uploads_dir, unique_filename)
                with open(filepath, 'wb') as f:
                    f.write(image_bytes)
                    
                file_record = File(
                    user_id=current_user.id,
                    original_filename=orig_filename,
                    storage_filename=unique_filename,
                    file_type=FileType.IMAGE,
                    file_size=len(image_bytes),
                    status=FileStatus.PROCESSED
                )
                db.session.add(file_record)
                db.session.commit()
                
                image_url = url_for('static', filename=f'uploads/{unique_filename}', _external=True)
                ai_reply = f"<br><img src=\"{image_url}\" alt=\"Generated Image\" />"
                
                ai_msg = Message(
                    chat_id=chat.id,
                    role=MessageRole.ASSISTANT,
                    content=ai_reply,
                    model_used="gemini-2.5-flash-image",
                    file_id=file_record.id
                )
                db.session.add(ai_msg)
                db.session.commit()
                
                yield f"data: {json.dumps({'chunk': ai_reply})}\n\n"
                yield "data: [DONE]\n\n"
            except Exception as e:
                current_app.logger.error(f"Image stream error: {e}")
                yield f"data: {json.dumps({'error': f'Failed to generate/edit image: {str(e)}'})}\n\n"
                
        return Response(generate_image_stream(), mimetype='text/event-stream')

    # Standard stream
    @stream_with_context
    def generate():
        try:
            history = Message.query.filter_by(chat_id=chat.id).order_by(Message.created_at.asc()).all()
            messages_for_ai = []
            for msg in history:
                if msg.role not in (MessageRole.SYSTEM,):
                    messages_for_ai.append({
                        "role": msg.role.value.lower(),
                        "content": msg.content
                    })
            
            from app.utils.gemini_client import generate_response_stream
            
            system_instruction = build_system_instruction(chat.id)
            image_paths = []
            for img in image_files:
                path = os.path.join(current_app.root_path, 'static', 'uploads', img.storage_filename)
                if os.path.exists(path):
                    image_paths.append(path)
                    
            full_reply = ""
            for chunk in generate_response_stream(messages_for_ai, system_instruction=system_instruction, image_paths=image_paths):
                full_reply += chunk
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"
            
            ai_msg = Message(
                chat_id=chat.id,
                role=MessageRole.ASSISTANT,
                content=full_reply,
                model_used="gemini-2.5-flash"
            )
            db.session.add(ai_msg)
            db.session.commit()
            
            yield "data: [DONE]\n\n"
        except Exception as e:
            current_app.logger.error(f"Gemini API Stream Error: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            
    return Response(generate(), mimetype='text/event-stream')



@chat_bp.route('/<chat_id>/upload', methods=['POST'])
@login_required
def upload_file(chat_id):
    chat = Chat.query.filter_by(id=chat_id, user_id=current_user.id).first_or_404()
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
        
    filename = secure_filename(file.filename)
    unique_filename = f"{uuid.uuid4()}_{filename}"
    
    # S3 config
    s3_bucket = current_app.config.get('S3_BUCKET_NAME')
    aws_key = current_app.config.get('AWS_ACCESS_KEY_ID')
    
    s3_url = None
    
    file_record = File(
        user_id=current_user.id,
        original_filename=filename,
        storage_filename=unique_filename,
        file_type=get_file_type(filename),
        file_size=0,
        status=FileStatus.UPLOADED
    )
    
    try:
        # Save locally first
        uploads_dir = os.path.join(current_app.root_path, 'static', 'uploads')
        os.makedirs(uploads_dir, exist_ok=True)
        temp_path = os.path.join(uploads_dir, unique_filename)
        file.save(temp_path)
        
        file_size = os.path.getsize(temp_path)
        file_record.file_size = file_size
        
        # Extract text content if it's a document (PDF, DOCX, TXT, CSV)
        extracted_text = extract_text_from_file(temp_path, file_record.file_type)
        if extracted_text:
            file_record.extracted_text = extracted_text
        
        if aws_key and aws_key != 'your-aws-access-key' and s3_bucket:
            # Upload to AWS S3
            with open(temp_path, 'rb') as f_obj:
                s3_url = upload_file_to_s3(f_obj, s3_bucket, unique_filename)
            file_record.s3_key = unique_filename
            file_record.status = FileStatus.PROCESSED
            os.remove(temp_path) # Remove local temp buffer
        else:
            # Save local server path fallback
            file_record.status = FileStatus.PROCESSED
            s3_url = url_for('static', filename=f'uploads/{unique_filename}', _external=True)
            
        db.session.add(file_record)
        db.session.commit()
        
        # Add system message link to chat
        file_msg = Message(
            chat_id=chat.id,
            role=MessageRole.SYSTEM,
            content=f"Uploaded file: {filename} ({file_record.get_readable_size()})",
            file_id=file_record.id
        )
        db.session.add(file_msg)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'file': {
                'id': file_record.id,
                'filename': filename,
                'url': s3_url,
                'type': file_record.file_type.value,
                'size': file_record.get_readable_size()
            },
            'message': {
                'id': file_msg.id,
                'content': file_msg.content,
                'role': 'system'
            }
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"File upload error: {e}")
        return jsonify({'error': f"Failed to upload file: {str(e)}"}), 500


@chat_bp.route('/<chat_id>/delete', methods=['POST'])
@login_required
def delete_chat(chat_id):
    chat = Chat.query.filter_by(id=chat_id, user_id=current_user.id).first_or_404()
    chat.status = ChatStatus.DELETED
    db.session.commit()
    flash('Chat deleted', 'success')
    return redirect(url_for('chat.index'))
