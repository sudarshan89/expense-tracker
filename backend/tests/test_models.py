from datetime import datetime
from datetime import datetime
from decimal import Decimal

from core.models import (
    Owner,
    Account,
    Category,
    Expense,
)


class TestOwner:
    def test_create_valid_owner(self, sample_owner_data):
        """Test creating a valid owner."""
        owner = Owner(**sample_owner_data)
        assert owner.name == "TestOwner"
        assert owner.card_name == "T Owner"
        assert isinstance(owner.created_at, datetime)

    def test_owner_pk_sk_generation(self, sample_owner_data):
        """Test owner PK/SK generation."""
        owner = Owner(**sample_owner_data)
        assert owner.get_pk() == "OWNER#TestOwner"
        assert owner.get_sk() == "OWNER#TestOwner"


class TestAccount:
    def test_create_valid_account(self, sample_account_data):
        """Test creating a valid account."""
        account = Account(**sample_account_data)
        assert account.account_name == "Test Account"
        assert account.bank_name == "Test Bank"
        assert account.owner_name == "TestOwner"
        assert account.active is True

    def test_account_pk_sk_generation(self, sample_account_data):
        """Test account PK/SK generation."""
        account = Account(**sample_account_data)
        assert account.get_pk() == "ACCOUNT#Test Account#TestOwner"
        assert account.get_sk() == "ACCOUNT#Test Account#TestOwner"


class TestCategory:
    def test_create_valid_category(self, sample_category_data):
        """Test creating a valid category."""
        category = Category(**sample_category_data)
        assert category.name == "TestCategory"
        assert category.labels == ["test", "sample"]
        assert category.account_id == "Test Account TestOwner"
        assert category.card_name == "T Owner"
        assert category.active is True

    def test_category_pk_sk_generation(self, sample_category_data):
        """Test category PK/SK generation."""
        category = Category(**sample_category_data)
        assert category.get_pk() == "CATEGORY#TestCategory"
        assert category.get_sk() == "CATEGORY#TestCategory"


class TestExpense:
    def test_create_valid_expense(self, sample_expense_data):
        """Test creating a valid expense."""
        expense = Expense(**sample_expense_data)
        assert expense.description == "Test Expense"
        assert expense.card_member == "T Owner"
        assert expense.assigned_card_member == "T Owner"  # Default assignment
        assert expense.amount == Decimal("25.50")
        assert expense.category == "TestCategory"

    def test_expense_pk_sk_generation(self, sample_expense_data):
        """Test expense PK/SK generation."""
        expense = Expense(**sample_expense_data)
        assert expense.get_pk() == f"EXPENSE#{expense.expense_id}"
        assert expense.get_sk() == f"EXPENSE#{expense.expense_id}"
        assert expense.get_pk() == expense.get_sk()
