"""
Excepciones de dominio y negocio para el microservicio persistence.
Única fuente de verdad de excepciones en todo el sistema.
"""


class DomainError(Exception):
    """Excepción base para todos los errores de dominio y negocio."""

    pass


class DocumentNotFoundError(DomainError):
    """Lanzada cuando un documento no existe por su ID o checksum."""

    def __init__(self, document_id: str):
        self.document_id = document_id
        super().__init__(f"Document with id '{document_id}' was not found.")


class DocumentAlreadyExistsError(DomainError):
    """Lanzada cuando se intenta crear un documento con un checksum que ya existe."""

    def __init__(self, checksum: str, existing_id: str):
        self.checksum = checksum
        self.existing_id = existing_id
        super().__init__(
            f"Document with checksum '{checksum}' already exists with id '{existing_id}'."
        )


class PersistenceInfrastructureError(DomainError):
    """Lanzada cuando ocurre una falla no recuperable en el motor de persistencia."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(f"Persistence infrastructure failure: {message}")


class DocumentTooLargeError(DomainError):
    """Lanzada cuando un documento supera el límite BSON de 16 MB de MongoDB."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(f"Document too large: {message}")
