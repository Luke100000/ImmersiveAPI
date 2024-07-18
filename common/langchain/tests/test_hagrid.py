import asyncio
import json
import logging
import time

from common.langchain.types import Message
from modules.mca.chain import get_chat_completion, message_to_dict
from modules.mca.mca import MODELS, CHARACTERS, HAGRID_SECRET

logging.basicConfig(level=logging.INFO)


def main():
    response = asyncio.run(
        get_chat_completion(
            # MODELS["gpt-4o"],
            MODELS["llama3-70b"],
            CHARACTERS[HAGRID_SECRET],
            [
                Message(
                    role="system",
                    content="[shared_memory:true][world_id:default][character_id:hagrid][glossaries:minecraft_wiki]",
                ),
                Message(
                    role="user",
                    content="How to get amethysts?",
                    name="Conczin",
                ),
            ],
            [],
            HAGRID_SECRET,
            langsmith_project="hagrid",
        )
    )

    print(json.dumps(message_to_dict(response), indent=2))

    time.sleep(100000)


if __name__ == "__main__":
    main()
