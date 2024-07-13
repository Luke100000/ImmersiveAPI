import hashlib
import os
import re
from contextlib import contextmanager
from functools import cache

from dotenv import load_dotenv
from groq import Groq
from langchain_core.messages import AIMessage, ToolCall
from langchain_core.prompts import ChatPromptTemplate
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
def get_information_extractor():
    return InformationExtractor()


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
    match = re.search(r"Minecraft villager named (.+?) and the Player named", text)
    if match:
        return match.group(1)
    else:
        return None


def get_conversation(messages: list[Message], max_characters: int = 1024 * 256):
    i = 0
    for i, message in enumerate(messages[::-1]):
        max_characters -= len(message.content)
        if max_characters < 0:
            break

    return "\n".join(
        [f"{message.name}: {message.content}" for message in messages[-i - 1 :]]
    )


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
            f"{descriptions.get(key, key)}\n{{{key}}}"
            for key in prompt.keys()
            if prompt[key]
        ]
    )
    return ChatPromptTemplate.from_template(template)


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
    return get_information_extractor().invoke(
        {
            "query": query,
            "document": document,
        }
    )


@contextmanager
def dummy_context_manager():
    yield


async def get_chat_completion(
    model: Model,
    character: Character,
    messages: list[Message],
    tools: list[dict],
    auth_token: str,
    langsmith_project: str = None,
) -> AIMessage:
    if langsmith_project:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGSMITH_PROJECT"] = langsmith_project

    # Preload
    get_glossary_manager()
    get_vector_compressor()

    with trace(
        "Chat",
        "chain",
        project_name=langsmith_project,
        inputs={"messages": messages, "tools": tools},
        tags=[model.model, character.name],
    ) if langsmith_project else dummy_context_manager():
        kwargs = dict(
            temperature=0.85,
            max_tokens=150,
            user=hashlib.sha256(auth_token.encode("UTF-8")).hexdigest(),
            stop=character.stop,
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

        # Enable tools and add glossary functions if requested
        tooled_llm = llm
        if model.tools:
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
            if len(tools) > 0:
                tooled_llm = llm.bind_tools(tools)

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
        use_memory = get_boolean(flags, "use_memory", True)
        shared_memory = get_boolean(flags, "shared_memory", False)
        session_id = (
            None
            if character_id is None
            else f"{world_id if shared_memory else player_id}_{character_id}"
        )

        # Clean the remaining messages and construct a query for RAG
        messages = clean_conversation(messages, player_id)
        query = get_conversation(messages, 400)

        prompt = {
            "static_system": static_system,
            "dynamic_system": get_vector_compressor().invoke(
                {
                    "input": dynamic_system,
                    "query": query,
                    "k": 5,
                }
            )
            if dynamic_system
            else "",
            "glossary": "\n".join(
                [
                    get_glossary_entry(query, glossary)
                    for glossary in character.glossary
                    if not glossary.confirm
                ]
            ),
            "memory": get_memory_manager(
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
            else get_conversation(messages, character.fallback_memory_characters),
        }

        # Launch
        chain = get_template(prompt) | tooled_llm
        chain.name = "Chat"
        response = chain.invoke(prompt)

        # If the response contains glossary calls, enrich the prompt with the glossary entries
        if isinstance(response, AIMessage) and response.tool_calls:
            glossaries = []
            already_called = set()
            for tool in response.tool_calls:
                tool: ToolCall = tool
                if (
                    tool["name"].startswith("glossary_")
                    and tool["name"] not in already_called
                ):
                    already_called.add(tool["name"])
                    index = int(tool["name"].replace("glossary_", ""))
                    glossary = character.glossary[index]
                    glossaries.append(get_glossary_entry(query, glossary))

            # Call again, with glossary enriched prompt
            if glossaries:
                prompt["glossary"] = "\n".join([g for g in glossaries if len(g) > 8])
                chain = get_template(prompt) | llm
                chain.name = "Chat with glossary"
                response = chain.invoke(prompt)

        os.environ["LANGCHAIN_TRACING_V2"] = "false"
        return response


def message_to_dict(message: AIMessage):
    return {
        "choices": [
            {
                "message": {
                    "content": message.content.strip('"').strip(),
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