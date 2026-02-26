from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from llms.chatgpt import vectorize, ask_chatgpt
from vectordb.pineconedb import index as pc_index
from utils.models import UserInput, RegisterRequest, VerifyResponse
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import func, distinct
from database.db import engine, ChatHistory, User
import uuid
from datetime import datetime, timedelta

app = FastAPI(title="LangChat API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        
templates = Jinja2Templates(directory='templates')

@app.post("/register", response_model=VerifyResponse)
async def register(req: RegisterRequest, db: Session = Depends(get_db)):
    username = req.username.strip()

    try:
        user = db.query(User).filter_by(username=username).first()
        
        if user:
            return VerifyResponse(
                success=True,
                user_id=user.id,
                message=f"Welcome back, {username}!"
            )

        new_user = User(username=username)
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        return VerifyResponse(
            success=True,
            user_id=new_user.id,
            message=f"Welcome, {username}! What do you want to know about LangChain?"
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/verify")
async def verify(req: RegisterRequest, db: Session = Depends(get_db)):
    username = req.username.strip()
    user = db.query(User).filter_by(username=username).first()
    
    if not user:
        return {"success": False, "message": "user not found"}
    
    return {"success": True, "user_id": user.id, "username": username}

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/")
async def ask(user_input: UserInput, db: Session = Depends(get_db)):

    user = db.query(User).filter_by(username=user_input.username).first()
    if not user:
        raise HTTPException(status_code=401, detail="please register first.")
    
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    messages_today = db.query(func.count(ChatHistory.id)).filter(
        ChatHistory.user_id == user.id,
        ChatHistory.role == "user",
        ChatHistory.timestamp >= today_start
    ).scalar()
    
    if messages_today >= 7:
        raise HTTPException(
            status_code=429, 
            detail=f"daily message limit (7) reached. don't ask much. go back to work. grind it"
        )
    
    session_id = user_input.session_id or str(uuid.uuid4())
    user_text = user_input.user_input
    print(f"User {user_input.username} | received query: {user_text} | Daily count: {messages_today + 1}/7")

    db.add(ChatHistory(user_id=user.id, session_id=session_id, role="user", content=user_text))
    db.commit()

    embedded_user = vectorize(user_text)
    pc_resp = pc_index.query(
        namespace='all_webpages',
        vector=embedded_user,
        top_k=5,
        include_metadata=True
    )
    print('indexed query')
    retrieval = ""
    for index, match in enumerate(pc_resp.matches):
        filename = match['metadata']['filename']
        print(f"match {index+1} [{match['score']}]: {filename}")
        with open(f"files/extracted_pages/{filename}", 'r') as f:
            retrieval += f"doc_{index+1}: {filename}"+ "\n" +f.read() + "\n"
        
    prompt = f"""you are responsible for answering questions about LangChain documentation. 
    you are given retrieved context from documentation. only answer based on them. 
    don't just copy paste response from your context. explain the response to user friendly. 
    start your response stating response to question and explain in depth.
    if question is about integrating to the code or how to write particular code ,thing, try to give/explain with code examples. 
    so, your response should be two parts:
    Response to your question: ... be a bit speific, tell main ,brief response, but at the same time, be specific about terms, things used. write one paprapgraph, you can make it moderate long, not too short
    Detailed Explanation: ....
    user question: {user_text}.\nretrieved context: {retrieval}"""

    print('gpt responding...')
    bot_response = await ask_chatgpt(prompt)

    db.add(ChatHistory(user_id=user.id, session_id=session_id, role="bot", content=bot_response))
    db.commit()

    return {"response": bot_response, "session_id": session_id}





@app.get("/remaining_messages")
async def remaining_messages(username: str, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(username=username).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    messages_today = db.query(func.count(ChatHistory.id)).filter(
        ChatHistory.user_id == user.id,
        ChatHistory.role == "user",
        ChatHistory.timestamp >= today_start
    ).scalar()
    
    remaining = max(0, 7 - messages_today)
    return {"messages_sent": messages_today, "remaining": remaining, "daily_limit": 7}


@app.get("/get_history/{session_id}")
async def get_history(session_id: str, username: str, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(username=username).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    
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
async def get_sessions(username: str, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(username=username).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    
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
def delete_chat(session_id: str, username: str, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(username=username).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    
    deleted_count = (
        db.query(ChatHistory)
        .filter_by(user_id=user.id, session_id=session_id)
        .delete()
    )
    db.commit()
    
    if deleted_count == 0:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return {"success": True, "deleted_messages": deleted_count}