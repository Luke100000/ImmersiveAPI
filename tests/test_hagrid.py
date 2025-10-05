import json
import logging
import time

from app.llm.types import Message, Role
from app.modules.mca.chain import get_chat_completion, message_to_dict
from app.modules.mca.mca import CHARACTERS, HAGRID_SECRET, MODELS

logging.basicConfig(level=logging.INFO)


def main():
    response = get_chat_completion(
        MODELS["gpt-4.1-mini"],
        CHARACTERS[HAGRID_SECRET],
        [
            Message(
                role=Role.system,
                content="[use_memory:true][shared_memory:true][world_id:default][character_id:hagrid][glossaries:mca_wiki]",
            ),
            Message(
                role=Role.user,
                content="How to get amethysts?",
                name="Conczin",
            ),
        ],
        [],
        HAGRID_SECRET,
    )

    print(json.dumps(message_to_dict(response), indent=2))

    time.sleep(100000)


if __name__ == "__main__":
    main()
