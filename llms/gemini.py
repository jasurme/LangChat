from google import genai
from dotenv import load_dotenv
load_dotenv()
gemini = genai.Client()
import json

def ask_gemini(user_prompt:str ='why you arent sleeping?', structured_class: dict=None, model:str='gemini-2.5-flash'): 
    structured_config = {"temperature": 0.1}
    if structured_class:
        structured_config.update(
            {
            "response_mime_type": "application/json",
            "response_json_schema": structured_class.model_json_schema()
        }
        )
    return gemini.models.generate_content(
        model= model,
        contents=user_prompt, 
        config=structured_config
    ).text