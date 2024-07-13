import asyncio

from common.langchain.types import Message
from modules.mca.chain import get_chat_completion
from modules.mca.mca import MODELS, CHARACTERS, HAGRID_SECRET


def main():
    response = asyncio.run(
        get_chat_completion(
            # MODELS["gpt-4o"],
            MODELS["llama3-70b"],
            CHARACTERS[HAGRID_SECRET],
            [
                Message(
                    role="user",
                    content="Hey how can I disable the screen at the beginning?",
                    name="Conczin",
                )
            ],
            HAGRID_SECRET,
        )
    )

    print(response)


if __name__ == "__main__":
    main()
