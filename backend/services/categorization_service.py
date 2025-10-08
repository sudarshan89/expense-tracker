import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Optional

from core.models import Expense
from core.text_utils import normalize_text
from services import dynamo_expenses as db

logger = logging.getLogger(__name__)


class AutoCategorizationService:
    """Service for automatically categorizing expenses based on historical data and label matching."""

    def __init__(self):
        pass

    def categorize_expense(self, expense: Expense) -> Expense:
        """
        Auto-categorize a single expense using the 3-step logic:
        1. Historical exact match (last 3 months)
        2. Label substring matching (card-member prioritized)
        3. Unknown fallback

        Also updates assigned_card_member based on the category's card_name.

        Args:
            expense: Expense to categorize

        Returns:
            Updated expense with category, category_hint, and assigned_card_member populated
        """
        logger.info(f"Auto-categorizing expense: {expense.expense_id}")

        # Step 1: Check for historical exact match
        historical_category = self._find_historical_match(expense)
        if historical_category:
            expense.category = historical_category
            expense.is_auto_categorized = True
            expense.category_hint = []  # Empty list for historical exact matches
            self._update_assigned_card_member_from_category(
                expense, historical_category
            )
            logger.info(f"Found historical match: {historical_category}")
            return expense

        # Step 2: Label substring matching
        matched_category = self._find_label_match(expense)
        if matched_category:
            expense.category = matched_category
            expense.is_auto_categorized = True
            expense.category_hint = []  # Empty list for successful matches
            self._update_assigned_card_member_from_category(expense, matched_category)
            logger.info(f"Found label match: {matched_category}")
            return expense

        # Step 3: Unknown fallback
        # Find the appropriate Unknown category for this card_member
        unknown_category = self._find_unknown_category_for_card_member(
            expense.card_member
        )
        if not unknown_category:
            raise ValueError(
                f"No Unknown category found for card_member: {expense.card_member}"
            )

        expense.category = unknown_category
        expense.is_auto_categorized = True
        expense.needs_review = True
        expense.category_hint = []  # No candidates for unknown fallback
        self._update_assigned_card_member_from_category(expense, unknown_category)
        logger.info(f"No match found, categorized as {unknown_category}")

        return expense

    def _find_historical_match(self, expense: Expense) -> Optional[str]:
        """
        Find exact historical match from last 3 months.

        Args:
            expense: Expense to match against

        Returns:
            Category name if exact match found, None otherwise
        """
        # Get expenses from last 3 months
        three_months_ago = datetime.now() - timedelta(days=90)

        try:
            # Query recent categorized expenses
            recent_expenses = self._get_recent_categorized_expenses(three_months_ago)

            normalized_desc = normalize_text(expense.description)

            for historical_expense in recent_expenses:
                historical_desc = normalize_text(historical_expense.description)

                # Check exact match on normalized description and amount
                if normalized_desc == historical_desc and self._amounts_equal(
                    expense.amount, historical_expense.amount
                ):
                    return historical_expense.category

        except Exception as e:
            logger.error(f"Error in historical match: {e}")

        return None

    def _find_label_match(self, expense: Expense) -> Optional[str]:
        """
        Find label match using simple substring matching with card-member priority.

        Iterates through categories (prioritized by matching card_name),
        normalizes each label, and returns the first category where a label
        appears as a substring in the normalized description.

        Args:
            expense: Expense to match against

        Returns:
            Category name if match found, None otherwise
        """
        try:
            # Get all active categories
            categories = db.list_categories()
            active_categories = [cat for cat in categories if cat.active]

            # Prioritize categories matching the expense's card_member
            normalized_card_member = normalize_text(expense.card_member)
            matching_card_categories = [
                cat
                for cat in active_categories
                if normalize_text(cat.card_name) == normalized_card_member
            ]
            other_categories = [
                cat
                for cat in active_categories
                if normalize_text(cat.card_name) != normalized_card_member
            ]
            prioritized_categories = matching_card_categories + other_categories

            normalized_desc = normalize_text(expense.description)
            logger.debug(f"Normalized description: '{normalized_desc}'")
            logger.debug(
                f"Checking {len(prioritized_categories)} categories (card-member prioritized)"
            )

            # Check each category's labels for substring match
            for category in prioritized_categories:
                for label in category.labels:
                    normalized_label = normalize_text(label)
                    if normalized_label and normalized_label in normalized_desc:
                        logger.info(
                            f"Label match: '{label}' found in description for category '{category.name}'"
                        )
                        return category.name

            logger.debug("No label matches found")
            return None

        except Exception as e:
            logger.error(f"Error in label matching: {e}")
            return None

    def _get_recent_categorized_expenses(self, since_date: datetime) -> List[Expense]:
        """Get categorized expenses since the given date."""
        # This is a simplified approach - in production you'd want more efficient querying
        from core.models import ExpenseFilter

        expense_filter = ExpenseFilter(start_date=since_date)
        all_recent = db.list_expenses(expense_filter)

        # Filter to only categorized expenses (not "Unknown")
        return [exp for exp in all_recent if exp.category and exp.category != "Unknown"]

    @staticmethod
    def _normalize_text(text: Optional[str]) -> str:
        """
        DEPRECATED: Use core.text_utils.normalize_text instead.
        This wrapper remains for backward compatibility in tests/usages.
        """
        return normalize_text(text)

    def _amounts_equal(
        self, amount1: Decimal, amount2: Decimal, tolerance: Decimal = Decimal("0.01")
    ) -> bool:
        """
        Compare two amounts with floating-point tolerance.

        Args:
            amount1: First amount
            amount2: Second amount
            tolerance: Comparison tolerance (default 0.01)

        Returns:
            True if amounts are equal within tolerance
        """
        return abs(amount1 - amount2) <= tolerance

    def _update_assigned_card_member_from_category(
        self, expense: Expense, category_name: str
    ) -> None:
        """
        Update expense assigned_card_member and account_id based on category.

        Args:
            expense: Expense to update
            category_name: Name of the assigned category
        """
        try:
            category = db.get_category(category_name)
            if category:
                if not category.card_name:
                    raise ValueError(f"Category '{category_name}' has no card_name")
                if not category.account_id:
                    raise ValueError(f"Category '{category_name}' has no account_id")

                expense.assigned_card_member = category.card_name
                expense.account_id = category.account_id
                logger.debug(
                    f"Updated assigned_card_member to: {category.card_name}, account_id to: {category.account_id}"
                )
            else:
                raise ValueError(f"Category '{category_name}' not found")
        except Exception as e:
            logger.error(
                f"Error updating assigned_card_member for category {category_name}: {e}"
            )
            raise

    def _find_unknown_category_for_card_member(self, card_member: str) -> Optional[str]:
        """
        Find the appropriate Unknown category for a given card_member.
        Returns category name like "John-Unknown" or "Jane-Unknown".

        Args:
            card_member: Card member name from expense

        Returns:
            Category name of matching Unknown category, or None if not found
        """
        try:
            # Get all categories
            categories = db.list_categories()

            # Filter for Unknown categories (names ending with "-Unknown")
            unknown_categories = [
                cat for cat in categories if cat.name.endswith("-Unknown")
            ]

            # Find the one matching this card_member
            for category in unknown_categories:
                if normalize_text(category.card_name) == normalize_text(card_member):
                    logger.debug(
                        f"Found Unknown category '{category.name}' for card_member '{card_member}'"
                    )
                    return category.name

            logger.warning(f"No Unknown category found for card_member: {card_member}")
            return None
        except Exception as e:
            logger.error(
                f"Error finding Unknown category for card_member {card_member}: {e}"
            )
            return None

    def update_expense_assigned_card_member_on_category_change(
        self, expense: Expense, new_category_name: str
    ) -> Expense:
        """
        Update expense assigned_card_member when category is manually changed.

        Args:
            expense: Expense to update
            new_category_name: New category name

        Returns:
            Updated expense with new assigned_card_member
        """
        self._update_assigned_card_member_from_category(expense, new_category_name)
        return expense
