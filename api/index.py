from app import create_app
from app.config import config
import os

# Use production config for Vercel deployment
env = os.environ.get('FLASK_ENV', 'production')
app = create_app(config[env])

# Vercel expects the WSGI app to be named 'app'
