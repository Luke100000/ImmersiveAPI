from enum import Enum
from typing import Optional

from langchain_core.messages import SystemMessage, AIMessage, HumanMessage, BaseMessage
from pydantic import BaseModel


class Role(Enum):
    system = "system"
    user = "user"
    assistant = "assistant"


class Message(BaseModel):
    role: Role = Role.user
    content: str
    name: Optional[str] = None

    def as_langchain(self) -> BaseMessage:
        if self.role == Role.system:
            return SystemMessage(content=self.content)
        elif self.role == Role.user:
            return HumanMessage(content=self.content, name=self.name)
        elif self.role == Role.assistant:
            return AIMessage(content=self.content, name=self.name)
        else:
            raise ValueError(f"Invalid role: {self.role}")


class Body(BaseModel):
    model: str
    messages: list[Message]
    tools: list[dict] = []


class Model(BaseModel):
    price: float
    model: str
    provider: str
    system: str = ""
    whitelist: Optional[set] = None
    tools: bool = False


class GlossarySearch(BaseModel):
    tags: set[str]
    description: str
    k: int
    lambda_mult: float = 0.5
    always: bool = True
    compression_model: str = "llama-3.3-70b-versatile"
    compression: bool = True


class Character(BaseModel):
    """
    A character config, defining its capabilities, intelligence, and base personality.
    """

    name: str
    system: str
    dynamic_k: int = 4
    glossary: dict[str, GlossarySearch] = {}
    default_model: str = "default"
    fallback_memory_characters: int = 3000
    memory_characters_per_level: int = 1000
    memory_sentences_per_summary: int = 3
    memory_model: str = "llama-3.1-8b-instant"
    langsmith_project: Optional[str] = None
    stop: list[str] = ["\n"]
