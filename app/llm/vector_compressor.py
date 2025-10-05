from typing import Optional

from langchain.embeddings import CacheBackedEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_core.runnables import Runnable, RunnableConfig

from ..llm.lru_in_memory_store import LRUInMemoryStore
from ..shared_models import ADDITIONAL_QUERY_PROMPTS, get_sentence_embeddings


def recursive_split(text: str, max_length: int, separators: list[str]) -> list[str]:
    texts = [text]
    for seperator in separators:
        new_texts = []
        for text in texts:
            if len(text) > max_length:
                splits = text.split(seperator)
                for s in splits[:-1]:
                    new_texts.append(s + seperator)
                new_texts.append(splits[-1])
            else:
                new_texts.append(text)
        texts = new_texts
    return texts


def split_text(text: str, max_length: int) -> list[Document]:
    docs: list[Document] = []
    buffer = ""
    for fragment in recursive_split(
        text, max_length // 2, ["\n", ".", "!", "?", " ", ""]
    ):
        if len(buffer) > 0 and len(buffer) + len(fragment) > max_length:
            docs.append(Document(page_content=buffer))
            buffer = ""
        buffer += fragment
    if len(buffer) > 0:
        docs[-1].page_content += buffer
    return docs


def split_by_indices(objects: list, indices: list) -> tuple[list, list]:
    indices = set([len(objects) + i if i < 0 else i for i in indices])
    included = [objects[i] for i in indices if 0 <= i < len(objects)]
    excluded = [obj for i, obj in enumerate(objects) if i not in indices]
    return included, excluded


class VectorCompressor(Runnable):
    """
    A tool to compress a large string of text using a vector store and query.
    """

    def __init__(self, document_size: int = 400, static_docs: list[int] = None):
        """
        :param document_size: The size of each document to split the input into.
        :param static_docs: A list of indices of documents to keep static, by default the first and last doc.
        """
        if static_docs is None:
            static_docs = [-1, 0]

        self.document_size = document_size
        self.static_doc_indices = static_docs

        self.embedding = get_sentence_embeddings()
        self.cached_embedding = CacheBackedEmbeddings.from_bytes_store(
            self.embedding,
            LRUInMemoryStore(4096),
            namespace=self.embedding.name,
        )

    def invoke(
        self, input_dict: dict, config: Optional[RunnableConfig] = None, **kwargs
    ) -> str:
        assert isinstance(input_dict, dict), "Input must be a dictionary."
        assert "input" in input_dict, "Input not found in input dict."
        assert "query" in input_dict, "Query not found in input dict."
        assert "k" in input_dict, "K not found in input dict."

        # Skip small context
        if len(input_dict["input"]) < self.document_size * (
            input_dict["k"] + len(self.static_doc_indices)
        ):
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
            fetch_k=input_dict["k"] * 4,
        )

        return "\n".join([doc.page_content for doc in retrieved_docs])
