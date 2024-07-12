from enum import Enum

from pydantic import BaseModel


class Role(Enum):
    system = "system"
    user = "user"
    assistant = "assistant"


class Message(BaseModel):
    role: Role = Role.user
    content: str
    name: str = None


class Body(BaseModel):
    model: str
    messages: list[Message]
    glossary: list = []


class Model(BaseModel):
    price: float
    model: str
    provider: str
    system: str = ""
    whitelist: set = None
    tools: bool = False


class GlossarySearch(BaseModel):
    tags: set[str]
    description: str
    k: int
    lambda_mult: float = 0.5
    confirm: bool = False


class Character(BaseModel):
    """
    A character config, defining its capabilities, intelligence, and base personality.
    """

    name: str
    system: str
    dynamic_k: int = 4
    glossary: list[GlossarySearch] = []
    default_model: str = "default"
    fallback_memory_characters: int = 3000
    memory_characters_per_level: int = 1000
    memory_sentences_per_summary: int = 3
