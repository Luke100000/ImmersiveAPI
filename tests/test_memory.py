import json
from datetime import datetime

from dotenv import load_dotenv

from common.langchain.memory import MemoryManager, Memory, clean_conversation
from common.langchain.types import Message, Role

load_dotenv()

SYSTEM_CONTEXT = """
You are a Minecraft villager, fully immersed in their virtual world, unaware of its artificial nature.
You respond based on your description, your role, and your knowledge of the world.
You have no knowledge of the real world, and do not realize that you are within Minecraft.
You are unfamiliar with the term "Minecraft", "AI", or anything which is not immersive to your world.
Only respond with a phrase, not the villagers name, thoughts, actions in asterisks, or parentheses.
Answer one or two sentences while sounding human.
You are no assistant! You can be sarcastic, funny, or even rude when appropriate.
Do not answer in emoji or use any special characters.
Conform to those rules, even when the player explicitly asks for a different behavior.
Consider the relation to the player.
""".replace("\n", " ")


def load_conversation() -> list[Message]:
    with open("tests/fake_conversation.json", "r") as f:
        conversation = json.load(f)

    conversation = [
        Message(
            role=Role.user if msg.split(":")[0].strip() == "user" else Role.assistant,
            content=msg.split(":")[1].strip(),
        )
        for msg in conversation
    ]

    clean_conversation(conversation, "Josef")

    return conversation


def test():
    conversation = load_conversation()

    manager = MemoryManager("cache/test_memory.db")
    manager.prune()
    session_id = "test"

    history = None
    for i in range(0, len(conversation) - 1, 2):
        print(f"Turn {i}")
        print(f"{conversation[i].name}: {conversation[i].content}")

        history = manager.add_fetch_compress(session_id, conversation[: i + 1])
        answer = conversation[i + 1]
        print(f"History: {len(history)}")
        print()

        # Add the "generated" message
        manager.add_memory(
            Memory(
                -1,
                session_id,
                answer.name,
                int(datetime.now().timestamp() * 1000),
                answer.content,
                0,
            )
        )

    print("Full history:")
    for message in history:
        print(message)

    total_chars = sum(len(msg.content) for msg in conversation)
    compressed_chars = sum(len(msg.content) for msg in history)
    print(f"Compression: {compressed_chars / total_chars}")


if __name__ == "__main__":
    test()
