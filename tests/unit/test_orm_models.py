from sqlalchemy import inspect
from app.infrastructure.database.models import DocumentORM, Base


def test_document_orm_table_definition():
    assert DocumentORM.__tablename__ == "documents"
    columns = {c.name: c for c in DocumentORM.__table__.columns}

    # Columnas esperadas
    assert "id" in columns
    assert "checksum_sha256" in columns
    assert "filename" in columns
    assert "extracted_text" in columns
    assert "page_count" in columns
    assert "file_size_bytes" in columns
    assert "metadata" in columns
    assert "created_at" in columns
    assert "updated_at" in columns

    # Restricciones
    assert columns["id"].primary_key is True
    assert columns["checksum_sha256"].unique is True
    assert columns["checksum_sha256"].nullable is False
    assert columns["filename"].nullable is False
    assert columns["extracted_text"].nullable is False
    assert columns["created_at"].nullable is False
    assert columns["updated_at"].nullable is False
