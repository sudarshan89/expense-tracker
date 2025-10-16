import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

import click
import requests
import yaml
from aws_requests_auth.aws_auth import AWSRequestsAuth
from dotenv import load_dotenv
from rich.console import Console
from rich.prompt import Confirm
from rich.table import Table

load_dotenv()

console = Console()


def format_date(iso_string: str, date_format: str = "%d/%m/%Y") -> str:
    """Format ISO date string to specified format.

    Args:
        iso_string: ISO format date string (e.g., "2025-01-15T10:30:00")
        date_format: strftime format string (default: dd/mm/yyyy)

    Returns:
        Formatted date string
    """
    return datetime.fromisoformat(iso_string).strftime(date_format)


def load_seed_yaml(seed_file: Optional[str] = None) -> Dict[str, Any]:
    """Load seed data from YAML file.

    Args:
        seed_file: Optional path to custom seed file. If None, uses default seed_data.yaml

    Returns:
        Dict with keys: owners, accounts, categories

    Raises:
        FileNotFoundError: If seed file doesn't exist
        yaml.YAMLError: If YAML file is malformed
    """
    if seed_file:
        yaml_path = Path(seed_file)
    else:
        # Default: look for seed_data.yaml in the same directory as this script
        script_dir = Path(__file__).parent
        yaml_path = script_dir / "seed_data.yaml"

    if not yaml_path.exists():
        raise FileNotFoundError(
            f"Seed file not found: {yaml_path}\n"
            f"Please ensure seed_data.yaml exists or specify a custom file with --seed-file"
        )

    try:
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        # Validate required keys
        required_keys = ["owners", "accounts", "categories"]
        missing_keys = [key for key in required_keys if key not in data]
        if missing_keys:
            raise ValueError(
                f"Seed file missing required keys: {missing_keys}. "
                f"Expected keys: {required_keys}"
            )

        return data

    except yaml.YAMLError as e:
        console.print(f"[red]Error parsing YAML file: {e}[/red]")
        raise


class ExpenseTrackerClient:
    def __init__(self):
        self.api_endpoint = os.getenv("API_ENDPOINT")
        self.aws_access_key_id = os.getenv("AWS_ACCESS_KEY_ID")
        self.aws_secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY")
        self.aws_region = os.getenv("AWS_REGION", "ap-southeast-2")

        # Check if running in local development mode
        self.is_local = self._is_local_development()

        if self.is_local:
            # Local development mode - no AWS authentication required
            console.print("[yellow]Running in local development mode[/yellow]")
            self.auth = None
        else:
            # Production mode - require AWS credentials
            if not all(
                [self.api_endpoint, self.aws_access_key_id, self.aws_secret_access_key]
            ):
                console.print(
                    "[red]Error: Missing required environment variables[/red]"
                )
                console.print(
                    "Required: API_ENDPOINT, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY"
                )
                sys.exit(1)

            self.auth = AWSRequestsAuth(
                aws_access_key=self.aws_access_key_id,
                aws_secret_access_key=self.aws_secret_access_key,
                aws_token=os.getenv("AWS_SESSION_TOKEN"),
                aws_host=self.api_endpoint.replace("https://", "")
                .replace("http://", "")
                .rstrip("/"),
                aws_region=self.aws_region,
                aws_service="execute-api",
            )

    def _is_local_development(self) -> bool:
        """Detect if running in local development mode."""
        if not self.api_endpoint:
            return False
        return (
            self.api_endpoint.startswith("http://localhost")
            or self.api_endpoint.startswith("http://127.0.0.1")
            or os.getenv("ENVIRONMENT") == "local"
        )

    def make_request(
        self, method: str, path: str, quiet: bool = False, **kwargs
    ) -> Optional[dict]:
        """Make an authenticated request to API.

        Args:
            method: HTTP method
            path: API path
            quiet: If True, suppress error messages (for expected failures)
            **kwargs: Additional arguments for requests
        """
        url = f"{self.api_endpoint.rstrip('/')}{path}"

        try:
            if self.is_local:
                # Local development - no authentication
                response = requests.request(method, url, **kwargs)
            else:
                # Production - use AWS SigV4 authentication
                response = requests.request(method, url, auth=self.auth, **kwargs)

            response.raise_for_status()

            if response.headers.get("content-type", "").startswith("application/json"):
                return response.json()
            return {"message": response.text}

        except requests.exceptions.HTTPError as e:
            if not quiet:
                console.print(
                    f"[red]HTTP Error {e.response.status_code}: {e.response.text}[/red]"
                )
            return None
        except Exception as e:
            if not quiet:
                console.print(f"[red]Error: {str(e)}[/red]")
            return None

    def make_request_with_files(
        self, method: str, path: str, files: dict
    ) -> Optional[dict]:
        """Make an authenticated request with file upload."""
        url = f"{self.api_endpoint.rstrip('/')}{path}"

        try:
            if self.is_local:
                # Local development - no authentication
                response = requests.request(method, url, files=files)
            else:
                # Production - use AWS SigV4 authentication
                response = requests.request(method, url, auth=self.auth, files=files)

            response.raise_for_status()

            if response.headers.get("content-type", "").startswith("application/json"):
                return response.json()
            return {"message": response.text}

        except requests.exceptions.HTTPError as e:
            console.print(
                f"[red]HTTP Error {e.response.status_code}: {e.response.text}[/red]"
            )
            return None
        except Exception as e:
            console.print(f"[red]Error: {str(e)}[/red]")
            return None

    def health_check(self) -> bool:
        """Check API health status."""
        console.print(
            f"Checking API health status...:Endpoint {str(self.api_endpoint)} Access Key {str(self.aws_access_key_id)}"
        )
        result = self.make_request("GET", "/health")
        if result:
            table = Table(title="API Health Check")
            table.add_column("Field", style="cyan")
            table.add_column("Value", style="magenta")

            table.add_row("Status", result.get("status", "unknown"))
            table.add_row("Timestamp", result.get("timestamp", "unknown"))
            table.add_row("Version", result.get("version", "unknown"))

            console.print(table)
            return result.get("status") == "healthy"
        return False


def resolve_expense_id(client: ExpenseTrackerClient, expense_id: str) -> Optional[str]:
    """Resolve a partial or full expense ID to a full expense ID.

    Args:
        client: ExpenseTrackerClient instance
        expense_id: Full or partial expense ID (8 chars or less for partial)

    Returns:
        Full expense ID if found, None otherwise.

    Raises click.ClickException on ambiguous partial matches.
    """
    # First try exact match (quietly, as we expect this might fail for partial IDs)
    result = client.make_request("GET", f"/expenses/{expense_id}", quiet=True)
    if result:
        return result["expense_id"]

    # If not found and it looks like a partial ID (8 chars or less), try to find it
    if len(expense_id) <= 8:
        # Enforce a minimal length to avoid overly broad scans
        if len(expense_id) < 3:
            raise click.ClickException("Partial ID must be at least 3 characters")

        # 1) Try optimized search endpoint first
        matches = client.make_request(
            "GET", "/expenses/search", params={"prefix": expense_id}, quiet=True
        )

        # 2) If search endpoint not available or returned nothing, fall back to listing
        if not matches:
            all_expenses = client.make_request("GET", "/expenses", quiet=True) or []
            matches = [
                e for e in all_expenses if str(e.get("expense_id", "")).startswith(expense_id)
            ]

        if matches:
            if len(matches) == 1:
                return matches[0]["expense_id"]
            else:
                # Multiple matches found — surface a clear error so callers don't add their own
                ids = ", ".join(m.get("expense_id", "") for m in matches)
                raise click.ClickException(
                    f"Multiple expenses found matching '{expense_id}': {ids}"
                )

    return None


@click.group()
@click.version_option(version="1.0.0")
def cli():
    """Expense Tracker CLI - Personal expense categorization system."""
    pass


@cli.command()
def health():
    """Check API health status."""
    client = ExpenseTrackerClient()
    if client.health_check():
        console.print("[green]✓ API is healthy[/green]")
    else:
        console.print("[red]✗ API health check failed[/red]")
        sys.exit(1)


@cli.command()
def test():
    """Test authenticated API connection."""
    client = ExpenseTrackerClient()
    result = client.make_request("GET", "/")

    if result:
        console.print("[green]✓ Authentication successful[/green]")
        console.print(f"Message: {result.get('message', 'No message')}")
        console.print(f"Version: {result.get('version', 'Unknown')}")
    else:
        console.print("[red]✗ Authentication failed[/red]")
        sys.exit(1)


# Owner Commands
@cli.group()
def owners():
    """Owner management commands."""
    pass


@owners.command("create")
@click.option("--name", required=True, help="Owner name")
@click.option("--card-name", required=True, help="Name as appears on card")
def create_owner(name: str, card_name: str):
    """Create a new owner."""
    client = ExpenseTrackerClient()

    owner_data = {"name": name, "card_name": card_name}

    result = client.make_request("POST", "/owners", json=owner_data)
    if result:
        console.print(f"[green]✓ Created owner: {result['name']}[/green]")
        console.print(f"Card Name: {result['card_name']}")
    else:
        console.print("[red]✗ Failed to create owner[/red]")
        sys.exit(1)


@owners.command("list")
def list_owners():
    """List all owners."""
    client = ExpenseTrackerClient()

    result = client.make_request("GET", "/owners")
    if result is not None:
        if not result:
            console.print("No owners found")
            return

        table = Table(title="Owners")
        table.add_column("Name", style="cyan")
        table.add_column("Card Name", style="magenta")
        table.add_column("Created", style="yellow")

        for owner in result:
            created_date = datetime.fromisoformat(owner["created_at"]).strftime(
                "%Y-%m-%d"
            )
            table.add_row(owner["name"], owner["card_name"], created_date)

        console.print(table)
    else:
        console.print("[red]✗ Failed to retrieve owners[/red]")
        sys.exit(1)


# Account Commands
@cli.group()
def accounts():
    """Account management commands."""
    pass


@accounts.command("create")
@click.option("--account-name", required=True, help="Account name")
@click.option("--bank-name", required=True, help="Bank name")
@click.option("--owner-name", required=True, help="Owner name")
@click.option("--active/--inactive", default=True, help="Account active status")
def create_account(account_name: str, bank_name: str, owner_name: str, active: bool):
    """Create a new account."""
    client = ExpenseTrackerClient()

    account_data = {
        "account_name": account_name,
        "bank_name": bank_name,
        "owner_name": owner_name,
        "active": active,
    }

    result = client.make_request("POST", "/accounts", json=account_data)
    if result:
        console.print(
            f"[green]✓ Created account: {result['account_name']} ({result['owner_name']})[/green]"
        )
        console.print(f"Bank: {result['bank_name']}")
        console.print(f"Active: {result['active']}")
    else:
        console.print("[red]✗ Failed to create account[/red]")
        sys.exit(1)


@accounts.command("list")
@click.option("--owner-name", help="Filter by owner name")
def list_accounts(owner_name: Optional[str]):
    """List all accounts, optionally filtered by owner."""
    client = ExpenseTrackerClient()

    params = {}
    if owner_name:
        params["owner_name"] = owner_name

    result = client.make_request("GET", "/accounts", params=params)
    if result is not None:
        if not result:
            console.print("No accounts found")
            return

        table = Table(title="Accounts")
        table.add_column("Account Name", style="cyan")
        table.add_column("Bank", style="magenta")
        table.add_column("Owner", style="yellow")
        table.add_column("Active", style="green")
        table.add_column("Created", style="blue")

        for account in result:
            created_date = datetime.fromisoformat(account["created_at"]).strftime(
                "%Y-%m-%d"
            )
            active_status = "✓" if account["active"] else "✗"
            table.add_row(
                account["account_name"],
                account["bank_name"],
                account["owner_name"],
                active_status,
                created_date,
            )

        console.print(table)
    else:
        console.print("[red]✗ Failed to retrieve accounts[/red]")
        sys.exit(1)


@accounts.command("deactivate")
@click.argument("account_id")
def deactivate_account(account_id: str):
    """Deactivate an account by account_id (format: 'account_name owner_name')."""
    client = ExpenseTrackerClient()

    if not Confirm.ask(f"Are you sure you want to deactivate account '{account_id}'?"):
        console.print("Operation cancelled")
        return

    result = client.make_request("PATCH", f"/accounts/{account_id}/deactivate")
    if result:
        console.print(
            f"[green]✓ Deactivated account: {result['account_name']} ({result['owner_name']})[/green]"
        )
    else:
        console.print("[red]✗ Failed to deactivate account[/red]")
        sys.exit(1)


# Category Commands
@cli.group()
def categories():
    """Category management commands."""
    pass


@categories.command("create")
@click.option("--name", required=True, help="Category name")
@click.option("--labels", help="Comma-separated list of labels")
@click.option(
    "--account-id", required=True, help="Account ID (format: 'account_name owner_name')"
)
@click.option(
    "--card-name",
    required=False,
    help="Card name (defaults to inferred from account_id)",
)
@click.option("--active/--inactive", default=True, help="Category active status")
def create_category(
    name: str,
    labels: Optional[str],
    account_id: str,
    card_name: Optional[str],
    active: bool,
):
    """Create a new category."""
    client = ExpenseTrackerClient()

    label_list = []
    if labels:
        label_list = [label.strip() for label in labels.split(",") if label.strip()]

    # If card_name not provided, attempt to infer as the last token of account_id.
    # Note: This is a best-effort fallback for convenience and tests; provide --card-name to be explicit.
    inferred_card_name = card_name
    if not inferred_card_name and account_id:
        parts = account_id.split()
        if parts:
            inferred_card_name = parts[-1]

    category_data = {
        "name": name,
        "labels": label_list,
        "account_id": account_id,
        "card_name": inferred_card_name,
        "active": active,
    }

    result = client.make_request("POST", "/categories", json=category_data)
    if result:
        console.print(f"[green]✓ Created category: {result['name']}[/green]")
        console.print(f"Account: {result['account_id']}")
        console.print(f"Card Member: {result.get('card_name', '-')}")
        console.print(
            f"Labels: {', '.join(result['labels']) if result['labels'] else 'None'}"
        )
    else:
        console.print("[red]✗ Failed to create category[/red]")
        sys.exit(1)


@categories.command("list")
@click.option("--account-id", help="Filter by account ID")
def list_categories(account_id: Optional[str]):
    """List all categories, optionally filtered by account."""
    client = ExpenseTrackerClient()

    params = {}
    if account_id:
        params["account_id"] = account_id

    result = client.make_request("GET", "/categories", params=params)
    if result is not None:
        if not result:
            console.print("No categories found")
            return

        table = Table(title="Categories")
        table.add_column("Name", style="cyan")
        table.add_column("Account", style="magenta")
        table.add_column("Card Member", style="blue")
        table.add_column("Labels", style="yellow")
        table.add_column("Active", style="green")
        table.add_column("Created", style="white")

        for category in result:
            created_date = datetime.fromisoformat(category["created_at"]).strftime(
                "%Y-%m-%d"
            )
            active_status = "✓" if category["active"] else "✗"
            labels_str = ", ".join(category["labels"]) if category["labels"] else "None"
            card_member = category.get("card_name") or "-"
            table.add_row(
                category["name"],
                category["account_id"],
                card_member,
                labels_str,
                active_status,
                created_date,
            )

        console.print(table)
    else:
        console.print("[red]✗ Failed to retrieve categories[/red]")
        sys.exit(1)


@categories.command("update-labels")
@click.argument("name")
@click.option("--labels", required=True, help="Comma-separated list of labels")
def update_category_labels(name: str, labels: str):
    """Update category labels."""
    client = ExpenseTrackerClient()

    label_list = [label.strip() for label in labels.split(",") if label.strip()]

    update_data = {"labels": label_list}

    result = client.make_request(
        "PATCH", f"/categories/{name}/labels", json=update_data
    )
    if result:
        console.print(f"[green]✓ Updated category labels: {result['name']}[/green]")
        console.print(
            f"New labels: {', '.join(result['labels']) if result['labels'] else 'None'}"
        )
    else:
        console.print("[red]✗ Failed to update category labels[/red]")
        sys.exit(1)


@categories.command("deactivate")
@click.argument("name")
def deactivate_category(name: str):
    """Deactivate a category."""
    client = ExpenseTrackerClient()

    if not Confirm.ask(f"Are you sure you want to deactivate category '{name}'?"):
        console.print("Operation cancelled")
        return

    result = client.make_request("PATCH", f"/categories/{name}/deactivate")
    if result:
        console.print(f"[green]✓ Deactivated category: {result['name']}[/green]")
    else:
        console.print("[red]✗ Failed to deactivate category[/red]")
        sys.exit(1)


# Expense Commands
@cli.group()
def expenses():
    """Expense management commands."""
    pass


@expenses.command("create")
@click.option("--date", required=True, help="Expense date (YYYY-MM-DD)")
@click.option("--description", required=True, help="Expense description")
@click.option("--card-member", required=True, help="Card member name")
@click.option("--amount", required=True, type=float, help="Expense amount")
@click.option("--category", help="Category name")
@click.option("--account-number", help="Account number")
@click.option("--account-id", help="Account ID (account_name + space + owner_name)")
def create_expense(
    date: str,
    description: str,
    card_member: str,
    amount: float,
    category: Optional[str],
    account_number: Optional[str],
    account_id: Optional[str],
):
    """Create a new expense."""
    client = ExpenseTrackerClient()

    try:
        expense_date = datetime.fromisoformat(date)
    except ValueError:
        console.print("[red]Invalid date format. Use YYYY-MM-DD[/red]")
        sys.exit(1)

    expense_data = {
        "date": expense_date.isoformat(),
        "description": description,
        "card_member": card_member,
        "amount": str(amount),
    }

    if category:
        expense_data["category"] = category
    if account_number:
        expense_data["account_number"] = account_number
    if account_id:
        expense_data["account_id"] = account_id

    result = client.make_request("POST", "/expenses", json=expense_data)
    if result:
        console.print(f"[green]✓ Created expense: {result['expense_id']}[/green]")
        console.print(f"Description: {result['description']}")
        console.print(f"Amount: ${result['amount']}")
        console.print(f"Date: {result['date']}")
    else:
        console.print("[red]✗ Failed to create expense[/red]")
        sys.exit(1)


@expenses.command("list")
@click.option("--start-date", help="Start date (YYYY-MM-DD)")
@click.option("--end-date", help="End date (YYYY-MM-DD)")
@click.option("--category", help="Category name")
@click.option("--card-member", help="Card member name")
@click.option("--account-id", help="Account ID (account_name + space + owner_name)")
@click.option("--needs-review", is_flag=True, help="Show only expenses needing review")
@click.option("--limit", type=int, default=20, help="Limit number of results")
def list_expenses(
    start_date: Optional[str],
    end_date: Optional[str],
    category: Optional[str],
    card_member: Optional[str],
    account_id: Optional[str],
    needs_review: bool,
    limit: int,
):
    """List expenses with optional filtering."""
    client = ExpenseTrackerClient()

    params = {}
    if start_date:
        try:
            params["start_date"] = datetime.fromisoformat(start_date).isoformat()
        except ValueError:
            console.print("[red]Invalid start date format. Use YYYY-MM-DD[/red]")
            sys.exit(1)

    if end_date:
        try:
            params["end_date"] = datetime.fromisoformat(end_date).isoformat()
        except ValueError:
            console.print("[red]Invalid end date format. Use YYYY-MM-DD[/red]")
            sys.exit(1)

    if category:
        params["category"] = category
    if card_member:
        params["card_member"] = card_member
    if account_id:
        params["account_id"] = account_id
    if needs_review:
        params["needs_review"] = True

    result = client.make_request("GET", "/expenses", params=params)
    if result is not None:
        if not result:
            console.print("No expenses found")
            return

        # Limit results for display
        expenses_to_show = result[:limit] if len(result) > limit else result

        table = Table(title=f"Expenses ({len(expenses_to_show)}/{len(result)} shown)")
        table.add_column("ID", style="cyan", max_width=8)
        table.add_column("Date", style="yellow")
        table.add_column("Description", style="white", max_width=30)
        table.add_column("Amount", style="green")
        table.add_column("Category", style="magenta")
        table.add_column("Category Hints", style="magenta", max_width=30)
        table.add_column("Card Member", style="blue", no_wrap=True)
        table.add_column("Assigned Card Member", style="blue", no_wrap=True)

        for expense in expenses_to_show:
            expense_date = datetime.fromisoformat(expense["date"]).strftime("%Y-%m-%d")
            description = (
                expense["description"][:27] + "..."
                if len(expense["description"]) > 30
                else expense["description"]
            )
            category = expense.get("category") or "None"
            hints = expense.get("category_hint")
            category_hints = ", ".join(hints) if hints else "-"
            assigned = expense.get("assigned_card_member") or expense.get("card_member")
            table.add_row(
                expense["expense_id"][:8],
                expense_date,
                description,
                f"${expense['amount']}",
                category,
                category_hints,
                expense["card_member"],
                assigned,
            )

        console.print(table)

        if len(result) > limit:
            console.print(
                f"[yellow]Showing {limit} of {len(result)} expenses. Use --limit to show more.[/yellow]"
            )
    else:
        console.print("[red]✗ Failed to retrieve expenses[/red]")
        sys.exit(1)


@expenses.command("update")
@click.argument("expense_id")
@click.option("--category", help="New category")
@click.option("--assigned-card-member", help="New assigned card member")
def update_expense(
    expense_id: str, category: Optional[str], assigned_card_member: Optional[str]
):
    """Update expense category or assigned card member."""
    client = ExpenseTrackerClient()

    if not category and not assigned_card_member:
        console.print("[red]Must specify at least one field to update[/red]")
        sys.exit(1)

    # Resolve partial ID to full ID
    full_expense_id = resolve_expense_id(client, expense_id)
    if not full_expense_id:
        console.print(f"[red]✗ Expense '{expense_id}' not found[/red]")
        sys.exit(1)

    update_data = {}
    if category:
        update_data["category"] = category
    if assigned_card_member:
        update_data["assigned_card_member"] = assigned_card_member

    result = client.make_request(
        "PATCH", f"/expenses/{full_expense_id}", json=update_data
    )
    if result:
        console.print(f"[green]✓ Updated expense: {result['expense_id']}[/green]")
        console.print(f"Category: {result.get('category', 'None')}")
        console.print(f"Assigned Card Member: {result['assigned_card_member']}")
    else:
        console.print("[red]✗ Failed to update expense[/red]")
        sys.exit(1)


@expenses.command("update-card-member")
@click.argument("expense_id")
@click.argument("card_member")
def update_expense_card_member(expense_id: str, card_member: str):
    """Update expense assigned card member using dedicated endpoint."""
    client = ExpenseTrackerClient()

    # Resolve partial ID to full ID
    full_expense_id = resolve_expense_id(client, expense_id)
    if not full_expense_id:
        console.print(f"[red]✗ Expense '{expense_id}' not found[/red]")
        sys.exit(1)

    update_data = {"assigned_card_member": card_member}
    result = client.make_request(
        "PATCH", f"/expenses/{full_expense_id}/assigned-card-member", json=update_data
    )

    if result:
        console.print(
            f"[green]✓ Updated assigned card member for expense: {result['expense_id']}[/green]"
        )
        console.print(f"Assigned Card Member: {result['assigned_card_member']}")
    else:
        console.print("[red]✗ Failed to update assigned card member[/red]")
        sys.exit(1)


@expenses.command("bulk-update")
@click.option("--category", required=True, help="Category to assign to all expenses")
@click.option("--ids", required=True, help="Comma-separated list of expense IDs (full or partial)")
def bulk_update_expenses(category: str, ids: str):
    """Update category for multiple expenses at once.

    Examples:
        # Using full IDs
        expense-tracker expenses bulk-update --category Coffee --ids "abc123...,def456..."

        # Using partial IDs (will auto-resolve)
        expense-tracker expenses bulk-update --category Coffee --ids "abc123,def456,ghi789"
    """
    client = ExpenseTrackerClient()

    # Parse IDs from comma-separated string
    id_list = [id.strip() for id in ids.split(",") if id.strip()]

    if not id_list:
        console.print("[red]No expense IDs provided[/red]")
        sys.exit(1)

    # Resolve partial IDs to full IDs
    console.print(f"[yellow]Resolving {len(id_list)} expense IDs...[/yellow]")
    full_ids = []
    resolution_errors = []

    for expense_id in id_list:
        try:
            full_id = resolve_expense_id(client, expense_id)
            if full_id:
                full_ids.append(full_id)
            else:
                resolution_errors.append(f"Not found: {expense_id}")
        except click.ClickException as e:
            resolution_errors.append(f"{expense_id}: {str(e)}")

    # Show resolution errors if any
    if resolution_errors:
        console.print("\n[red]ID Resolution Errors:[/red]")
        for error in resolution_errors:
            console.print(f"  • {error}")

        if not full_ids:
            console.print("[red]No valid expense IDs found[/red]")
            sys.exit(1)

        console.print(f"\n[yellow]Proceeding with {len(full_ids)} valid IDs[/yellow]")

    # Show preview of what will be updated
    console.print(f"\n[bold]Update Preview:[/bold]")
    console.print(f"  Category: [cyan]{category}[/cyan]")
    console.print(f"  Expense Count: [yellow]{len(full_ids)}[/yellow]")
    console.print(f"  IDs: {', '.join([id[:8] + '...' for id in full_ids[:5]])}")
    if len(full_ids) > 5:
        console.print(f"       ... and {len(full_ids) - 5} more")

    # Confirmation prompt
    if not Confirm.ask(f"\nUpdate {len(full_ids)} expense(s) to category '{category}'?"):
        console.print("Operation cancelled")
        return

    # Update each expense by calling existing endpoint
    console.print(f"\n[yellow]Updating expenses...[/yellow]")
    success_count = 0
    failure_count = 0
    failures = []

    for expense_id in full_ids:
        update_data = {"category": category}
        result = client.make_request(
            "PATCH", f"/expenses/{expense_id}", json=update_data, quiet=True
        )

        if result:
            success_count += 1
            console.print(f"  [green]✓ {expense_id[:8]}...[/green]")
        else:
            failure_count += 1
            failures.append(expense_id)
            console.print(f"  [red]✗ {expense_id[:8]}... (failed)[/red]")

    # Display summary
    console.print(f"\n[bold]Bulk Update Results:[/bold]")
    console.print(f"  Total: {len(full_ids)}")
    console.print(f"  [green]Success: {success_count}[/green]")
    console.print(f"  [red]Failed: {failure_count}[/red]")

    if failure_count > 0:
        console.print("\n[red]Failed IDs:[/red]")
        for failed_id in failures:
            console.print(f"  • {failed_id[:8]}...")

    if success_count > 0:
        console.print(f"\n[green]✓ Successfully updated {success_count} expense(s)[/green]")

    if failure_count > 0:
        sys.exit(1)


@expenses.command("delete")
@click.argument("expense_id")
def delete_expense(expense_id: str):
    """Delete an expense."""
    client = ExpenseTrackerClient()

    # Resolve partial ID to full ID
    full_expense_id = resolve_expense_id(client, expense_id)
    if not full_expense_id:
        console.print(f"[red]✗ Expense '{expense_id}' not found[/red]")
        sys.exit(1)

    if not Confirm.ask(
        f"Are you sure you want to delete expense '{full_expense_id[:8]}...'?"
    ):
        console.print("Operation cancelled")
        return

    response = client.make_request("DELETE", f"/expenses/{full_expense_id}")
    # DELETE returns 204 No Content, so response will be None on success
    if (
        response is not None
        or client.make_request("GET", f"/expenses/{full_expense_id}") is None
    ):
        console.print(f"[green]✓ Deleted expense: {full_expense_id[:8]}...[/green]")
    else:
        console.print("[red]✗ Failed to delete expense[/red]")
        sys.exit(1)


@expenses.command("show")
@click.argument("expense_id")
def show_expense(expense_id: str):
    """Show detailed information for a specific expense."""
    client = ExpenseTrackerClient()

    # Resolve partial ID to full ID
    full_expense_id = resolve_expense_id(client, expense_id)
    if not full_expense_id:
        console.print(f"[red]✗ Expense '{expense_id}' not found[/red]")
        sys.exit(1)

    # Get the full expense details
    result = client.make_request("GET", f"/expenses/{full_expense_id}")
    if result:
        # Create a detailed table for the expense
        actual_expense_id = result["expense_id"]
        table = Table(title=f"Expense Details: {actual_expense_id}")
        table.add_column("Field", style="cyan", min_width=20)
        table.add_column("Value", style="white", min_width=30)

        # Core Information
        table.add_row("[bold]CORE INFORMATION[/bold]", "")
        table.add_row("Expense ID", result["expense_id"])
        expense_date = datetime.fromisoformat(result["date"]).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        table.add_row("Date", expense_date)
        table.add_row("Description", result["description"])
        table.add_row("Amount", f"${result['amount']}")

        # Card Information
        table.add_row("", "")  # Spacer
        table.add_row("[bold]CARD INFORMATION[/bold]", "")
        table.add_row("Card Member", result["card_member"])
        table.add_row(
            "Assigned Card Member", result.get("assigned_card_member", "None")
        )

        # Transaction Details
        table.add_row("", "")  # Spacer
        table.add_row("[bold]TRANSACTION DETAILS[/bold]", "")
        table.add_row("Account Number", result.get("account_number") or "None")
        table.add_row("Extended Details", result.get("extended_details") or "None")
        table.add_row(
            "Appears On Statement As", result.get("appears_on_statement_as") or "None"
        )
        table.add_row("Reference", result.get("reference") or "None")

        # Location Information
        if any(
            [
                result.get("address"),
                result.get("city_state"),
                result.get("zip_code"),
                result.get("country"),
            ]
        ):
            table.add_row("", "")  # Spacer
            table.add_row("[bold]LOCATION INFORMATION[/bold]", "")
            table.add_row("Address", result.get("address") or "None")
            table.add_row("City/State", result.get("city_state") or "None")
            table.add_row("Zip Code", result.get("zip_code") or "None")
            table.add_row("Country", result.get("country") or "None")

        # Categorization Information
        table.add_row("", "")  # Spacer
        table.add_row("[bold]CATEGORIZATION[/bold]", "")
        table.add_row("Category", result.get("category") or "None")

        # Category hints (list)
        category_hints = result.get("category_hint")
        if category_hints and isinstance(category_hints, list):
            hints_str = ", ".join(category_hints)
        else:
            hints_str = "None"
        table.add_row("Category Hints", hints_str)

        # Auto-categorization status
        is_auto = result.get("is_auto_categorized", False)
        table.add_row("Auto-Categorized", "✓ Yes" if is_auto else "✗ No")

        needs_review = result.get("needs_review", False)
        table.add_row("Needs Review", "⚠️ Yes" if needs_review else "✓ No")

        # Metadata
        table.add_row("", "")  # Spacer
        table.add_row("[bold]METADATA[/bold]", "")
        created_date = datetime.fromisoformat(result["created_at"]).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        table.add_row("Created At", created_date)

        console.print(table)
    else:
        console.print(f"[red]✗ Failed to retrieve expense details[/red]")
        sys.exit(1)


@expenses.command("upload-csv")
@click.argument("file_path", type=click.Path(exists=True))
def upload_csv(file_path: str):
    """Upload CSV file containing expenses."""
    client = ExpenseTrackerClient()

    console.print(f"Uploading CSV file: {file_path}")

    try:
        with open(file_path, "rb") as f:
            files = {"file": (os.path.basename(file_path), f, "text/csv")}

            # Make request with files parameter instead of json
            response = client.make_request_with_files(
                "POST", "/expenses/upload", files=files
            )

        if response:
            if response.get("success"):
                console.print(f"[green]✓ {response['message']}[/green]")
                if response.get("processed_count", 0) > 0:
                    console.print(
                        f"Successfully processed {response['processed_count']} expenses"
                    )
            else:
                console.print(f"[yellow]! {response['message']}[/yellow]")

            # Show errors if any
            if response.get("errors"):
                console.print("\n[red]Errors encountered:[/red]")
                for error in response["errors"]:
                    console.print(f"  • {error}")

        else:
            console.print("[red]✗ Failed to upload CSV file[/red]")
            sys.exit(1)

    except Exception as e:
        console.print(f"[red]Error reading file: {str(e)}[/red]")
        sys.exit(1)


# Reports Commands
@cli.group(invoke_without_command=True)
@click.pass_context
@click.option("--start-date", help="Start date (YYYY-MM-DD)")
@click.option("--end-date", help="End date (YYYY-MM-DD)")
@click.option(
    "--month",
    help="Month filter (3-letter abbreviation: Jan, Feb, etc.). Defaults to previous month. Overrides start/end dates.",
)
@click.option("--category", help="Category name")
@click.option("--assigned-card-member", help="Assigned card member name")
@click.option("--needs-review", is_flag=True, help="Show only expenses needing review")
@click.option("--summary", is_flag=True, help="Show summary only (no expense details)")
def reports(
    ctx,
    start_date: Optional[str],
    end_date: Optional[str],
    month: Optional[str],
    category: Optional[str],
    assigned_card_member: Optional[str],
    needs_review: bool,
    summary: bool,
):
    """Generate expense reports.

    Defaults to 'by-account' report if no subcommand is specified.
    The report groups expenses by assigned_card_member (not original card_member).
    Use --month for quick date filtering (11th to 11th window), or --start-date/--end-date for custom ranges.
    By default, reports for the previous month.
    """
    if ctx.invoked_subcommand is None:
        # No subcommand specified, invoke by-account with the provided options
        ctx.invoke(
            report_by_account,
            start_date=start_date,
            end_date=end_date,
            month=month,
            category=category,
            assigned_card_member=assigned_card_member,
            needs_review=needs_review,
            summary=summary,
        )


@reports.command("by-account")
@click.option("--start-date", help="Start date (YYYY-MM-DD)")
@click.option("--end-date", help="End date (YYYY-MM-DD)")
@click.option(
    "--month",
    help="Month filter (3-letter abbreviation: Jan, Feb, etc.). Defaults to previous month. Overrides start/end dates.",
)
@click.option("--category", help="Category name")
@click.option("--assigned-card-member", help="Assigned card member name")
@click.option("--needs-review", is_flag=True, help="Show only expenses needing review")
@click.option("--summary", is_flag=True, help="Show summary only (no expense details)")
def report_by_account(
    start_date: Optional[str],
    end_date: Optional[str],
    month: Optional[str],
    category: Optional[str],
    assigned_card_member: Optional[str],
    needs_review: bool,
    summary: bool,
):
    """Generate expense report grouped by account.

    The report groups expenses by assigned_card_member (not original card_member).
    Use --month for quick date filtering (11th to 11th window), or --start-date/--end-date for custom ranges.
    By default, reports for the previous month.
    """
    client = ExpenseTrackerClient()

    # Calculate previous month as default if no date filters provided
    if not month and not start_date and not end_date:
        from datetime import datetime as dt

        now = dt.now()
        # Get previous month
        prev_month = now.month - 1 if now.month > 1 else 12
        month_names = [
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "May",
            "Jun",
            "Jul",
            "Aug",
            "Sep",
            "Oct",
            "Nov",
            "Dec",
        ]
        month = month_names[prev_month - 1]

    # Build query parameters
    params = {}
    if month:
        params["month"] = month
    else:
        if start_date:
            try:
                params["start_date"] = datetime.fromisoformat(start_date).isoformat()
            except ValueError:
                console.print("[red]Invalid start date format. Use YYYY-MM-DD[/red]")
                sys.exit(1)

        if end_date:
            try:
                params["end_date"] = datetime.fromisoformat(end_date).isoformat()
            except ValueError:
                console.print("[red]Invalid end date format. Use YYYY-MM-DD[/red]")
                sys.exit(1)

    if category:
        params["category"] = category
    if assigned_card_member:
        params["assigned_card_member"] = assigned_card_member
    if needs_review:
        params["needs_review"] = True

    # Make API request
    result = client.make_request("GET", "/reports/expenses-by-account", params=params)

    if not result:
        console.print("[red]✗ Failed to generate report[/red]")
        sys.exit(1)

    # Display report
    console.print(f"\n[bold blue]Expenses by Account Report[/bold blue]")

    if month:
        console.print(f"Month Filter: {month.capitalize()}")

    if result.get("start_date"):
        console.print(f"Start Date: {format_date(result['start_date'])}")
    if result.get("end_date"):
        console.print(f"End Date: {format_date(result['end_date'])}")

    console.print(
        f"Total Amount: [green]${float(result.get('total_amount', 0)):.2f}[/green]"
    )
    console.print(f"Total Expenses: {result.get('total_expenses', 0)}")

    if assigned_card_member:
        console.print(f"Filtered by Assigned Card Member: {assigned_card_member}")

    account_groups = result.get("account_groups", [])

    if not account_groups:
        console.print("\n[yellow]No expenses found matching the criteria[/yellow]")
        return

    # Group accounts by owner
    from itertools import groupby

    grouped_by_owner = groupby(account_groups, key=lambda x: x["owner_name"])

    for owner_name, owner_groups in grouped_by_owner:
        owner_groups_list = list(owner_groups)

        # Print owner header
        console.print(f"\n[bold magenta]{'='*60}[/bold magenta]")
        console.print(f"[bold magenta]Owner: {owner_name}[/bold magenta]")
        console.print(f"[bold magenta]{'='*60}[/bold magenta]")

        # Create summary table for this owner
        summary_table = Table(title=f"{owner_name}'s Accounts")
        summary_table.add_column("Account", style="cyan", min_width=25)
        summary_table.add_column("Count", justify="right", style="white")
        summary_table.add_column("Total Amount", justify="right", style="green")

        for group in owner_groups_list:
            summary_table.add_row(
                group["account_name"],
                str(group["expense_count"]),
                f"${float(group['total_amount']):.2f}",
            )

        console.print(summary_table)

        # Calculate and display owner total
        owner_total = sum(float(group["total_amount"]) for group in owner_groups_list)
        console.print(
            f"[bold yellow]{owner_name} Total: ${owner_total:.2f}[/bold yellow]\n"
        )

        # Show detailed expenses if not summary mode
        if not summary:
            for group in owner_groups_list:
                console.print(f"\n[bold cyan]{group['account_name']}[/bold cyan]")
                console.print(
                    f"Count: {group['expense_count']} | Total: [green]${float(group['total_amount']):.2f}[/green]"
                )

                expense_table = Table()
                expense_table.add_column("Date", style="yellow", min_width=10)
                expense_table.add_column("Description", style="white", max_width=40)
                expense_table.add_column(
                    "Amount", justify="right", style="green", min_width=10
                )
                expense_table.add_column("Category", style="magenta", max_width=15)

                for expense in group["expenses"]:
                    expense_table.add_row(
                        format_date(expense["date"]),
                        expense["description"][:40]
                        + ("..." if len(expense["description"]) > 40 else ""),
                        f"${abs(float(expense['amount'])):.2f}",
                        expense.get("category", "Unknown"),
                    )

                console.print(expense_table)


# Seed Data Command
@cli.command()
@click.option(
    "--seed-file",
    type=click.Path(exists=True),
    help="Path to custom seed YAML file (default: cli/seed_data.yaml)",
)
def seed(seed_file: Optional[str] = None):
    """Seed database with all data from YAML file.

    Seeds all available entities in dependency order (owners → accounts → categories).

    Examples:
        expense-tracker seed                         # Use default seed_data.yaml
        expense-tracker seed --seed-file=custom.yaml # Use custom YAML file
    """
    # Load seed data
    try:
        seed_data = load_seed_yaml(seed_file)
    except (FileNotFoundError, yaml.YAMLError, ValueError) as e:
        console.print(f"[red]Error loading seed data: {e}[/red]")
        sys.exit(1)

    console.print("[bold blue]Starting database seed...[/bold blue]\n")

    client = ExpenseTrackerClient()
    results = {}

    # Seed in dependency order: owners → accounts → categories
    entity_order = ["owners", "accounts", "categories"]

    for entity_type in entity_order:
        if entity_type not in seed_data:
            continue

        entity_data = seed_data[entity_type]
        if not entity_data:
            continue

        entity_label = entity_type.capitalize()
        console.print(f"[bold]{entity_label}:[/bold]")
        created_count = 0
        skipped_count = 0

        if entity_type == "owners":
            for item in entity_data:
                result = client.make_request("POST", "/owners", json=item)
                if result:
                    console.print(f"  [green]✓ {result['name']}[/green]")
                    created_count += 1
                else:
                    console.print(f"  [dim]- {item['name']} (already exists)[/dim]")
                    skipped_count += 1

        elif entity_type == "accounts":
            for item in entity_data:
                result = client.make_request("POST", "/accounts", json=item)
                if result:
                    console.print(
                        f"  [green]✓ {result['account_name']} ({result['owner_name']})[/green]"
                    )
                    created_count += 1
                else:
                    console.print(
                        f"  [dim]- {item['account_name']} {item['owner_name']} (already exists)[/dim]"
                    )
                    skipped_count += 1

        elif entity_type == "categories":
            for item in entity_data:
                result = client.make_request("POST", "/categories", json=item)
                if result:
                    console.print(f"  [green]✓ {result['name']}[/green]")
                    created_count += 1
                else:
                    console.print(f"  [dim]- {item['name']} (already exists)[/dim]")
                    skipped_count += 1

        results[entity_type] = {
            "total": len(entity_data),
            "created": created_count,
            "skipped": skipped_count,
        }
        console.print(
            f"  [blue]{created_count} created, {skipped_count} skipped[/blue]\n"
        )

    # Summary
    console.print("[bold green]✓ Seed complete![/bold green]")
    console.print("\n[bold]Summary:[/bold]")
    for entity_type, stats in results.items():
        console.print(
            f"  {entity_type.capitalize()}: {stats['created']}/{stats['total']} created"
        )


if __name__ == "__main__":
    cli()
