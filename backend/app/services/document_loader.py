from pathlib import Path

import docx
from pypdf import PdfReader


class DocumentLoader:

    SUPPORTED_TYPES = {
        ".txt",
        ".pdf",
        ".docx",
    }

    def load(
        self,
        file_path: str,
    ) -> str:

        extension = Path(
            file_path
        ).suffix.lower()

        if extension not in self.SUPPORTED_TYPES:
            raise ValueError(
                f"Unsupported file type: {extension}"
            )

        if extension == ".txt":
            return self._load_txt(file_path)

        if extension == ".pdf":
            return self._load_pdf(file_path)

        if extension == ".docx":
            return self._load_docx(file_path)

        raise ValueError(
            "Unsupported document type."
        )

    def _load_txt(
        self,
        file_path: str,
    ) -> str:

        with open(
            file_path,
            "r",
            encoding="utf-8",
        ) as file:
            return file.read()

    def _load_pdf(
        self,
        file_path: str,
    ) -> str:

        reader = PdfReader(file_path)

        pages = []

        for page in reader.pages:

            text = page.extract_text()

            if text:
                pages.append(text)

        return "\n".join(pages)

    def _load_docx(
        self,
        file_path: str,
    ) -> str:

        document = docx.Document(file_path)

        paragraphs = [
            paragraph.text
            for paragraph in document.paragraphs
            if paragraph.text.strip()
        ]

        return "\n".join(paragraphs)