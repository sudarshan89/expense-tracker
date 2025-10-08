import importlib.util

import pytest
from fastapi.testclient import TestClient

# Skip these tests if python-multipart is not installed
if importlib.util.find_spec("multipart") is None:  # pragma: no cover - env dependent
    pytest.skip(
        "python-multipart not installed; skipping upload tests", allow_module_level=True
    )

from local_main import app
from services.csv_service import parse_csv_expenses, validate_csv_file


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def sample_csv_content():
    """Sample CSV content for testing."""
    return """Date,Description,Card Member,Account #,Amount,Extended Details,Appears On Your Statement As,Address,City/State,Zip Code,Country,Reference,Category
21/09/2025,APPLE.COM/BILL SYDNEY,J DOE,1003,12.99,Foreign Spend Amount: 23.00 USD,APPLE.COM/BILL,"255 PITT STREET SYDNEY",NSW 2000,2000,UNITED STATES,AT252540002000010028867,Retail & Grocery-Online Purchases
22/09/2025,COFFEE SHOP,J DOE,1003,5.50,,,,"",,,,,Food & Dining"""


@pytest.fixture
def sample_csv_bytes(sample_csv_content):
    """Sample CSV content as bytes."""
    return sample_csv_content.encode("utf-8")


class TestCSVService:
    def test_parse_valid_csv(self, sample_csv_content):
        """Test parsing valid CSV content."""
        expenses, errors = parse_csv_expenses(sample_csv_content)

        assert len(errors) == 0
        assert len(expenses) == 2

        # Check first expense
        expense1 = expenses[0]
        assert expense1.description == "APPLE.COM/BILL SYDNEY"
        assert expense1.card_member == "J DOE"
        assert str(expense1.amount) == "12.99"
        assert expense1.date.day == 21
        assert expense1.date.month == 9
        assert expense1.date.year == 2025

    def test_parse_csv_missing_headers(self):
        """Test CSV with missing required headers."""
        invalid_csv = "Name,Price\nApple,5.00"
        expenses, errors = parse_csv_expenses(invalid_csv)

        assert len(expenses) == 0
        assert len(errors) > 0
        assert "Missing required CSV headers" in errors[0]

    def test_validate_csv_file_size(self):
        """Test CSV file size validation."""
        large_content = "x" * (600 * 1024)  # 600KB
        errors = validate_csv_file(large_content.encode("utf-8"), max_size_kb=500)

        assert len(errors) > 0
        assert "File too large" in errors[0]

    def test_validate_empty_file(self):
        """Test empty file validation."""
        errors = validate_csv_file(b"")

        assert len(errors) > 0
        assert "File is empty" in errors[0]


class TestCSVUploadAPI:
    def test_upload_valid_csv(self, client, sample_csv_bytes, setup_unknown_categories):
        """Test uploading valid CSV file."""
        files = {"file": ("test.csv", sample_csv_bytes, "text/csv")}
        response = client.post("/expenses/upload", files=files)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["processed_count"] == 2
        assert data["error_count"] == 0

    def test_upload_invalid_file_type(self, client):
        """Test uploading non-CSV file."""
        files = {"file": ("test.txt", b"not a csv", "text/plain")}
        response = client.post("/expenses/upload", files=files)

        assert response.status_code == 400
        assert "File must be a CSV file" in response.json()["detail"]

    def test_upload_empty_csv(self, client):
        """Test uploading empty CSV file."""
        files = {"file": ("empty.csv", b"", "text/csv")}
        response = client.post("/expenses/upload", files=files)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "File is empty" in data["errors"][0]

    def test_upload_csv_with_invalid_dates(self, client):
        """Test uploading CSV with invalid date format."""
        invalid_csv = """Date,Description,Card Member,Amount
2025-09-21,Test,John,10.00"""

        files = {"file": ("invalid.csv", invalid_csv.encode("utf-8"), "text/csv")}
        response = client.post("/expenses/upload", files=files)

        assert response.status_code == 200
        data = response.json()
        assert data["processed_count"] == 0
        assert data["error_count"] > 0
        assert any("Invalid date format" in error for error in data["errors"])

    def test_upload_csv_with_auto_categorization(self, client, clean_db):
        """Test CSV upload with auto-categorization functionality."""
        from services import dynamo_expenses as db
        from core.models import OwnerCreate, AccountCreate, CategoryCreate

        # Set up test data - create owner, account, and categories
        owner = db.create_owner(
            OwnerCreate(name="TestOwner", card_name="J DOE")
        )
        account = db.create_account(
            AccountCreate(
                account_name="Test Account",
                bank_name="Test Bank",
                owner_name="TestOwner",
                card_member="J DOE",
            )
        )

        # Create categories with labels that should match CSV entries
        coffee_category = db.create_category(
            CategoryCreate(
                name="Coffee",
                labels=["coffee", "cafe"],
                account_id="Test Account TestOwner",
                card_name="J DOE",
            )
        )

        apple_category = db.create_category(
            CategoryCreate(
                name="Apple",
                labels=["apple.com", "apple"],
                account_id="Test Account TestOwner",
                card_name="J DOE",
            )
        )

        # Create Unknown category for fallback
        unknown_category = db.create_category(
            CategoryCreate(
                name="TestOwner-Unknown",
                labels=[],
                account_id="Test Account TestOwner",
                card_name="J DOE",
            )
        )

        # CSV without category column - should trigger auto-categorization
        csv_content = """Date,Description,Card Member,Account #,Amount
21/09/2025,APPLE.COM/BILL SYDNEY,J DOE,1003,12.99
22/09/2025,COFFEE SHOP DOWNTOWN,J DOE,1003,5.50
23/09/2025,UNKNOWN MERCHANT,J DOE,1003,25.00"""

        files = {"file": ("test_auto_cat.csv", csv_content.encode("utf-8"), "text/csv")}
        response = client.post("/expenses/upload", files=files)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["processed_count"] == 3
        assert data["error_count"] == 0
        assert data["auto_categorized_count"] == 3  # All should be auto-categorized

        # With the new tie-breaking logic, "APPLE.COM/BILL SYDNEY" should now match
        # the "Apple" category (it contains "apple.com"), so only unknown merchant needs review
        assert data["needs_review_count"] == 1  # Only unknown merchant needs review

        # Check that message includes auto-categorization info
        assert "auto-categorized" in data["message"]
