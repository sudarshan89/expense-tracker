from datetime import datetime
from decimal import Decimal

import pytest

from core.models import (
    ExpenseFilter,
    ExpenseCreate,
    OwnerCreate,
    AccountCreate,
    CategoryCreate,
)
from services import dynamo_expenses as db
from services.reports_service import ReportsService


class TestBillingCycleDates:
    """Test billing cycle date range calculation (12th-to-11th)."""

    def test_derive_date_range_jan(self):
        """Test January billing cycle: Jan 12 to Feb 11."""
        start, end = ReportsService.derive_date_range_for_month("jan", 2025)
        assert start == datetime(2025, 1, 12)
        assert end == datetime(2025, 2, 11)

    def test_derive_date_range_dec(self):
        """Test December billing cycle: Dec 12 to Jan 11 (next year)."""
        start, end = ReportsService.derive_date_range_for_month("dec", 2025)
        assert start == datetime(2025, 12, 12)
        assert end == datetime(2026, 1, 11)

    def test_derive_date_range_case_insensitive(self):
        """Test month input is case insensitive."""
        start1, end1 = ReportsService.derive_date_range_for_month("JAN", 2025)
        start2, end2 = ReportsService.derive_date_range_for_month("jan", 2025)
        start3, end3 = ReportsService.derive_date_range_for_month("Jan", 2025)

        assert start1 == start2 == start3
        assert end1 == end2 == end3

    def test_derive_date_range_invalid_month(self):
        """Test invalid month raises ValueError."""
        with pytest.raises(ValueError, match="Invalid month"):
            ReportsService.derive_date_range_for_month("invalid", 2025)

    def test_derive_date_range_empty_month(self):
        """Test empty month raises ValueError."""
        with pytest.raises(ValueError, match="month is required"):
            ReportsService.derive_date_range_for_month("", 2025)


class TestReportTotalCalculation:
    """Test report total amount calculation logic."""

    def test_report_excludes_negative_amounts(self, clean_db):
        """Test that negative amounts (payments) are excluded from totals."""
        # Setup
        expense_repo = db

        # Create owner
        owner = db.create_owner(OwnerCreate(name="TestOwner", card_name="T Owner"))

        # Create account
        account = db.create_account(
            AccountCreate(
                account_name="Test Account",
                bank_name="Test Bank",
                owner_name="TestOwner",
                card_member="T Owner",
            )
        )

        # Create category
        category = db.create_category(
            CategoryCreate(
                name="TestCategory",
                labels=["test"],
                account_id="Test Account TestOwner",
                card_name="T Owner",
            )
        )

        # Create expenses: 2 positive (expenses) and 1 negative (payment)
        db.create_expense(
            ExpenseCreate(
                date=datetime(2025, 9, 15),
                description="Expense 1",
                card_member="T Owner",
                assigned_card_member="T Owner",
                amount=Decimal("100.00"),
                category="TestCategory",
                account_id="Test Account TestOwner",
            )
        )
        db.create_expense(
            ExpenseCreate(
                date=datetime(2025, 9, 16),
                description="Expense 2",
                card_member="T Owner",
                assigned_card_member="T Owner",
                amount=Decimal("50.00"),
                category="TestCategory",
                account_id="Test Account TestOwner",
            )
        )
        db.create_expense(
            ExpenseCreate(
                date=datetime(2025, 9, 17),
                description="Payment",
                card_member="T Owner",
                assigned_card_member="T Owner",
                amount=Decimal("-150.00"),  # Payment (negative amount)
                category="TestCategory",
                account_id="Test Account TestOwner",
            )
        )

        # Generate report
        reports_service = ReportsService()
        expense_filter = ExpenseFilter(
            start_date=datetime(2025, 9, 1),
            end_date=datetime(2025, 9, 30),
        )
        report = reports_service.get_expenses_by_account_report(expense_filter)

        # Assert: Total should be 150.00 (100 + 50), excluding the -150 payment
        assert report.total_amount == Decimal("150.00")
        assert report.total_expenses == 3  # All 3 expenses counted
        assert len(report.account_groups) == 1
        assert report.account_groups[0].total_amount == Decimal("150.00")

    def test_report_excludes_card_payments_account(self, clean_db):
        """Test that Card-Payments account is excluded from total and display."""
        # Setup
        expense_repo = db

        # Create owner
        owner = db.create_owner(OwnerCreate(name="TestOwner", card_name="T Owner"))

        # Create regular account
        regular_account = db.create_account(
            AccountCreate(
                account_name="Regular Account",
                bank_name="Test Bank",
                owner_name="TestOwner",
                card_member="T Owner",
            )
        )

        # Create Card-Payments account
        card_payments_account = db.create_account(
            AccountCreate(
                account_name="Card-Payments",
                bank_name="Test Bank",
                owner_name="TestOwner",
                card_member="T Owner",
            )
        )

        # Create categories
        regular_category = db.create_category(
            CategoryCreate(
                name="RegularCategory",
                labels=["test"],
                account_id="Regular Account TestOwner",
                card_name="T Owner",
            )
        )
        card_payments_category = db.create_category(
            CategoryCreate(
                name="CardPaymentsCategory",
                labels=["payment"],
                account_id="Card-Payments TestOwner",
                card_name="T Owner",
            )
        )

        # Create expenses
        db.create_expense(
            ExpenseCreate(
                date=datetime(2025, 9, 15),
                description="Regular Expense",
                card_member="T Owner",
                amount=Decimal("100.00"),
                category="RegularCategory",
                account_id="Regular Account TestOwner",
            )
        )
        db.create_expense(
            ExpenseCreate(
                date=datetime(2025, 9, 16),
                description="Card Payment",
                card_member="T Owner",
                amount=Decimal("200.00"),
                category="CardPaymentsCategory",
                account_id="Card-Payments TestOwner",
            )
        )

        # Generate report
        reports_service = ReportsService()
        expense_filter = ExpenseFilter(
            start_date=datetime(2025, 9, 1),
            end_date=datetime(2025, 9, 30),
        )
        report = reports_service.get_expenses_by_account_report(expense_filter)

        # Assert: Card-Payments excluded from total and display
        assert report.total_amount == Decimal("100.00")  # Only regular expense
        assert len(report.account_groups) == 1  # Card-Payments not in display
        assert report.account_groups[0].account_name == "Regular Account"


class TestReportExpenseSorting:
    """Test expense sorting in reports (newest to oldest)."""

    def test_expenses_sorted_newest_first(self, clean_db):
        """Test that expenses within account are sorted newest to oldest."""
        # Setup
        expense_repo = db

        # Create owner
        owner = db.create_owner(OwnerCreate(name="TestOwner", card_name="T Owner"))

        # Create account
        account = db.create_account(
            AccountCreate(
                account_name="Test Account",
                bank_name="Test Bank",
                owner_name="TestOwner",
                card_member="T Owner",
            )
        )

        # Create category
        category = db.create_category(
            CategoryCreate(
                name="TestCategory",
                labels=["test"],
                account_id="Test Account TestOwner",
                card_name="T Owner",
            )
        )

        # Create expenses in random date order
        expense1 = db.create_expense(
            ExpenseCreate(
                date=datetime(2025, 9, 10),
                description="Oldest Expense",
                card_member="T Owner",
                amount=Decimal("10.00"),
                category="TestCategory",
                account_id="Test Account TestOwner",
            )
        )
        expense2 = db.create_expense(
            ExpenseCreate(
                date=datetime(2025, 9, 20),
                description="Newest Expense",
                card_member="T Owner",
                amount=Decimal("20.00"),
                category="TestCategory",
                account_id="Test Account TestOwner",
            )
        )
        expense3 = db.create_expense(
            ExpenseCreate(
                date=datetime(2025, 9, 15),
                description="Middle Expense",
                card_member="T Owner",
                amount=Decimal("15.00"),
                category="TestCategory",
                account_id="Test Account TestOwner",
            )
        )

        # Generate report
        reports_service = ReportsService()
        expense_filter = ExpenseFilter(
            start_date=datetime(2025, 9, 1),
            end_date=datetime(2025, 9, 30),
        )
        report = reports_service.get_expenses_by_account_report(expense_filter)

        # Assert: Expenses sorted newest to oldest
        assert len(report.account_groups) == 1
        expenses = report.account_groups[0].expenses

        assert len(expenses) == 3
        assert expenses[0].description == "Newest Expense"  # Sept 20
        assert expenses[1].description == "Middle Expense"  # Sept 15
        assert expenses[2].description == "Oldest Expense"  # Sept 10
