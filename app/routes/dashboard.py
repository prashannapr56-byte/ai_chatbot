from flask import Blueprint, render_template
from flask_login import login_required, current_user
from app.models.chat import Chat, ChatStatus, Message
from app.models.file import File
from app.models.api_usage import APIUsage

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/')
@dashboard_bp.route('/index')
@login_required
def index():
    # Gather stats for the dashboard
    total_chats = Chat.query.filter_by(user_id=current_user.id, status=ChatStatus.ACTIVE).count()
    total_messages = Message.query.join(Chat).filter(Chat.user_id == current_user.id).count()
    total_files = File.query.filter_by(user_id=current_user.id).count()
    recent_chats = Chat.query.filter_by(
        user_id=current_user.id, status=ChatStatus.ACTIVE
    ).order_by(Chat.updated_at.desc()).limit(5).all()

    return render_template(
        'dashboard/index.html',
        total_chats=total_chats,
        total_messages=total_messages,
        total_files=total_files,
        recent_chats=recent_chats
    )
