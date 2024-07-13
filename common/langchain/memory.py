import sqlite3
from dataclasses import dataclass
from datetime import datetime
from functools import cache
from typing import Optional

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnableConfig
from langchain_groq import ChatGroq
from langsmith import traceable

from common.langchain.types import Message, Role


@dataclass
class Memory:
    id: int
    session_id: str
    name: str
    time: int
    content: str
    level: int


compression_system_prompt = """
You are a memory compression AI.
Given a conversation between you and one or more humans (as well as memories from the past), extract key memories into up to {sentences} sentences.
Be concise and only return the summary in one single line, do not prepend or append any additional text.
Do not drop information, but still stay very concise.

For example:
"Carl: Hey Bob, did you see the new episode of that sci-fi show last night?"
"You: No, I missed it! Was it good?"
"Carl: Yeah, it was amazing! They introduced a new character who can time travel."
"You: That sounds awesome. I'll definitely have to watch it tonight."
"Carl: You won't regret it. The plot twists are mind-blowing."
"You: Great!

Output:
Carl praises a sci-fi show's new episode featuring a time-traveling character.

Answer ONLY with the summary, in a single line.
"""


@cache
def _get_compression_chain(model: str = "llama3-70b-8192"):
    return (
        ChatPromptTemplate.from_messages(
            [
                ("system", compression_system_prompt),
                ("human", "{messages}"),
            ]
        )
        | ChatGroq(model=model, temperature=0, max_tokens=200, stop=["\n"])
        | (lambda x: x.content)
    )


def _to_conversation(memories: list[Memory]) -> str:
    """
    Convert memories to a conversation.
    """
    return "\n".join([f"{memory.name}: {memory.content}" for memory in memories])


def _populate_names(conversation: list, default_name: str) -> list:
    """
    Memories are multi-speaker, thus ensure that name is set, and use "You" for the assistant.
    """
    for message in conversation:
        if message.role == Role.user and message.name is None:
            message.name = default_name
        elif message.role == Role.assistant:
            message.name = "You"
    return conversation


def _strip_system(conversation: list) -> list:
    return [message for message in conversation if message.role != Role.system]


def clean_conversation(conversation: list[Message], default_name: str) -> list[Message]:
    return _populate_names(_strip_system(conversation), default_name)


class MemoryManager(Runnable):
    """
    A manager class that stores conversations in an SQLite database.
    """

    def __init__(
        self,
        db_file: str = "cache/memory.db",
        characters_per_level: int = 700,
        sentences_per_summary: int = 3,
        model: str = "llama3-70b-8192",
    ):
        self.conn = sqlite3.connect(db_file)
        self.create_table()

        self.characters_per_level = characters_per_level
        self.sentences_per_summary = sentences_per_summary

        self.chain = _get_compression_chain(model=model)

    @traceable(run_type="tool", name="Memorize")
    def invoke(self, input_dict: dict, config: Optional[RunnableConfig] = None) -> str:
        assert isinstance(input_dict, dict), "Input must be a dictionary."
        assert "session_id" in input_dict, "Session ID not found in input dict."
        assert "conversation" in input_dict, "Conversation not found in input dict."

        return self.add_fetch_compress(
            input_dict["session_id"], input_dict["conversation"]
        )

    def create_table(self):
        """
        Create the memory table if it doesn't exist.
        """
        query = """
        CREATE TABLE IF NOT EXISTS memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            name TEXT NOT NULL,
            time INTEGER NOT NULL,
            content TEXT NOT NULL,
            level INTEGER DEFAULT 0
        )
        """
        self.conn.execute(query)
        self.conn.commit()

    def add_memory(self, memory: Memory):
        """
        Add a memory to the database.
        """
        query = """
        INSERT INTO memory (session_id, name, time, content, level)
        VALUES (?, ?, ?, ?, ?)
        """
        self.conn.execute(
            query,
            (
                memory.session_id,
                memory.name,
                memory.time,
                memory.content,
                memory.level,
            ),
        )
        self.conn.commit()

    def _split_buffer(self, buffer: list[Memory]) -> tuple[list[Memory], list[Memory]]:
        """
        Split a buffer into two parts, one that can be compressed and one that can't.
        """
        count = 0
        split_index = 0
        for split_index, memory in enumerate(buffer):
            if count > self.characters_per_level:
                break
            count += len(memory.content)
        return buffer[:split_index], buffer[split_index:]

    def _compress_buffer(self, count: int, buffer: list[Memory]) -> list[Memory]:
        # Threshold reached, summarize
        if count > self.characters_per_level * 1.5 and len(buffer) >= 3:
            to_be_summarized, too_recent = self._split_buffer(buffer)
            summarized_memory = self._summarize(to_be_summarized)
            self.remove_memories(to_be_summarized)
            self.add_memory(summarized_memory)
            return [summarized_memory] + too_recent
        else:
            return buffer

    def compress_memory(self, memories: list[Memory]) -> list[Memory]:
        """
        Compress memories by summarizing the first n tokens on each level.
        """

        compressed_memories = []

        count = 0
        last_level = 0
        to_be_summarized = []
        for memory in memories:
            if memory.level < last_level:
                compressed_memories.extend(
                    self._compress_buffer(count, to_be_summarized)
                )

                # Reset and start next compression level
                count = 0
                to_be_summarized = []

            count += len(memory.content)
            to_be_summarized.append(memory)
            last_level = memory.level

        compressed_memories.extend(self._compress_buffer(count, to_be_summarized))

        return compressed_memories

    def fetch_memories(self, session_id: str) -> list[Memory]:
        """
        Fetch memories from a given session (usually the NPCs unique id).
        """
        query = """
        SELECT * FROM memory
        WHERE session_id = ?
        ORDER BY time, ROWID
        """
        cursor = self.conn.execute(query, (session_id,))
        rows = cursor.fetchall()
        memories = [Memory(*row) for row in rows]
        return memories

    def _summarize(self, memories: list[Memory]) -> Memory:
        """
        Summarize memories into fewer memories.
        """
        messages = [f"{memory.name}: {memory.content}" for memory in memories]
        summary = self.chain.invoke(
            {
                "messages": "\n".join(messages),
                "sentences": self.sentences_per_summary,
            }
        )
        return Memory(
            -1,
            memories[0].session_id,
            "memory",
            memories[len(memories) // 2].time,
            summary,
            memories[0].level + 1,
        )

    def add_fetch_compress(self, session_id: str, conversation: list[Message]) -> str:
        self._verify_conversation(conversation)

        # fetch memories
        memories = self.fetch_memories(session_id)

        # find first tracked message
        index = -1
        any_matched = False
        for index, message in enumerate(conversation[::-1]):
            if any(
                memory.level == 0
                and memory.name == message.name
                and memory.content == message.content
                for memory in memories
            ):
                any_matched = True
                break

        if any_matched:
            conversation = [] if index == 0 else conversation[-index:]

        # add memories
        for message in conversation:
            memory = Memory(
                id=-1,
                session_id=session_id,
                name=message.name,
                time=int(datetime.now().timestamp() * 1000),
                content=message.content,
                level=0,
            )
            self.add_memory(memory)
            memories.append(memory)

        # compress memories
        compressed_memories = self.compress_memory(memories)

        return _to_conversation(compressed_memories)

    def prune(self):
        """
        Prune conversations older than a year.
        """
        query = "DELETE FROM memory WHERE 1"
        self.conn.execute(query)
        self.conn.commit()

    def close(self):
        """
        Close the database connection.
        """
        self.conn.close()

    def remove_memories(self, memories: list[Memory]):
        """
        Remove memories from the database.
        """
        ids = [memory.id for memory in memories if memory.id >= 0]
        query = f"DELETE FROM memory WHERE id IN ({', '.join(map(str, ids))})"
        self.conn.execute(query)
        self.conn.commit()

    def _verify_conversation(self, conversation: list[Message]):
        for message in conversation:
            if message.role == Role.system:
                raise ValueError("System messages are not allowed in the conversation.")
            if message.name is None:
                raise ValueError("All messages must have a name.")
