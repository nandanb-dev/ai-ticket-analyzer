import io


def extract_text(content: bytes, filename: str) -> str:
    name = filename.lower()

    if name.endswith(".pdf"):
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(content))
        return "\n".join(p.extract_text() or "" for p in reader.pages)

    if name.endswith(".docx"):
        from docx import Document
        doc = Document(io.BytesIO(content))  # no temp file needed
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())

    # .txt / .md — plain text
    return content.decode("utf-8", errors="ignore")
