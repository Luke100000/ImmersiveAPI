import base64
import hashlib
import os
import secrets
from typing import List

from dotenv import load_dotenv
from github import Github, Auth
from github.Issue import Issue
from github.Repository import Repository
from pydantic import BaseModel

from main import Configurator

load_dotenv()


def generate_random_base64(length):
    random_bytes = secrets.token_bytes(length)
    return base64.b64encode(random_bytes).decode("utf-8")


def index_issues(repo: Repository):
    issues = {}
    for issue in repo.get_issues(state="all"):
        issues[get_issue_hash(issue.body)] = issue
    return issues


def get_issue_hash(body: str):
    return hashlib.sha256(body.encode()).hexdigest()


def get_issue(
    repo: Repository, issues: dict[str, Issue], stacktrace: str, project: str
):
    body = f"```\n{stacktrace}\n```"
    h = hashlib.sha256(body.encode()).hexdigest()
    if h in issues:
        return issues[h]
    else:
        issue = repo.create_issue(
            title=stacktrace.split("\n")[0][:128],
            body=body,
            labels=[project],
        )
        issues[get_issue_hash(issue.body)] = issue
        return issue


class IssueFile(BaseModel):
    name: str
    content: str


class Issue(BaseModel):
    project: str
    version: str
    stacktrace: str
    meta: str
    files: List[IssueFile]


def init(configurator: Configurator):
    configurator.register("Error", "Error reporting and artifact uploading.")

    # The issues index is not thread-safe
    configurator.assert_single_process()

    auth = Auth.Token(os.getenv("GITHUB_TOKEN"))
    g = Github(auth=auth)

    repo_id = os.getenv("GITHUB_REPO")
    branch = "issues"

    repo = g.get_repo(repo_id)
    issues = index_issues(repo)

    @configurator.post("/v1/error")
    def post_issue(body: Issue):
        # Create issue
        issue = get_issue(repo, issues, body.stacktrace, body.project)

        # Only upload limited number of artifacts
        if issue.comments > 16:
            return

        # Create comment with artifacts
        comment_id = generate_random_base64(16)
        comment = [f"`{body.project}` - `{body.version}`", "\n"]

        # Optional meta
        if body.meta:
            comment.append(body.meta)
            comment.append("\n")

        # Upload artifacts
        for file in body.files:
            path = f"artifacts/{issue.id}/{comment_id}/{file.name}"

            repo.create_file(
                path,
                f"Uploaded artifact",
                base64.b64decode(file.content),
                branch=branch,
            )

            blob = f"https://github.com/{repo_id}/blob/{branch}/{path}"
            comment.append(f"* [{file.name}]({blob})")

        # Create comment
        issue.create_comment("\n".join(comment))
