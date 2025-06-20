from typing import Optional

import faiss
from langchain.embeddings import CacheBackedEmbeddings
from langchain.storage import LocalFileStore
from langchain_community.docstore import InMemoryDocstore
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_core.runnables import Runnable, RunnableConfig
from langchain_text_splitters import (
    RecursiveCharacterTextSplitter,
)

from common.rag.document_manager import InformationPage
from common.shared_models import get_sentence_embeddings, ADDITIONAL_QUERY_PROMPTS


class GlossaryManager(Runnable):
    """
    Maintains a searchable database of documents.
    """

    def __init__(self):
        self.embedding = get_sentence_embeddings()
        self.cached_embedding = CacheBackedEmbeddings.from_bytes_store(
            self.embedding,
            LocalFileStore("cache/embeddings"),
            namespace=self.embedding.name,
        )

        index = faiss.IndexFlatL2(len(self.cached_embedding.embed_query("hello world")))
        self.db = FAISS(
            embedding_function=self.cached_embedding,
            index=index,
            docstore=InMemoryDocstore(),
            index_to_docstore_id={},
        )
        self.text_splitter = RecursiveCharacterTextSplitter(
            separators=["\n\n", "\n", ".", " ", ""], chunk_size=1000, chunk_overlap=100
        )

    def add_documents(self, tag: str, documents: list[InformationPage]):
        docs = [
            Document(
                id=doc.source,
                page_content=doc.simplified,
                metadata={
                    "tag": tag,
                    "source": doc.source,
                    "title": doc.title,
                    "summary": doc.summary,
                },
            )
            for doc in documents
        ]

        split_docs = self.text_splitter.split_documents(docs)

        self.db.add_documents(split_docs)

    def invoke(self, input_dict: dict, config: Optional[RunnableConfig] = None) -> str:
        assert "query" in input_dict, "Query is required"

        # Construct filter expression
        filter_expression = None
        if "filter" in input_dict:
            if len(input_dict["filter"]) == 1:
                filter_expression = {"tag": input_dict["filter"][0]}
            else:
                filter_expression = {
                    "$or": [{"tag": value} for value in input_dict["filter"]]
                }

        # Search
        results = self.db.max_marginal_relevance_search(
            query=ADDITIONAL_QUERY_PROMPTS.get(self.embedding.name, "")
            + input_dict["query"],
            k=input_dict.get("k", 4),
            fetch_k=input_dict.get("k", 4) * 5,
            filter=filter_expression,
            lambda_mult=input_dict.get("lambda_mult", 0.5),
        )

        # List all titles first to merge summaries
        titles = []
        summaries = []
        sources = []
        for result in results:
            if result.metadata["title"] not in titles:
                titles.append(result.metadata["title"])
                summaries.append(result.metadata["summary"])
                sources.append(result.metadata["source"])

        # Stringify results
        data = []
        for title, summary, source in zip(titles, summaries, sources):
            data.append("# " + title)
            data.append("*" + summary + "*")
            data.append("source: " + source)
            for result in results:
                if result.metadata["title"] == title:
                    data.append(result.page_content)
            data.append("")
        return "\n".join(data).strip()
