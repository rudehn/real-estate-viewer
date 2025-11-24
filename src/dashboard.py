from datetime import date, timedelta

import httpx
import pandas as pd
import plotly.express as px
import streamlit as st

# --- CONFIGURATION ---
API_URL = "http://127.0.0.1:8000"
st.set_page_config(page_title="Real Estate Discovery", layout="wide", page_icon="🏠")

# --- DATA FETCHING ---


def fetch_transactions(filters: dict, limit: int = 1000) -> tuple[pd.DataFrame, int]:
    """Fetches data from the FastAPI backend with applied filters."""
    params = {"limit": limit, "offset": 0}
    clean_filters = {k: v for k, v in filters.items() if v is not None and v != ""}
    params.update(clean_filters)

    try:
        response = httpx.get(f"{API_URL}/transactions", params=params, timeout=10.0)
        response.raise_for_status()
        data = response.json()

        df = pd.DataFrame(data["entities"])
        return df, data["count"]
    except httpx.ConnectError:
        st.error(f"❌ Could not connect to backend at {API_URL}. Is it running?")
        return pd.DataFrame(), 0
    except Exception as e:
        st.error(f"❌ Error fetching data: {e}")
        return pd.DataFrame(), 0


# --- SIDEBAR AND FILTER SETUP ---


def setup_sidebar_and_filters():
    """Defines the sidebar UI, initializes state, and returns API filters."""
    st.sidebar.header("🔍 Filter Criteria")

    # Initialize state for map zooming
    if "map_selection" not in st.session_state:
        st.session_state.map_selection = []
    if "map_zoom_level" not in st.session_state:
        st.session_state.map_zoom_level = 10

    # 1. Date Range
    st.sidebar.subheader("Sale Date")
    start_date = st.sidebar.date_input("Start Date", value=date(2010, 1, 1))
    end_date = st.sidebar.date_input("End Date", value=date.today())

    # 2. Price Range
    st.sidebar.subheader("Price ($)")
    MAX_PRICE = 500_000_000
    min_price, max_price = st.sidebar.slider("Sale Price Range", 0, MAX_PRICE, (10_000, MAX_PRICE))

    # 3. Acres
    st.sidebar.subheader("Size (Acres)")
    MAX_ACREAGE = 10000.0
    min_acres, max_acres = st.sidebar.slider("Acres", 0.0, MAX_ACREAGE, (0.1, MAX_ACREAGE))

    # 4. Parcel Class
    st.sidebar.subheader("Class")
    class_options = {
        "Agricultural": "Agricultural",
        "Commercial": "Commercial",
        "Exempt": "Exempt",
        "Industrial": "Industrial",
        "Residential": "Residential",
        "Utilities": "Utilities",
    }
    selected_classes = st.sidebar.multiselect(
        "Parcel Class", options=list(class_options.keys()), default=["Residential"]
    )
    selected_class_codes = [class_options[c] for c in selected_classes]

    # 5. Limit control
    fetch_limit = st.sidebar.number_input(
        "Max Rows to Fetch", min_value=100, max_value=50000, value=5000
    )

    api_filters = {
        "sale_date__gte": start_date,
        "sale_date__lte": end_date,
        "sale_price__gte": min_price,
        "sale_price__lte": max_price,
        "acres__gte": min_acres,
        "acres__lte": max_acres,
        "parcel_class__in": selected_class_codes if selected_class_codes else None,
        "is_geocoded": True,
    }

    return api_filters, selected_class_codes, fetch_limit


# --- DATA PROCESSING ---


def process_data(df: pd.DataFrame, selected_class_codes: list) -> pd.DataFrame:
    """Performs client-side data cleaning and derived calculations."""
    if df.empty:
        return df

    # Ensure date column is datetime object
    df["sale_date"] = pd.to_datetime(df["sale_date"])

    # Client-side calculations
    df["price_per_acre"] = df.apply(
        lambda x: x["sale_price"] / x["acres"] if x["acres"] > 0 else 0, axis=1
    )
    df["tax_ratio"] = df.apply(
        lambda x: x["sale_price"] / x["assessed_total"]
        if x["assessed_total"] and x["assessed_total"] > 0
        else None,
        axis=1,
    )

    # Local filtering for robustness
    if selected_class_codes:
        df = df[df["parcel_class"].isin(selected_class_codes)]

    # Prepare map data columns
    df["latitude"] = df["parcel"].apply(lambda x: x.get("latitude") if x else None)
    df["longitude"] = df["parcel"].apply(lambda x: x.get("longitude") if x else None)

    return df.dropna(subset=["latitude", "longitude"]).copy()  # Only keep geocoded properties


# --- TAB RENDERERS ---


def render_map_explorer(display_df: pd.DataFrame, current_zoom: int, map_center: dict):
    """Renders the interactive map and handles zoom/selection logic."""
    col_map_header, col_map_reset = st.columns([4, 1])
    with col_map_header:
        st.subheader("Map View (Select Region to Zoom)")
    with col_map_reset:
        if st.button("🔄 Reset Map Zoom"):
            st.session_state.map_selection = []
            st.session_state.map_zoom_level = 10
            st.rerun()

    if display_df.empty:
        st.warning("No properties found in the selected time window or region.")
        return

    # 1. Plotly Figure Setup
    fig = px.scatter_mapbox(
        display_df,
        lat="latitude",
        lon="longitude",
        hover_name="parcel_location",
        hover_data={
            "latitude": False,
            "longitude": False,
            "sale_price": ":$,.0f",
            "new_owner": True,
            "sale_date": "|%b %d, %Y",
            "acres": ":.2f",
            "parcel_id": True,
        },
        color="sale_price",
        color_continuous_scale="Viridis",
        size="acres",
        size_max=15,
        zoom=current_zoom,
        height=600,
    )

    # 2. Explicitly apply zoom and center to prevent snap-back issues
    fig.update_layout(
        mapbox_style="open-street-map",
        margin={"r": 0, "t": 0, "l": 0, "b": 0},
        mapbox={"center": map_center, "zoom": current_zoom},
    )

    # 3. Render and Capture Selection Event
    event = st.plotly_chart(fig, use_container_width=True, on_select="rerun", selection_mode="box")

    # 4. Handle selection event and progressive zoom
    if event and event.selection and event.selection["points"]:
        selected_indices = [p["point_index"] for p in event.selection["points"]]
        new_ids = display_df.iloc[selected_indices]["parcel_id"].tolist()

        # Only rerun and zoom if the selection has actually changed
        if set(new_ids) != set(st.session_state.map_selection):
            st.session_state.map_selection = new_ids

            # Progressive Zoom Logic: Increase zoom if a NEW selection is made
            current_zoom_level = st.session_state.map_zoom_level
            st.session_state.map_zoom_level = min(22, current_zoom_level + 2)

            st.rerun()


def render_market_analysis(df: pd.DataFrame):
    """Renders the sales timeline scatter plot, filtered by current map selection."""
    st.subheader(f"Market Trends ({len(df):,} properties)")

    if df.empty:
        st.info("No data selected for market analysis.")
        return

    df_sorted = df.sort_values("sale_date")
    fig_trend = px.scatter(
        df_sorted,
        x="sale_date",
        y="sale_price",
        color="parcel_class",
        size="acres",
        hover_data=["parcel_location", "new_owner"],
        title="Sales Timeline",
    )
    st.plotly_chart(fig_trend, use_container_width=True)


def render_raw_grid(df: pd.DataFrame):
    """Renders the detailed transaction log DataFrame, filtered by current map selection."""
    st.subheader(f"Detailed Transaction Log ({len(df):,} properties)")

    if df.empty:
        st.info("No data selected for detailed log.")
        return

    st.dataframe(
        df,
        column_config={
            "parcel_id": "ID",
            "sale_price": st.column_config.NumberColumn("Price", format="$%d"),
            "acres": st.column_config.NumberColumn("Acres", format="%.2f"),
            "sale_date": st.column_config.DateColumn("Date"),
            "tax_ratio": st.column_config.ProgressColumn(
                "Tax Ratio (Sale/Assessed)", format="%.2f", min_value=0, max_value=2
            ),
            "price_per_acre": st.column_config.NumberColumn("$/Acre", format="$%d"),
        },
        hide_index=True,
        use_container_width=True,
    )


# --- MAIN EXECUTION ---


def main():
    """Orchestrates the entire dashboard flow."""

    # 1. Setup Filters and State
    api_filters, selected_class_codes, fetch_limit = setup_sidebar_and_filters()

    st.title("🏠 Property Map Explorer")

    # 2. Fetch Data from API and Process
    raw_df, total_count = fetch_transactions(api_filters, limit=fetch_limit)

    if raw_df.empty:
        st.warning(
            "No data found. Try adjusting the filters in the sidebar or ensure your backend API is running and populated."
        )
        return

    # Process data (adds derived columns, filters by class, extracts lat/lon)
    processed_df = process_data(raw_df, selected_class_codes)

    if processed_df.empty:
        st.warning("No properties matched filters or have been successfully geocoded.")
        return

    # --- 3. Centralized Filtering UI and Logic (Time and Map Selection) ---

    # 3a. Time Slider Filter (Applies to all subsequent data)
    min_dt = processed_df["sale_date"].min().to_pydatetime()
    max_dt = processed_df["sale_date"].max().to_pydatetime()
    if min_dt == max_dt:
        max_dt = min_dt + timedelta(days=1)

    st.markdown("##### Filter Data by Sale Date")
    st.caption("This filter applies to all tabs.")

    start_val, end_val = st.slider(
        "Date Window (Applies to all tabs)",
        min_value=min_dt,
        max_value=max_dt,
        value=(min_dt, max_dt),
        format="MM/DD/YY",
    )

    time_filtered_df = processed_df[
        (processed_df["sale_date"] >= start_val) & (processed_df["sale_date"] <= end_val)
    ].copy()

    # 3b. Map Selection Filter (Final Filter for all tabs)
    current_zoom = st.session_state.map_zoom_level
    final_df = time_filtered_df  # Default final data

    if st.session_state.map_selection:
        # If a map selection exists, filter the time-filtered data by the selected parcel_ids
        filtered_by_selection_df = time_filtered_df[
            time_filtered_df["parcel_id"].isin(st.session_state.map_selection)
        ].copy()

        if not filtered_by_selection_df.empty:
            final_df = filtered_by_selection_df
        else:
            # If selection exists but results in empty data (e.g., due to time filter change), reset state
            st.session_state.map_selection = []
            st.session_state.map_zoom_level = 10
            final_df = time_filtered_df.copy()

    # Calculate map center based on the FINAL data being displayed
    map_center = {
        "lat": final_df["latitude"].median() if not final_df.empty else 0,
        "lon": final_df["longitude"].median() if not final_df.empty else 0,
    }

    # 4. Top Metrics (Reflect FINAL filtered data)
    col1, col2, col3 = st.columns(3)
    if not final_df.empty:
        col1.metric("Properties Displayed (Filtered)", len(final_df))
        col2.metric("Avg Price (Filtered)", f"${final_df['sale_price'].mean():,.0f}")
        col3.metric("Avg Price/Acre (Filtered)", f"${final_df['price_per_acre'].mean():,.0f}")
    else:
        col1.metric("Properties Displayed (Filtered)", 0)
        col2.metric("Avg Price (Filtered)", "$0")
        col3.metric("Avg Price/Acre (Filtered)", "$0")

    # 5. Tabbed Layout
    tab1, tab2, tab3 = st.tabs(["🌎 Map Explorer", "📈 Market Analysis", "📄 Raw Grid"])
    st.markdown("---")

    st.info(
        f"All tabs below show **{len(final_df):,}** properties from the current filters and map selection."
    )

    with tab1:
        render_map_explorer(final_df, current_zoom, map_center)

    with tab2:
        render_market_analysis(final_df)  # Filtered!

    with tab3:
        render_raw_grid(final_df)  # Filtered!


if __name__ == "__main__":
    main()
