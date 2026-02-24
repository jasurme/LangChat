from fastapi import FastAPI, Request, Depends
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from llms.chatgpt import vectorize, ask_chatgpt
from vectordb.pineconedb import index as pc_index
from utils.models import UserInput
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import func, distinct
from database.db import engine, ChatHistory
import uuid

app = FastAPI()
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        
templates = Jinja2Templates(directory='templates')

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/")
async def ask(user_input: UserInput, db: Session = Depends(get_db)):
    
    session_id = user_input.session_id or str(uuid.uuid4())
    user_text = user_input.user_input
    print("received query: ", user_text)

    # Save user message
    db.add(ChatHistory(session_id=session_id, role="user", content=user_text))
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
        
    prompt = f"you are responsible for answering questions about LangChain documentation. you are given retrieved context from documentation. only answer based on them. \n user question: {user_text}.\nretrieved context: {retrieval}"

    print('gpt responding...')
    bot_response = await ask_chatgpt(prompt)

    # Save bot message
    db.add(ChatHistory(session_id=session_id, role="bot", content=bot_response))
    db.commit()

    return {"response": bot_response, "session_id": session_id}


@app.get("/get_history/{session_id}")
async def get_history(session_id: str, db: Session = Depends(get_db)):
    messages = db.query(ChatHistory).filter_by(session_id=session_id).order_by(ChatHistory.timestamp.asc()).all()
    return [{"role": m.role, "content": m.content} for m in messages]


@app.get("/sessions")
async def get_sessions(db: Session = Depends(get_db)):
    
    """Return all unique sessions with their first user message as title and last timestamp."""
    
    # Get all distinct session_ids with their latest timestamp
    sessions_query = (
        db.query(
            ChatHistory.session_id,
            func.max(ChatHistory.timestamp).label("last_active"),
        )
        .group_by(ChatHistory.session_id)
        .order_by(func.max(ChatHistory.timestamp).desc())
        .all()
    )
    
    result = []
    for session in sessions_query:
        # Get the first user message as the title
        first_msg = (
            db.query(ChatHistory)
            .filter_by(session_id=session.session_id, role="user")
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
def delete_chat(session_id: str, db: Session = Depends(get_db)):
    db.query(ChatHistory).filter_by(session_id=session_id).delete()
    db.commit()