import os
import sys
from datetime import datetime, UTC

import pytest
from click.testing import CliRunner

# Ensure project root is importable when running tests from backend/
CURRENT_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, os.pardir, os.pardir))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from cli.main import cli, ExpenseTrackerClient  # noqa: E402


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


def test_health_positive(runner: CliRunner, monkeypatch: pytest.MonkeyPatch):
    # Arrange: make health_check return True
    monkeypatch.setenv("API_ENDPOINT", "http://localhost:8000")

    def fake_health_check(self: ExpenseTrackerClient) -> bool:  # type: ignore[override]
        return True

    monkeypatch.setattr(ExpenseTrackerClient, "health_check", fake_health_check)

    # Act
    result = runner.invoke(cli, ["health"])

    # Assert
    assert result.exit_code == 0, result.output
    assert "API is healthy" in result.output


def test_test_command_positive(runner: CliRunner, monkeypatch: pytest.MonkeyPatch):
    # Arrange: mock make_request to emulate root endpoint success
    monkeypatch.setenv("API_ENDPOINT", "http://localhost:8000")

    def fake_make_request(self: ExpenseTrackerClient, method: str, path: str, **kwargs):
        assert method == "GET" and path == "/"
        return {"message": "Welcome", "version": "1.0.0"}

    monkeypatch.setattr(ExpenseTrackerClient, "make_request", fake_make_request)

    # Act
    result = runner.invoke(cli, ["test"])

    # Assert
    assert result.exit_code == 0, result.output
    assert "Authentication successful" in result.output
    assert "Message: Welcome" in result.output
    assert "Version: 1.0.0" in result.output


def test_categories_list_positive(runner: CliRunner, monkeypatch: pytest.MonkeyPatch):
    # Arrange: return one category
    monkeypatch.setenv("API_ENDPOINT", "http://localhost:8000")

    created_at = datetime.now(UTC).isoformat()

    def fake_make_request(self: ExpenseTrackerClient, method: str, path: str, **kwargs):
        assert method == "GET" and path == "/categories"
        return [
            {
                "name": "Health",
                "labels": ["Gym"],
                "account_id": "Health John",
                "card_name": "J Doe",
                "active": True,
                "created_at": created_at,
            }
        ]

    monkeypatch.setattr(ExpenseTrackerClient, "make_request", fake_make_request)

    # Act
    result = runner.invoke(cli, ["categories", "list"])

    # Assert
    assert result.exit_code == 0, result.output
    # Table header and row contents
    assert "Categories" in result.output
    assert "Health" in result.output
    assert "Health John" in result.output
    assert "J Doe" in result.output


def test_expenses_list_positive_shows_assigned_member(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
):
    # Arrange: return one expense with assigned_card_member
    monkeypatch.setenv("API_ENDPOINT", "http://localhost:8000")

    now_iso = datetime.now(UTC).isoformat()

    def fake_make_request(self: ExpenseTrackerClient, method: str, path: str, **kwargs):
        assert method == "GET" and path == "/expenses"
        return [
            {
                "expense_id": "12345678-aaaa-bbbb-cccc-1234567890ab",
                "date": now_iso,
                "description": "Coffee at 104",
                "amount": "4.50",
                "category": "JohnSpend",
                "category_hint": ["JohnSpend"],
                "card_member": "J Doe",
                "assigned_card_member": "Jane",
                "created_at": now_iso,
            }
        ]

    monkeypatch.setattr(ExpenseTrackerClient, "make_request", fake_make_request)

    # Act
    result = runner.invoke(cli, ["expenses", "list"])

    # Assert
    assert result.exit_code == 0, result.output
    assert "Expenses (1/1 shown)" in result.output
    assert "Assigned Card Member" in result.output
    assert "Jane" in result.output  # from assigned_card_member


def test_expenses_show_positive(runner: CliRunner, monkeypatch: pytest.MonkeyPatch):
    # Arrange: return expense by ID
    monkeypatch.setenv("API_ENDPOINT", "http://localhost:8000")

    now_iso = datetime.now(UTC).isoformat()
    expense_id = "abcdef12-3456-7890-abcd-ef1234567890"

    def fake_make_request(self: ExpenseTrackerClient, method: str, path: str, **kwargs):
        if method == "GET" and path == f"/expenses/{expense_id}":
            return {
                "expense_id": expense_id,
                "date": now_iso,
                "description": "Amazon Web Services",
                "amount": "12.34",
                "category": "JohnSpend",
                "category_hint": ["JohnSpend"],
                "card_member": "J Doe",
                "assigned_card_member": "J Doe",
                "created_at": now_iso,
            }
        # In case the command tries a follow-up list call (shouldn't if exact match was found)
        if method == "GET" and path == "/expenses":
            return []
        raise AssertionError(f"Unexpected request: {method} {path}")

    monkeypatch.setattr(ExpenseTrackerClient, "make_request", fake_make_request)

    # Act
    result = runner.invoke(cli, ["expenses", "show", expense_id])

    # Assert
    assert result.exit_code == 0, result.output
    assert "Expense Details" in result.output
    assert expense_id in result.output
    assert "Assigned Card Member" in result.output
    assert "Amazon Web Services" in result.output


class TestResolveExpenseId:
    """Test shortened expense ID resolution."""

    def test_resolve_full_id(self, monkeypatch: pytest.MonkeyPatch):
        """Test resolving a full expense ID."""
        from cli.main import resolve_expense_id, ExpenseTrackerClient

        monkeypatch.setenv("API_ENDPOINT", "http://localhost:8000")
        client = ExpenseTrackerClient()

        full_id = "abcdef12-3456-7890-abcd-ef1234567890"

        def fake_make_request(
            self: ExpenseTrackerClient, method: str, path: str, **kwargs
        ):
            if method == "GET" and path == f"/expenses/{full_id}":
                return {"expense_id": full_id, "description": "Test"}
            return None

        monkeypatch.setattr(ExpenseTrackerClient, "make_request", fake_make_request)

        result = resolve_expense_id(client, full_id)
        assert result == full_id

    def test_resolve_partial_id_single_match(self, monkeypatch: pytest.MonkeyPatch):
        """Test resolving a partial ID with single match."""
        from cli.main import resolve_expense_id, ExpenseTrackerClient

        monkeypatch.setenv("API_ENDPOINT", "http://localhost:8000")
        client = ExpenseTrackerClient()

        partial_id = "abcdef12"
        full_id = "abcdef12-3456-7890-abcd-ef1234567890"

        def fake_make_request(
            self: ExpenseTrackerClient, method: str, path: str, **kwargs
        ):
            if method == "GET" and path == f"/expenses/{partial_id}":
                return None  # No exact match
            if method == "GET" and path == "/expenses":
                # Return list of all expenses
                return [
                    {"expense_id": full_id, "description": "Test 1"},
                    {
                        "expense_id": "12345678-1111-2222-3333-444444444444",
                        "description": "Test 2",
                    },
                ]
            return None

        monkeypatch.setattr(ExpenseTrackerClient, "make_request", fake_make_request)

        result = resolve_expense_id(client, partial_id)
        assert result == full_id

    def test_resolve_partial_id_no_match(self, monkeypatch: pytest.MonkeyPatch):
        """Test resolving a partial ID with no match."""
        from cli.main import resolve_expense_id, ExpenseTrackerClient

        monkeypatch.setenv("API_ENDPOINT", "http://localhost:8000")
        client = ExpenseTrackerClient()

        partial_id = "zzzzzzzz"

        def fake_make_request(
            self: ExpenseTrackerClient, method: str, path: str, **kwargs
        ):
            if method == "GET" and path == f"/expenses/{partial_id}":
                return None  # No exact match
            if method == "GET" and path == "/expenses":
                # Return list with no matches
                return [
                    {
                        "expense_id": "abcdef12-3456-7890-abcd-ef1234567890",
                        "description": "Test 1",
                    },
                ]
            return None

        monkeypatch.setattr(ExpenseTrackerClient, "make_request", fake_make_request)

        result = resolve_expense_id(client, partial_id)
        assert result is None

    def test_resolve_partial_id_multiple_matches_exits(
        self, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ):
        """Test that multiple partial ID matches causes exit with error."""
        monkeypatch.setenv("API_ENDPOINT", "http://localhost:8000")

        partial_id = "abc123"

        def fake_make_request(
            self: ExpenseTrackerClient, method: str, path: str, **kwargs
        ):
            if method == "GET" and path == f"/expenses/{partial_id}":
                return None  # No exact match
            if method == "GET" and path == "/expenses":
                # Return multiple matches
                return [
                    {
                        "expense_id": f"{partial_id}11-1111-1111-1111-111111111111",
                        "description": "Test 1",
                    },
                    {
                        "expense_id": f"{partial_id}22-2222-2222-2222-222222222222",
                        "description": "Test 2",
                    },
                ]
            return None

        monkeypatch.setattr(ExpenseTrackerClient, "make_request", fake_make_request)

        # Test with expenses show command which uses resolve_expense_id
        result = runner.invoke(cli, ["expenses", "show", partial_id])

        # Should exit with error
        assert result.exit_code != 0
        assert "Multiple expenses found" in result.output

    def test_update_with_partial_id(
        self, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ):
        """Test expense update works with partial ID."""
        monkeypatch.setenv("API_ENDPOINT", "http://localhost:8000")

        partial_id = "abc123"
        full_id = "abc12345-6789-1234-5678-123456789012"

        def fake_make_request(
            self: ExpenseTrackerClient, method: str, path: str, **kwargs
        ):
            if method == "GET" and path == f"/expenses/{partial_id}":
                return None  # No exact match
            if method == "GET" and path == "/expenses":
                # Single match for partial ID
                return [{"expense_id": full_id, "description": "Test"}]
            if method == "PATCH" and path == f"/expenses/{full_id}":
                # Return updated expense
                return {
                    "expense_id": full_id,
                    "description": "Test",
                    "category": "NewCategory",
                    "assigned_card_member": "T Owner",
                }
            return None

        monkeypatch.setattr(ExpenseTrackerClient, "make_request", fake_make_request)

        result = runner.invoke(
            cli, ["expenses", "update", partial_id, "--category", "NewCategory"]
        )

        assert result.exit_code == 0
        assert "Updated expense" in result.output
        assert full_id in result.output
