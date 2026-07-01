import csv
import hashlib
import io
import json
import os
import uuid
from pathlib import Path
from typing import Iterable
from uuid import UUID

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from services.shared.models import FileChunk, FileReference
from .config import settings


SUPPORTED_EXTENSIONS = {
    ".txt", ".md", ".json", ".csv", ".py", ".js", ".ts", ".tsx", ".html", ".css",
    ".pdf", ".docx", ".xlsx",
}


def estimate_tokens(text: str) -> int:
    try:
        import tiktoken

        encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(text or ""))
    except Exception:
        return max(1, len((text or "").split()))


def _storage_root() -> Path:
    root = Path(settings.FILE_STORAGE_LOCAL_DIR)
    if not root.is_absolute():
        root = Path(__file__).resolve().parents[3] / root
    root.mkdir(parents=True, exist_ok=True)
    return root


def _s3_client():
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT_URL,
        aws_access_key_id=settings.S3_ACCESS_KEY_ID,
        aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY,
        region_name=settings.S3_REGION,
    )


def storage_provider() -> str:
    if (
        settings.FILE_STORAGE_PROVIDER.lower() == "s3"
        and settings.S3_BUCKET
        and settings.S3_ACCESS_KEY_ID
        and settings.S3_SECRET_ACCESS_KEY
    ):
        return "s3"
    return "local"


def put_object(object_key: str, data: bytes, content_type: str | None) -> None:
    if storage_provider() == "s3":
        _s3_client().put_object(
            Bucket=settings.S3_BUCKET,
            Key=object_key,
            Body=data,
            ContentType=content_type or "application/octet-stream",
        )
        return

    path = _storage_root() / object_key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def get_object(object_key: str) -> bytes:
    if storage_provider() == "s3":
        response = _s3_client().get_object(Bucket=settings.S3_BUCKET, Key=object_key)
        return response["Body"].read()
    path = _storage_root() / object_key
    if not path.exists():
        raise HTTPException(status_code=404, detail="Stored object not found")
    return path.read_bytes()


def delete_object(object_key: str) -> None:
    if storage_provider() == "s3":
        _s3_client().delete_object(Bucket=settings.S3_BUCKET, Key=object_key)
        return
    path = _storage_root() / object_key
    if path.exists():
        path.unlink()


async def create_file_reference(
    db: Session,
    user_id: UUID,
    upload: UploadFile,
    owner_type: str = "chat",
    owner_id: UUID | None = None,
) -> FileReference:
    filename = Path(upload.filename or "upload").name
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {extension or 'unknown'}")

    data = await upload.read()
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File exceeds 25 MB limit")

    checksum = hashlib.sha256(data).hexdigest()
    object_key = f"users/{user_id}/files/{uuid.uuid4()}{extension}"
    put_object(object_key, data, upload.content_type)

    record = FileReference(
        user_id=user_id,
        owner_type=owner_type,
        owner_id=owner_id,
        storage_provider=storage_provider(),
        bucket=settings.S3_BUCKET,
        object_key=object_key,
        filename=filename,
        content_type=upload.content_type,
        size_bytes=len(data),
        checksum_sha256=checksum,
        status="active",
        metadata_json={"extension": extension},
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def _text_from_pdf(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    return "\n\n".join(page.extract_text() or "" for page in reader.pages)


def _text_from_docx(data: bytes) -> str:
    from docx import Document

    document = Document(io.BytesIO(data))
    return "\n".join(paragraph.text for paragraph in document.paragraphs)


def _text_from_xlsx(data: bytes) -> str:
    from openpyxl import load_workbook

    workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    rows: list[str] = []
    for sheet in workbook.worksheets:
        rows.append(f"# Sheet: {sheet.title}")
        for row in sheet.iter_rows(values_only=True):
            rows.append("\t".join("" if value is None else str(value) for value in row))
    return "\n".join(rows)


def extract_text_from_file(record: FileReference) -> str:
    data = get_object(record.object_key)
    extension = Path(record.filename).suffix.lower()
    if extension == ".pdf":
        return _text_from_pdf(data)
    if extension == ".docx":
        return _text_from_docx(data)
    if extension == ".xlsx":
        return _text_from_xlsx(data)
    if extension == ".csv":
        decoded = data.decode("utf-8", errors="ignore")
        reader = csv.reader(io.StringIO(decoded))
        return "\n".join("\t".join(row) for row in reader)
    if extension == ".json":
        decoded = data.decode("utf-8", errors="ignore")
        try:
            return json.dumps(json.loads(decoded), indent=2)
        except Exception:
            return decoded
    return data.decode("utf-8", errors="ignore")


def chunk_text(text: str, max_tokens: int = 700) -> Iterable[tuple[str, int]]:
    paragraphs = [part.strip() for part in (text or "").splitlines() if part.strip()]
    current: list[str] = []
    current_tokens = 0
    for paragraph in paragraphs:
        tokens = estimate_tokens(paragraph)
        if current and current_tokens + tokens > max_tokens:
            content = "\n".join(current)
            yield content, estimate_tokens(content)
            current = []
            current_tokens = 0
        current.append(paragraph)
        current_tokens += tokens
    if current:
        content = "\n".join(current)
        yield content, estimate_tokens(content)


def extract_file_to_chunks(db: Session, user_id: UUID, file_id: UUID) -> dict:
    record = db.query(FileReference).filter(
        FileReference.id == file_id,
        FileReference.user_id == user_id,
        FileReference.status == "active",
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="File not found")

    text = extract_text_from_file(record)
    db.query(FileChunk).filter(FileChunk.file_id == record.id, FileChunk.user_id == user_id).delete()
    chunks = []
    for index, (content, token_count) in enumerate(chunk_text(text)):
        chunks.append(FileChunk(
            file_id=record.id,
            user_id=user_id,
            chunk_index=index,
            content=content,
            token_count=token_count,
            metadata_json={"filename": record.filename},
        ))
    db.add_all(chunks)
    record.metadata_json = {**(record.metadata_json or {}), "extracted": True, "chunk_count": len(chunks)}
    db.commit()
    return {"file_id": str(record.id), "chunk_count": len(chunks), "token_count": sum(c.token_count or 0 for c in chunks)}


def file_context_for_prompt(db: Session, user_id: UUID, file_ids: list[str], query: str, limit: int = 8) -> str:
    if not file_ids:
        return ""
    parsed_ids = []
    for file_id in file_ids:
        try:
            parsed_ids.append(UUID(str(file_id)))
        except ValueError:
            continue
    if not parsed_ids:
        return ""

    query_terms = {term.lower() for term in (query or "").split() if len(term) > 2}
    chunks = db.query(FileChunk, FileReference.filename).join(
        FileReference, FileReference.id == FileChunk.file_id
    ).filter(
        FileChunk.user_id == user_id,
        FileChunk.file_id.in_(parsed_ids),
    ).all()

    ranked = []
    for chunk, filename in chunks:
        content_lower = chunk.content.lower()
        score = sum(1 for term in query_terms if term in content_lower)
        ranked.append((score, chunk, filename))
    ranked.sort(key=lambda item: (item[0], -(item[1].chunk_index or 0)), reverse=True)

    blocks = []
    for _, chunk, filename in ranked[:limit]:
        blocks.append(f"FILE: {filename}\nCHUNK: {chunk.chunk_index}\n{chunk.content}")
    return "\n\n---\n\n".join(blocks)


def get_file_text(db: Session, user_id: UUID, file_id: UUID) -> str:
    record = db.query(FileReference).filter(FileReference.id == file_id, FileReference.user_id == user_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="File not found")
    return extract_text_from_file(record)
