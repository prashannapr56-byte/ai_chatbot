from flask import Blueprint, request, jsonify, render_template, redirect, url_for, flash, current_app, session
from flask_login import login_user, logout_user, login_required, current_user
from app import db, limiter
from app.models import User, Session, Log
from app.models.user import UserStatus
from app.utils.security import validate_email, validate_password
from app.utils.email import send_email
from app.utils.tokens import generate_email_verification_token, generate_password_reset_token, verify_token
import datetime
import uuid

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/register', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def register():
    if request.method == 'GET':
        return render_template('auth/register.html')
    
    # Handle registration form submission
    data = request.form
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    first_name = data.get('first_name', '').strip()
    last_name = data.get('last_name', '').strip()
    
    # Validate input
    if not all([email, password, first_name, last_name]):
        flash('All fields are required', 'error')
        return render_template('auth/register.html')
    
    if not validate_email(email):
        flash('Please enter a valid email address', 'error')
        return render_template('auth/register.html')
    
    is_valid, message = validate_password(password)
    if not is_valid:
        flash(message, 'error')
        return render_template('auth/register.html')
    
    # Check if user already exists
    if User.query.filter_by(email=email).first():
        flash('Email already registered', 'error')
        return render_template('auth/register.html')
    
    # Create new user (automatically verified & active for easy development)
    try:
        user = User(
            email=email,
            first_name=first_name,
            last_name=last_name,
            email_verified=True,
            status=UserStatus.ACTIVE
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        # Log registration
        log = Log(
            level='info',
            module='auth',
            message=f'User registered (auto-activated): {user.email}',
            user_id=user.id
        )
        db.session.add(log)
        db.session.commit()
        
        # Auto-login and make session permanent/persistent
        login_user(user, remember=True)
        session.permanent = True
        
        flash('Registration successful! Welcome to your AI Chatbot.', 'success')
        return redirect(url_for('dashboard.index'))
    
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Registration error: {str(e)}')
        flash('An error occurred during registration. Please try again.', 'error')
        return render_template('auth/register.html')

@auth_bp.route('/verify-email/')
def verify_email(token):
    payload = verify_token(token, 'email_verification')
    if not payload:
        flash('Invalid or expired verification link', 'error')
        return redirect(url_for('auth.login'))
    
    user = User.query.get(payload['user_id'])
    if not user or user.email != payload['email']:
        flash('Invalid verification link', 'error')
        return redirect(url_for('auth.login'))
    
    if user.email_verified:
        flash('Email already verified', 'info')
        return redirect(url_for('auth.login'))
    
    user.email_verified = True
    user.status = 'active'
    user.email_verification_token = None
    db.session.commit()
    
    flash('Email verified successfully! You can now login.', 'success')
    return redirect(url_for('auth.login'))

@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    
    if request.method == 'GET':
        return render_template('auth/login.html')
    
    # Handle login form submission
    data = request.form
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    
    if not email or not password:
        flash('Please enter both email and password', 'error')
        return render_template('auth/login.html')
    
    user = User.query.filter_by(email=email).first()
    
    if not user or not user.check_password(password):
        flash('Invalid email or password', 'error')
        return render_template('auth/login.html')
    
    if not user.email_verified:
        flash('Please verify your email before logging in', 'error')
        return render_template('auth/login.html')
    
    if not user.is_active():
        flash('Your account is not active. Please contact support.', 'error')
        return render_template('auth/login.html')
    
    # Update last login and create session
    user.last_login = datetime.datetime.utcnow()
    
    session_token = str(uuid.uuid4())
    db_session = Session(
        user_id=user.id,
        session_token=session_token,
        expires_at=datetime.datetime.utcnow() + datetime.timedelta(days=365),
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string
    )
    
    db.session.add(db_session)
    db.session.commit()
    
    login_user(user, remember=True)
    session.permanent = True
    
    # Log successful login
    log = Log(
        level='info',
        module='auth',
        message=f'User logged in: {user.email}',
        user_id=user.id,
        ip_address=request.remote_addr
    )
    db.session.add(log)
    db.session.commit()
    
    flash('Login successful!', 'success')
    next_page = request.args.get('next')
    return redirect(next_page or url_for('dashboard.index'))

@auth_bp.route('/logout')
@login_required
def logout():
    # Log logout action
    log = Log(
        level='info',
        module='auth',
        message=f'User logged out: {current_user.email}',
        user_id=current_user.id,
        ip_address=request.remote_addr
    )
    db.session.add(log)
    db.session.commit()
    
    logout_user()
    flash('You have been logged out successfully', 'success')
    return redirect(url_for('auth.login'))

@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
@limiter.limit("3 per minute")
def forgot_password():
    if request.method == 'GET':
        return render_template('auth/forgot_password.html')
    
    email = request.form.get('email', '').strip().lower()
    user = User.query.filter_by(email=email).first()
    # Always show success to avoid email enumeration
    flash('If that email is registered, a reset link has been sent.', 'info')
    if user:
        token = generate_password_reset_token(user.id)
        reset_url = url_for('auth.reset_password', token=token, _external=True)
        send_email(
            subject="Password Reset – AI Chatbot",
            recipient=user.email,
            template='reset_password',
            user=user,
            reset_url=reset_url
        )
    return redirect(url_for('auth.login'))

@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    payload = verify_token(token, 'password_reset')
    if not payload:
        flash('Invalid or expired reset link', 'error')
        return redirect(url_for('auth.login'))
    
    if request.method == 'GET':
        return render_template('auth/reset_password.html', token=token)
    
    password = request.form.get('password', '')
    is_valid, message = validate_password(password)
    if not is_valid:
        flash(message, 'error')
        return render_template('auth/reset_password.html', token=token)
    
    user = User.query.get(payload['user_id'])
    user.set_password(password)
    db.session.commit()
    flash('Password updated successfully! Please log in.', 'success')
    return redirect(url_for('auth.login'))

