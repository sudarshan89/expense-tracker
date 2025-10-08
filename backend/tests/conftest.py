import os
from datetime import datetime
from decimal import Decimal

import pytest

# Set environment for testing
os.environ["ENVIRONMENT"] = "local"
os.environ["DYNAMODB_TABLE_NAME"] = "expense-tracker-test"

from core.database import DynamoDBSetup


@pytest.fixture(scope="session")
def test_db():
    """Create a test database instance."""
    db_setup = DynamoDBSetup()

    # Create test table
    try:
        db_setup.create_table_if_not_exists()
        yield db_setup
    finally:
        # Clean up test table
        try:
            table = db_setup.get_table()
            table.delete()
        except Exception:
            pass  # Table might not exist


@pytest.fixture
def clean_db(test_db):
    """Provide a clean database for each test."""
    table = test_db.get_table()

    # Clear all items from table
    response = table.scan()
    for item in response["Items"]:
        table.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})

    yield table


@pytest.fixture
def sample_owner_data():
    """Sample owner data for testing."""
    return {"name": "TestOwner", "card_name": "T Owner"}


@pytest.fixture
def sample_account_data():
    """Sample account data for testing."""
    return {
        "account_name": "Test Account",
        "bank_name": "Test Bank",
        "owner_name": "TestOwner",
        "card_member": "T Owner",
        "active": True,
    }


@pytest.fixture
def sample_category_data():
    """Sample category data for testing."""
    return {
        "name": "TestCategory",
        "labels": ["test", "sample"],
        "account_id": "Test Account TestOwner",
        "card_name": "T Owner",
        "active": True,
    }


@pytest.fixture
def sample_expense_data():
    """Sample expense data for testing."""
    return {
        "date": datetime(2025, 9, 21),
        "description": "Test Expense",
        "card_member": "T Owner",
        "amount": Decimal("25.50"),
        "category": "TestCategory",
    }


@pytest.fixture
def setup_unknown_categories(clean_db):
    """Set up Unknown categories for common test card members."""
    from services import dynamo_expenses as db
    from core.models import OwnerCreate, AccountCreate, CategoryCreate

    # Create test owner
    owner = db.create_owner(OwnerCreate(name="TestOwner", card_name="J DOE"))

    # Create test account
    account = db.create_account(
        AccountCreate(
            account_name="Test-Unknown",
            bank_name="Test Bank",
            owner_name="TestOwner",
            card_member="J DOE",
        )
    )

    # Create Unknown category
    unknown_category = db.create_category(
        CategoryCreate(
            name="TestOwner-Unknown",
            labels=[],
            account_id="Test-Unknown TestOwner",
            card_name="J DOE",
        )
    )

    return {"owner": owner, "account": account, "unknown_category": unknown_category}
