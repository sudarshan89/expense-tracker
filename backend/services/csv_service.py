import csv
import logging
from datetime import datetime
from decimal import Decimal
from io import StringIO
from typing import List, Dict, Tuple

from core.models import ExpenseCreate

logger = logging.getLogger(__name__)


def parse_csv_expenses(csv_content: str) -> Tuple[List[ExpenseCreate], List[str]]:
    """
    Parse CSV content and return expense data and any errors.

    Args:
        csv_content: Raw CSV file content as string

    Returns:
        Tuple of (list of ExpenseCreate objects, list of error messages)
    """
    expenses = []
    errors = []

    try:
        csv_reader = csv.DictReader(StringIO(csv_content))

        # Check if required headers exist
        required_headers = {"Date", "Description", "Card Member", "Amount"}
        if not required_headers.issubset(set(csv_reader.fieldnames or [])):
            missing = required_headers - set(csv_reader.fieldnames or [])
            errors.append(f"Missing required CSV headers: {', '.join(missing)}")
            return expenses, errors

        for row_num, row in enumerate(
            csv_reader, start=2
        ):  # Start at 2 for header line
            try:
                expense = _parse_expense_row(row)
                expenses.append(expense)
            except Exception as e:
                errors.append(f"Row {row_num}: {str(e)}")

    except Exception as e:
        errors.append(f"Failed to parse CSV: {str(e)}")

    return expenses, errors


def _parse_expense_row(row: Dict[str, str]) -> ExpenseCreate:
    """Parse a single CSV row into an ExpenseCreate object."""

    # Parse date - expect DD/MM/YYYY format
    date_str = row.get("Date", "").strip()
    if not date_str:
        raise ValueError("Date is required")

    try:
        parsed_date = datetime.strptime(date_str, "%d/%m/%Y")
    except ValueError:
        raise ValueError(f"Invalid date format '{date_str}'. Expected DD/MM/YYYY")

    # Parse amount
    amount_str = row.get("Amount", "").strip()
    if not amount_str:
        raise ValueError("Amount is required")

    try:
        # Remove currency symbols and commas
        amount_clean = amount_str.replace("$", "").replace(",", "").strip()
        amount = Decimal(amount_clean)
    except (ValueError, TypeError):
        raise ValueError(f"Invalid amount format '{amount_str}'")

    # Required fields
    description = row.get("Description", "").strip()
    if not description:
        raise ValueError("Description is required")

    card_member = row.get("Card Member", "").strip()
    if not card_member:
        raise ValueError("Card Member is required")

    # Optional fields
    account_number = row.get("Account #", "").strip() or None
    extended_details = row.get("Extended Details", "").strip() or None
    appears_on_statement_as = (
        row.get("Appears On Your Statement As", "").strip() or None
    )
    address = row.get("Address", "").strip() or None
    city_state = row.get("City/State", "").strip() or None
    zip_code = row.get("Zip Code", "").strip() or None
    country = row.get("Country", "").strip() or None
    reference = row.get("Reference", "").strip() or None
    category_hint_str = row.get("Category", "").strip()
    category_hint = [category_hint_str] if category_hint_str else None

    return ExpenseCreate(
        date=parsed_date,
        description=description,
        card_member=card_member,
        account_number=account_number,
        amount=amount,
        extended_details=extended_details,
        appears_on_statement_as=appears_on_statement_as,
        address=address,
        city_state=city_state,
        zip_code=zip_code,
        country=country,
        reference=reference,
        category_hint=category_hint,
    )


def validate_csv_file(file_content: bytes, max_size_kb: int = 500) -> List[str]:
    """
    Validate CSV file before processing.

    Args:
        file_content: Raw file content as bytes
        max_size_kb: Maximum file size in KB

    Returns:
        List of validation errors (empty if valid)
    """
    errors = []

    # Check file size
    file_size_kb = len(file_content) / 1024
    if file_size_kb > max_size_kb:
        errors.append(f"File too large: {file_size_kb:.1f}KB (max {max_size_kb}KB)")

    # Check if file is empty
    if len(file_content) == 0:
        errors.append("File is empty")

    try:
        # Try to decode as UTF-8
        file_content.decode("utf-8")
    except UnicodeDecodeError:
        errors.append("File must be UTF-8 encoded")

    return errors
