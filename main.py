from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from llms.chatgpt import vectorize, ask_chatgpt, stream_chatgpt
from vectordb.pineconedb import index as pc_index
from utils.models import UserInput, RegisterRequest, LoginRequest, AuthResponse
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import func
from database.db import engine, ChatHistory, User
from dotenv import load_dotenv
import uuid
import json
import os
import bcrypt
import jwt
from datetime import datetime, timedelta

load_dotenv()

JWT_SECRET = os.getenv("JWT_SECRET", "dev-only-change-me-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_DAYS = 30

app = FastAPI(title="LangChat API", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
security = HTTPBearer()
templates = Jinja2Templates(directory='templates')


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())

def create_token(user_id: int, username: str) -> str:
    payload = {
        "user_id": user_id,
        "username": username,
        "exp": datetime.utcnow() + timedelta(days=JWT_EXPIRY_DAYS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired. Please sign in again.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token. Please sign in again.")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    payload = decode_token(credentials.credentials)
    user = db.query(User).filter_by(id=payload["user_id"]).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


@app.post("/register", response_model=AuthResponse)
async def register(req: RegisterRequest, db: Session = Depends(get_db)):
    username = req.username.strip()

    existing = db.query(User).filter_by(username=username).first()
    if existing:
        raise HTTPException(status_code=409, detail="Username already taken")

    new_user = User(username=username, password_hash=hash_password(req.password))
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    token = create_token(new_user.id, username)
    return AuthResponse(
        success=True,
        token=token,
        username=username,
        message=f"Welcome, {username}!",
    )

@app.post("/login", response_model=AuthResponse)
async def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(username=req.username.strip()).first()

    if not user or not user.password_hash:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    if not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = create_token(user.id, user.username)
    return AuthResponse(
        success=True,
        token=token,
        username=user.username,
        message=f"Welcome back, {user.username}!",
    )

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/chat")
async def ask(
    user_input: UserInput,
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    payload = decode_token(credentials.credentials)
    user_id = payload["user_id"]

    db = SessionLocal()
    try:
        user = db.query(User).filter_by(id=user_id).first()
        if not user:
            raise HTTPException(status_code=401, detail="User not found")

        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        messages_today = db.query(func.count(ChatHistory.id)).filter(
            ChatHistory.user_id == user.id,
            ChatHistory.role == "user",
            ChatHistory.timestamp >= today_start,
        ).scalar()

        if messages_today >= 4:
            raise HTTPException(
                status_code=429,
                detail="Daily message limit (4) reached. Come back tomorrow!",
            )

        session_id = user_input.session_id or str(uuid.uuid4())
        user_text = user_input.user_input

        db.add(ChatHistory(user_id=user.id, session_id=session_id, role="user", content=user_text))
        db.commit()
    finally:
        db.close()

    embedded_user = vectorize(user_text)
    pc_resp = pc_index.query(
        namespace='all_webpages',
        vector=embedded_user,
        top_k=5,
        include_metadata=True,
    )

    retrieval = ""
    for idx, match in enumerate(pc_resp.matches):
        filename = match['metadata']['filename']
        with open(f"files/extracted_pages/{filename}", 'r') as f:
            retrieval += f"doc_{idx+1}: {filename}\n" + f.read() + "\n"

    prompt = f"""you are responsible for answering questions about LangChain documentation. 
    you are given retrieved context from documentation. only answer based on them. 
    don't just copy paste response from your context. explain the response to user friendly. 
    start your response stating response to question and explain in depth.
    if question is about integrating to the code or how to write particular code ,thing, try to give/explain with code examples. 
    so, your response should be two parts:
    Response to your question: ... be a bit speific, tell main ,brief response, but at the same time, be specific about terms, things used. write one paprapgraph, you can make it moderate long, not too short
    dont blindly take from first retrieved context text, think and answer to user question and there may be a lot of other irrelevant information in retrieved context, so think and answer. don't take all seriously
    and also sometimes right answer mayn't be in top of context or first retrieved context text, don't just take from first retrieved context text, think and answer. but never make up answer yourself, only answer based on retrieved context.
    Detailed Explanation: ....
    user question: {user_text}.\nretrieved context: {retrieval}"""

    def generate():
        full_response = ""
        try:
            for chunk in stream_chatgpt(prompt):
                full_response += chunk
                yield f"data: {json.dumps({'token': chunk})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            return

        save_db = SessionLocal()
        try:
            save_db.add(ChatHistory(user_id=user_id, session_id=session_id, role="bot", content=full_response))
            save_db.commit()
        except Exception:
            pass
        finally:
            save_db.close()

        yield f"data: {json.dumps({'done': True, 'session_id': session_id})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/remaining_messages")
async def remaining_messages(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    messages_today = db.query(func.count(ChatHistory.id)).filter(
        ChatHistory.user_id == user.id,
        ChatHistory.role == "user",
        ChatHistory.timestamp >= today_start,
    ).scalar()

    remaining = max(0, 4 - messages_today)
    return {"messages_sent": messages_today, "remaining": remaining, "daily_limit": 4}


@app.get("/get_history/{session_id}")
async def get_history(
    session_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    messages = (
        db.query(ChatHistory)
        .filter_by(user_id=user.id, session_id=session_id)
        .order_by(ChatHistory.timestamp.asc())
        .all()
    )

    if not messages:
        raise HTTPException(status_code=404, detail="Session not found")

    return [{"role": m.role, "content": m.content} for m in messages]


@app.get("/sessions")
async def get_sessions(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    sessions_query = (
        db.query(
            ChatHistory.session_id,
            func.max(ChatHistory.timestamp).label("last_active"),
        )
        .filter_by(user_id=user.id)
        .group_by(ChatHistory.session_id)
        .order_by(func.max(ChatHistory.timestamp).desc())
        .all()
    )

    result = []
    for session in sessions_query:
        first_msg = (
            db.query(ChatHistory)
            .filter_by(user_id=user.id, session_id=session.session_id, role="user")
            .order_by(ChatHistory.timestamp.asc())
            .first()
        )
        title = first_msg.content[:60] if first_msg else "New Chat"
        result.append({
            "session_id": session.session_id,
            "title": title,
            "last_active": session.last_active.isoformat() if session.last_active else None,
        })

    return result


@app.delete("/delete_chat/{session_id}")
async def delete_chat(
    session_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    deleted_count = (
        db.query(ChatHistory)
        .filter_by(user_id=user.id, session_id=session_id)
        .delete()
    )
    db.commit()

    if deleted_count == 0:
        raise HTTPException(status_code=404, detail="Session not found")

    return {"success": True, "deleted_messages": deleted_count}
