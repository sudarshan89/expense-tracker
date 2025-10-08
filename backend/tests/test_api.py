import pytest
from fastapi.testclient import TestClient

from local_main import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def auth_headers():
    """Mock auth headers for local testing."""
    return {}


class TestOwnerAPI:
    def test_create_owner(self, client, auth_headers, sample_owner_data):
        """Test creating owner via API."""
        response = client.post("/owners", json=sample_owner_data, headers=auth_headers)

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "TestOwner"
        assert data["card_name"] == "T Owner"

    def test_list_owners(self, client, auth_headers, sample_owner_data):
        """Test listing owners via API."""
        # Create owner first
        client.post("/owners", json=sample_owner_data, headers=auth_headers)

        # List owners
        response = client.get("/owners", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert any(owner["name"] == "TestOwner" for owner in data)


class TestAccountAPI:
    def test_create_account(
        self, client, auth_headers, sample_owner_data, sample_account_data
    ):
        """Test creating account via API."""
        # Create owner first
        client.post("/owners", json=sample_owner_data, headers=auth_headers)

        # Create account
        response = client.post(
            "/accounts", json=sample_account_data, headers=auth_headers
        )

        assert response.status_code == 201
        data = response.json()
        assert data["account_name"] == "Test Account"
        assert data["owner_name"] == "TestOwner"

    def test_list_accounts(
        self, client, auth_headers, sample_owner_data, sample_account_data
    ):
        """Test listing accounts via API."""
        # Setup
        client.post("/owners", json=sample_owner_data, headers=auth_headers)
        client.post("/accounts", json=sample_account_data, headers=auth_headers)

        # Test
        response = client.get("/accounts", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1


class TestCategoryAPI:
    def test_create_category(
        self,
        client,
        auth_headers,
        sample_owner_data,
        sample_account_data,
        sample_category_data,
    ):
        """Test creating category via API."""
        # Setup
        client.post("/owners", json=sample_owner_data, headers=auth_headers)
        client.post("/accounts", json=sample_account_data, headers=auth_headers)

        # Test
        response = client.post(
            "/categories", json=sample_category_data, headers=auth_headers
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "TestCategory"
        assert data["labels"] == ["test", "sample"]

    def test_list_categories(
        self,
        client,
        auth_headers,
        sample_owner_data,
        sample_account_data,
        sample_category_data,
    ):
        """Test listing categories via API."""
        # Setup
        client.post("/owners", json=sample_owner_data, headers=auth_headers)
        client.post("/accounts", json=sample_account_data, headers=auth_headers)
        client.post("/categories", json=sample_category_data, headers=auth_headers)

        # Test
        response = client.get("/categories", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1


class TestExpenseAPI:
    def test_create_expense(self, client, auth_headers):
        """Test creating expense via API."""
        expense_data = {
            "date": "2025-09-21T00:00:00",
            "description": "Test API Expense",
            "card_member": "Test User",
            "amount": "30.00",
            "category": "TestCategory",
        }

        response = client.post("/expenses", json=expense_data, headers=auth_headers)

        assert response.status_code == 201
        data = response.json()
        assert data["description"] == "Test API Expense"
        assert data["amount"] == "30.00"

    def test_list_expenses(self, client, auth_headers):
        """Test listing expenses via API."""
        # Create expense first
        expense_data = {
            "date": "2025-09-21T00:00:00",
            "description": "Test Expense",
            "card_member": "Test User",
            "amount": "25.50",
        }
        client.post("/expenses", json=expense_data, headers=auth_headers)

        # Test
        response = client.get("/expenses", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1


class TestExpenseAssignedCardMemberAPI:
    @pytest.fixture
    def setup_owners_and_categories(self, client, auth_headers):
        """Set up owners and categories for testing."""
        # Create owners
        client.post(
            "/owners", json={"name": "John", "card_name": "J Doe"}, headers=auth_headers
        )
        client.post(
            "/owners",
            json={"name": "Jane", "card_name": "J Smith"},
            headers=auth_headers,
        )

        # Create accounts
        client.post(
            "/accounts",
            json={
                "account_name": "Test Account",
                "bank_name": "Test Bank",
                "owner_name": "John",
                "card_member": "J Doe",
            },
            headers=auth_headers,
        )

        # Create categories
        client.post(
            "/categories",
            json={
                "name": "JohnSpend",
                "labels": ["test"],
                "account_id": "Test Account John",
                "card_name": "J Doe",
            },
            headers=auth_headers,
        )

    def test_update_assigned_card_member_success(
        self, client, auth_headers, setup_owners_and_categories
    ):
        """Test successful update of assigned card member."""
        # Create expense first
        expense_data = {
            "date": "2024-01-01T10:00:00",
            "description": "Test expense",
            "card_member": "J Doe",
            "amount": "10.00",
        }
        expense_response = client.post(
            "/expenses", json=expense_data, headers=auth_headers
        )
        expense_id = expense_response.json()["expense_id"]

        # Update assigned card member
        update_data = {"assigned_card_member": "J Smith"}
        response = client.patch(
            f"/expenses/{expense_id}/assigned-card-member",
            json=update_data,
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["assigned_card_member"] == "J Smith"

    def test_update_assigned_card_member_invalid_card_name(
        self, client, auth_headers, setup_owners_and_categories
    ):
        """Test update with invalid card name."""
        # Create expense first
        expense_data = {
            "date": "2024-01-01T10:00:00",
            "description": "Test expense",
            "card_member": "J Doe",
            "amount": "10.00",
        }
        expense_response = client.post(
            "/expenses", json=expense_data, headers=auth_headers
        )
        expense_id = expense_response.json()["expense_id"]

        # Try to update with invalid card member
        update_data = {"assigned_card_member": "Invalid Card Name"}
        response = client.patch(
            f"/expenses/{expense_id}/assigned-card-member",
            json=update_data,
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert "Invalid card_member" in response.json()["detail"]

    def test_update_assigned_card_member_expense_not_found(self, client, auth_headers):
        """Test update for non-existent expense."""
        update_data = {"assigned_card_member": "J Doe"}
        response = client.patch(
            "/expenses/non-existent-id/assigned-card-member",
            json=update_data,
            headers=auth_headers,
        )

        assert response.status_code == 404

    def test_category_update_also_updates_assigned_card_member(
        self, client, auth_headers, setup_owners_and_categories
    ):
        """Test that updating category also updates assigned_card_member."""
        # Create expense first
        expense_data = {
            "date": "2024-01-01T10:00:00",
            "description": "Test expense",
            "card_member": "J Doe",
            "amount": "10.00",
        }
        expense_response = client.post(
            "/expenses", json=expense_data, headers=auth_headers
        )
        expense_id = expense_response.json()["expense_id"]

        # Update category (should also update assigned_card_member)
        update_data = {"category": "JohnSpend"}  # This category has card_name "J Doe"
        response = client.patch(
            f"/expenses/{expense_id}", json=update_data, headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["category"] == "JohnSpend"
        assert (
            data["assigned_card_member"] == "J Doe"
        )  # Should be updated to category's card_name


class TestHealthAPI:
    def test_health_check(self, client):
        """Test health check endpoint."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["environment"] == "local"

    def test_root_endpoint(self, client):
        """Test root endpoint."""
        response = client.get("/")

        assert response.status_code == 200
        data = response.json()
        assert "Expense Tracker API" in data["message"]
