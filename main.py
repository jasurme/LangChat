from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from llms.chatgpt import vectorize, ask_chatgpt
from vectordb.pineconedb import index as pc_index
from utils.models import UserInput
app = FastAPI()

templates = Jinja2Templates(directory='templates')

@app.get("/", response_class=HTMLResponse)
async def ask(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/")
async def ask(user_input: UserInput):
    
    user_input = user_input.user_input
    print("received query: ", user_input)
    embedded_user = vectorize(user_input)
    pc_resp = pc_index.query(
        namespace='all_webpages',
        vector=embedded_user,
        top_k=3,
        include_metadata=True
    )
    print('indexed query')
    retrieval = ""
    for index, match in enumerate(pc_resp.matches):
        filename = match['metadata']['filename']
        print(f"match {index+1} [{match['score']}]: {filename}")
        with open(f"files/extracted_pages/{filename}", 'r') as f:
            retrieval += f"doc_{index+1}: {filename}"+ "\n" +f.read() + "\n"
        
    prompt = f"you are responsible for answering questions about LangChain documentation. you are given retrieved context from documentation. only answer based on them. \n user question: {user_input}.\nretrieved context: {retrieval}"

    print('gpt responding...')
    return {"response": await ask_chatgpt(prompt) }

     