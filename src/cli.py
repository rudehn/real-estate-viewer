import asyncio
import typer
from db.engine import init_db
from db.ingestors import ingest_data_files, ingest_weekly_data
from services.data_retrieval import retrieve_yearly_data
from services.geocoding import geocode_parcels
from logging_config import configure_logging, get_logger

app = typer.Typer()
logger = get_logger(__name__)
"""
Usage

python cli.py init-db
python cli.py ingest-yearly data
python cli.py fetch-data
"""

@app.command()
def init(log_level: str = typer.Option("INFO", "--log-level", help="Logging level")):
    """Initialize the database tables."""
    configure_logging(log_level)
    logger.info("Creating tables...")
    asyncio.run(init_db())
    logger.info("Tables created.")

@app.command()
def fetch(
    force: bool = typer.Option(False, "--force", help="Re-download files even if already on disk"),
    log_level: str = typer.Option("INFO", "--log-level", help="Logging level"),
):
    """Download fresh data from the web."""
    configure_logging(log_level)
    logger.info("Fetching yearly data...")
    retrieve_yearly_data(force=force)
    logger.info("Done.")

@app.command()
def ingest(
    directory: str = "data",
    log_level: str = typer.Option("INFO", "--log-level", help="Logging level"),
):
    """Ingest CSV files from the data directory."""
    configure_logging(log_level)
    logger.info("Ingesting data from %s...", directory)
    asyncio.run(ingest_data_files(directory))
    logger.info("Ingestion complete.")

@app.command()
def ingest_weekly(
    log_level: str = typer.Option("INFO", "--log-level", help="Logging level"),
):
    """Download and ingest all new weekly sales files from the county website."""
    configure_logging(log_level)
    asyncio.run(ingest_weekly_data())
    logger.info("Weekly ingestion complete.")


@app.command()
def geocode(
    loops: int = typer.Option(1, help="How many batches to run"),
    batch_size: int = typer.Option(10_000, help="Parcels per batch (max 10,000 for Census API)"),
    log_level: str = typer.Option("INFO", "--log-level", help="Logging level"),
):
    """Geocode parcels that are missing coordinates using the Census batch API."""
    configure_logging(log_level)
    logger.info("Starting geocoding (%d loops of %d records)...", loops, batch_size)
    for i in range(loops):
        logger.info("--- Loop %d/%d ---", i + 1, loops)
        asyncio.run(geocode_parcels(batch_size=batch_size))
    logger.info("Geocoding run complete.")

if __name__ == "__main__":
    app()