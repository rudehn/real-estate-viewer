# Real Estate Viewer
This project provides a basic UI to view real estate transactions in part of Ohio. Public data is scraped, processed & made available via an api.

## Getting Started
Start up the devcontainer and run these commands

```
uvicorn main:app --app-dir src --reload --host 0.0.0.0

streamlit run src/dashboard.py
```

## Database revisions

alembic init -t async migrations
- Update alembic.ini: set sqlalchemy.url = sqlite+aiosqlite:///./database.db
- Update migrations.env.py: import db.models & set target_metadata = SQLModel.metadata
alembic revision --autogenerate -m "Add latitude and longitude to parcels"
alembic upgrade head

# Dashboard Example

![alt text](<dashboard-example.png>)
