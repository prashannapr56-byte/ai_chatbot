from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from functools import wraps
from app.models.user import User, UserStatus, UserRole
from app.models.chat import Chat
from app.models.log import Log
from app import db

admin_bp = Blueprint('admin', __name__)


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin():
            flash('Admin access required', 'error')
            return redirect(url_for('dashboard.index'))
        return f(*args, **kwargs)
    return decorated


@admin_bp.route('/')
@login_required
@admin_required
def index():
    total_users = User.query.count()
    active_users = User.query.filter_by(status=UserStatus.ACTIVE).count()
    total_chats = Chat.query.count()
    recent_logs = Log.query.order_by(Log.created_at.desc()).limit(20).all()
    return render_template(
        'admin/index.html',
        total_users=total_users,
        active_users=active_users,
        total_chats=total_chats,
        recent_logs=recent_logs
    )


@admin_bp.route('/users')
@login_required
@admin_required
def users():
    all_users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin/users.html', users=all_users)


@admin_bp.route('/users/<user_id>/toggle', methods=['POST'])
@login_required
@admin_required
def toggle_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.status == UserStatus.ACTIVE:
        user.status = UserStatus.INACTIVE
        flash(f'User {user.email} deactivated', 'success')
    else:
        user.status = UserStatus.ACTIVE
        flash(f'User {user.email} activated', 'success')
    db.session.commit()
    return redirect(url_for('admin.users'))
