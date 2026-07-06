from app import db
from app.models.base import BaseModel
import enum

class ChatStatus(enum.Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"

class Chat(BaseModel):
    __tablename__ = 'chats'
    
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(255), nullable=False, default="New Chat")
    status = db.Column(db.Enum(ChatStatus), default=ChatStatus.ACTIVE)
    
    # Relationships
    messages = db.relationship('Message', backref='chat', lazy=True, cascade='all, delete-orphan')
    
    def get_message_count(self):
        return len(self.messages)
    
    def get_last_message(self):
        return self.messages[-1] if self.messages else None
    
    def __repr__(self):
        return f'<Chat {self.id}>'

class MessageRole(enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"

class Message(BaseModel):
    __tablename__ = 'messages'
    
    chat_id = db.Column(db.String(36), db.ForeignKey('chats.id'), nullable=False)
    role = db.Column(db.Enum(MessageRole), nullable=False)
    content = db.Column(db.Text, nullable=False)
    tokens_used = db.Column(db.Integer, default=0)
    model_used = db.Column(db.String(50), nullable=True)
    
    # For file context
    file_id = db.Column(db.String(36), db.ForeignKey('files.id'), nullable=True)
    
    def __repr__(self):
        return f'<Message {self.id}>'
