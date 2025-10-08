"""Reports service for expense tracking."""

import logging
from decimal import Decimal
from typing import Optional

from core.models import (
    ExpenseFilter,
    AccountExpenseGroup,
    ExpensesByAccountReport,
)
from services import dynamo_expenses as db

logger = logging.getLogger(__name__)


class ReportsService:
    """Service for generating expense reports."""

    MONTH_MAP = {
        "jan": 1,
        "feb": 2,
        "mar": 3,
        "apr": 4,
        "may": 5,
        "jun": 6,
        "jul": 7,
        "aug": 8,
        "sep": 9,
        "oct": 10,
        "nov": 11,
        "dec": 12,
    }

    def __init__(self):
        pass

    @staticmethod
    def derive_date_range_for_month(month: str, year: int | None = None):
        """Derive 12th-to-11th date range for a given 3-letter month.

        Returns (start_date, end_date) as naive datetimes in local year unless a specific year is provided.
        Raises ValueError for invalid month strings.
        """
        from datetime import datetime as _dt

        if not month:
            raise ValueError("month is required")
        m_key = month.strip().lower()
        if m_key not in ReportsService.MONTH_MAP:
            raise ValueError(
                "Invalid month. Provide a 3-letter month like 'Jan', 'Feb', ... 'Dec'"
            )
        m = ReportsService.MONTH_MAP[m_key]
        now_year = year or _dt.now().year
        start = _dt(now_year, m, 12)
        if m == 12:
            end = _dt(now_year + 1, 1, 11)
        else:
            end = _dt(now_year, m + 1, 11)
        return start, end

    def get_expenses_by_account_report(
        self, expense_filter: ExpenseFilter
    ) -> Optional[ExpensesByAccountReport]:
        """Generate a report of expenses grouped by account."""
        try:
            # Get expenses based on filter
            expenses = db.list_expenses(expense_filter)
            if not expenses:
                return ExpensesByAccountReport(
                    start_date=expense_filter.start_date,
                    end_date=expense_filter.end_date,
                    total_amount=Decimal("0"),
                    total_expenses=0,
                    account_groups=[],
                )

            # Group expenses by account_id directly
            grouped_expenses = {}
            total_amount = Decimal("0")

            for expense in expenses:
                if not expense.account_id:
                    logger.warning(
                        f"Expense {expense.expense_id} has no account_id, skipping"
                    )
                    continue

                account_id = expense.account_id

                # Parse account_id to extract account_name and owner_name
                # Format: "account_name owner_name" (space-separated)
                # Use rsplit to split from the right since owner_name has no spaces
                parts = account_id.rsplit(" ", 1)
                if len(parts) != 2:
                    logger.warning(
                        f"Invalid account_id format '{account_id}' for expense {expense.expense_id}, skipping"
                    )
                    continue

                account_name, owner_name = parts

                if account_id not in grouped_expenses:
                    grouped_expenses[account_id] = {
                        "account_name": account_name,
                        "owner_name": owner_name,
                        "expenses": [],
                        "total_amount": Decimal("0"),
                    }

                grouped_expenses[account_id]["expenses"].append(expense)

                # Only sum positive amounts (actual expenses)
                # Negative amounts are payments made to the card, not expenses to be tracked
                if expense.amount > 0:
                    grouped_expenses[account_id]["total_amount"] += expense.amount
                    # Exclude Card-Payments account from grand total
                    # Card-Payments is used to track payments made to credit cards, not actual expenses
                    if account_name != "Card-Payments":
                        total_amount += expense.amount

            # Create account groups
            account_groups = []
            for account_id, data in grouped_expenses.items():
                account_name = data["account_name"]
                owner_name = data["owner_name"]

                # Skip Card-Payments account from report display
                # This account tracks payments made to credit cards, not actual expenses
                if account_name == "Card-Payments":
                    continue

                # Sort expenses by date descending (newest first)
                sorted_expenses = sorted(
                    data["expenses"], key=lambda x: x.date, reverse=True
                )
                group = AccountExpenseGroup(
                    account_id=account_id,
                    account_name=account_name,
                    owner_name=owner_name,
                    total_amount=data["total_amount"],
                    expense_count=len(sorted_expenses),
                    expenses=sorted_expenses,
                )
                account_groups.append(group)

            # Sort by owner name, then by total amount descending within each owner
            account_groups.sort(key=lambda x: (x.owner_name, -x.total_amount))

            return ExpensesByAccountReport(
                start_date=expense_filter.start_date,
                end_date=expense_filter.end_date,
                total_amount=total_amount,
                total_expenses=len(expenses),
                account_groups=account_groups,
            )

        except Exception as e:
            logger.error(f"Error generating expenses by account report: {e}")
            return None
