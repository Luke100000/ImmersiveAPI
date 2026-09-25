import time

from httpx import HTTPStatusError
from langchain_core.runnables import RunnableSerializable
from langchain_core.runnables.utils import Input, Output
from loguru import logger


def rate_limited_call(
    llm: RunnableSerializable, prompt: Input, retries: int = 10
) -> Output:
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
                logger.info("Rate limit hit, retrying after {} seconds.", retry_after)
                time.sleep(retry_after)
                continue
            else:
                raise RuntimeError(f"An error occurred: {e.response.text}")
    raise RuntimeError("Rate limit exceeded after multiple retries.")
