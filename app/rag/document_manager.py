import logging
import sqlite3
from dataclasses import dataclass, field
from functools import cache
from typing import List, Optional

from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_mistralai import ChatMistralAI
from pydantic import BaseModel

from ..llm.ratelimit import rate_limited_call
from ..rag.html_processor import get_chapters


class Summary(BaseModel):
    title: str
    summary: str
    tags: str


def get_model(model: str, max_tokens: Optional[int] = None):
    return ChatMistralAI(model_name=model, temperature=0, max_tokens=max_tokens)


@cache
def get_summary_chain(model: str = "mistral-small"):
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
    llm = get_model(model, 500)

    prompt = ChatPromptTemplate.from_template(template)

    return prompt | llm.with_structured_output(Summary, method="json_mode")


@cache
def get_simplifier_chain(model: str = "mistral-medium"):
    system = """
You are a content post-processor for a RAG system, removing errors introduced by web scraping.
For example, perform the following operations:
- Convert tables into lists while keeping all information
- Remove web scraping artifacts like links, image tags, incomplete lines, formatting, app.
- Remove fragments like "Jump to navigation", "From Minecraft Wiki", or headers commonly used in wikis app.
Do not strip information, only reformat and compact.
Output valid markdown!
Only respond with the markdown reformatted content, do not prepend or append anything.

{content}
    """.strip()

    llm = get_model(model, 4096)

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

    return prompt | llm | postprocess


CONTEXT_SIZE = 16384


@cache
def _get_connection():
    conn = sqlite3.connect("cache/documents.db", check_same_thread=False)
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
    def from_content(source: str, content: str, simplify: bool = True):
        row = InformationPage._fetch_document_by_source(source)

        if row:
            # Load doc from the cache
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
            )

            # Data has changed, request reprocessing
            if db_content != content:
                doc.content = content
                doc.simplified_content = ""
                doc.summary = ""
        else:
            # Create a new doc
            doc = InformationPage(source=source, content=content)

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

    def _simplify(self, chunksize: Optional[int] = None):
        logging.info(f"Simplifying {self.source} ({len(self.content)} characters)")

        if chunksize is None:
            chunksize = CONTEXT_SIZE // 2

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
            chunk = rate_limited_call(get_simplifier_chain(), {"content": content})
            simplified_chunks.append(chunk)
            factor = int(len(chunk) / len(content) * 100)
            logging.info(
                f"  Reduced size of chunk {i + 1} of {len(merged_chapters)} by {100 - factor}% to {len(chunk)} characters."
            )

        self.simplified_content = "\n".join(simplified_chunks)

    def _summarize(self, max_size: int = 9_000):
        assert self.simplified

        # And summarize it
        logging.info(f"Summarizing {self.source}")

        summary: Summary = rate_limited_call(
            get_summary_chain(), {"content": self.simplified[:max_size]}
        )

        self.title = summary.title
        self.summary = summary.summary
        self.tags = clean_tags(summary.tags.split(","))


class DocumentManager:
    def get_documents(self) -> List[InformationPage]:
        raise NotImplementedError
