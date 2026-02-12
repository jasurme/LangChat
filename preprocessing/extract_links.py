
from tavily import TavilyClient
from pydantic import BaseModel, Field
import requests
JINA_API_KEY='jina_db6f8ad4aeb14f029997aa256fe22c7abEoVOzrcbTfdNEvuXH2c4JUddHVa'
from typing import List
from llms.chatgpt import ask_chatgpt
from dotenv import load_dotenv
from utils.models import ExtractLinks
import re
import time
load_dotenv()
tavily = TavilyClient()
class ExtractedLinks(BaseModel):
    links: List[str] = Field(description='list of extracted links. for example: "https://docs.langchain.com/api-reference/sandboxes-v2/delete-a-sandbox.md"')
n_of_lines = 0
with open('files/llms.txt', 'r', encoding='utf-8') as f:
    for line in f:
        n_of_lines +=1

divided = n_of_lines // 20
print(n_of_lines)
headers = {
        "Authorization": f"Bearer {JINA_API_KEY}",
        "X-Return-Format": "markdown" 
    }
page_number = 0
for i in range(1,(divided-1)*20+2, 20):
    print(i)
    text_chunk = ""
    start_line = i
    end_line = i+19
    print('end_line ', end_line)
    with open('files/llms.txt', 'r', encoding='utf-8') as f:
        for line_number, line in enumerate(f, 1):
            if start_line <= line_number <= end_line:
                text_chunk += line
            elif line_number > end_line:
                break
        
        prompt = f"you need to extract webpage links from text below. mostly links are .md file links, for example 'https://docs.langchain.com/langsmith/assistants.md'.\ntext: \n{text_chunk}"
        links = ask_chatgpt(user_prompt=prompt, structured_class=ExtractedLinks).links
        for i,link in enumerate(links):
            print(f'extracting page {page_number}: {link}')
            
            try: 
                response = requests.get(f"https://r.jina.ai/{link}", headers=headers)
                if response.status_code == 200:
                    page_text = response.text 
                else: 
                    time.sleep(10)
                    response = requests.get(f"https://r.jina.ai/{link}", headers=headers)
                    page_text = response.text 
                print(f'extracted it: {page_text[:30]}')
                clean_name = re.sub(r'[^\w\s-]', '_', link)
                with open(f'files/extracted_pages/page_{page_number}_{clean_name}.txt', 'w', encoding='utf-8')as f:
                    f.write(page_text)
                page_number+=1
                print('wrote it. moving next...')
            except Exception as e: print(f'error happened while fetching: {link}\n error: {e}')

        




