from functools import cache
from typing import Optional

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnableConfig
from langchain_groq import ChatGroq
from langsmith import traceable

compression_system_prompt = """
Given a document retrieved from a RAG system, extract the relevant parts of that document given that query.
If nothing is relevant, return a single asterisks. Only return information relevant to the query.
Only answer with the extracted information, do not prepend or append any additional text or provide reasoning.

Document:
{document}

Query:
{query}

Extracted Information:
""".strip()


@cache
def _get_compression_chain(model: str):
    return (
        ChatPromptTemplate.from_template(compression_system_prompt)
        | ChatGroq(model=model, temperature=0, max_tokens=300)
        | (lambda x: x.content)
    )


class InformationExtractor(Runnable):
    """
    Given a document and query, retrieve the relevant parts of the document.
    """

    def __init__(self, model: str = "llama-3.3-70b-versatile"):
        self.chain = _get_compression_chain(model)

    @traceable(run_type="tool", name="Information Extractor")
    def invoke(self, input_dict: dict, config: Optional[RunnableConfig] = None) -> str:
        assert isinstance(input_dict, dict), "Input must be a dictionary."
        assert "query" in input_dict, "Query is required"
        assert "document" in input_dict, "Document is required"
        return self.chain.invoke(input_dict)
