from app import db
from app.models.base import BaseModel
import enum

class FileType(enum.Enum):
    PDF = "pdf"
    DOCX = "docx"
    TXT = "txt"
    CSV = "csv"
    IMAGE = "image"
    OTHER = "other"

class FileStatus(enum.Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    PROCESSED = "processed"
    ERROR = "error"

class File(BaseModel):
    __tablename__ = 'files'
    
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    storage_filename = db.Column(db.String(255), nullable=False)
    file_type = db.Column(db.Enum(FileType), nullable=False)
    file_size = db.Column(db.Integer, nullable=False)  # Size in bytes
    status = db.Column(db.Enum(FileStatus), default=FileStatus.UPLOADED)
    s3_key = db.Column(db.String(500), nullable=True)
    
    # Extracted content (for text files)
    extracted_text = db.Column(db.Text, nullable=True)
    
    # Relationships
    messages = db.relationship('Message', backref='file', lazy=True)
    
    def get_readable_size(self):
        """Convert file size to human readable format"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if self.file_size < 1024.0:
                return f"{self.file_size:.2f} {unit}"
            self.file_size /= 1024.0
        return f"{self.file_size:.2f} TB"
    
    def __repr__(self):
        return f'<File {self.original_filename}>'
