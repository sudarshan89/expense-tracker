from datetime import datetime, UTC
from decimal import Decimal
from typing import List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


class Owner(BaseModel):
    """Owner entity - immutable after creation."""

    name: str = Field(..., description="Unique owner name")
    card_name: str = Field(..., description="Name as appears on card")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("name")
    def name_must_not_be_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("Owner name cannot be empty")
        return value.strip()

    @field_validator("card_name")
    def card_name_must_not_be_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("Card name cannot be empty")
        return value.strip()

    def get_pk(self) -> str:
        return f"OWNER#{self.name}"

    def get_sk(self) -> str:
        return f"OWNER#{self.name}"


class OwnerCreate(BaseModel):
    """Request model for creating a new owner."""

    name: str
    card_name: str


class Account(BaseModel):
    """Account entity."""

    account_name: str = Field(..., description="Account name")
    bank_name: str = Field(..., description="Bank name")
    owner_name: str = Field(..., description="Owner name (foreign key)")
    card_member: str = Field(
        ..., description="Card member name (must match Owner.card_name)"
    )
    active: bool = Field(default=True, description="Account active status")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("account_name")
    def account_name_must_not_be_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("Account name cannot be empty")
        return value.strip()

    @field_validator("bank_name")
    def bank_name_must_not_be_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("Bank name cannot be empty")
        return value.strip()

    @field_validator("owner_name")
    def owner_name_must_not_be_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("Owner name cannot be empty")
        return value.strip()

    @field_validator("card_member")
    def card_member_must_not_be_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("Card member cannot be empty")
        return value.strip()

    def get_pk(self) -> str:
        return f"ACCOUNT#{self.account_name}#{self.owner_name}"

    def get_sk(self) -> str:
        return f"ACCOUNT#{self.account_name}#{self.owner_name}"

    def get_account_id(self) -> str:
        """Unique account identifier: account_name + space + owner_name."""
        return f"{self.account_name} {self.owner_name}"


class AccountCreate(BaseModel):
    """Request model for creating a new account."""

    account_name: str
    bank_name: str
    owner_name: str
    card_member: str
    active: bool = True


class AccountUpdate(BaseModel):
    """Request model for updating an account (only active status)."""

    active: bool


class Category(BaseModel):
    """Category entity."""

    name: str = Field(..., description="Unique category name")
    labels: List[str] = Field(
        default_factory=list, description="List of labels for auto-categorization"
    )
    account_id: str = Field(
        ..., description="Associated account ID (account_name + space + owner_name)"
    )
    card_name: str = Field(
        ..., description="Card name (foreign key to Owner.card_name)"
    )
    active: bool = Field(default=True, description="Category active status")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("name")
    def name_must_not_be_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("Category name cannot be empty")
        return value.strip()

    @field_validator("account_id")
    def account_id_must_not_be_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("Account ID cannot be empty")
        return value.strip()

    @field_validator("card_name")
    def card_name_must_not_be_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("Card name cannot be empty")
        return value.strip()

    @field_validator("labels")
    def labels_must_be_clean(cls, value: Optional[List[str]]) -> List[str]:
        if value is None:
            return []
        # Remove empty strings and strip whitespace
        return [label.strip() for label in value if label and label.strip()]

    def get_pk(self) -> str:
        return f"CATEGORY#{self.name}"

    def get_sk(self) -> str:
        return f"CATEGORY#{self.name}"


class CategoryCreate(BaseModel):
    """Request model for creating a new category."""

    name: str
    labels: List[str] = Field(default_factory=list)
    account_id: str
    card_name: str
    active: bool = True


class CategoryUpdate(BaseModel):
    """Request model for updating a category (labels and active status only)."""

    labels: Optional[List[str]] = None
    active: Optional[bool] = None


class Expense(BaseModel):
    """Expense entity with time-based partitioning."""

    expense_id: str = Field(
        default_factory=lambda: str(uuid4()), description="Unique expense ID"
    )
    date: datetime = Field(..., description="Expense date")
    description: str = Field(..., description="Expense description")
    card_member: str = Field(..., description="Card member name")
    assigned_card_member: Optional[str] = Field(
        None, description="Assigned card member (defaults to card_member)"
    )
    account_number: Optional[str] = Field(None, description="Account number")
    account_id: Optional[str] = Field(
        None, description="Associated account ID (account_name + space + owner_name)"
    )
    amount: Decimal = Field(..., description="Expense amount")
    extended_details: Optional[str] = Field(None, description="Extended details")
    appears_on_statement_as: Optional[str] = Field(
        None, description="Appears on statement as"
    )
    address: Optional[str] = Field(None, description="Address")
    city_state: Optional[str] = Field(None, description="City/State")
    zip_code: Optional[str] = Field(None, description="Zip code")
    country: Optional[str] = Field(None, description="Country")
    reference: Optional[str] = Field(None, description="Reference")
    category_hint: Optional[List[str]] = Field(
        None,
        description="Category hint candidates from auto-categorization (becomes required list after auto-categorization)",
    )
    category: Optional[str] = Field(None, description="Derived/assigned category")
    is_auto_categorized: bool = Field(
        default=False, description="Whether category was auto-assigned"
    )
    needs_review: bool = Field(
        default=False, description="Whether expense needs manual review"
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def set_assigned_card_member_default(self):
        if self.assigned_card_member is None:
            self.assigned_card_member = self.card_member
        return self

    @model_validator(mode="after")
    def enforce_category_hint_requirement(self):
        """Enforce rule: category_hint becomes required (non-null list) after auto-categorization."""
        if self.is_auto_categorized and self.category_hint is None:
            self.category_hint = []
        return self

    @field_validator("description")
    def description_must_not_be_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("Description cannot be empty")
        return value.strip()

    @field_validator("card_member")
    def card_member_must_not_be_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("Card member cannot be empty")
        return value.strip()

    def get_pk(self) -> str:
        """Primary key: EXPENSE#{expense_id}."""
        return f"EXPENSE#{self.expense_id}"

    def get_sk(self) -> str:
        """Sort key: EXPENSE#{expense_id} (same as PK for direct lookups)."""
        return f"EXPENSE#{self.expense_id}"


class ExpenseCreate(BaseModel):
    """Request model for creating a new expense."""

    date: datetime
    description: str
    card_member: str
    assigned_card_member: Optional[str] = None
    account_number: Optional[str] = None
    account_id: Optional[str] = None
    amount: Decimal
    extended_details: Optional[str] = None
    appears_on_statement_as: Optional[str] = None
    address: Optional[str] = None
    city_state: Optional[str] = None
    zip_code: Optional[str] = None
    country: Optional[str] = None
    reference: Optional[str] = None
    category_hint: Optional[List[str]] = None
    category: Optional[str] = None
    is_auto_categorized: bool = False
    needs_review: bool = False


class ExpenseUpdate(BaseModel):
    """Request model for updating an expense (assigned_card_member and category only)."""

    assigned_card_member: Optional[str] = None
    category: Optional[str] = None


class ExpenseAssignedCardMemberUpdate(BaseModel):
    """Request model for updating only assigned_card_member field."""

    assigned_card_member: str


class ExpenseFilter(BaseModel):
    """Filter model for expense queries."""

    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    account_id: Optional[str] = None
    category: Optional[str] = None
    assigned_card_member: Optional[str] = None
    needs_review: Optional[bool] = None


class AccountExpenseGroup(BaseModel):
    """Model for expenses grouped by account."""

    account_id: str = Field(
        ..., description="Account ID (account_name + space + owner_name)"
    )
    account_name: str = Field(..., description="Account name")
    owner_name: str = Field(..., description="Owner name")
    total_amount: Decimal = Field(..., description="Total amount for this account")
    expense_count: int = Field(..., description="Number of expenses")
    expenses: List[Expense] = Field(
        ..., description="List of expenses for this account"
    )


class ExpensesByAccountReport(BaseModel):
    """Report model for expenses grouped by account."""

    start_date: Optional[datetime] = Field(None, description="Report start date")
    end_date: Optional[datetime] = Field(None, description="Report end date")
    total_amount: Decimal = Field(..., description="Total amount across all accounts")
    total_expenses: int = Field(..., description="Total number of expenses")
    account_groups: List[AccountExpenseGroup] = Field(
        ..., description="Expense groups by account"
    )
