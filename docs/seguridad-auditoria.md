# Auditoría de Seguridad, Contenedor y Dependencias (`persistence`)

Política automatizada de escaneo de vulnerabilidades, generación de SBOM, higiene de secretos y ejecución local para **Persistence** (Issue `#22`).

## 1. Controles en CI (`.github/workflows/security-audit.yml`)
- **`python-dependency-audit`:** valida `uv lock --check`, ejecuta `pip-audit --strict` sobre dependencias de producción (`uv export --frozen --no-dev`) y publica el SBOM CycloneDX 1.5 (`sbom-python-cyclonedx.json`).
- **`container-image-grype-scan`:** construye `Dockerfile` y ejecuta Anchore Grype con `.grype.yaml` (`severity-cutoff: high`, `fail-build: true`), exportando reportes **SARIF** y **JSON** como artefactos.
- **`secret-hygiene-scan`:** ejecuta `gitleaks` sobre el repositorio para detectar credenciales o secretos filtrados.

## 2. Política de Severidad y Excepciones (`.grype.yaml`)
- **Bloqueante en CI:** `High` y `Critical` fallan el pipeline.
- **Excepciones documentadas:** toda excepción requiere CVE exacto, paquete, justificación técnica y fecha de expiración (`YYYY-MM-DD`).

## 3. Higiene de Secretos
- `.dockerignore` excluye `.env`, `.git`, `.venv`, `tests/` y `docs/`; el contenedor corre como usuario no-root `appuser` (`UID 10001`).
- `app/redaction.py` y `app/request_logging.py` redactan cabeceras sensibles y credenciales en logs y `/trace`.
```

## 5. Remediaciones Aplicadas (Issue #22)
- **dnspython:** 2.9.0 -> 2.9.2 (CVE-2026-128089).
- **opentelemetry-api:** 1.45.1 -> 1.45.2 (CVE-2026-126360).
- **Imagen base (python:3.13-slim):** parcheo de paquetes Debian mediante apt-get upgrade en Dockerfile y excepciones temporales (expiracion 2027-03-01) en .grype.yaml para 6 CVEs Medium/Low del binario CPython 3.13.18.
