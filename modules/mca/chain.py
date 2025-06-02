import logging
import os
import re
import time
from contextlib import contextmanager
from functools import cache
from typing import Optional

import requests
from cachetools import cached, TTLCache
from dotenv import load_dotenv
from groq import Groq
from httpx import HTTPStatusError
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, SystemMessage, BaseMessage
from langchain_groq import ChatGroq
from langchain_mistralai import ChatMistralAI
from langchain_openai import ChatOpenAI
from langsmith import trace, traceable

from common.config import settings
from common.langchain.glossary_manager import GlossaryManager
from common.langchain.information_extractor import InformationExtractor
from common.langchain.memory import MemoryManager, clean_conversation
from common.langchain.types import Message, Model, Character, GlossarySearch, Role
from common.langchain.vector_compressor import VectorCompressor
from common.rag.git_document_manager import GitDocumentManager
from common.rag.wiki_document_manager import WikiDocumentManager

load_dotenv()


@cache
def get_client():
    return Groq(
        api_key=os.environ.get("GROQ_API_KEY"),
    )


@cache
def get_memory_manager(**kwargs):
    return MemoryManager(**kwargs)


@cache
def get_vector_compressor():
    return VectorCompressor()


@cache
def get_information_extractor(model: str):
    return InformationExtractor(model)


@cache
def get_glossary_manager():
    manager = GlossaryManager()
    for glossary in settings["global"]["glossaries"]:
        if glossary["type"] == "wiki":
            manager.add_documents(
                glossary["name"],
                WikiDocumentManager(glossary["index_url"]).get_documents(),
            )
        elif glossary["type"] == "git":
            manager.add_documents(
                glossary["name"],
                GitDocumentManager(
                    glossary["repository"],
                ).get_documents(),
            )
        else:
            raise ValueError(f"Unknown glossary type: {glossary['type']}")
    return manager


def get_villager(text: str):
    """
    Backwards compatibility for missing character IDs.
    """
    match = re.search(r"Minecraft villager named (.+?) and the Player named", text)
    if match:
        return match.group(1)
    else:
        return None


def crop_conversation(
    messages: list[Message], max_characters: int = 1024 * 256
) -> list[Message]:
    i = 0
    for i, message in enumerate(messages[::-1]):
        max_characters -= len(message.content)
        if max_characters < 0:
            break
    return messages[-i - 1 :]


def to_conversation(messages: list[Message]):
    return "\n".join([f"{message.name}: {message.content}" for message in messages])


def get_system_flags(system: str):
    pattern = re.compile(r"\[(.*?)]")
    matches = pattern.findall(system)

    flags = {}
    for match in matches:
        key, value = match.split(":")
        flags[key] = value

    rest = pattern.sub("", system)

    return flags, rest


def get_boolean(flags: dict, key: str, default: bool = False):
    return flags[key].lower() == "true" if key in flags else default


@traceable(run_type="chain", name="Process Glossary")
def get_glossary_entry(query: str, glossary: GlossarySearch) -> str:
    document = get_glossary_manager().invoke(
        {
            "query": query,
            "k": glossary.k,
            "filter": list(glossary.tags),
            "lambda_mult": glossary.lambda_mult,
        }
    )
    return (
        get_information_extractor(glossary.compression_model).invoke(
            {
                "query": query,
                "document": document,
            }
        )
        if glossary.compression and document
        else document
    )


@contextmanager
def dummy_context_manager():
    yield


@cached(TTLCache(maxsize=1, ttl=3600))
def get_models():
    return [
        m["name"]
        for m in requests.get(
            url="https://api.conczin.net/v1/chat/models",
            params={"min_size": 7},
        ).json()
    ]


def get_chat_completion(
    model: Model,
    character: Character,
    messages: list[Message],
    tools: list[dict],
    auth_token: str,
    langsmith_project: Optional[str] = None,
) -> AIMessage:
    if langsmith_project:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGSMITH_PROJECT"] = langsmith_project

    # Preload
    get_glossary_manager()
    get_vector_compressor()

    with (
        trace(
            "Chat",
            "chain",
            project_name=langsmith_project,
            inputs={"messages": messages, "tools": tools},
            tags=[model.model, character.name],
        )
        if langsmith_project
        else dummy_context_manager()
    ):
        # Instantiate model
        if model.provider == "mistral":
            llm = ChatMistralAI(
                model_name=model.model,
                max_retries=5,
                temperature=0.85,
                max_tokens=150,
            )
        elif model.provider == "groq":
            llm = ChatGroq(
                model=model.model,
                max_retries=5,
                temperature=0.85,
                max_tokens=150,
                stop_sequences=character.stop,
            )
        elif model.provider == "openai":
            llm = ChatOpenAI(
                model=model.model,
                max_retries=5,
                temperature=0.85,
                max_tokens=150,
                stop_sequences=character.stop,
            )
        elif model.provider == "horde":
            # A model with `llama-3-instruct` format is added to have consistent results
            # TODO: Filter by template
            models = ["koboldcpp/L3-8B-Stheno-v3.2"] + get_models()

            if len(models) == 1:
                raise ValueError("No models available.")

            llm = ChatOpenAI(
                base_url="https://api.conczin.net/v1",
                model=",".join(models),
                api_key=os.environ.get("HORDE_API_KEY"),  # pyright: ignore [reportArgumentType]
                max_retries=3,
                temperature=0.85,
                max_tokens=100,
                stop_sequences=character.stop,
                timeout=180,
            )
        else:
            raise ValueError(f"Unknown provider: {model.provider}")

        # Enable tools and add glossary functions if requested
        if model.tools and len(tools) > 0:
            llm = llm.bind_tools(tools)

        # Process system prompt
        static_system = character.system + "\n" + model.system
        if messages[0].role == Role.system:
            flags, dynamic_system = get_system_flags(messages[0].content)
        else:
            flags, dynamic_system = {}, ""

        # Extract session related data
        world_id = flags.get("world_id", auth_token)
        player_id = flags.get("player_id", auth_token)
        character_id = (
            flags["character_id"]
            if "character_id" in flags
            else get_villager(messages[0].content)
        )
        use_memory = get_boolean(flags, "use_memory", False)
        shared_memory = get_boolean(flags, "shared_memory", False)
        session_id = (
            None
            if character_id is None
            else f"{world_id if shared_memory else player_id}_{character_id}"
        )
        enabled_glossaries = {g.strip() for g in flags.get("glossaries", "").split(",")}

        # Clean the remaining messages and construct a query for RAG
        messages = clean_conversation(messages, player_id)
        query = to_conversation(crop_conversation(messages, 400))

        # If the system is too large, compress it using a RAG
        dynamic_system = (
            get_vector_compressor().invoke(
                {
                    "input": dynamic_system,
                    "query": query,
                    "k": 3,
                }
            )
            if dynamic_system
            else ""
        )

        # Construct the prompt
        prompt: list[BaseMessage] = (
            [SystemMessage(f"{static_system}\n{dynamic_system}")]
            + [
                AIMessage(
                    content=get_glossary_entry(query, glossary),
                    name="Glossary",
                )
                for key, glossary in character.glossary.items()
                if glossary.always or key in enabled_glossaries
            ]
            + (
                get_memory_manager(
                    characters_per_level=character.memory_characters_per_level,
                    sentences_per_summary=character.memory_sentences_per_summary,
                    model=character.memory_model,
                ).invoke(
                    {
                        "session_id": session_id,
                        "conversation": messages,
                    }
                )
                if use_memory and session_id is not None
                else [
                    m.as_langchain()
                    for m in crop_conversation(
                        messages, character.fallback_memory_characters
                    )
                ]
            )
        )

        # Launch
        response = timeout_call(llm, prompt)

        os.environ["LANGCHAIN_TRACING_V2"] = "false"

        return response


def timeout_call(
    llm: BaseChatModel, prompt: list[BaseMessage], retries: int = 10
) -> AIMessage:
    """
    Call the LLM with a timeout.
    """
    for _ in range(retries):
        try:
            return llm.invoke(prompt)
        except HTTPStatusError as e:
            if e.response.status_code == 429:
                # Rate limit error, wait and retry
                retry_after = float(e.response.headers.get("Retry-After", 0.5))
                logging.info(f"Rate limit hit, retrying after {retry_after} seconds...")
                time.sleep(retry_after)
                continue
            else:
                raise RuntimeError(f"An error occurred: {e.response.text}")
    raise RuntimeError("Rate limit exceeded after multiple retries.")


def message_to_dict(message: AIMessage) -> dict:
    """
    Convert an AIMessage to an OpenAI API response object.
    """
    return {
        "choices": [
            {
                "message": {
                    "content": str(message.content).strip('"').strip(),
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": tool["id"],
                            "type": "function",
                            "function": {
                                "name": tool["name"],
                                "arguments": tool["args"],
                            },
                        }
                        for tool in message.tool_calls
                    ],
                }
            }
        ]
    }
