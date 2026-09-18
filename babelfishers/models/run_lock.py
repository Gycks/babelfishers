from pydantic import BaseModel


class RunLockEntry(BaseModel):
    path: str
    locale: str
    content_hash: str
    config_fingerprint: str
    last_run_at: int
