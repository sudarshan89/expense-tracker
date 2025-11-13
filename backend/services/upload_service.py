"""Service to handle CSV expense upload processing pipeline.

Encapsulates: validation (pre-done by csv_service), parsing, optional auto-categorization,
 and persistence via repositories. Returns aggregate metrics and errors to be composed by API.
"""

from __future__ import annotations

from typing import List, Tuple

from core.models import Expense, ExpenseCreate
from services import dynamo_expenses as db
from services.categorization_service import AutoCategorizationService
from services.csv_service import parse_csv_expenses


class UploadProcessingService:
    """Orchestrates CSV upload expense processing.

    Keeping all side-effect logic outside API routes improves separation of concerns
    and makes the pipeline easier to test.
    """

    def __init__(self):
        self.categorization = AutoCategorizationService()

    def process_csv_text(self, csv_text: str) -> Tuple[int, int, int, int, int, List[str]]:
        """Process CSV text and persist expenses.

        Returns:
            created_count, updated_count, auto_categorized_count, needs_review_count,
            total_processed_count, all_errors
        """
        expenses, parsing_errors = parse_csv_expenses(csv_text)

        created_count = 0
        updated_count = 0
        auto_categorized_count = 0
        needs_review_count = 0
        processing_errors: List[str] = []

        for expense_data in expenses:
            try:
                # Check if expense with this reference already exists
                existing_expense = None
                if expense_data.reference:
                    existing_expense = db.get_expense_by_reference(expense_data.reference)

                expense = Expense(**expense_data.model_dump())

                # Apply auto-categorization if no category was provided in CSV
                # (both for new and updated expenses)
                if not expense.category:
                    expense = self.categorization.categorize_expense(expense)
                    if expense.is_auto_categorized:
                        auto_categorized_count += 1
                    if expense.needs_review:
                        needs_review_count += 1
                else:
                    # Ensure category_hint present as list if category manually provided
                    expense.category_hint = expense.category_hint or []

                # Persist (create or update)
                if existing_expense:
                    # Update existing expense
                    _ = db.update_expense_from_csv(
                        existing_expense.expense_id,
                        ExpenseCreate(**expense.model_dump(exclude={"expense_id", "created_at"}))
                    )
                    updated_count += 1
                else:
                    # Create new expense
                    _ = db.create_expense(
                        ExpenseCreate(**expense.model_dump(exclude={"expense_id", "created_at"}))
                    )
                    created_count += 1
            except Exception as e:  # pragma: no cover - robust error aggregation
                processing_errors.append(f"Failed to process expense: {str(e)}")

        all_errors = parsing_errors + processing_errors
        total_processed = created_count + updated_count
        return created_count, updated_count, auto_categorized_count, needs_review_count, total_processed, all_errors
