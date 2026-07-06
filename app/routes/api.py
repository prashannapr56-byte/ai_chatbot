from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from app.models.chat import Chat, Message, ChatStatus
from app.models.user import User

api_bp = Blueprint('api', __name__)


@api_bp.route('/health')
def health():
    return jsonify({'status': 'ok', 'message': 'AI Chatbot API is running'})


@api_bp.route('/chats', methods=['GET'])
@login_required
def get_chats():
    chats = Chat.query.filter_by(
        user_id=current_user.id, status=ChatStatus.ACTIVE
    ).order_by(Chat.updated_at.desc()).all()
    return jsonify([{
        'id': c.id,
        'title': c.title,
        'created_at': c.created_at.isoformat(),
        'updated_at': c.updated_at.isoformat(),
        'message_count': c.get_message_count()
    } for c in chats])


@api_bp.route('/chats/<chat_id>/messages', methods=['GET'])
@login_required
def get_messages(chat_id):
    chat = Chat.query.filter_by(id=chat_id, user_id=current_user.id).first_or_404()
    messages = Message.query.filter_by(chat_id=chat.id).order_by(Message.created_at.asc()).all()
    return jsonify([{
        'id': m.id,
        'role': m.role.value,
        'content': m.content,
        'created_at': m.created_at.isoformat(),
        'model_used': m.model_used
    } for m in messages])


@api_bp.route('/profile', methods=['GET'])
@login_required
def get_profile():
    return jsonify({
        'id': current_user.id,
        'email': current_user.email,
        'first_name': current_user.first_name,
        'last_name': current_user.last_name,
        'role': current_user.role.value,
        'email_verified': current_user.email_verified
    })
