# Expense Tracker App - Stories Document

## Story breakdown

### E2: Core Data Management
#### Overview
- CRUD operations for Owners, Accounts, Categories
- Relationship management endpoints
- CLI commands for entity management
- References stories.md + S1:Core Data Management for more details
##### Task E2.1: Create new owners, based on seed data
###### Details 
- Create new owners, based on seed data. Below are the fields which are required for the owner entity.
  - Name
  - Card Name
- Values in CSV format are below
  - John, J Doe
  - Jane, J Smith
  - Joint, J Smith
-  Characteristics
  - Owners are immutable entities. 
  - They cannot be updated or deleted. 
  - The name is a unique identifier.
  - All fields are required.
- Operations allowed
  - Create new owner
  - List all owners
##### Task E2.2: Create new accounts, based on seed data
###### Details
- Create new accounts, based on seed data. Below are the fields which are required for the account entity.
  - Account Name
  - Bank Name
  - Owner Name
  - Card Member
  - Active
- Values in CSV format are below
  - Pocket Money, HSBC, John, J Doe, true
  - Salary, HSBC, John, J Doe, true
-  Characteristics
  - `account_id` (Account Name + space + Owner Name) is the unique identifier. Example: "Pocket Money John".
  - `account_id` is stored as the foreign key on related entities.
  - Card Member establishes direct link to expense processing - must match an existing Owner.card_name value.
  - Card Member enables direct expense-to-account resolution via card_member lookup.
  - Account can be made inactive; no other fields can be updated after creation.
  - Each account is associated with a single owner. The owner cannot be changed once persisted.
  - Card Member cannot be changed once the account is persisted.
  - All fields are required.
  - Default value of Active is true
- Operations allowed
  - Add new account
  - List all accounts
  - Inactivate account by account name

##### Task E2.3: Create new categories, based on seed data
###### Details 
- Create new categories, based on seed data. Below are the fields which are required for the category entity.
  - Name
  - Labels - this is a list of labels
  - `account_id` (Account Name + space + Owner Name) is used as the foreign key.
  - Card Name
  - Active
- Values in CSV format are below (`name,labels,account_id,card_name,active`)
  - Water,"[WATERCARE]","CC Holding John","J Doe",true
  - Apple,"[APPLE.COM/BILL]","CC Holding John","J Doe",true
  - Internet,"[broadcom]","CC Holding John","J Doe",true
  - JohnSpend,"[cafe,coffee,OPENAI,AMAZON WEB SERVICES,SUSHI]","CC Holding John","J Doe",true
  - Unknown,"[]","Joint Joint","J Smith",true
-  Characteristics
  - Name is a unique identifier.
  - **Canonical Category Set**: The system defines five standard categories: Water, Apple, Internet, JohnSpend, and Unknown.
  - **Unknown Category**: The "Unknown" category serves as a fallback for expenses that cannot be auto-categorized. It has empty labels and requires manual review.
  - Each category is associated with a single account. Account cannot be changed. `account_id` (concat) is the foreign key.
  - Each category can be made inactive.
  - Labels persist as lists in DynamoDB (seed values are comma-separated strings for human readability). These labels can be updated.
  - Only the labels field and the active field can be updated. No other fields can be updated.
  - Category cannot be deleted.
  - All fields are required.
  - Default value of Active is true
- Operations allowed
  - Add new category
  - List all categories
  - Update category labels
  - Inactivate category by category name

##### Task E2.4: Recording expense, based on manual input
###### Details 
- Record new expense. Below are the fields which are required for an expense.
  - Id - auto generated 
  - Date	
  - Description	
  - Card Member	
  - Assigned Card Member 	
  - Account Number	
  - Amount	
  - Extended Details	
  - Appears On Your Statement As	
  - Address	City/State	
  - Zip Code	
  - Country	
  - Reference	
  - Category Hint
  - Category (auto-derived)
- Example values are below
  - 11/09/2025,APPLE.COM/BILL SYDNEY,J DOE,J DOE,-1003,12.99,Foreign Spend Amount: 23.00 UNITED STATES DOLLAR Commission Amount: 0.97 Currency Exchange Rate: null APPLE.COM/BILL SYDNEY,"CAPITAL CENTRE LEVEL 13
255 PITT STREET SYDNEY",2000,UNITED STATES,AT252540002000010028867,	Retail & Grocery-Online Purchases
 
- Characteristics
  - Date, Description, Card Member, Assigned Card Member, and Amount are required fields.
  - All other fields are optional at capture time. `Category Hint` becomes required (non-null list) once auto-categorisation runs or when any category is assigned.
  - Each expense stores a category name. The value is derived automatically but can be overridden by the user. When overridden, it must still reference an existing category name.
  - `Category Hint` stores a DynamoDB list of candidate categories generated during auto-categorisation. It is always a list (empty list when no candidates exist, never null). This field is enforced at the model level to ensure data consistency.
  - Assigned Card Member default value is Card Member.
- Operations allowed
  - Add new expense
  - Update assigned card member, this is a derived field. The derived value can be overridden through manual input.
  - List all expenses for date range, default is current month
  - Update Category (override the derived value through manual input).
  - Delete expense
- List all the fields for an expense by ID

### E3: Expense Processing 
#### Overview
- CSV upload and parsing
- Expense persistence
- Auto-categorization logic based on category label mappings
- AI-based categorization recommendations for unknown expenses inputting into manual categorization workflow
- Updating categorization labels based on user input

##### Task E3.1: Upload CSV file and persist expenses
###### Details 
- Field names are below
  - ```Date,Description,Card Member,Account #,Amount,Extended Details,Appears On Your Statement As,Address,City/State,Zip Code,Country,Reference,Category```
- Examples values are below
  - ```11/09/2025,APPLE.COM/BILL SYDNEY,J DOE,J DOE,-1003,12.99,Foreign Spend Amount: 23.00 UNITED STATES DOLLAR Commission Amount: 0.97 Currency Exchange Rate: null APPLE.COM/BILL SYDNEY,"CAPITAL CENTRE LEVEL 13 255 PITT STREET SYDNEY",2000,UNITED STATES,AT252540002000010028867,	Retail & Grocery-Online Purchases```
- Characteristics
    - Perform basic validation on the input file.
    - Perform basic error handling on the input file. For example, the presence of mandatory fields.
    - Map CSV rows to expense model fields. Ignore the incoming `Category` column and allow the auto-categorisation step to populate it.
    - Persist the expenses to the database.
    - A typical file size is 1000 rows and less than 500 KB in size.
- Operations allowed
    - Upload CSV file and persist expenses

##### Task E3.2: Auto-categorization logic based on labels assigned to categories 
###### Details 
- An expense is categorized based on the category label mappings. The auto-categorisation logic should be executed after a new expense CSV is uploaded and persisted.
- The logic is as follows:
  - If the normalised expense description and amount match 100% with the description and amount of a categorised expense from the last three months, categorise the new expense using that historical category. Apply a tolerance-aware floating-point comparison when comparing amounts.
  - Else if the normalised expense description contains a category label (after normalisation) for any active category, categorise the expense as the first matching category, prioritising categories whose `card_name` matches the expense's card member.
  - Else, categorise the expense as "Unknown".
- Example
  - If the expense description is "APPLE.COM/BILL SYDNEY" and amount is "12.99" and these match exactly with expense description and amount of a previous expense and the previous expense was categorized as "JohnSpend" then categorize this expense as "JohnSpend".
  - Else if the expense description is "AT PUBLIC TRANSPORT AT  AUCKLAND CENTRA", and the label `"AT PUBLIC TRANSPORT"` exists for "JohnSpend", categorize the expense as "JohnSpend" because the label appears as a substring of the normalised description (with matching card member taking precedence).
  - Else the expense description is "MINI SMILES LIMITED     HELENSVILLE, US", categorize the expense as "Unknown".
- Characteristics 
  - Normalise the description and category labels before matching. Normalising includes lowercasing, trimming whitespace, collapsing double spaces, and removing punctuation and special characters (retain digits).
  - An expense is deemed categorised when the stored category is not "Unknown".
  - When multiple categories share matching labels, prioritise those whose `card_name` matches the expense's card member; otherwise use insertion order to provide deterministic results.
  - If no match is found, categorise the expense as "Unknown" and leave `category_hint` empty (or populate with optional suggestions from future enhancements).
- If multiple categories share identical labels that match the expense description, apply card-member-based priority:
    - Find categories where `category.card_name` matches `expense.card_member` (case-insensitive exact match).
    - If matches are found, restrict the candidate set to those categories before selecting the highest score.
    - If no card-member match is found or a tie remains after filtering, retain the deterministic tie-breaker (alphabetical) to pick the stored category and place the rest in `category_hint`.
- After auto-categorisation completes, `category_hint` is always persisted as a list (possibly empty) so downstream consumers can rely on the field's presence.
- needs_review Lifecycle:
  - Set to `True` when an expense is auto-categorized as "Unknown" (no historical match or label match found)
  - Automatically cleared to `False` when the category is manually updated by the user
  - This ensures reviewed expenses are no longer flagged for review
  - The flag is only set during auto-categorization; successful categorization (historical or label match) keeps it as `False`
- Operations allowed
  - The category is a derived field. It is computed by the code. It must match the Category.Name from the Category table/entity.
  - The category for a given expense can be updated by the user, via the CLI.

##### Task E3.3: Update Assigned Card Member for an expense
###### Details
- The assigned_card_member should be updated under the following conditions.
  - As part of the auto-categorisation process, the assigned card member is updated with the card_name field of the category.
  - If the user manually updates the category, the assigned card member is updated with the card_name field of the category.
  - If the user manually updates the assigned card member, the assigned card member is updated.
- Characteristics
  - It must match the card_name from the Owner entity.
- Operations allowed
  - The assigned_card_member is a derived field. It is computed by the code. It must match the Category.card_name from the Category table/entity.
  - The assigned_card_member for a given expense can be updated by the user, via the CLI.

##### Task E3.4: Bulk Category Assignment
###### Details
- Allow users to update the category for multiple expenses in a single CLI operation
- User provides explicit list of expense IDs (comma-separated) and target category
- System resolves partial IDs, validates each expense, and updates category
- Each update is independent - failures don't prevent other updates from succeeding

- Characteristics
  - CLI-only feature (no new backend endpoints)
  - Reuses existing single-expense update endpoint for each operation
  - Supports partial expense IDs with auto-resolution
  - Shows preview and requires confirmation before proceeding
  - Provides real-time progress feedback during updates
  - Returns detailed summary with success/failure counts
  - Inherits all business logic: needs_review clearing, validation, assigned_card_member updates

- Operations allowed
  - CLI: `expense-tracker expenses bulk-update --category "CategoryName" --ids "id1,id2,id3"`
    - `--category`: Required. Target category to assign
    - `--ids`: Required. Comma-separated list of full or partial expense IDs
    - Shows preview with resolved IDs and count
    - Requires confirmation before applying changes
    - Displays per-expense progress and final summary

- Example Usage
  ```bash
  # Update multiple expenses to Coffee category
  expense-tracker expenses bulk-update --category Coffee --ids "abc123,def456,ghi789"

  # Works with partial IDs (auto-resolves)
  expense-tracker expenses bulk-update --category JohnSpend --ids "abc,def,ghi"
  ```


### E5: Reporting & Analytics
#### Overview
- Generate account-based expense reports
- Provide filtering capabilities for targeted analysis
- Support both CLI and REST API access

##### Task E5.1: Expenses by Account Report
###### Details
- Generate comprehensive reports showing expenses grouped by account
- Support filtering by date range, category, card member, and review status
- Calculate totals and counts for each account group
- Sort accounts by total spending (highest to lowest)

- Characteristics
  - Uses existing card_member → account relationships via card_name lookup
  - Provides both summary and detailed views
  - Handles absolute values for amount calculations (expense amounts are stored as negative values)
  - Gracefully handles expenses without matching accounts

- Operations allowed
  - REST API: `GET /reports/expenses-by-account` with optional query parameters
  - CLI command: `expense-tracker reports by-account` with filtering options
  - Summary mode: Shows account totals only
  - Detailed mode: Shows individual expenses

- API Parameters
  - `start_date`: ISO format date string (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
  - `end_date`: ISO format date string
  - `month`: 3-letter month abbreviation (e.g., "Jan", "Feb", "Oct") - case insensitive. Derives 12th-to-11th billing cycle date range. Takes precedence over start_date/end_date when provided.
  - `category`: Category name filter
  - `assigned_card_member`: Assigned card member name filter
  - `needs_review`: Boolean flag for expenses needing review

- CLI Options
  - `--start-date`: Start date (YYYY-MM-DD)
  - `--end-date`: End date (YYYY-MM-DD)
  - `--month`: Month filter (3-letter abbreviation: Jan, Feb, etc.). Overrides start/end dates. Defaults to previous month (12th-to-11th billing cycle) when no date filters provided.
  - `--category`: Category name filter
  - `--assigned-card-member`: Assigned card member name filter
  - `--needs-review`: Show only expenses needing review
  - `--summary`: Show summary only (no expense details)

- Output Format
  - REST API: JSON with structured expense groups and metadata
  - CLI: Rich formatted tables with colored output
  - Includes total amounts, expense counts, and account details

- Report Behavior
  - **Date Display**: CLI shows dates in dd/mm/yyyy format (e.g., 11/09/2025). API returns ISO format.
  - **Expense Sorting**: Within each account, expenses are sorted newest to oldest (descending by date)
  - **Total Amount Calculation**:
    - Only positive amounts (actual expenses) are included in totals
    - Negative amounts (payments made to credit cards) are excluded from totals
    - Card-Payments account is excluded from the grand total
  - **Account Display**: Card-Payments account is hidden from report output (used internally for payment tracking, not expense reporting)
  - **Owner Totals**: CLI displays total spending per owner below their account summary table

## Technical requirements
- The entities should be modeled for best performance in DynamoDB.
- Entity field names should be updated where required so they are easy to reference in Python code.
- Indexes should be created as required.
- Keep the implementation simple. Caching and batching are not needed at this point.
- Write a minimal suite of tests covering models, repositories, API routes, and CLI workflows to validate the current functionality
- Optimise for code simplicity rather than scalability and performance
