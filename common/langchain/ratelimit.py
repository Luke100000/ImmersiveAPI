import logging
import time

from httpx import HTTPStatusError
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, AIMessage


def rate_limited_call(
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
                retry_after = float(e.response.headers.get("Retry-After", 0.25))
                logging.info(f"Rate limit hit, retrying after {retry_after} seconds...")
                time.sleep(retry_after)
                continue
            else:
                raise RuntimeError(f"An error occurred: {e.response.text}")
    raise RuntimeError("Rate limit exceeded after multiple retries.")
