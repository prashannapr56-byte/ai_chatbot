from app import db
from app.models.base import BaseModel
import enum

class APIService(enum.Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    COHERE = "cohere"

class APIUsage(BaseModel):
    __tablename__ = 'api_usage'
    
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    service = db.Column(db.Enum(APIService), nullable=False)
    endpoint = db.Column(db.String(100), nullable=False)
    tokens_used = db.Column(db.Integer, default=0)
    cost = db.Column(db.Numeric(10, 6), default=0.0)  # Cost in USD
    success = db.Column(db.Boolean, default=True)
    error_message = db.Column(db.Text, nullable=True)
    
    def __repr__(self):
        return f'<APIUsage {self.service.name}>'
