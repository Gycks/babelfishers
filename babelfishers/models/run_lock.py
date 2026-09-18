from enum import StrEnum

from pydantic import BaseModel


class StaleReason(StrEnum):
    NEW = "new"
    TARGET_MISSING = "target missing"
    CONTENT_CHANGED = "source changed"
    CONFIG_CHANGED = "config changed"


class RunLockEntry(BaseModel):
    path: str
    locale: str
    content_hash: str
    config_fingerprint: str
    last_run_at: int
