from pydantic import BaseModel


class Culture(BaseModel):
    code: str
    name: str
    # Set on a plain code such as `pt`: the regional variant it stands for on every engine.
    default_variant: str | None = None
