import io
import os
import tempfile

from fastapi import UploadFile


def extract_text(file: UploadFile) -> str:
    content = file.file.read()
    name = (file.filename or "").lower()

    if name.endswith(".pdf"):
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(content))
        return "\n".join(p.extract_text() or "" for p in reader.pages)

    if name.endswith(".docx"):
        from docx import Document
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        doc = Document(tmp_path)
        os.unlink(tmp_path)
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())

    # .txt / .md — plain text
    return content.decode("utf-8", errors="ignore")
