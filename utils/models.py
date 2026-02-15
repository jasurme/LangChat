from pydantic import BaseModel
from typing import List

class ExtractLinks(BaseModel):
    link_list: List[str]


class UserInput(BaseModel):
    user_input: str
