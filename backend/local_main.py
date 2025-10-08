from app_factory import AppConfig, create_app


config = AppConfig(
    title="Expense Tracker API (Local)",
    description="Personal expense categorization system - Local Development",
    version="1.0.0",
    environment="local",
    root_message="Expense Tracker API (Local Development)",
    log_context="Expense Tracker API (Local Development)",
)
app = create_app(config)
