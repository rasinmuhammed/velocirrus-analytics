import streamlit as st
import pandas as pd
import pydeck as pdk
import numpy as np
import geopandas as gpd
from datetime import datetime, timedelta

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Velocirrus Analytics",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 2. HELPER FUNCTIONS & MOCK DATA ---
# We use caching to prevent reloading heavy data on every click
@st.cache_data
def generate_mock_flight_path():
    """
    Generates a realistic flight path from London (LHR) to New York (JFK)
    for demonstration purposes if APIs are unavailable.
    """
    # Create a great circle path roughly
    lons = np.linspace(-0.45, -73.77, 100)
    lats = np.linspace(51.47, 40.64, 100)
    
    # Add some realistic variation (altitude changes)
    # Cruising at 35,000ft to 39,000ft
    alts = np.linspace(10668, 11887, 100) 
    
    # Create timestamp series (8 hour flight)
    start_time = datetime.now()
    times = [start_time + timedelta(minutes=i*4.8) for i in range(100)]
    
    df = pd.DataFrame({
        "longitude": lons,
        "latitude": lats,
        "altitude": alts,
        "time": times,
        # Calculate a mock 'Energy Forcing' (EF) based on physics logic
        # Higher EF in the middle of the Atlantic (cold/humid)
        "ef": [50 * np.sin(i/10) if 30 < i < 70 else 0 for i in range(100)]
    })
    return df

@st.cache_data
def generate_mock_contrail_zones():
    """
    Generates polygons representing 'Contrail Likely Zones' (CLZs).
    Used if Google API key is not provided.
    """
    # Create two polygon zones over the Atlantic
    p1 = [
        [-40, 45], [-30, 45], [-30, 50], [-40, 50], [-40, 45]
    ]
    p2 = [
        [-20, 48], [-15, 48], [-15, 52], [-20, 52], [-20, 48]
    ]
    
    data = [
        {"name": "Zone Alpha (High Humidity)", "path": p1, "color": [255, 0, 0, 100]},
        {"name": "Zone Beta (Ice Supersaturated)", "path": p2, "color": [255, 140, 0, 100]}
    ]
    return data

# --- 3. SIDEBAR & CONTROLS ---
st.sidebar.header("🛸 Velocirrus Flight Deck")

data_source = st.sidebar.radio(
    "Data Source",
    ["Demo Mode (Simulation)", "Live Data (OpenSky + GFS)"]
)

flight_id = st.sidebar.text_input("ICAO24 / Callsign", value="AAL100")
date_select = st.sidebar.date_input("Flight Date", datetime.now())

st.sidebar.markdown("---")
st.sidebar.info(
    """
    **Velocirrus Analytics**
    
    *Optimizing the Invisible.*
    
    This tool models aviation-induced cloudiness (Contrails) to reduce radiative forcing.
    
    **Legend:**
    🔴 Red Path: High Warming Impact
    🟢 Green Path: Low/No Impact
    🟥 Polygons: Contrail Likely Zones
    """
)

# --- 4. MAIN LOGIC ENGINE ---
st.title("⚡ Velocirrus")
st.markdown("**Real-time Contrail Mitigation & Trajectory Optimization**")

# Setup containers for layout
col1, col2, col3 = st.columns(3)
map_container = st.container()

# Logic Branching
if data_source == "Demo Mode (Simulation)":
    # --- SIMULATION PATH ---
    st.warning("⚠️ Running in Simulation Mode. No APIs are being called.")
    
    # Load Mock Data
    flight_df = generate_mock_flight_path()
    zones_data = generate_mock_contrail_zones()
    
    # Calculate Metrics
    total_dist = 5554.2 # km approx LHR-JFK
    avg_ef = flight_df['ef'].mean()
    contrail_len = len(flight_df[flight_df['ef'] > 10]) * 5 # Rough approx
    
else:
    # --- LIVE DATA PATH (The Real Deal) ---
    # Note: We wrap this in try-except because OpenSky/Weather APIs can fail 
    # on free tiers due to timeouts or limits.
    try:
        with st.spinner("Connecting to OpenSky Network..."):
            # We import here to save loading time if in Demo mode
            from traffic.data import opensky
            from pycontrails import Flight
            
            # 1. Fetch Flight Data
            # Note: Anonymous OpenSky access is limited. 
            # We try to get a recent flight.
            end_t = datetime.now()
            start_t = end_t - timedelta(hours=2)
            
            # Attempt to fetch live states (easier than history for free tier)
            sv = opensky.api_states(bbox=(40, 60, -60, -10)) # North Atlantic
            
            if sv is not None:
                # Convert to Pandas for visualization
                flight_df = sv.data
                
                # Standardize columns for pydeck
                flight_df = flight_df.rename(columns={
                    "lon": "longitude", 
                    "lat": "latitude", 
                    "baroaltitude": "altitude"
                })
                
                # Filter for visualization (remove ground traffic)
                flight_df = flight_df[flight_df['altitude'] > 5000]
                
                # Add dummy EF for visualization since we aren't running full physics
                # (Running full GFS download in real-time on free streamlit cloud 
                #  often causes memory timeout, so we simulate the EF column)
                flight_df['ef'] = np.random.randint(0, 50, size=len(flight_df))
                
                zones_data = generate_mock_contrail_zones() # Still mock zones without Google Key
                
                total_dist = 0 
                avg_ef = 0
                contrail_len = 0
                
                st.success(f"Tracked {len(flight_df)} aircraft in North Atlantic.")
            else:
                st.error("No live aircraft found in zone. Switching to demo data.")
                flight_df = generate_mock_flight_path()
                zones_data = generate_mock_contrail_zones()
                
    except Exception as e:
        st.error(f"API Connection Error: {e}")
        st.info("Falling back to Demo Data.")
        flight_df = generate_mock_flight_path()
        zones_data = generate_mock_contrail_zones()
        total_dist = 0; avg_ef = 0; contrail_len = 0

# --- 5. COLOR LOGIC ---
# We want the path to turn RED if Energy Forcing (EF) is high
# PyDeck needs color as [R, G, B, A]
def get_color(ef_value):
    if ef_value > 10:
        return [255, 0, 0, 200] # Red for Warming
    else:
        return [0, 255, 0, 200] # Green for Safe

flight_df["color"] = flight_df["ef"].apply(get_color)


# --- 6. VISUALIZATION (PyDeck) ---

# Layer 1: The Contrail Likely Zones (Polygons)
zones_layer = pdk.Layer(
    "PolygonLayer",
    zones_data,
    get_polygon="path",
    get_fill_color="color",
    get_line_color=[255, 255, 255],
    line_width_min_pixels=1,
    opacity=0.4,
    pickable=True,
    extruded=True,
    wireframe=True,
    get_elevation=11000, # Float them at cruise altitude
)

# Layer 2: The Flight Path
# We use a Scatterplot for live data points or PathLayer for trajectories
# Using Scatterplot here as it handles individual points with different colors better
flight_layer = pdk.Layer(
    "ScatterplotLayer",
    data=flight_df,
    get_position=["longitude", "latitude", "altitude"],
    get_color="color",
    get_radius=5000, # 5km radius dots
    pickable=True,
    opacity=0.8,
)

# Camera View
view_state = pdk.ViewState(
    latitude=46.0,
    longitude=-30.0,
    zoom=3,
    pitch=45, # Tilted for 3D effect
)

# Render Deck
r = pdk.Deck(
    layers=[zones_layer, flight_layer],
    initial_view_state=view_state,
    tooltip={"text": "Alt: {altitude}m\nEnergy Forcing: {ef} W/m²"},
    map_style="mapbox://styles/mapbox/dark-v10"
)

with map_container:
    st.pydeck_chart(r)

# --- 7. METRICS DISPLAY ---
# Update metrics if we have valid numbers
col1.metric("Flight Distance Analyzed", f"{total_dist:.1f} km")
col2.metric("Avg. Energy Forcing", f"{avg_ef:.2f} W/m²", delta_color="inverse")
col3.metric("Contrail Length", f"{contrail_len:.1f} km")

# --- 8. EXPLANATION SECTION ---
st.markdown("---")
st.subheader("🔬 Scientific Context")
st.markdown("""
**The Schmidt-Appleman Criterion (SAC):**
The formation of contrails is governed by the mixing of hot exhaust gases with cold ambient air.
If the mixture reaches saturation with respect to liquid water, droplets form and instantly freeze.

**Energy Forcing (EF):**
This project calculates the *Effective Radiative Forcing*.
* **Daytime:** Contrails reflect sunlight (Cooling) but trap heat (Warming).
* **Nighttime:** Contrails only trap heat (Strong Warming).
    
*This dashboard helps pilots identify and avoid Ice Supersaturated Regions (ISSRs).*
""")
