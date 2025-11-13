"""DynamoDB helper functions for expense tracker.

Direct CRUD operations without repository abstraction.
"""

import logging
from datetime import datetime
from decimal import Decimal
from functools import reduce
from typing import Dict, List, Optional

from boto3.dynamodb.conditions import Attr, Key
from botocore.exceptions import ClientError

from core.database import DynamoDBSetup
from core.models import (
    Account,
    AccountCreate,
    AccountUpdate,
    Category,
    CategoryCreate,
    CategoryUpdate,
    Expense,
    ExpenseCreate,
    ExpenseFilter,
    ExpenseUpdate,
    Owner,
    OwnerCreate,
)
from services.categorization_service import normalize_text

logger = logging.getLogger(__name__)

# Initialize database singleton
_db_setup = DynamoDBSetup()
_table = _db_setup.get_table()

# Cache for owner card names
_card_names_cache: Optional[List[str]] = None


def _handle_error(error: ClientError, operation: str) -> None:
    """Handle and log DynamoDB client errors."""
    error_code = error.response["Error"]["Code"]
    logger.error(f"DynamoDB {operation} failed: {error_code} - {error}")

    if error_code == "ConditionalCheckFailedException":
        raise ValueError("Item already exists or condition not met")
    elif error_code == "ResourceNotFoundException":
        raise ValueError("Item not found")
    else:
        raise RuntimeError(f"Database operation failed: {error_code}")


def _invalidate_card_names_cache() -> None:
    """Invalidate the card names cache."""
    global _card_names_cache
    _card_names_cache = None


# ============================================================================
# OWNER OPERATIONS
# ============================================================================


def create_owner(owner_data: OwnerCreate) -> Optional[Owner]:
    """Create a new owner (immutable entity)."""
    owner = Owner(**owner_data.model_dump())

    try:
        _table.put_item(
            Item={
                "PK": owner.get_pk(),
                "SK": owner.get_sk(),
                "EntityType": "Owner",
                "name": owner.name,
                "card_name": owner.card_name,
                "created_at": owner.created_at.isoformat(),
            },
            ConditionExpression="attribute_not_exists(PK)",
        )
        logger.info(f"Created owner: {owner.name}")
        _invalidate_card_names_cache()
        return owner
    except ClientError as e:
        _handle_error(e, "create owner")


def get_owner(name: str) -> Optional[Owner]:
    """Get owner by name."""
    try:
        response = _table.get_item(Key={"PK": f"OWNER#{name}", "SK": f"OWNER#{name}"})

        if "Item" in response:
            item = response["Item"]
            return Owner(
                name=item["name"],
                card_name=item["card_name"],
                created_at=datetime.fromisoformat(item["created_at"]),
            )
        return None
    except ClientError as e:
        _handle_error(e, "get owner")


def list_owners() -> Optional[List[Owner]]:
    """List all owners."""
    try:
        response = _table.scan(FilterExpression=Attr("EntityType").eq("Owner"))

        owners = []
        for item in response["Items"]:
            owners.append(
                Owner(
                    name=item["name"],
                    card_name=item["card_name"],
                    created_at=datetime.fromisoformat(item["created_at"]),
                )
            )

        owners.sort(key=lambda x: x.created_at)
        return owners
    except ClientError as e:
        _handle_error(e, "list owners")


def get_card_names() -> List[str]:
    """Get all card names from owners (cached)."""
    global _card_names_cache

    if _card_names_cache is not None:
        return _card_names_cache

    owners = list_owners()
    if not owners:
        _card_names_cache = []
    else:
        _card_names_cache = [owner.card_name for owner in owners]

    return _card_names_cache


# ============================================================================
# ACCOUNT OPERATIONS
# ============================================================================


def create_account(account_data: AccountCreate) -> Optional[Account]:
    """Create a new account."""
    account = Account(**account_data.model_dump())

    # Build GSI1 keys for querying accounts by owner
    gsi1_pk = f"OWNER#{account.owner_name}"
    gsi1_sk = f"ACCOUNT#{account.account_name}"

    try:
        _table.put_item(
            Item={
                "PK": account.get_pk(),
                "SK": account.get_sk(),
                "EntityType": "Account",
                "account_name": account.account_name,
                "bank_name": account.bank_name,
                "owner_name": account.owner_name,
                "card_member": account.card_member,
                "active": account.active,
                "created_at": account.created_at.isoformat(),
                "GSI1PK": gsi1_pk,
                "GSI1SK": gsi1_sk,
            },
            ConditionExpression="attribute_not_exists(PK)",
        )
        logger.info(f"Created account: {account.account_name} for {account.owner_name}")
        return account
    except ClientError as e:
        _handle_error(e, "create account")


def get_account(account_id: str) -> Optional[Account]:
    """Get account by ID (account_name + space + owner_name)."""
    try:
        parts = account_id.split(" ", 1)
        if len(parts) != 2:
            return None

        account_name, owner_name = parts
        response = _table.get_item(
            Key={
                "PK": f"ACCOUNT#{account_name}#{owner_name}",
                "SK": f"ACCOUNT#{account_name}#{owner_name}",
            }
        )

        if "Item" in response:
            item = response["Item"]
            return Account(
                account_name=item["account_name"],
                bank_name=item["bank_name"],
                owner_name=item["owner_name"],
                card_member=item["card_member"],
                active=item.get("active", True),
                created_at=datetime.fromisoformat(item["created_at"]),
            )
        return None
    except ClientError as e:
        _handle_error(e, "get account")


def list_accounts(owner_name: Optional[str] = None) -> Optional[List[Account]]:
    """List all accounts, optionally filtered by owner."""
    try:
        if owner_name:
            # Use GSI1 to query accounts by owner
            response = _table.query(
                IndexName="GSI1",
                KeyConditionExpression=Key("GSI1PK").eq(f"OWNER#{owner_name}")
                & Key("GSI1SK").begins_with("ACCOUNT#"),
            )
        else:
            # Scan all accounts
            response = _table.scan(FilterExpression=Attr("EntityType").eq("Account"))

        accounts = []
        for item in response["Items"]:
            accounts.append(
                Account(
                    account_name=item["account_name"],
                    bank_name=item["bank_name"],
                    owner_name=item["owner_name"],
                    card_member=item["card_member"],
                    active=item.get("active", True),
                    created_at=datetime.fromisoformat(item["created_at"]),
                )
            )

        accounts.sort(key=lambda x: x.created_at)
        return accounts
    except ClientError as e:
        _handle_error(e, "list accounts")


def update_account(account_id: str, update_data: AccountUpdate) -> Optional[Account]:
    """Update account (active status only)."""
    account = get_account(account_id)
    if not account:
        return None

    pk = account.get_pk()
    sk = account.get_sk()

    try:
        response = _table.update_item(
            Key={"PK": pk, "SK": sk},
            UpdateExpression="SET active = :active",
            ExpressionAttributeValues={":active": update_data.active},
            ConditionExpression="attribute_exists(PK)",
            ReturnValues="ALL_NEW",
        )

        item = response["Attributes"]
        return Account(
            account_name=item["account_name"],
            bank_name=item["bank_name"],
            owner_name=item["owner_name"],
            card_member=item["card_member"],
            active=item["active"],
            created_at=datetime.fromisoformat(item["created_at"]),
        )
    except ClientError as e:
        _handle_error(e, "update account")


# ============================================================================
# CATEGORY OPERATIONS
# ============================================================================


def create_category(category_data: CategoryCreate) -> Optional[Category]:
    """Create a new category."""
    category = Category(**category_data.model_dump())

    try:
        _table.put_item(
            Item={
                "PK": category.get_pk(),
                "SK": category.get_sk(),
                "EntityType": "Category",
                "name": category.name,
                "labels": category.labels,
                "account_id": category.account_id,
                "card_name": category.card_name,
                "active": category.active,
                "created_at": category.created_at.isoformat(),
            },
            ConditionExpression="attribute_not_exists(PK)",
        )
        logger.info(f"Created category: {category.name}")
        return category
    except ClientError as e:
        _handle_error(e, "create category")


def get_category(name: str) -> Optional[Category]:
    """Get category by name."""
    try:
        response = _table.get_item(
            Key={"PK": f"CATEGORY#{name}", "SK": f"CATEGORY#{name}"}
        )

        if "Item" in response:
            item = response["Item"]
            return Category(
                name=item["name"],
                labels=item.get("labels", []),
                account_id=item["account_id"],
                card_name=item["card_name"],
                active=item.get("active", True),
                created_at=datetime.fromisoformat(item["created_at"]),
            )
        return None
    except ClientError as e:
        _handle_error(e, "get category")


def list_categories(account_id: Optional[str] = None) -> Optional[List[Category]]:
    """List all categories, optionally filtered by account."""
    try:
        response = _table.scan(FilterExpression=Attr("EntityType").eq("Category"))

        categories = []
        for item in response["Items"]:
            category = Category(
                name=item["name"],
                labels=item.get("labels", []),
                account_id=item["account_id"],
                card_name=item["card_name"],
                active=item.get("active", True),
                created_at=datetime.fromisoformat(item["created_at"]),
            )

            if account_id is None or category.account_id == account_id:
                categories.append(category)

        categories.sort(key=lambda x: x.created_at)
        return categories
    except ClientError as e:
        _handle_error(e, "list categories")


def update_category(name: str, update_data: CategoryUpdate) -> Optional[Category]:
    """Update category (labels and active status only)."""
    category = get_category(name)
    if not category:
        return None

    pk = category.get_pk()
    sk = category.get_sk()

    # Build update expression
    update_expressions = []
    expression_values = {}

    if update_data.labels is not None:
        update_expressions.append("labels = :labels")
        expression_values[":labels"] = update_data.labels

    if update_data.active is not None:
        update_expressions.append("active = :active")
        expression_values[":active"] = update_data.active

    if not update_expressions:
        return category

    try:
        response = _table.update_item(
            Key={"PK": pk, "SK": sk},
            UpdateExpression=f"SET {', '.join(update_expressions)}",
            ExpressionAttributeValues=expression_values,
            ConditionExpression="attribute_exists(PK)",
            ReturnValues="ALL_NEW",
        )

        item = response["Attributes"]
        return Category(
            name=item["name"],
            labels=item.get("labels", []),
            account_id=item["account_id"],
            card_name=item["card_name"],
            active=item["active"],
            created_at=datetime.fromisoformat(item["created_at"]),
        )
    except ClientError as e:
        _handle_error(e, "update category")


# ============================================================================
# EXPENSE OPERATIONS
# ============================================================================


def _item_to_expense(item: Dict) -> Expense:
    """Convert DynamoDB item to Expense model."""
    return Expense(
        expense_id=item["expense_id"],
        date=datetime.fromisoformat(item["date"]),
        description=item["description"],
        card_member=item["card_member"],
        assigned_card_member=item.get("assigned_card_member"),
        account_number=item.get("account_number"),
        account_id=item.get("account_id"),
        amount=Decimal(item["amount"]),
        extended_details=item.get("extended_details"),
        appears_on_statement_as=item.get("appears_on_statement_as"),
        address=item.get("address"),
        city_state=item.get("city_state"),
        zip_code=item.get("zip_code"),
        country=item.get("country"),
        reference=item.get("reference"),
        category_hint=item.get("category_hint"),
        category=item.get("category"),
        is_auto_categorized=item.get("is_auto_categorized", False),
        needs_review=item.get("needs_review", False),
        created_at=datetime.fromisoformat(item["created_at"]),
    )


def _validate_card_member(card_member: str) -> None:
    """Validate that card_member exists in Owner entities."""
    valid_card_names = get_card_names()

    if not valid_card_names:
        raise ValueError("No owners found in system")

    if card_member not in valid_card_names:
        raise ValueError(
            f"Invalid card_member '{card_member}'. Must match an existing Owner.card_name: {valid_card_names}"
        )


def create_expense(expense_data: ExpenseCreate) -> Optional[Expense]:
    """Create a new expense."""
    expense = Expense(**expense_data.model_dump())

    # Prepare item for DynamoDB
    item = {
        "PK": expense.get_pk(),
        "SK": expense.get_sk(),
        "EntityType": "Expense",
        "expense_id": expense.expense_id,
        "date": expense.date.isoformat(),
        "description": expense.description,
        "card_member": expense.card_member,
        "assigned_card_member": expense.assigned_card_member,
        "amount": str(expense.amount),
        "is_auto_categorized": expense.is_auto_categorized,
        "needs_review": expense.needs_review,
        "created_at": expense.created_at.isoformat(),
    }

    # Add optional fields
    optional_fields = [
        "account_number",
        "account_id",
        "extended_details",
        "appears_on_statement_as",
        "address",
        "city_state",
        "zip_code",
        "country",
        "reference",
        "category_hint",
    ]
    for field in optional_fields:
        value = getattr(expense, field)
        if value is not None:
            item[field] = value

    # Add category if assigned
    if expense.category:
        item["category"] = expense.category

    try:
        _table.put_item(Item=item)
        logger.info(f"Created expense: {expense.expense_id}")
        return expense
    except ClientError as e:
        _handle_error(e, "create expense")


def update_expense_from_csv(expense_id: str, expense_data: ExpenseCreate) -> Optional[Expense]:
    """Update an existing expense from CSV upload data (overwrites all fields except expense_id and created_at)."""
    # First get the existing expense to preserve its ID and created_at
    existing_expense = get_expense(expense_id)
    if not existing_expense:
        return None

    # Create updated expense object, preserving expense_id and created_at from existing
    updated_expense = Expense(
        expense_id=existing_expense.expense_id,
        created_at=existing_expense.created_at,
        **expense_data.model_dump()
    )

    # Prepare complete item for DynamoDB (full overwrite)
    item = {
        "PK": updated_expense.get_pk(),
        "SK": updated_expense.get_sk(),
        "EntityType": "Expense",
        "expense_id": updated_expense.expense_id,
        "date": updated_expense.date.isoformat(),
        "description": updated_expense.description,
        "card_member": updated_expense.card_member,
        "assigned_card_member": updated_expense.assigned_card_member,
        "amount": str(updated_expense.amount),
        "is_auto_categorized": updated_expense.is_auto_categorized,
        "needs_review": updated_expense.needs_review,
        "created_at": updated_expense.created_at.isoformat(),
    }

    # Add optional fields
    optional_fields = [
        "account_number",
        "account_id",
        "extended_details",
        "appears_on_statement_as",
        "address",
        "city_state",
        "zip_code",
        "country",
        "reference",
        "category_hint",
    ]
    for field in optional_fields:
        value = getattr(updated_expense, field)
        if value is not None:
            item[field] = value

    # Add category if assigned
    if updated_expense.category:
        item["category"] = updated_expense.category

    try:
        _table.put_item(Item=item)
        logger.info(f"Updated expense from CSV: {expense_id}")
        return updated_expense
    except ClientError as e:
        _handle_error(e, "update expense from CSV")


def get_expense(expense_id: str) -> Optional[Expense]:
    """Get expense by ID using direct get_item."""
    try:
        response = _table.get_item(
            Key={"PK": f"EXPENSE#{expense_id}", "SK": f"EXPENSE#{expense_id}"}
        )

        if "Item" in response:
            return _item_to_expense(response["Item"])
        return None
    except ClientError as e:
        _handle_error(e, "get expense")


def get_expense_by_reference(reference: str) -> Optional[Expense]:
    """Get expense by reference field using ReferenceIndex GSI."""
    if not reference or not reference.strip():
        return None

    try:
        response = _table.query(
            IndexName="ReferenceIndex",
            KeyConditionExpression=Key("reference").eq(reference.strip())
        )

        if response["Items"]:
            # Return the first matching expense (should only be one)
            return _item_to_expense(response["Items"][0])
        return None
    except ClientError as e:
        _handle_error(e, "get expense by reference")


def search_expenses_by_id_prefix(prefix: str) -> List[Expense]:
    """Search expenses whose IDs start with a prefix.

    Performs a single table scan with a begins_with filter and caps
    the response at 1,000 items. Pagination via LastEvaluatedKey is not
    followed, so callers should treat the result as best-effort rather than
    exhaustive when large datasets are present.
    """
    if not prefix:
        return []

    try:
        response = _table.scan(
            FilterExpression=Attr("expense_id").begins_with(prefix), Limit=1000
        )
        expenses = [_item_to_expense(item) for item in response["Items"]]
        expenses.sort(key=lambda e: e.date, reverse=True)
        return expenses
    except ClientError as e:
        _handle_error(e, "search expenses by prefix")
        return []


def list_expenses(expense_filter: ExpenseFilter) -> Optional[List[Expense]]:
    """List expenses with filtering support (uses table scan)."""
    try:
        # Build filter expression - start with expense key prefix
        filter_conditions = [Attr("PK").begins_with("EXPENSE#")]

        if expense_filter.start_date:
            filter_conditions.append(
                Attr("date").gte(expense_filter.start_date.isoformat())
            )

        if expense_filter.end_date:
            filter_conditions.append(
                Attr("date").lte(expense_filter.end_date.isoformat())
            )

        if expense_filter.account_id:
            filter_conditions.append(Attr("account_id").eq(expense_filter.account_id))

        if expense_filter.category:
            filter_conditions.append(Attr("category").eq(expense_filter.category))

        if expense_filter.assigned_card_member:
            # DynamoDB filter is case-sensitive, will normalize in memory
            filter_conditions.append(Attr("assigned_card_member").exists())

        if expense_filter.needs_review is not None:
            filter_conditions.append(
                Attr("needs_review").eq(expense_filter.needs_review)
            )

        # Combine all conditions with AND
        filter_expr = reduce(lambda a, b: a & b, filter_conditions)

        # Scan table with filter
        response = _table.scan(FilterExpression=filter_expr)
        expenses = [_item_to_expense(item) for item in response["Items"]]

        # Handle normalized card_member filtering in memory
        if expense_filter.assigned_card_member:
            normalized_filter = normalize_text(expense_filter.assigned_card_member)
            expenses = [
                e
                for e in expenses
                if normalize_text(e.assigned_card_member) == normalized_filter
            ]

        # Sort by date: newest to oldest
        expenses.sort(key=lambda e: e.date, reverse=True)

        logger.info(f"Retrieved {len(expenses)} expenses")
        return expenses
    except ClientError as e:
        _handle_error(e, "list expenses")


def update_expense(expense_id: str, update_data: ExpenseUpdate) -> Optional[Expense]:
    """Update expense (assigned_card_member and category only)."""
    from services.categorization_service import AutoCategorizationService

    # First find the expense to get its PK/SK
    expense = get_expense(expense_id)
    if not expense:
        return None

    # Validate assigned_card_member if provided
    if update_data.assigned_card_member is not None:
        _validate_card_member(update_data.assigned_card_member)

    pk = expense.get_pk()
    sk = expense.get_sk()

    # Build update expression
    update_expressions = []
    expression_values = {}

    # Handle category update with automatic assigned_card_member update
    if update_data.category is not None:
        # Look up the new category to get its account_id
        new_category = get_category(update_data.category)
        if not new_category:
            raise ValueError(f"Category '{update_data.category}' not found")

        # Update assigned_card_member based on new category's card_name
        categorization_service = AutoCategorizationService()
        updated_expense = categorization_service.update_expense_assigned_card_member_on_category_change(
            expense, update_data.category
        )

        update_expressions.append("category = :category")
        update_expressions.append("assigned_card_member = :assigned_card_member")
        update_expressions.append("account_id = :account_id")
        update_expressions.append("needs_review = :needs_review")
        expression_values[":category"] = update_data.category
        expression_values[":assigned_card_member"] = (
            updated_expense.assigned_card_member
        )
        expression_values[":account_id"] = new_category.account_id
        expression_values[":needs_review"] = False

    # Handle direct assigned_card_member update (only if category is not being updated)
    elif update_data.assigned_card_member is not None:
        update_expressions.append("assigned_card_member = :assigned_card_member")
        expression_values[":assigned_card_member"] = update_data.assigned_card_member

    if not update_expressions:
        return expense

    try:
        response = _table.update_item(
            Key={"PK": pk, "SK": sk},
            UpdateExpression=f"SET {', '.join(update_expressions)}",
            ExpressionAttributeValues=expression_values,
            ConditionExpression="attribute_exists(PK)",
            ReturnValues="ALL_NEW",
        )

        return _item_to_expense(response["Attributes"])
    except ClientError as e:
        _handle_error(e, "update expense")


def delete_expense(expense_id: str) -> Optional[bool]:
    """Delete expense by ID."""
    expense = get_expense(expense_id)
    if not expense:
        return False

    try:
        _table.delete_item(
            Key={"PK": expense.get_pk(), "SK": expense.get_sk()},
            ConditionExpression="attribute_exists(PK)",
        )
        logger.info(f"Deleted expense: {expense_id}")
        return True
    except ClientError as e:
        _handle_error(e, "delete expense")
