from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from core.models import (
    Expense,
    OwnerCreate,
    AccountCreate,
    CategoryCreate,
    ExpenseCreate,
)
from services import dynamo_expenses as db
from services.categorization_service import AutoCategorizationService


class TestAutoCategorizationService:
    """Test cases for auto-categorization service."""

    @pytest.fixture
    def categorization_service(self, clean_db):
        """Create categorization service instance."""
        return AutoCategorizationService()

    @pytest.fixture
    def sample_categories(self, clean_db):
        """Create sample categories for testing."""
        # Create test owner and account first
        owner = db.create_owner(OwnerCreate(name="TestOwner", card_name="T Owner"))
        account = db.create_account(
            AccountCreate(
                account_name="Test Account",
                bank_name="Test Bank",
                owner_name="TestOwner",
                card_member="T Owner",
            )
        )

        # Create categories
        categories = [
            db.create_category(
                CategoryCreate(
                    name="Coffee",
                    labels=["cafe", "coffee", "starbucks"],
                    account_id="Test Account TestOwner",
                    card_name="T Owner",
                )
            ),
            db.create_category(
                CategoryCreate(
                    name="Transport",
                    labels=["PUBLIC TRANSPORT", "bus", "train"],
                    account_id="Test Account TestOwner",
                    card_name="T Owner",
                )
            ),
            db.create_category(
                CategoryCreate(
                    name="Apple",
                    labels=["APPLE.COM", "apple"],
                    account_id="Test Account TestOwner",
                    card_name="T Owner",
                )
            ),
            db.create_category(
                CategoryCreate(
                    name="TestOwner-Unknown",
                    labels=[],
                    account_id="Test Account TestOwner",
                    card_name="T Owner",
                )
            ),
        ]
        return categories

    def test_normalize_text(self, categorization_service):
        """Test text normalization function."""
        assert (
            categorization_service._normalize_text("APPLE.COM/BILL SYDNEY")
            == "apple com bill sydney"
        )
        assert (
            categorization_service._normalize_text("  Multiple   Spaces  ")
            == "multiple spaces"
        )
        assert (
            categorization_service._normalize_text("Special!@#$%^&*()Chars")
            == "special chars"
        )
        assert (
            categorization_service._normalize_text("Keep123Numbers456")
            == "keep123numbers456"
        )
        assert categorization_service._normalize_text("") == ""
        assert categorization_service._normalize_text(None) == ""

    def test_amounts_equal(self, categorization_service):
        """Test amount comparison with tolerance."""
        assert categorization_service._amounts_equal(Decimal("12.99"), Decimal("12.99"))
        assert categorization_service._amounts_equal(
            Decimal("12.99"), Decimal("12.98")
        )  # Within tolerance
        assert not categorization_service._amounts_equal(
            Decimal("12.99"), Decimal("12.95")
        )  # Outside tolerance

    def test_historical_exact_match(
        self, categorization_service, sample_categories, clean_db
    ):
        """Test historical exact matching logic."""

        # Create a historical expense
        historical_expense = db.create_expense(
            ExpenseCreate(
                date=datetime.now() - timedelta(days=30),
                description="STARBUCKS COFFEE STORE",
                card_member="T Owner",
                amount=Decimal("5.50"),
                category="Coffee",
            )
        )

        # Create new expense with same description and amount
        new_expense = Expense(
            date=datetime.now(),
            description="STARBUCKS COFFEE STORE",
            card_member="T Owner",
            amount=Decimal("5.50"),
        )

        # Test historical match
        historical_category = categorization_service._find_historical_match(new_expense)
        assert historical_category == "Coffee"

    def test_historical_no_match_different_amount(
        self, categorization_service, sample_categories, clean_db
    ):
        """Test that historical matching fails with different amounts."""

        # Create a historical expense
        db.create_expense(
            ExpenseCreate(
                date=datetime.now() - timedelta(days=30),
                description="STARBUCKS COFFEE STORE",
                card_member="T Owner",
                amount=Decimal("5.50"),
                category="Coffee",
            )
        )

        # Create new expense with same description but different amount
        new_expense = Expense(
            date=datetime.now(),
            description="STARBUCKS COFFEE STORE",
            card_member="T Owner",
            amount=Decimal("7.50"),  # Different amount
        )

        # Should not match
        historical_category = categorization_service._find_historical_match(new_expense)
        assert historical_category is None

    def test_historical_no_match_too_old(
        self, categorization_service, sample_categories, clean_db
    ):
        """Test that historical matching fails for expenses older than 3 months."""

        # Create an old historical expense (4 months ago)
        db.create_expense(
            ExpenseCreate(
                date=datetime.now() - timedelta(days=120),
                description="STARBUCKS COFFEE STORE",
                card_member="T Owner",
                amount=Decimal("5.50"),
                category="Coffee",
            )
        )

        # Create new expense with same description and amount
        new_expense = Expense(
            date=datetime.now(),
            description="STARBUCKS COFFEE STORE",
            card_member="T Owner",
            amount=Decimal("5.50"),
        )

        # Should not match (too old)
        historical_category = categorization_service._find_historical_match(new_expense)
        assert historical_category is None

    def test_fuzzy_label_match_success(self, sample_categories, categorization_service):
        """Test successful label substring matching."""
        # Ensure categories are created first by accessing the fixture
        assert len(sample_categories) == 4

        # Debug: Check if categories can be retrieved directly
        direct_categories = db.list_categories()
        print(f"Direct category check: {len(direct_categories)} categories found")
        for cat in direct_categories:
            print(f"  - {cat.name}: {cat.labels}")

        new_expense = Expense(
            date=datetime.now(),
            description="COFFEE SHOP DOWNTOWN",
            card_member="T Owner",
            amount=Decimal("4.50"),
        )

        result = categorization_service._find_label_match(new_expense)
        assert result == "Coffee"

    def test_fuzzy_label_match_transport(
        self, categorization_service, sample_categories
    ):
        """Test label matching for transport category."""
        new_expense = Expense(
            date=datetime.now(),
            description="AT PUBLIC TRANSPORT AUCKLAND",
            card_member="T Owner",
            amount=Decimal("3.50"),
        )

        result = categorization_service._find_label_match(new_expense)
        assert result == "Transport"

    def test_fuzzy_label_no_match_low_score(
        self, categorization_service, sample_categories
    ):
        """Test that unrelated descriptions don't match."""
        new_expense = Expense(
            date=datetime.now(),
            description="COMPLETELY UNRELATED EXPENSE",
            card_member="T Owner",
            amount=Decimal("10.00"),
        )

        result = categorization_service._find_label_match(new_expense)
        assert result is None

    def test_card_member_priority_resolution(
        self, categorization_service, sample_categories, clean_db
    ):
        """Test card-member priority when multiple categories have same labels."""

        # Create another category with same labels but different card_name
        db.create_category(
            CategoryCreate(
                name="CoffeeOther",
                labels=["coffee"],  # Same label as existing Coffee category
                account_id="Test Account TestOwner",
                card_name="Other Owner",  # Different card name
            )
        )

        new_expense = Expense(
            date=datetime.now(),
            description="COFFEE SHOP DOWNTOWN",
            card_member="T Owner",  # Matches first category's card_name
            amount=Decimal("4.50"),
        )

        result = categorization_service._find_label_match(new_expense)
        assert result == "Coffee"  # Should prefer matching card_name

    def test_full_categorization_workflow_historical_match(
        self, categorization_service, sample_categories, clean_db
    ):
        """Test complete categorization workflow with historical match."""

        # Create historical expense
        db.create_expense(
            ExpenseCreate(
                date=datetime.now() - timedelta(days=30),
                description="STARBUCKS COFFEE",
                card_member="T Owner",
                amount=Decimal("5.50"),
                category="Coffee",
            )
        )

        # Create new expense for categorization
        new_expense = Expense(
            date=datetime.now(),
            description="STARBUCKS COFFEE",
            card_member="T Owner",
            amount=Decimal("5.50"),
        )

        # Categorize
        result = categorization_service.categorize_expense(new_expense)

        assert result.category == "Coffee"
        assert result.is_auto_categorized is True
        assert (
            result.category_hint == []
        )  # Historical matches have empty category_hint list

    def test_full_categorization_workflow_fuzzy_match(
        self, categorization_service, sample_categories
    ):
        """Test complete categorization workflow with fuzzy match."""
        new_expense = Expense(
            date=datetime.now(),
            description="COFFEE BEANS ROASTERY",
            card_member="T Owner",
            amount=Decimal("12.00"),
        )

        # Categorize
        result = categorization_service.categorize_expense(new_expense)

        assert result.category == "Coffee"
        assert result.is_auto_categorized is True

    def test_full_categorization_workflow_unknown(
        self, categorization_service, sample_categories
    ):
        """Test complete categorization workflow with unknown result."""
        new_expense = Expense(
            date=datetime.now(),
            description="COMPLETELY UNKNOWN MERCHANT XYZ",
            card_member="T Owner",
            amount=Decimal("99.99"),
        )

        # Categorize
        result = categorization_service.categorize_expense(new_expense)

        assert result.category == "TestOwner-Unknown"
        assert result.is_auto_categorized is True
        assert result.needs_review is True

    def test_assigned_card_member_updated_on_auto_categorization(
        self, categorization_service, sample_categories
    ):
        """Test that assigned_card_member is updated during auto-categorization."""
        new_expense = Expense(
            date=datetime.now(),
            description="STARBUCKS COFFEE",
            card_member="Original Member",  # Different from category's card_name
            amount=Decimal("5.50"),
        )

        # Categorize
        result = categorization_service.categorize_expense(new_expense)

        assert result.category == "Coffee"
        assert (
            result.assigned_card_member == "T Owner"
        )  # Should be updated to category's card_name

    def test_assigned_card_member_updated_on_manual_category_change(
        self, categorization_service, sample_categories
    ):
        """Test that assigned_card_member is updated when category is manually changed."""
        expense = Expense(
            date=datetime.now(),
            description="Test expense",
            card_member="Original Member",
            assigned_card_member="Original Member",
            amount=Decimal("10.00"),
        )

        # Update category manually
        result = categorization_service.update_expense_assigned_card_member_on_category_change(
            expense, "Transport"
        )

        assert (
            result.assigned_card_member == "T Owner"
        )  # Should be updated to Transport category's card_name

    def test_assigned_card_member_handles_unknown_category(
        self, categorization_service, sample_categories, clean_db
    ):
        """Test that assigned_card_member is handled properly for Unknown category."""
        # Create additional owner/account/unknown category for different card member
        db.create_owner(OwnerCreate(name="OriginalOwner", card_name="Original Member"))
        db.create_account(
            AccountCreate(
                account_name="Original Account",
                bank_name="Test Bank",
                owner_name="OriginalOwner",
                card_member="Original Member",
            )
        )
        db.create_category(
            CategoryCreate(
                name="OriginalOwner-Unknown",
                labels=[],
                account_id="Original Account OriginalOwner",
                card_name="Original Member",
            )
        )

        new_expense = Expense(
            date=datetime.now(),
            description="COMPLETELY UNKNOWN MERCHANT",
            card_member="Original Member",
            amount=Decimal("99.99"),
        )

        # Categorize (should result in Unknown)
        result = categorization_service.categorize_expense(new_expense)

        assert result.category == "OriginalOwner-Unknown"
        # assigned_card_member should be updated based on Unknown category lookup
        assert result.assigned_card_member == "Original Member"
        assert result.account_id == "Original Account OriginalOwner"

    def test_assigned_card_member_validation_in_repository(self, clean_db):
        """Test that repository validates assigned_card_member against Owner.card_name."""
        from core.models import ExpenseUpdate

        # Create owner first (required for validation)
        db.create_owner(OwnerCreate(name="TestOwner", card_name="T Owner"))

        # Create expense first
        expense = db.create_expense(
            ExpenseCreate(
                date=datetime.now(),
                description="Test expense",
                card_member="T Owner",
                amount=Decimal("10.00"),
            )
        )

        # Try to update with invalid card_member
        with pytest.raises(ValueError, match="Invalid card_member"):
            db.update_expense(
                expense.expense_id,
                ExpenseUpdate(assigned_card_member="Invalid Card Name"),
            )

        # Valid update should work
        updated = db.update_expense(
            expense.expense_id, ExpenseUpdate(assigned_card_member="T Owner")
        )
        assert updated is not None
        assert updated.assigned_card_member == "T Owner"

    def test_needs_review_cleared_on_manual_category_update(
        self, categorization_service, sample_categories, clean_db
    ):
        """Test that needs_review flag is cleared when category is manually updated."""
        from core.models import ExpenseUpdate

        # Create an expense that gets categorized as Unknown (needs_review=True)
        new_expense = Expense(
            date=datetime.now(),
            description="UNKNOWN MERCHANT XYZ",
            card_member="T Owner",
            amount=Decimal("25.00"),
        )

        # Auto-categorize (should result in Unknown with needs_review=True)
        categorized_expense = categorization_service.categorize_expense(new_expense)
        assert categorized_expense.category == "TestOwner-Unknown"
        assert categorized_expense.needs_review is True

        # Persist the expense
        persisted_expense = db.create_expense(
            ExpenseCreate(
                date=categorized_expense.date,
                description=categorized_expense.description,
                card_member=categorized_expense.card_member,
                amount=categorized_expense.amount,
                category=categorized_expense.category,
                needs_review=categorized_expense.needs_review,
            )
        )

        # Verify it was persisted with needs_review=True
        retrieved_expense = db.get_expense(persisted_expense.expense_id)
        assert retrieved_expense.needs_review is True
        assert retrieved_expense.category == "TestOwner-Unknown"

        # Manually update the category (simulate user review)
        updated_expense = db.update_expense(
            persisted_expense.expense_id, ExpenseUpdate(category="Coffee")
        )

        # Verify needs_review flag is now cleared
        assert updated_expense is not None
        assert updated_expense.category == "Coffee"
        assert updated_expense.needs_review is False
        assert updated_expense.assigned_card_member == "T Owner"
