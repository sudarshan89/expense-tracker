from mangum import Mangum

from app_factory import AppConfig, create_app

config = AppConfig(
    title="Expense Tracker API",
    description="Personal expense categorization system",
    version="1.0.0",
    root_message="Expense Tracker API",
)
app = create_app(config)

handler = Mangum(app, lifespan="off")
