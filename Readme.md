Start up the devcontainer

uvicorn main:app --app-dir src --reload --host 0.0.0.0

streamlit run src/dashboard.py


# Database revisions

alembic init -t async migrations
- Update alembic.ini: set sqlalchemy.url = sqlite+aiosqlite:///./database.db
- Update migrations.env.py: import db.models & set target_metadata = SQLModel.metadata
alembic revision --autogenerate -m "Add latitude and longitude to parcels"
alembic upgrade head