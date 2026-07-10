import logging
import os
from logging.handlers import RotatingFileHandler

def setup_logging(app):
    # Stream handler (always works, including serverless)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s'
    ))
    stream_handler.setLevel(logging.INFO)
    app.logger.addHandler(stream_handler)

    # File handler (skip on read-only filesystems like Vercel)
    try:
        if not os.path.exists('logs'):
            os.makedirs('logs')
        file_handler = RotatingFileHandler(
            'logs/ai_chatbot.log', 
            maxBytes=10240, 
            backupCount=10
        )
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)
    except OSError:
        app.logger.warning('File logging disabled (read-only filesystem)')

    app.logger.setLevel(logging.INFO)
    app.logger.info('AI Chatbot startup')
