import pytest
from app.infrastructure.repositories.memory import InMemoryDocumentRepository
from tests.contract.test_repository_contract import BaseDocumentRepositoryContractTest


class TestInMemoryDocumentRepository(BaseDocumentRepositoryContractTest):
    """Ejecución de la suite de contrato contra InMemoryDocumentRepository."""

    @pytest.fixture
    def memory_repo(self) -> InMemoryDocumentRepository:
        return InMemoryDocumentRepository()

    async def get_repository(self) -> InMemoryDocumentRepository:
        return InMemoryDocumentRepository()
