from setuptools import setup, find_packages

setup(
    name="expense-tracker-cli",
    version="1.0.0",
    description="CLI for Expense Tracker API",
    py_modules=["main"],
    install_requires=[
        "click==8.1.7",
        "requests==2.32.5",
        "aws-requests-auth==0.4.3",
        "python-dotenv==1.0.0",
        "rich==13.7.0",
    ],
    entry_points={
        "console_scripts": [
            "expense-tracker=main:cli",
        ],
    },
    python_requires=">=3.9",
)
