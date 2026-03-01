from openai import OpenAI
from dotenv import load_dotenv
from pydantic import BaseModel
load_dotenv()
gpt_client = OpenAI()
class GptResponse(BaseModel):
    response: str

async def ask_chatgpt(user_prompt:str ='why you arent sleeping?', structured_class: dict=None, model:str='gpt-4o-mini'):
    resp =  gpt_client.responses.parse(
        model=model,
        input=user_prompt,
        text_format=structured_class if structured_class else GptResponse
    )

    return resp.output_parsed if structured_class else resp.output_parsed.response

def stream_chatgpt(prompt, model='gpt-4o-mini'):
    stream = gpt_client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        stream=True,
    )
    for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content

def vectorize(query: str):
    return gpt_client.embeddings.create(
        model='text-embedding-3-large',
        input=query
    ).data[0].embedding

