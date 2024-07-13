import hashlib
import os
import re
from functools import cache

from dotenv import load_dotenv
from groq import Groq
from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq
from langchain_mistralai import ChatMistralAI
from langchain_openai import ChatOpenAI

from common.langchain.glossary_manager import GlossaryManager
from common.langchain.memory import MemoryManager, clean_conversation
from common.langchain.types import Message, Model, Character
from common.langchain.vector_compressor import VectorCompressor
from common.rag.git_document_manager import GitDocumentManager

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
def get_glossary_manager():
    manager = GlossaryManager()
    manager.add_documents(
        "mca_wiki",
        GitDocumentManager(
            "https://github.com/Luke100000/minecraft-comes-alive.wiki.git"
        ).get_documents(),
    )
    return manager


def get_villager(text: str):
    match = re.search(r"Minecraft villager named (.+?) and the Player named", text)
    if match:
        return match.group(1)
    else:
        return None


def get_conversation(messages: list[Message], max_characters: int = 1024 * 256):
    for i, message in enumerate(messages[::-1]):
        if max_characters < 0:
            break
        max_characters -= len(message.content)

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


def get_template(prompt: dict[str, str]):
    descriptions = {
        "static_system": "System prompt:",
        "dynamic_system": "Context specific system prompt:",
        "glossary": "Retrieved content from knowledge base:",
        "memory": "Memory and current conversation:",
    }

    template = "\n--------\n\n".join(
        [
            f"{descriptions.get(key, key)}:\n{{{key}}}"
            for key in prompt.keys()
            if prompt[key]
        ]
    )
    return ChatPromptTemplate.from_template(template)


async def get_chat_completion(
    model: Model, character: Character, messages: list[Message], auth_token: str
) -> str:
    kwargs = dict(
        temperature=0.85,
        max_tokens=150,
        user=hashlib.sha256(auth_token.encode("UTF-8")).hexdigest(),
        stop=["\n"],
    )
    if model.provider == "conczin":
        llm = ChatOpenAI(
            model=model.model,
            openai_api_base="https://llm.conczin.net/v1",
            **kwargs,
        )
    elif model.provider == "mistral":
        llm = ChatMistralAI(model=model.model, **kwargs)
    elif model.provider == "groq":
        llm = ChatGroq(model=model.model, **kwargs)
    elif model.provider == "openai":
        llm = ChatOpenAI(model=model.model, **kwargs)
    else:
        raise ValueError(f"Unknown provider: {model.provider}")

    # todo if it supports tools (llama70b and openai)
    tooled_llm = llm
    if model.tools:
        tools = []
        for index, glossary in enumerate(character.glossary):
            if glossary.confirm:
                tools.append(
                    {
                        "type": "function",
                        "function": {
                            "name": f"glossary_{index}",
                            "description": glossary.description,
                            "parameters": {
                                "type": "object",
                                "properties": {},
                                "required": [],
                            },
                        },
                    }
                )
                # todo add a "stop conversation" to hagrid and deprecate hallo hagrid
        tooled_llm = llm.bind_tools(tools)

    # Process system prompt
    static_system = character.system + "\n" + model.system
    if messages[0].role == "system":
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
    use_memory = get_boolean(flags, "use_memory", True)
    shared_memory = get_boolean(flags, "shared_memory", False)
    session_id = (
        None
        if character_id is None
        else ((world_id if shared_memory else player_id) + character_id)
    )

    # Clean the remaining messages and construct a query for RAG
    messages = clean_conversation(messages, player_id)
    query = get_conversation(messages, 500)

    prompt = {
        "static_system": static_system,
        "dynamic_system": get_vector_compressor().invoke(
            {
                "input": dynamic_system,
                "query": query,
                "k": 5,
            }
        ),
        "glossary": ""
        if True
        else get_glossary_manager().invoke(
            {
                "query": query,
                "k": 5,
                "filter": ["mca_wiki"],
                "lambda_mult": 0.5,
            }
        ),
        "memory": get_memory_manager(
            characters_per_level=character.memory_characters_per_level,
            sentences_per_summary=character.memory_sentences_per_summary,
        ).invoke(
            {
                "session_id": session_id,
                "conversation": messages,
            }
        )
        if use_memory and session_id is not None
        else get_conversation(messages, character.fallback_memory_characters),
    }

    # Launch
    chain = get_template(prompt) | tooled_llm
    response = chain.invoke(prompt)

    if isinstance(response, AIMessage) and response.tool_calls:
        for tool in response.tool_calls:
            if tool["name"].startswith("glossary_"):
                index = int(tool["name"].replace("glossary_", ""))
                glossary = character.glossary[index]
                prompt["glossary"] = get_glossary_manager().invoke(
                    {
                        "query": query,
                        "k": glossary.k,
                        "filter": list(glossary.tags),
                        "lambda_mult": glossary.lambda_mult,
                    }
                )
                # todo multi tool support?
                break

        # Call again, with glossary enriched prompt
        chain = get_template(prompt) | llm
        response = chain.invoke(prompt)

    return str(response.content)
