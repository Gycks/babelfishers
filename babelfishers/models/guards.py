from pydantic import BaseModel


class ProtectedEntry(BaseModel):
    token: str
    replacement: str


class PlaceholderSpan(BaseModel):
    start: int
    end: int
    matched_text: str
    category: str
