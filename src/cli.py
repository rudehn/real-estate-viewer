import asyncio
import typer
from db.engine import init_db
from db.ingestors import ingest_data_files
from services.data_retrieval import retrieve_yearly_data
from services.geocoding import geocode_parcels, geocode_parcels_slow

app = typer.Typer()
"""
Usage

python cli.py init-db
python cli.py ingest-yearly data
python cli.py fetch-data
"""

@app.command()
def init():
    """Initialize the database tables."""
    print("Creating tables...")
    asyncio.run(init_db())
    print("Tables created.")

@app.command()
def fetch():
    """Download fresh data from the web."""
    print("Fetching yearly data...")
    retrieve_yearly_data()
    print("Done.")

@app.command()
def ingest(directory: str = "data"):
    """Ingest CSV files from the data directory."""
    print(f"Ingesting data from {directory}...")
    asyncio.run(ingest_data_files(directory))
    print("Ingestion complete.")

@app.command()
def geocode(loops: int = 1, batch_size: int = 50):
    """
    Geocode parcels that are missing coordinates.
    loops: How many batches to run (default 1)
    batch_size: Parcels per batch (default 50)
    """
    print(f"Starting geocoding loop ({loops} loops of {batch_size} records)...")
    
    for i in range(loops):
        print(f"--- Loop {i+1}/{loops} ---")
        asyncio.run(geocode_parcels(batch_size=batch_size))
    
    print("Geocoding run complete.")

@app.command()
def geocode_slow(loops: int = 1, batch_size: int = 50):
    """
    Geocode parcels that are missing coordinates.
    loops: How many batches to run (default 1)
    batch_size: Parcels per batch (default 50)
    """
    print(f"Starting geocoding loop ({loops} loops of {batch_size} records)...")
    
    for i in range(loops):
        print(f"--- Loop {i+1}/{loops} ---")
        asyncio.run(geocode_parcels_slow(batch_size=batch_size))
    
    print("Geocoding run complete.")

if __name__ == "__main__":
    app()