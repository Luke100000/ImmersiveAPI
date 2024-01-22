from functools import cache
from typing import List, Optional, Union

from huggingface_hub import hf_hub_download
from llama_cpp import Llama


@cache
def get_model() -> Llama:
    model_path = hf_hub_download(
        repo_id="TheBloke/Mistral-7B-Instruct-v0.2-GGUF",
        filename="mistral-7b-instruct-v0.2.Q4_K_M.gguf",
    )

    # Set gpu_layers to the number of layers to offload to GPU. Set to 0 if no GPU acceleration is available on your system.
    return Llama(
        model_path=model_path,
        chat_format="llama-2",
        n_ctx=8192,
        n_threads=3,
        n_gpu_layers=0,
    )


def generate_text(
    messages: List[dict],
    temperature: float = 0.2,
    top_p: float = 0.95,
    top_k: int = 40,
    stop: Optional[Union[str, List[str]]] = None,
    seed: Optional[int] = None,
    max_tokens: Optional[int] = None,
    presence_penalty: float = 0.0,
    frequency_penalty: float = 0.0,
    repeat_penalty: float = 1.1,
) -> str:
    if stop is None:
        stop = []

    llm = get_model()

    output = llm.create_chat_completion(
        messages=messages,
        temperature=temperature,
        top_p=top_p,
        top_k=top_k,
        stop=stop,
        seed=seed,
        max_tokens=max_tokens,
        presence_penalty=presence_penalty,
        frequency_penalty=frequency_penalty,
        repeat_penalty=repeat_penalty,
    )

    return output["choices"][0]["message"]["content"]
