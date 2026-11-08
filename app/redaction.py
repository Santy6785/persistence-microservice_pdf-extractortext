"""
Funciones puras de redacción de datos sensibles.

No depende de FastAPI ni de ningún framework, para poder reutilizarse tanto
en el middleware de trazado como en los tests unitarios.

N es siempre la cantidad de caracteres (len del str), nunca la cantidad de
bytes. Ninguna de estas funciones muta la entrada: devuelven copias.
"""

from typing import Any

REDACTED_NON_STRING = "<redacted: non-string>"


def redact_extracted_text(value: Any) -> Any:
    """Redacta recursivamente la clave ``extracted_text`` de un objeto JSON-like.

    Cuando el valor de ``extracted_text`` es un string, se reemplaza por
    ``"<redacted: N chars>"`` donde N es la cantidad de caracteres del string
    original (``len``, no bytes). Cuando el valor no es un string, se reemplaza
    por ``"<redacted: non-string>"``. El resto de campos y niveles se conservan.

    Devuelve una copia profunda: la entrada nunca se muta.

    Args:
        value: objeto JSON-like (dict, lista o valor escalar).

    Returns:
        Copia con los valores de ``extracted_text`` redactados.
    """
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, val in value.items():
            if key == "extracted_text":
                if isinstance(val, str):
                    result[key] = f"<redacted: {len(val)} chars>"
                else:
                    result[key] = REDACTED_NON_STRING
            else:
                result[key] = redact_extracted_text(val)
        return result
    if isinstance(value, list):
        return [redact_extracted_text(item) for item in value]
    return value


def redact_headers(headers: dict[str, str]) -> dict[str, str]:
    """Devuelve una copia de las cabeceras redacting Authorization y Cookie.

    La detección de las cabeceras sensibles es insensible a mayúsculas.
    Los demás valores se conservan sin modificar.
    """
    sensitive = {"authorization", "cookie"}
    result: dict[str, str] = {}
    for key, val in headers.items():
        if key.lower() in sensitive:
            result[key] = "<redacted>"
        else:
            result[key] = val
    return result


def non_json_body(body: bytes) -> str:
    """Devuelve una descripción del cuerpo sin filtrar su contenido crudo.

    Se usa cuando el cuerpo no es JSON válido o está malformado. Nunca se
    devuelven los bytes originales, solo su longitud.
    """
    return f"<non-json body: {len(body)} bytes>"
