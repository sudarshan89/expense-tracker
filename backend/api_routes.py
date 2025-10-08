from __future__ import annotations

import logging
from datetime import datetime, UTC
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request, UploadFile, File, status
from pydantic import BaseModel, Field

from core.models import (
    Account,
    AccountCreate,
    AccountUpdate,
    Category,
    CategoryCreate,
    CategoryUpdate,
    Expense,
    ExpenseAssignedCardMemberUpdate,
    ExpenseCreate,
    ExpenseFilter,
    ExpenseUpdate,
    ExpensesByAccountReport,
    Owner,
    OwnerCreate,
)
from services import dynamo_expenses as db
from services.csv_service import validate_csv_file
from services.reports_service import ReportsService
from services.upload_service import UploadProcessingService

logger = logging.getLogger("expense_tracker.api")
router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    timestamp: str
    version: str
    environment: Optional[str] = None


class UploadResponse(BaseModel):
    success: bool
    message: str
    processed_count: int
    error_count: int
    errors: List[str] = Field(default_factory=list)
    auto_categorized_count: int = 0
    needs_review_count: int = 0


@router.get("/health", response_model=HealthResponse)
async def health_check(request: Request) -> HealthResponse:
    """Health check endpoint for monitoring and validation."""
    logger.info("Health check endpoint called")

    config = getattr(request.app.state, "config", None)
    environment = getattr(config, "environment", None) if config else None
    version = getattr(config, "version", "1.0.0")

    return HealthResponse(
        status="healthy",
        timestamp=datetime.now(UTC).isoformat(),
        version=version,
        environment=environment,
    )


@router.get("/")
async def root(request: Request) -> Dict[str, str]:
    """Root endpoint providing service metadata."""
    config = getattr(request.app.state, "config", None)

    message = getattr(config, "root_message", "Expense Tracker API")
    version = getattr(config, "version", "1.0.0")

    response: Dict[str, str] = {"message": message, "version": version}

    if config and getattr(config, "environment", None):
        response["environment"] = config.environment

    return response


# Owner Management Endpoints (S1.1)
@router.post("/owners", response_model=Owner, status_code=status.HTTP_201_CREATED)
async def create_owner(owner_data: OwnerCreate) -> Owner:
    """Create a new owner (immutable entity)."""
    return db.create_owner(owner_data)


@router.get("/owners", response_model=List[Owner])
async def list_owners() -> List[Owner]:
    """List all owners."""
    return db.list_owners()


@router.get("/owners/{name}", response_model=Owner)
async def get_owner(name: str) -> Owner:
    """Get owner by name."""
    owner = db.get_owner(name)
    if not owner:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Owner '{name}' not found",
        )
    return owner


# Account Management Endpoints (S1.2)
@router.post("/accounts", response_model=Account, status_code=status.HTTP_201_CREATED)
async def create_account(account_data: AccountCreate) -> Account:
    """Create a new account."""
    return db.create_account(account_data)


@router.get("/accounts", response_model=List[Account])
async def list_accounts(owner_name: str = None) -> List[Account]:
    """List all accounts, optionally filtered by owner."""
    return db.list_accounts(owner_name=owner_name)


@router.get("/accounts/{account_id}", response_model=Account)
async def get_account(account_id: str) -> Account:
    """Get account by account_id (account_name + space + owner_name)."""
    account = db.get_account(account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account '{account_id}' not found",
        )
    return account


@router.patch("/accounts/{account_id}/deactivate", response_model=Account)
async def deactivate_account(account_id: str) -> Account:
    """Deactivate an account."""
    update_data = AccountUpdate(active=False)
    account = db.update_account(account_id, update_data)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account '{account_id}' not found",
        )
    return account


# Category Management Endpoints (S1.3)
@router.post(
    "/categories", response_model=Category, status_code=status.HTTP_201_CREATED
)
async def create_category(category_data: CategoryCreate) -> Category:
    """Create a new category."""
    return db.create_category(category_data)


@router.get("/categories", response_model=List[Category])
async def list_categories(account_id: str = None) -> List[Category]:
    """List all categories, optionally filtered by account."""
    return db.list_categories(account_id=account_id)


@router.get("/categories/{name}", response_model=Category)
async def get_category(name: str) -> Category:
    """Get category by name."""
    category = db.get_category(name)
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Category '{name}' not found",
        )
    return category


@router.patch("/categories/{name}/deactivate", response_model=Category)
async def deactivate_category(name: str) -> Category:
    """Deactivate a category."""
    update_data = CategoryUpdate(active=False)
    category = db.update_category(name, update_data)
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Category '{name}' not found",
        )
    return category


@router.patch("/categories/{name}/labels", response_model=Category)
async def update_category_labels(name: str, update_data: CategoryUpdate) -> Category:
    """Update category labels."""
    category = db.update_category(name, update_data)
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Category '{name}' not found",
        )
    return category


# Expense Management Endpoints (S1.4)
@router.post("/expenses", response_model=Expense, status_code=status.HTTP_201_CREATED)
async def create_expense(expense_data: ExpenseCreate) -> Expense:
    """Create a new expense."""
    return db.create_expense(expense_data)


@router.get("/expenses", response_model=List[Expense])
async def list_expenses(
    start_date: datetime = None,
    end_date: datetime = None,
    account_id: str = None,
    category: str = None,
    assigned_card_member: str = None,
    needs_review: bool = None,
) -> List[Expense]:
    """List expenses with optional filtering."""
    expense_filter = ExpenseFilter(
        start_date=start_date,
        end_date=end_date,
        account_id=account_id,
        category=category,
        assigned_card_member=assigned_card_member,
        needs_review=needs_review,
    )
    return db.list_expenses(expense_filter)


@router.get("/expenses/search", response_model=List[Expense])
async def search_expenses(prefix: str) -> List[Expense]:
    """Search expenses by expense_id prefix."""
    if not prefix or len(prefix) < 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Prefix must be at least 3 characters",
        )

    expenses = db.search_expenses_by_id_prefix(prefix)
    return expenses


@router.get("/expenses/{expense_id}", response_model=Expense)
async def get_expense(expense_id: str) -> Expense:
    """Get expense by ID."""
    expense = db.get_expense(expense_id)
    if not expense:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Expense '{expense_id}' not found",
        )
    return expense


@router.patch("/expenses/{expense_id}", response_model=Expense)
async def update_expense(expense_id: str, update_data: ExpenseUpdate) -> Expense:
    """Update expense (assigned_card_member and category only)."""
    expense = db.update_expense(expense_id, update_data)
    if not expense:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Expense '{expense_id}' not found",
        )
    return expense


@router.patch("/expenses/{expense_id}/assigned-card-member", response_model=Expense)
async def update_expense_assigned_card_member(
    expense_id: str, update_data: ExpenseAssignedCardMemberUpdate
) -> Expense:
    """Update expense assigned_card_member field."""
    expense_update = ExpenseUpdate(
        assigned_card_member=update_data.assigned_card_member
    )
    expense = db.update_expense(expense_id, expense_update)
    if not expense:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Expense '{expense_id}' not found",
        )
    return expense


@router.delete("/expenses/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_expense(expense_id: str):
    """Delete expense by ID."""
    deleted = db.delete_expense(expense_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Expense '{expense_id}' not found",
        )


@router.post("/expenses/upload", response_model=UploadResponse)
async def upload_csv_expenses(file: UploadFile = File(...)) -> UploadResponse:
    """Upload and process CSV file containing expenses."""
    # Validate file
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a CSV file",
        )

    # Read file content
    file_content = await file.read()

    # Validate file size and format
    validation_errors = validate_csv_file(file_content)
    if validation_errors:
        return UploadResponse(
            success=False,
            message="File validation failed",
            processed_count=0,
            error_count=len(validation_errors),
            errors=validation_errors,
            auto_categorized_count=0,
            needs_review_count=0,
        )

    # Delegate processing to service
    csv_text = file_content.decode("utf-8")
    processor = UploadProcessingService()
    (
        processed_count,
        auto_categorized_count,
        needs_review_count,
        all_errors,
    ) = processor.process_csv_text(csv_text)
    total_errors = len(all_errors)

    success = total_errors == 0 and processed_count > 0
    message = f"Processed {processed_count} expenses"
    if auto_categorized_count > 0:
        message += f", {auto_categorized_count} auto-categorized"
    if needs_review_count > 0:
        message += f", {needs_review_count} need review"
    if total_errors > 0:
        message += f", {total_errors} errors"

    return UploadResponse(
        success=success,
        message=message,
        processed_count=processed_count,
        error_count=total_errors,
        errors=all_errors[:10],  # Limit to first 10 errors for response size
        auto_categorized_count=auto_categorized_count,
        needs_review_count=needs_review_count,
    )


# Reports endpoints
@router.get("/reports/expenses-by-account", response_model=ExpensesByAccountReport)
async def get_expenses_by_account_report(
    start_date: str = None,
    end_date: str = None,
    category: str = None,
    assigned_card_member: str = None,
    needs_review: bool = None,
    month: str = None,
) -> ExpensesByAccountReport:
    """Generate a report of expenses grouped by account.

    New query parameter:
    - month: Optional 3-letter month abbreviation (e.g., "Jan", "feb", "OCT").
      When provided, the date range will be derived as follows using the current year:
        start_date = 12th of the given month (00:00:00)
        end_date   = 11th of the next month (00:00:00)
      If both month and explicit start/end dates are supplied, month takes precedence.
    """
    # Parse date parameters
    parsed_start_date = None
    parsed_end_date = None

    # If month is provided, derive dates based on the 11th-to-11th window
    if month:
        try:
            parsed_start_date, parsed_end_date = (
                ReportsService.derive_date_range_for_month(month)
            )
        except ValueError as ve:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(ve),
            )
    else:
        if start_date:
            try:
                parsed_start_date = datetime.fromisoformat(start_date)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid start_date format. Use ISO format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)",
                )

        if end_date:
            try:
                parsed_end_date = datetime.fromisoformat(end_date)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid end_date format. Use ISO format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)",
                )

    # Create filter
    expense_filter = ExpenseFilter(
        start_date=parsed_start_date,
        end_date=parsed_end_date,
        category=category,
        assigned_card_member=assigned_card_member,
        needs_review=needs_review,
    )

    # Generate report
    reports_service = ReportsService()
    report = reports_service.get_expenses_by_account_report(expense_filter)

    if report is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate report",
        )

    return report
