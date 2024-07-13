from typing import Optional

from langchain.embeddings import CacheBackedEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_core.runnables import Runnable, RunnableConfig
from langsmith import traceable

from common.langchain.lru_in_memory_store import LRUInMemoryStore
from common.shared_models import get_sentence_embeddings, ADDITIONAL_QUERY_PROMPTS


def split_text(text: str, max_length: int) -> list[Document]:
    docs: list[Document] = []
    buffer = ""
    for line in text.split("\n"):
        if len(buffer) > 0 and len(buffer) + len(line) > max_length:
            docs.append(Document.from_data(buffer))
            buffer = ""
        buffer += line + "\n"
    if len(buffer) > 0:
        docs.append(Document.from_data(buffer))
    return docs


def split_by_indices(
    objects: list[any], indices: list[any]
) -> tuple[list[any], list[any]]:
    indices = set(indices)
    included = [objects[i] for i in indices]
    excluded = [obj for i, obj in enumerate(objects) if i not in indices]
    return included, excluded


class VectorCompressor(Runnable):
    """
    A tool to compress a large string of text using a vector store and query.
    """

    def __init__(self, document_size: int = 300, static_docs: list[int] = None):
        """
        :param document_size: The size of each document to split the input into.
        :param static_docs: A list of indices of documents to keep static, by default the first and last doc.
        """
        if static_docs is None:
            static_docs = [0, -1]

        self.document_size = document_size
        self.static_doc_indices = static_docs

        self.embedding = get_sentence_embeddings()
        self.cached_embedding = CacheBackedEmbeddings.from_bytes_store(
            self.embedding,
            LRUInMemoryStore(4096),
            namespace=self.embedding.name,
        )

    @traceable(run_type="tool", name="Compress")
    def invoke(self, input_dict: dict, config: Optional[RunnableConfig] = None) -> str:
        assert isinstance(input_dict, dict), "Input must be a dictionary."
        assert "input" in input_dict, "Input not found in input dict."
        assert "query" in input_dict, "Query not found in input dict."
        assert "k" in input_dict, "K not found in input dict."

        # Skip small context
        if len(input_dict["input"]) < self.document_size * input_dict["k"]:
            return input_dict["input"]

        # Construct a document store
        docs = split_text(input_dict["input"], self.document_size)
        static_docs, docs = split_by_indices(docs, self.static_doc_indices)
        db = FAISS.from_documents(docs, self.cached_embedding)

        # Retrieve the top k documents
        retrieved_docs = static_docs + db.max_marginal_relevance_search(
            query=ADDITIONAL_QUERY_PROMPTS.get(self.embedding.name, "")
            + input_dict["query"],
            k=input_dict["k"],
            fetch_k=input_dict["k"] * 5,
        )

        return "\n".join([doc.page_content for doc in retrieved_docs])
