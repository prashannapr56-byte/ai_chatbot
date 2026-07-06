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


@chat_bp.route('/<chat_id>/send', methods=['POST'])
@login_required
def send_message(chat_id):
    chat = Chat.query.filter_by(id=chat_id, user_id=current_user.id).first_or_404()
    data = request.get_json()
    content = data.get('message', '').strip()

    if not content:
        return jsonify({'error': 'Message cannot be empty'}), 400

    # Save user message
    user_msg = Message(
        chat_id=chat.id,
        role=MessageRole.USER,
        content=content
    )
    db.session.add(user_msg)

    # --- Gemini AI Integration ---
    try:
        # Build conversation history
        history = Message.query.filter_by(chat_id=chat.id).order_by(Message.created_at.asc()).all()
        messages_for_ai = []
        for msg in history:
            if msg.role not in (MessageRole.SYSTEM,):
                messages_for_ai.append({
                    "role": msg.role.value.lower(),
                    "content": msg.content
                })
        # Add current user message
        messages_for_ai.append({"role": "user", "content": content})
        
        ai_reply = gemini_response(messages_for_ai)
        model_used = "gemini-1.5-flash"
    except Exception as e:
        current_app.logger.error(f"Gemini API Error: {e}")
        ai_reply = f"Error communicating with Gemini: {str(e)}"
        model_used = "error"

    # Save assistant message
    ai_msg = Message(
        chat_id=chat.id,
        role=MessageRole.ASSISTANT,
        content=ai_reply,
        model_used=model_used
    )
    db.session.add(ai_msg)

    # Update chat title if it's new
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
            
            full_reply = ""
            for chunk in generate_response_stream(messages_for_ai):
                full_reply += chunk
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"
            
            ai_msg = Message(
                chat_id=chat.id,
                role=MessageRole.ASSISTANT,
                content=full_reply,
                model_used="gemini-flash-lite-latest"
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
