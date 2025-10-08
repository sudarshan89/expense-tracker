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

    def process_csv_text(self, csv_text: str) -> Tuple[int, int, int, List[str]]:
        """Process CSV text and persist expenses.

        Returns:
            processed_count, auto_categorized_count, needs_review_count, all_errors
        """
        expenses, parsing_errors = parse_csv_expenses(csv_text)

        processed_count = 0
        auto_categorized_count = 0
        needs_review_count = 0
        processing_errors: List[str] = []

        for expense_data in expenses:
            try:
                expense = Expense(**expense_data.model_dump())

                # Apply auto-categorization if no category was provided in CSV
                if not expense.category:
                    expense = self.categorization.categorize_expense(expense)
                    if expense.is_auto_categorized:
                        auto_categorized_count += 1
                    if expense.needs_review:
                        needs_review_count += 1
                else:
                    # Ensure category_hint present as list if category manually provided
                    expense.category_hint = expense.category_hint or []

                # Persist
                _ = db.create_expense(
                    ExpenseCreate(**expense.model_dump(exclude={"expense_id"}))
                )
                processed_count += 1
            except Exception as e:  # pragma: no cover - robust error aggregation
                processing_errors.append(f"Failed to create expense: {str(e)}")

        all_errors = parsing_errors + processing_errors
        return processed_count, auto_categorized_count, needs_review_count, all_errors
