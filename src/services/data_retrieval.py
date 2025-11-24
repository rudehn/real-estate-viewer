import httpx
import zipfile
from io import BytesIO
from datetime import datetime
"""
This file handles retrieving data from the website
"""
DATA_DIR = "data"

def retrieve_yearly_data():
    """
    TODO: Make this smarter so it doesn't download data we already have
    """
    yearly_data = f"{DATA_DIR}/yearly/"
    base_url = "https://go.mcohio.org/applications/treasurer/search/data/Yearly"
    year = datetime.now().year
    min_year = 2001 # This is the earliest year of data on the website
    while year >= min_year:
        zip_name = f"SALES_{year}.zip"
        year -=1
        full_url = f"{base_url}/{zip_name}"
        print(f"Fetching {full_url}")
        response = httpx.get(full_url)
        if response.status_code >= 400:
            print(f"Skipping {full_url}")
            continue
        myzip = zipfile.ZipFile(BytesIO(response.content))
        myzip.extractall(path=yearly_data)

