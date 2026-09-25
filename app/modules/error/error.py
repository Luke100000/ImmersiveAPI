import base64
import binascii
import hashlib
import hmac
import ipaddress
import os
import re
import secrets
import threading

from dotenv import load_dotenv
from fastapi import HTTPException, Request
from github import Auth, Github
from github.Issue import Issue as GithubIssue
from github.Repository import Repository
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pyrate_limiter import Duration, Limiter, Rate

from app.configurator import Configurator

load_dotenv()


MIB = 1024 * 1024

MAX_HTTP_BODY_BYTES = 6 * MIB
MAX_FILES = 4
MAX_FILE_BYTES = 1 * MIB
MAX_TOTAL_FILE_BYTES = 4 * MIB
MAX_STACKTRACE_LENGTH = 64 * 1024
MAX_META_LENGTH = 16 * 1024
MAX_ENCODED_FILE_LENGTH = 4 * ((MAX_FILE_BYTES + 2) // 3)
MAX_REPORTS_PER_ISSUE = 16


def get_issue_hash(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def build_issue_body(stacktrace: str) -> str:
    return f"```\n{stacktrace}\n```"


def get_stacktrace_fingerprint(stacktrace: str) -> str:
    return get_issue_hash(build_issue_body(stacktrace))


def index_issues(repo: Repository) -> dict[str, GithubIssue]:
    issues = {}

    for issue in repo.get_issues(state="all"):
        if issue.body:
            issues[get_issue_hash(issue.body)] = issue

    return issues


def normalize_source_address(address: str) -> str:
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError:
        return address

    if isinstance(parsed, ipaddress.IPv6Address):
        return str(ipaddress.ip_network(f"{parsed}/64", strict=False))

    return str(parsed)


def make_source_key(secret: bytes, address: str) -> str:
    return hmac.new(
        secret,
        normalize_source_address(address).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def neutralize_mentions(value: str) -> str:
    return value.replace("@", "@\u200b")


class IssueFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=96)
    content: str = Field(min_length=1, max_length=MAX_ENCODED_FILE_LENGTH)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9._-]+", value):
            raise ValueError("invalid filename")

        if value in {".", ".."}:
            raise ValueError("invalid filename")

        return value

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        try:
            decoded = base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("invalid base64") from exc

        if len(decoded) > MAX_FILE_BYTES:
            raise ValueError("file exceeds 1 MiB")

        return value


class ErrorSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project: str = Field(min_length=1, max_length=64)
    version: str = Field(min_length=1, max_length=128)
    stacktrace: str = Field(min_length=1, max_length=MAX_STACKTRACE_LENGTH)
    meta: str = Field(default="", max_length=MAX_META_LENGTH)
    files: list[IssueFile] = Field(default_factory=list, max_length=MAX_FILES)

    @field_validator("project")
    @classmethod
    def validate_project(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._ -]{0,63}", value):
            raise ValueError("invalid project")

        return value

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+ -]{0,127}", value):
            raise ValueError("invalid version")

        return value

    @model_validator(mode="after")
    def validate_files(self):
        if len({file.name for file in self.files}) != len(self.files):
            raise ValueError("duplicate filenames")

        total_size = sum(
            len(base64.b64decode(file.content, validate=True)) for file in self.files
        )

        if total_size > MAX_TOTAL_FILE_BYTES:
            raise ValueError("total artifact size exceeds 4 MiB")

        return self


def init(configurator: Configurator):
    configurator.register(
        "Error",
        "Error reporting and artifact uploading.",
    )

    gh_token = os.getenv("GITHUB_TOKEN", "")
    if not gh_token:
        logger.warning("GITHUB_TOKEN is not set")
        return

    repo_id = os.getenv("GITHUB_REPO", "")
    if not repo_id:
        logger.warning("GITHUB_REPO is not set")
        return

    github = Github(auth=Auth.Token(gh_token))
    repo = github.get_repo(repo_id)
    branch = "issues"

    issues = index_issues(repo)

    issue_lock = threading.Lock()
    report_count_lock = threading.Lock()

    report_counts = {
        fingerprint: issue.comments for fingerprint, issue in issues.items()
    }

    source_key_secret = secrets.token_bytes(32)
    source_limiter = Limiter([Rate(5, Duration.SECOND * 10), Rate(10, Duration.MINUTE)])
    fingerprint_limiter = Limiter(Rate(5, Duration.MINUTE))
    new_issue_limiter = Limiter([Rate(10, Duration.MINUTE), Rate(100, Duration.HOUR)])

    github_write_limiter = Limiter(
        [Rate(60, Duration.MINUTE), Rate(300, Duration.HOUR)]
    )

    def rate_limit(
        limiter: Limiter,
        key: str,
        *,
        weight: int = 1,
    ) -> None:
        if not limiter.try_acquire(key, weight=weight):
            raise HTTPException(status_code=429, detail="Too many error reports")

    def reserve_report(fingerprint: str) -> bool:
        with report_count_lock:
            count = report_counts.get(fingerprint, 0)

            if count >= MAX_REPORTS_PER_ISSUE:
                return False

            report_counts[fingerprint] = count + 1
            return True

    def release_report(fingerprint: str) -> None:
        with report_count_lock:
            count = report_counts.get(fingerprint, 0)

            if count <= 1:
                report_counts[fingerprint] = 0
            else:
                report_counts[fingerprint] = count - 1

    @configurator.post("/v1/error")
    def post_issue(
        request: Request,
        body: ErrorSubmission,
    ):
        content_length = request.headers.get("content-length")

        if content_length is not None:
            try:
                size = int(content_length)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid Content-Length")

            if size > MAX_HTTP_BODY_BYTES:
                raise HTTPException(status_code=413, detail="Request body too large")

        source_address = (
            request.client.host if request.client is not None else "unknown"
        )

        source_key = make_source_key(
            source_key_secret,
            source_address,
        )

        rate_limit(
            source_limiter,
            source_key,
        )

        fingerprint = get_stacktrace_fingerprint(body.stacktrace)

        rate_limit(
            fingerprint_limiter,
            fingerprint,
        )

        if not reserve_report(fingerprint):
            raise HTTPException(
                status_code=429, detail="Too many reports for this error"
            )

        reserved_report = True

        try:
            with issue_lock:
                issue = issues.get(fingerprint)
                new_issue = issue is None

                if new_issue:
                    rate_limit(new_issue_limiter, "global")

            github_writes = len(body.files) + 1 + int(new_issue)

            rate_limit(github_write_limiter, "global", weight=github_writes)

            if issue is None:
                with issue_lock:
                    issue = issues.get(fingerprint)

                    if issue is None:
                        issue_body = build_issue_body(body.stacktrace)
                        first_line = body.stacktrace.split("\n", 1)[0].strip()

                        issue = repo.create_issue(
                            title=(first_line or "Error report")[:128],
                            body=issue_body,
                            labels=[body.project],
                        )

                        issues[fingerprint] = issue

            comment_id = secrets.token_hex(16)

            comment = [f"`{body.project}` - `{body.version}`", ""]

            if body.meta:
                comment.extend([neutralize_mentions(body.meta), ""])

            for file in body.files:
                content = base64.b64decode(
                    file.content,
                    validate=True,
                )

                stored_name = f"{secrets.token_hex(16)}-{file.name}"

                path = f"artifacts/{issue.id}/{comment_id}/{stored_name}"

                repo.create_file(
                    path,
                    "Uploaded artifact",
                    content,
                    branch=branch,
                )

                blob = f"https://github.com/{repo_id}/blob/{branch}/{path}"

                comment.append(f"* [{file.name}]({blob})")

            issue.create_comment("\n".join(comment))
            reserved_report = False

        finally:
            if reserved_report:
                release_report(fingerprint)
