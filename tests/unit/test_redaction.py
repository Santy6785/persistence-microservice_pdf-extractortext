"""
Tests de la función de redacción pura (app/redaction.py).

N es la cantidad de caracteres (len del str), nunca de bytes.
La función no muta la entrada: devuelve una copia.
"""

from app.redaction import (
    non_json_body,
    redact_extracted_text,
    redact_headers,
)


def test_redact_top_level_extracted_text():
    body = {"extracted_text": "Texto sensible de 31 caracteres"}
    result = redact_extracted_text(body)
    assert result["extracted_text"] == "<redacted: 31 chars>"
    assert "Texto sensible" not in str(result)


def test_redact_nested_dict():
    body = {"document": {"extracted_text": "secreto anidado"}}
    result = redact_extracted_text(body)
    assert result["document"]["extracted_text"] == "<redacted: 15 chars>"


def test_redact_inside_list():
    body = {"pages": [{"extracted_text": "uno"}, {"extracted_text": "dos"}]}
    result = redact_extracted_text(body)
    assert result["pages"][0]["extracted_text"] == "<redacted: 3 chars>"
    assert result["pages"][1]["extracted_text"] == "<redacted: 3 chars>"


def test_redact_zero_character_string():
    body = {"extracted_text": ""}
    result = redact_extracted_text(body)
    assert result["extracted_text"] == "<redacted: 0 chars>"


def test_redact_without_key_preserves_rest():
    body = {"filename": "a.pdf", "page_count": 2, "metadata": {"k": "v"}}
    result = redact_extracted_text(body)
    assert result == {"filename": "a.pdf", "page_count": 2, "metadata": {"k": "v"}}


def test_redact_non_string_value():
    body = {"extracted_text": 12345}
    result = redact_extracted_text(body)
    assert result["extracted_text"] == "<redacted: non-string>"


def test_redact_does_not_mutate_input():
    original = {"extracted_text": "original", "other": {"x": 1}}
    snapshot = dict(original)
    redact_extracted_text(original)
    assert original == snapshot


def test_redact_non_dict_input_passthrough():
    assert redact_extracted_text("hola") == "hola"
    assert redact_extracted_text(42) == 42
    assert redact_extracted_text(None) is None


def test_redact_headers_authorization_and_cookie():
    headers = {
        "Authorization": "Bearer secreto",
        "Cookie": "session=abc123",
        "X-Custom": "ok",
    }
    result = redact_headers(headers)
    assert result["Authorization"] == "<redacted>"
    assert result["Cookie"] == "<redacted>"
    assert result["X-Custom"] == "ok"


def test_redact_headers_case_insensitive():
    headers = {"authorization": "x", "COOKIE": "y", "Content-Type": "json"}
    result = redact_headers(headers)
    assert result["authorization"] == "<redacted>"
    assert result["COOKIE"] == "<redacted>"
    assert result["Content-Type"] == "json"


def test_non_json_body_never_leaks_content():
    raw = b"\x00\x01\x02binary garbage"
    result = non_json_body(raw)
    assert result == "<non-json body: 17 bytes>"
    assert raw not in result.encode()


def test_non_json_body_empty():
    assert non_json_body(b"") == "<non-json body: 0 bytes>"
