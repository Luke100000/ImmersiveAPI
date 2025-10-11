import glob
import hashlib
import os
from typing import List

from ..rag.document_manager import DocumentManager, InformationPage
from ..utils import get_cache_path


class GitDocumentManager(DocumentManager):
    def __init__(self, url: str):
        identifier = hashlib.md5(url.encode()).hexdigest()

        # clone
        path = get_cache_path(f"repos/{identifier}")
        path.parent.mkdir(parents=True, exist_ok=True)
        os.system(f"git clone {url} {path}")
        os.system(f"cd {path} && git pull")

        # reconstruct a human-readable base path
        base_path = url
        if base_path.endswith(".wiki.git"):
            base_path = base_path[:-9] + "/wiki"
        if base_path.endswith(".git"):
            base_path = base_path[:-4]

        self.documents = []
        for file in glob.glob(f"{path}/*.md"):
            filename = os.path.basename(file)
            if filename.endswith(".md"):
                filename = filename[:-3]
            if not filename.startswith("_") and not filename.startswith("."):
                with open(file, "r") as f:
                    try:
                        self.documents.append(
                            InformationPage.from_content(
                                f"{base_path}/{filename}", f.read(), simplify=False
                            )
                        )
                    except Exception as e:
                        print(f"Error reading {filename}: {e}")

    def get_documents(self) -> List[InformationPage]:
        return self.documents
