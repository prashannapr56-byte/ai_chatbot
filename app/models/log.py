from app import db
from app.models.base import BaseModel
import enum

class LogLevel(enum.Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

class Log(BaseModel):
    __tablename__ = 'logs'
    
    level = db.Column(db.Enum(LogLevel), nullable=False)
    module = db.Column(db.String(100), nullable=False)
    message = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    traceback = db.Column(db.Text, nullable=True)
    
    def __repr__(self):
        return f'<Log {self.level.name}>'
