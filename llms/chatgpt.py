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

def vectorize(query: str):
    return gpt_client.embeddings.create(
        model='text-embedding-3-large',
        input=query
    ).data[0].embedding

