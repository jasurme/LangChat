from pydantic import BaseModel
from typing import List, Optional

class ExtractLinks(BaseModel):
    link_list: List[str]


class UserInput(BaseModel):
    user_input: str
    session_id: Optional[str] = None
