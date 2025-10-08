import logging
import os
from typing import Any, Dict, List, Optional, Tuple

# Optional AWS SDK imports: provide fallbacks for local/tests where boto3 isn't installed
try:  # pragma: no cover - exercised implicitly via environment
    import boto3  # type: ignore
    from boto3.dynamodb.conditions import ConditionBase  # type: ignore
    from botocore.exceptions import ClientError  # type: ignore
except Exception:  # pragma: no cover - fallback for test environment without boto3
    boto3 = None  # type: ignore

    class ClientError(Exception):  # minimal compatible stub
        def __init__(self, response: Dict[str, Any], operation_name: str):
            super().__init__(response.get("Error", {}).get("Message", "ClientError"))
            self.response = response
            self.operation_name = operation_name

    class ConditionBase:  # typing stub
        pass

logger = logging.getLogger(__name__)


IN_MEMORY_TABLES: Dict[str, "InMemoryDynamoTable"] = {}


def _raise_client_error(code: str, message: str, operation: str) -> None:
    """Raise a boto-style ClientError for in-memory operations."""

    raise ClientError({"Error": {"Code": code, "Message": message}}, operation)


def _extract_attr_name(candidate: Any) -> str:
    """Extract the attribute/key name from a Dynamo condition operand."""

    return getattr(candidate, "name", "")


def _evaluate_condition(item: Dict[str, Any], condition: ConditionBase) -> bool:
    """Evaluate DynamoDB conditions against a dict.

    Supports: Equals, BeginsWith, GreaterThanEquals, LessThanEquals, And
    """

    condition_type = condition.__class__.__name__
    values = getattr(condition, "_values", ())

    # Handle compound condition
    if condition_type == "And":
        return all(_evaluate_condition(item, sub_condition) for sub_condition in values)

    if not values:
        return False

    attr_name = _extract_attr_name(values[0])
    attr_value = item.get(attr_name)

    # Handle comparison conditions
    if condition_type == "Equals":
        return attr_value == values[1]
    if condition_type == "BeginsWith":
        prefix = values[1]
        return isinstance(attr_value, str) and attr_value.startswith(prefix)
    if condition_type == "GreaterThanEquals":
        return attr_value is not None and attr_value >= values[1]
    if condition_type == "LessThanEquals":
        return attr_value is not None and attr_value <= values[1]

    return False


class InMemoryDynamoTable:
    """Minimal in-memory DynamoDB table used for local testing."""

    def __init__(self, table_name: str):
        self.table_name = table_name
        self._items: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self._current_scope: Optional[str] = None

    def _maybe_reset_for_test(self) -> None:
        """No-op: test data cleanup is handled by test fixtures."""
        pass

    # boto3.Table compatibility ---------------------------------------------------------
    def load(self) -> None:  # pragma: no cover - mirrors boto API
        return None

    def delete(self) -> None:
        self._items.clear()

    # CRUD operations ------------------------------------------------------------------
    def put_item(
        self,
        Item: Dict[str, Any],
        ConditionExpression: Optional[str] = None,
    ) -> Dict[str, Any]:
        key = (Item["PK"], Item["SK"])

        if ConditionExpression and "attribute_not_exists" in ConditionExpression:
            if key in self._items:
                _raise_client_error(
                    "ConditionalCheckFailedException",
                    "Item already exists",
                    "PutItem",
                )

        self._items[key] = Item.copy()
        return {"ResponseMetadata": {}}

    def get_item(self, Key: Dict[str, str]) -> Dict[str, Any]:
        key = (Key["PK"], Key["SK"])
        item = self._items.get(key)
        return {"Item": item.copy()} if item else {}

    def _filter_items(
        self, filter_expression: Optional[ConditionBase]
    ) -> List[Dict[str, Any]]:
        items = [item.copy() for item in self._items.values()]
        if not filter_expression:
            return items

        return [item for item in items if _evaluate_condition(item, filter_expression)]

    def scan(self, FilterExpression: Optional[ConditionBase] = None) -> Dict[str, Any]:
        items = self._filter_items(FilterExpression)
        return {"Items": items, "Count": len(items)}

    def query(
        self,
        KeyConditionExpression: ConditionBase,
        IndexName: Optional[str] = None,
    ) -> Dict[str, Any]:
        # IndexName is ignored because items already carry their index attributes.
        items = [item.copy() for item in self._items.values()]
        filtered = [
            item for item in items if _evaluate_condition(item, KeyConditionExpression)
        ]
        return {"Items": filtered, "Count": len(filtered)}

    def update_item(
        self,
        Key: Dict[str, str],
        UpdateExpression: str,
        ExpressionAttributeValues: Dict[str, Any],
        ConditionExpression: Optional[str] = None,
        ReturnValues: Optional[str] = None,
    ) -> Dict[str, Any]:
        key = (Key["PK"], Key["SK"])
        item = self._items.get(key)

        if ConditionExpression and "attribute_exists" in ConditionExpression and not item:
            _raise_client_error(
                "ConditionalCheckFailedException",
                "Item does not exist",
                "UpdateItem",
            )

        if item is None:
            item = {}

        assignments = UpdateExpression.replace("SET", "").split(",")
        for assignment in assignments:
            attr, value_key = assignment.strip().split("=", 1)
            attr = attr.strip()
            value = ExpressionAttributeValues[value_key.strip()]
            item[attr] = value

        self._items[key] = item

        if ReturnValues == "ALL_NEW":
            return {"Attributes": item.copy()}
        return {"ResponseMetadata": {}}

    def delete_item(
        self,
        Key: Dict[str, str],
        ConditionExpression: Optional[str] = None,
    ) -> Dict[str, Any]:
        key = (Key["PK"], Key["SK"])
        if key not in self._items:
            if ConditionExpression and "attribute_exists" in ConditionExpression:
                _raise_client_error(
                    "ConditionalCheckFailedException",
                    "Item does not exist",
                    "DeleteItem",
                )
            return {"ResponseMetadata": {}}

        del self._items[key]
        return {"ResponseMetadata": {}}


class DynamoDBSetup:
    """Singleton class for DynamoDB setup and table access."""

    _instance: Optional["DynamoDBSetup"] = None

    def __new__(cls):
        """Ensure only one instance of DynamoDBSetup exists."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        # Skip initialization if already done
        if self._initialized:
            return

        # Check if running in local development mode
        self.is_local = os.getenv("ENVIRONMENT") == "local"

        if self.is_local:
            self.table_name = os.getenv("DYNAMODB_TABLE_NAME", "expense-tracker-local")
            self.table = IN_MEMORY_TABLES.setdefault(
                self.table_name, InMemoryDynamoTable(self.table_name)
            )
        else:
            # Production AWS environment
            region = (
                os.getenv("AWS_DEFAULT_REGION")
                or os.getenv("AWS_REGION")
                or "ap-southeast-2"
            )
            self.dynamodb = boto3.resource("dynamodb", region_name=region)
            self.table_name = os.getenv("DYNAMODB_TABLE_NAME", "expense-tracker")

        self._initialized = True

    def create_table_if_not_exists(self) -> bool:
        """Create DynamoDB table if it doesn't exist."""

        if self.is_local:
            return True

        try:
            table = self.dynamodb.Table(self.table_name)
            table.load()
            logger.info(f"Table {self.table_name} already exists")
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "ResourceNotFoundException":
                return self._create_table()
            logger.error(f"Error checking table existence: {e}")
            return False

    def _create_table(self) -> bool:
        """Create the DynamoDB table with single-table design."""

        try:
            # Build table configuration based on environment
            table_config = {
                "TableName": self.table_name,
                "KeySchema": [
                    {"AttributeName": "PK", "KeyType": "HASH"},
                    {"AttributeName": "SK", "KeyType": "RANGE"},
                ],
                "AttributeDefinitions": [
                    {"AttributeName": "PK", "AttributeType": "S"},
                    {"AttributeName": "SK", "AttributeType": "S"},
                    {"AttributeName": "GSI1PK", "AttributeType": "S"},
                    {"AttributeName": "GSI1SK", "AttributeType": "S"},
                ],
            }

            # Use PAY_PER_REQUEST for both local and production
            table_config["GlobalSecondaryIndexes"] = [
                {
                    "IndexName": "GSI1",
                    "KeySchema": [
                        {"AttributeName": "GSI1PK", "KeyType": "HASH"},
                        {"AttributeName": "GSI1SK", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
            ]
            table_config["BillingMode"] = "PAY_PER_REQUEST"

            table = self.dynamodb.create_table(**table_config)

            # Wait for a table to be created
            table.wait_until_exists()
            logger.info(f"Table {self.table_name} created successfully")
            return True

        except ClientError as e:
            logger.error(f"Error creating table: {e}")
            return False

    def get_table(self):
        """Get reference to the DynamoDB table."""

        if self.is_local:
            return self.table
        return self.dynamodb.Table(self.table_name)


def initialize_database() -> bool:
    """Initialize database connection and create table if needed."""

    db_setup = DynamoDBSetup()
    return db_setup.create_table_if_not_exists()
