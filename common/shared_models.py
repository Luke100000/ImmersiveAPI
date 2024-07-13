from abc import ABC
from functools import cache

from langchain_core.embeddings import Embeddings
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_openai import OpenAIEmbeddings

from common.config import settings

ADDITIONAL_QUERY_PROMPTS = {
    "mixedbread-ai/mxbai-embed-large-v1": "Represent this sentence for searching relevant passages: ",
}


class NamedEmbedding(Embeddings, ABC):
    @property
    def name(self) -> str:
        return "unnamed"


class NamedOpenAIEmbeddings(NamedEmbedding, OpenAIEmbeddings):
    @property
    def name(self) -> str:
        return "openai/" + self.model


class NamedHuggingFaceEmbeddings(NamedEmbedding, HuggingFaceEmbeddings):
    @property
    def name(self) -> str:
        return self.model_name


@cache
def get_sentence_embeddings(
    model_name: str = settings["global"]["embedding"]["model"],
) -> NamedEmbedding:
    if model_name.startswith("text-embedding-3"):
        return NamedOpenAIEmbeddings(
            model=model_name,
        )
    else:
        return NamedHuggingFaceEmbeddings(
            model_name=model_name,
            model_kwargs={"device": "cpu"},
        )
