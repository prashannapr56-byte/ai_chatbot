#!/bin/bash
set -e

cd ~/cloud-ai-chatbot
source venv/bin/activate

# Initialize database
FLASK_ENV=production python3 -c "
from app import create_app, db
from app.config import config
app = create_app(config['production'])
with app.app_context():
    db.create_all()
    print('DB initialized OK')
"

# Install and enable systemd service
sudo cp ~/cloudchatbot.service /etc/systemd/system/cloudchatbot.service
sudo systemctl daemon-reload
sudo systemctl enable cloudchatbot
sudo systemctl restart cloudchatbot
sleep 2
sudo systemctl status cloudchatbot --no-pager
