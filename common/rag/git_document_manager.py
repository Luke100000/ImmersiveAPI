import glob
import hashlib
import os
from typing import List

from common.rag.document_manager import DocumentManager, InformationPage, QualityPreset


class GitDocumentManager(DocumentManager):
    def __init__(self, url: str, quality_preset: QualityPreset = QualityPreset.DEFAULT):
        identifier = hashlib.md5(url.encode()).hexdigest()

        # clone
        path = f"cache/repos/{identifier}"
        os.makedirs("cache/repos", exist_ok=True)
        os.system(f"git clone {url} {path}")
        os.system(f"cd {path} && git pull")

        self.documents = []
        for file in glob.glob(f"{path}/*.md"):
            filename = os.path.basename(file)
            if not filename.startswith("_") and not filename.startswith("."):
                with open(file, "r") as f:
                    try:
                        self.documents.append(
                            InformationPage.from_content(
                                f"{identifier}/{filename}",
                                f.read(),
                                simplify=False,
                                quality=quality_preset,
                            )
                        )
                    except Exception as e:
                        print(f"Error reading {filename}: {e}")

    def get_documents(self) -> List[InformationPage]:
        return self.documents
