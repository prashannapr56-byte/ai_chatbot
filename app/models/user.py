from app import db
from app.models.base import BaseModel
from app.utils.security import hash_password, check_password
# pyrefly: ignore [missing-import]
from flask_login import UserMixin
import enum

class UserRole(enum.Enum):
    ADMIN = "admin"
    USER = "user"

class UserStatus(enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    PENDING = "pending"

class User(BaseModel, UserMixin):
    __tablename__ = 'users'
    
    # Personal Information
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(128), nullable=False)
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    
    # Account Information
    role = db.Column(db.Enum(UserRole), default=UserRole.USER)
    status = db.Column(db.Enum(UserStatus), default=UserStatus.PENDING)
    email_verified = db.Column(db.Boolean, default=False)
    last_login = db.Column(db.DateTime, nullable=True)
    
    # Relationships
    chats = db.relationship('Chat', backref='user', lazy=True, cascade='all, delete-orphan')
    files = db.relationship('File', backref='user', lazy=True, cascade='all, delete-orphan')
    api_usage = db.relationship('APIUsage', backref='user', lazy=True, cascade='all, delete-orphan')
    
    # Verification tokens
    email_verification_token = db.Column(db.String(100), nullable=True)
    password_reset_token = db.Column(db.String(100), nullable=True)
    password_reset_expires = db.Column(db.DateTime, nullable=True)
    
    def set_password(self, password):
        self.password_hash = hash_password(password)
    
    def check_password(self, password):
        return check_password(self.password_hash, password)
    
    def get_id(self):
        return self.id
    
    def is_active(self):
        return self.status == UserStatus.ACTIVE
    
    def is_admin(self):
        return self.role == UserRole.ADMIN
    
    def __repr__(self):
        return f'<User {self.email}>'
