import logging
import sqlite3
import time
from dataclasses import dataclass, field
from enum import Enum
from functools import cache
from typing import List

from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from common.rag.html_processor import get_chapters


class Summary(BaseModel):
    title: str
    summary: str
    tags: str


def get_model(model: str, max_tokens: int = None):
    if model == "gpt-3.5-turbo":
        return ChatOpenAI(model=model, temperature=0, max_tokens=max_tokens)
    return ChatGroq(model=model, temperature=0, max_tokens=max_tokens)


@cache
def get_summary_chain(model: str):
    template = """
You are a summarizer for a RAG system, summarizing the content of a page.
Return a json dictionary containing the following fields:
- title: The name of this page usually represented by the very first heading, not longer than 2-4 words.
- summary: One or two sentences summarizing the content of the page.
- tags: Comma separated list of five tags that describe the content of the page. Try to remain general.

For example:
{{
    "title": "Apple Stew",
    "summary": "Apple stew is a dish made by cooking apples with sugar and cinnamon.",
    "tags": "food, recipe, dessert, apple, stew"
}}

Do not return an empty result!

Start of the content:
{content}
""".strip()
    model = get_model(model, 500)

    prompt = ChatPromptTemplate.from_template(template)

    return prompt | model.with_structured_output(Summary, method="json_mode")


# todo make this modifying, e.g. java files needs a different treatment than html


@cache
def get_simplifier_chain(model: str):
    system = """
You are a content post-processor for a RAG system, removing errors introduced by web scraping.
For example, perform the following operations:
- Convert tables into lists while keeping all information
- Remove web scraping artifacts like links, image tags, incomplete lines, formatting, ...
- Remove fragments like "Jump to navigation", "From Minecraft Wiki", or headers commonly used in wikis ...
Do not strip information, only reformat and compact.
Output valid markdown!
Only respond with the markdown reformatted content, do not prepend or append anything.

{content}
    """.strip()

    model = get_model(model, 4096)

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system),
            (
                "human",
                "Simplify:\n```md\n{content}\n```\nOnly respond with the markdown reformatted content, do not prepend or append anything.",
            ),
        ]
    )

    def postprocess(content: AIMessage):
        return content.content

    return prompt | model | postprocess


RATE_LIMITS = {
    "llama3-8b-8192": 30_000,
    "llama3-70b-8192": 6_000,
    "gpt-3.5-turbo": -1,
}

RATE_LIMIT_REQUESTS = {
    "llama3-8b-8192": 30,
    "llama3-70b-8192": 30,
    "gpt-3.5-turbo": -1,
}

CONTEXT_SIZES = {
    "llama3-8b-8192": 8192,
    "llama3-70b-8192": 8192,
    "gpt-3.5-turbo": 16384,
}

RATE_LIMIT_UTILIZATION = 0.5


def _rate_limit(
    content: str,
    tpm: int = -1,
    rpm: int = -1,
    utilization: float = RATE_LIMIT_UTILIZATION,
):
    if tpm > 0:
        t = (len(content) + 200) / 4 / tpm * 60 / utilization
    else:
        t = 0

    if rpm > 0:
        t = max(t, 60 / rpm / utilization)

    if t > 0:
        logging.info(f"Sleeping for {t} seconds")
        time.sleep(t)


@cache
def _get_connection():
    conn = sqlite3.connect("cache/documents.db")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS documents (
            source TEXT PRIMARY KEY,
            title TEXT,
            summary TEXT,
            tags TEXT,
            content TEXT,
            simplified_content TEXT
        )
    """
    )
    conn.commit()
    return conn


class QualityPreset(Enum):
    DEFAULT = dict(
        simplification_model="llama3-8b-8192", summarization_model="llama3-70b-8192"
    )
    HIGH = dict(
        simplification_model="llama3-70b-8192", summarization_model="llama3-70b-8192"
    )
    LOW = dict(
        simplification_model="llama3-8b-8192", summarization_model="llama3-8b-8192"
    )
    FAST = dict(
        simplification_model="gpt-3.5-turbo", summarization_model="gpt-3.5-turbo"
    )

    @property
    def simplification_model(self):
        return self.value["simplification_model"]

    @property
    def summarization_model(self):
        return self.value["summarization_model"]


def clean_tags(tags: list[str]):
    return [t.lower().strip() for t in tags]


@dataclass
class InformationPage:
    source: str = ""
    title: str = ""
    summary: str = ""
    tags: List[str] = field(default_factory=list)
    content: str = ""
    simplified_content: str = ""

    quality: QualityPreset = QualityPreset.DEFAULT

    @staticmethod
    def _fetch_document_by_source(source: str):
        cursor = _get_connection().execute(
            "SELECT * FROM documents WHERE source = ?", (source,)
        )
        return cursor.fetchone()

    @staticmethod
    def _insert_or_update_document(
        source: str,
        title: str,
        summary: str,
        tags: List[str],
        content: str,
        simplified_content: str,
    ):
        _get_connection().execute(
            """
            INSERT INTO documents (source, title, summary, tags, content, simplified_content) 
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(source) DO UPDATE SET
            title=excluded.title,
            summary=excluded.summary,
            tags=excluded.tags,
            content=excluded.content,
            simplified_content=excluded.simplified_content
        """,
            (source, title, summary, ",".join(tags), content, simplified_content),
        )
        _get_connection().commit()

    @staticmethod
    def from_content(
        source: str,
        content: str,
        simplify: bool = True,
        quality: QualityPreset = QualityPreset.DEFAULT,
    ):
        row = InformationPage._fetch_document_by_source(source)

        if row:
            # Load doc from cache
            (
                db_source,
                db_title,
                db_summary,
                db_tags,
                db_content,
                db_simplified_content,
            ) = row
            tags = db_tags.split(",") if db_tags else []
            doc = InformationPage(
                source=db_source,
                title=db_title,
                summary=db_summary,
                tags=tags,
                content=db_content,
                simplified_content=db_simplified_content,
                quality=quality,
            )

            # Data has changed, request reprocessing
            if db_content != content:
                doc.content = content
                doc.simplified_content = ""
                doc.summary = ""
        else:
            # Create new doc
            doc = InformationPage(
                source=source,
                content=content,
                quality=quality,
            )

        # Update document
        if doc.populate(simplify):
            InformationPage._insert_or_update_document(
                doc.source,
                doc.title,
                doc.summary,
                doc.tags,
                doc.content,
                doc.simplified_content,
            )

        return doc

    @property
    def simplified(self) -> str:
        """
        :return: The simplified content if available, otherwise the original content.
        """
        return self.simplified_content if self.simplified_content else self.content

    def populate(self, simplify: bool = True) -> bool:
        changes = False
        if simplify and not self.simplified_content:
            self._simplify()
            changes = True

        if not self.summary:
            self._summarize()
            changes = True

        if len(self.content) > 100 and self.content == self.simplified_content:
            self.simplified_content = ""
            changes = True

        return changes

    def _simplify(self, chunksize: int = None):
        logging.info(f"Simplifying {self.source} ({len(self.content)} characters)")

        if chunksize is None:
            chunksize = CONTEXT_SIZES[self.quality.simplification_model] // 2

        # Batch chapters into chunks
        merged_chapters = []
        for chapter in get_chapters(self.content):
            if (
                not merged_chapters
                or len(merged_chapters[-1]) + len(chapter) > chunksize
            ):
                for i in range(0, len(chapter), chunksize):
                    merged_chapters.append(chapter[i : i + chunksize])
            else:
                merged_chapters[-1] += "\n" + chapter

        # Simplify the content
        simplified_chunks = []
        for i, content in enumerate(merged_chapters):
            chunk = get_simplifier_chain(self.quality.simplification_model).invoke(
                {"content": content}
            )
            simplified_chunks.append(chunk)
            factor = int(len(chunk) / len(content) * 100)
            logging.info(
                f"  Reduced size of chunk {i + 1} of {len(merged_chapters)} by {100 - factor}% to {len(chunk)} characters."
            )

            # Sleep to stay below rate limit
            _rate_limit(
                content,
                RATE_LIMITS[self.quality.simplification_model],
                RATE_LIMIT_REQUESTS[self.quality.simplification_model],
            )

        self.simplified_content = "\n".join(simplified_chunks)

    def _summarize(self, max_size: int = 9_000):
        assert self.simplified

        # And summarize it
        logging.info(f"Summarizing {self.source}")
        # noinspection PyBroadException
        try:
            summary: Summary = get_summary_chain(
                self.quality.summarization_model
            ).invoke({"content": self.simplified[:max_size]})
        except Exception:
            logging.exception("Error summarizing content")
            summary: Summary = get_summary_chain("gpt-3.5-turbo").invoke(
                {"content": self.simplified[:max_size]}
            )

        self.title = summary.title
        self.summary = summary.summary
        self.tags = clean_tags(summary.tags.split(","))

        _rate_limit(
            self.simplified[:max_size],
            RATE_LIMITS[self.quality.summarization_model],
            RATE_LIMIT_REQUESTS[self.quality.summarization_model],
        )


class DocumentManager:
    def get_documents(self) -> List[InformationPage]:
        raise NotImplementedError
