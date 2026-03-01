from sqlalchemy import create_engine, Column, String, Text, DateTime, Integer, ForeignKey, inspect, text
from sqlalchemy.orm import declarative_base
from datetime import datetime
import os

IS_VERCEL = os.getenv("VERCEL", False)
DB_PATH = "/tmp/LangChatHistory.db" if IS_VERCEL else "LangChatHistory.db"
engine = create_engine(f'sqlite:///{DB_PATH}')

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.now)

class ChatHistory(Base):
    __tablename__ = 'chat_history'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    session_id = Column(String(100), index=True, nullable=False)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.now)

Base.metadata.create_all(engine)

inspector = inspect(engine)
if 'users' in inspector.get_table_names():
    columns = [c['name'] for c in inspector.get_columns('users')]
    if 'password_hash' not in columns:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN password_hash VARCHAR(255)"))
            conn.commit()
