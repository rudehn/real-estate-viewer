import asyncio
import httpx
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker
from db.engine import engine
from db.models import Parcel


# US Census API URL
CENSUS_URL = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"

async def geocode_parcels(batch_size: int = 50):
    """
    Finds parcels with missing coordinates and fetches them from the US Census.
    """
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # 1. Find parcels that have NO latitude
        statement = select(Parcel).where(Parcel.latitude == None).limit(batch_size)
        result = await session.exec(statement)
        parcels = result.all()

        if not parcels:
            print("✅ All parcels are already geocoded!")
            return

        print(f"🌍 Geocoding batch of {len(parcels)} parcels...")

        # 2. Setup an Async HTTP Client
        async with httpx.AsyncClient(timeout=10.0) as client:
            for parcel in parcels:
                # Construct the search address
                # Assuming Montgomery County, OH based on your URLs
                full_address = f"{parcel.parcel_location}, Montgomery County, OH"
                
                try:
                    response = await client.get(
                        CENSUS_URL, 
                        params={
                            "address": full_address,
                            "benchmark": "Public_AR_Current",
                            "format": "json"
                        }
                    )
                    data = response.json()
                    matches = data.get("result", {}).get("addressMatches", [])

                    if matches:
                        # Use the first match
                        coords = matches[0]["coordinates"]
                        parcel.longitude = coords["x"]
                        parcel.latitude = coords["y"]
                        session.add(parcel)
                        print(f"  📍 Found: {full_address} -> ({coords['y']}, {coords['x']})")
                    else:
                        print(f"  ❌ Not Found: {full_address}")
                        # Optional: Mark as 'not_found' in a separate column so we don't retry forever
                
                except Exception as e:
                    print(f"  ⚠️ Error: {e}")
                
                # Be nice to the free API (Sleep 0.2s)
                await asyncio.sleep(0.2)

        # 3. Commit the changes
        await session.commit()
        print(f"💾 Saved coordinates for batch.")



# ArcGIS World Geocoding Service (Public Endpoint)
ARCGIS_URL = "https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates"

async def geocode_parcels_slow(batch_size: int = 50):
    """
    Finds parcels with missing coordinates and fetches them via ArcGIS.
    """
    async_session = async_sessionmaker(
        engine, 
        class_=AsyncSession, 
        expire_on_commit=False
    )

    async with async_session() as session:
        # 1. Find parcels that have NO latitude
        statement = select(Parcel).where(Parcel.latitude == None).limit(batch_size)
        result = await session.exec(statement)
        parcels = result.all()

        if not parcels:
            print("✅ All parcels are already geocoded!")
            return

        print(f"🌍 Geocoding batch of {len(parcels)} parcels via ArcGIS...")

        async with httpx.AsyncClient(timeout=15.0) as client:
            for parcel in parcels:
                # ArcGIS prefers a "SingleLine" input for loose searches
                address_query = f"{parcel.parcel_location}, Montgomery County, OH"
                
                params = {
                    "SingleLine": address_query,
                    "f": "json",          # Format
                    "outFields": "*",     # Return all fields
                    "maxLocations": 1     # Only want the top result
                }
                
                try:
                    response = await client.get(ARCGIS_URL, params=params)
                    # print(response.status_code)
                    # print(response.content)
                    data = response.json()
                    candidates = data.get("candidates", [])

                    if candidates:
                        match = candidates[0]
                        location = match["location"]
                        
                        # ArcGIS returns x (lon) and y (lat)
                        parcel.latitude = float(location["y"])
                        parcel.longitude = float(location["x"])
                        
                        # Optional: Update location with the "official" string from Esri
                        parcel.parcel_location = match["address"] 
                        
                        session.add(parcel)
                        print(f"  📍 Found: {parcel.parcel_location} ({match['score']}%)")
                    else:
                        print(f"  ❌ Not Found: {address_query}")
                        # Mark as not found so we don't retry (optional logic)
                        # parcel.latitude = 0.0 
                        # session.add(parcel)

                except Exception as e:
                    print(f"  ⚠️ Error: {e}")
                
                # Be polite! Sleep 0.5s to avoid another ban
                await asyncio.sleep(0.5) 

        await session.commit()
        print("💾 Saved coordinates for batch.")        


# URL for OpenStreetMap Nominatim
OSM_URL = "https://nominatim.openstreetmap.org/search"

async def geocode_parcels_2(batch_size: int = 50):
    """
    Finds parcels with missing coordinates and fetches them from OpenStreetMap.
    """
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # 1. Find parcels that have NO latitude
        statement = select(Parcel).where(Parcel.latitude == None).limit(batch_size)
        result = await session.exec(statement)
        parcels = result.all()

        if not parcels:
            print("✅ All parcels are already geocoded!")
            return

        print(f"🌍 Geocoding batch of {len(parcels)} parcels via OpenStreetMap...")

        async with httpx.AsyncClient(timeout=10.0) as client:
            for parcel in parcels:
                # OSM allows structured queries which is much more accurate
                # We tell it explicitly what the street and county are
                params = {
                    "street": parcel.parcel_location,
                    "county": "Montgomery County",
                    "state": "OH",
                    "format": "json",
                    "limit": 1
                }
                
                # OSM REQUIRES a User-Agent header identifying your app
                headers = {
                    "User-Agent": "RealEstateApp/1.0 (code@example.com)" 
                }

                try:
                    response = await client.get(OSM_URL, params=params, headers=headers)
                    print(response.status_code)
                    print(response.content)
                    data = response.json()

                    if data:
                        # OSM returns string values for lat/lon, we cast to float
                        match = data[0]
                        parcel.latitude = float(match["lat"])
                        parcel.longitude = float(match["lon"])
                        session.add(parcel)
                        print(f"  📍 Found: {parcel.parcel_location}")
                    else:
                        print(f"  ❌ Not Found: {parcel.parcel_location}")
                        # Optimization: You might want to set latitude to 0.0 
                        # so we don't retry this address forever.

                except Exception as e:
                    print(f"  ⚠️ Error: {e}")
                
                # CRITICAL: OpenStreetMap policy requires 1 second between requests
                await asyncio.sleep(1.0) 

        await session.commit()
        print("💾 Saved coordinates for batch.")