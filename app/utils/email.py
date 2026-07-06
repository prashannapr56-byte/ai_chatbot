from flask_mail import Message
from app import mail
from flask import current_app, render_template
import threading

def send_async_email(app, msg):
    with app.app_context():
        mail.send(msg)

def send_email(subject, recipient, template, **kwargs):
    app = current_app._get_current_object()
    msg = Message(
        subject=subject,
        sender=app.config['MAIL_USERNAME'],
        recipients=[recipient],
        html=render_template(f'emails/{template}.html', **kwargs)
    )
    
    # Send email asynchronously
    thread = threading.Thread(target=send_async_email, args=(app, msg))
    thread.start()
    return thread
