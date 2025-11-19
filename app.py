import streamlit as st
import pandas as pd
import pydeck as pdk
import numpy as np
import geopandas as gpd
import requests
from datetime import datetime, timedelta
from shapely.geometry import Point, Polygon, shape

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Velocirrus Analytics",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 2. HELPER FUNCTIONS ---

@st.cache_data
def get_google_contrail_zones(api_key, time_iso):
    """
    Fetches real Contrail Likely Zones (CLZs) from Google's API.
    """
    url = "https://contrails.googleapis.com/v2/regions"
    params = {
        "key": api_key,
        "time": time_iso
    }
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        
        # Parse GeoJSON to list of dicts for PyDeck
        # Google returns MultiPolygons
        zones = []
        if 'features' in data:
            for feature in data['features']:
                # Extract coordinates
                coords = feature['geometry']['coordinates'][0] 
                zones.append({
                    "path": coords,
                    "color": [255, 0, 0, 120], # Red for danger
                    "name": "Google Predicted CLZ"
                })
        return zones
    except Exception as e:
        st.sidebar.error(f"Google API Error: {str(e)}")
        return None

@st.cache_data
def generate_mock_contrail_zones():
    """Fallback mock zones if API fails or no key provided"""
    p1 = [[-40, 45], [-30, 45], [-30, 50], [-40, 50], [-40, 45]]
    p2 = [[-20, 48], [-15, 48], [-15, 52], [-20, 52], [-20, 48]]
    return [
        {"name": "Zone Alpha (Simulated)", "path": p1, "color": [255, 0, 0, 100]},
        {"name": "Zone Beta (Simulated)", "path": p2, "color": [255, 140, 0, 100]}
    ]

# --- 3. SIDEBAR & CONTROLS ---
st.sidebar.header("🛸 Velocirrus Flight Deck")

# API KEY INPUT
google_api_key = st.sidebar.text_input("Google API Key (Optional)", type="password")

data_source = st.sidebar.radio(
    "Data Source",
    ["Live Data (OpenSky + Google)", "Demo Mode (Simulation)"]
)

st.sidebar.markdown("---")
st.sidebar.info(
    """
    **Velocirrus Analytics**
    *Optimizing the Invisible.*
    
    **Legend:**
    🔴 Red Zone: High Contrail Probability
    ✈️ White Dot: Aircraft
    """
)

# --- 4. MAIN LOGIC ENGINE ---
st.title("⚡ Velocirrus")
st.markdown("**Real-time Contrail Mitigation & Trajectory Optimization**")

map_container = st.container()
col1, col2, col3 = st.columns(3)

flight_data = []
zones_data = []
status_msg = st.empty()

# --- LOGIC BRANCHING ---
if data_source == "Demo Mode (Simulation)":
    # ... (Existing mock logic kept for safety) ...
    flight_df = pd.DataFrame({
        "longitude": np.linspace(-0.45, -73.77, 100),
        "latitude": np.linspace(51.47, 40.64, 100),
        "altitude": np.linspace(10668, 11887, 100),
        "ef": [50 * np.sin(i/10) if 30 < i < 70 else 0 for i in range(100)]
    })
    zones_data = generate_mock_contrail_zones()
    total_flights = 1

else:
    # --- LIVE DATA EXECUTION ---
    try:
        with st.spinner("Scanning Atmosphere & Traffic..."):
            # 1. Fetch Contrail Zones (Google or Fallback)
            current_time = datetime.utcnow().isoformat() + "Z"
            
            if google_api_key:
                real_zones = get_google_contrail_zones(google_api_key, current_time)
                if real_zones:
                    zones_data = real_zones
                    st.toast("Connected to Google Contrails API", icon="☁️")
                else:
                    zones_data = generate_mock_contrail_zones()
            else:
                st.sidebar.warning("No API Key. Using Simulated Cloud Zones.")
                zones_data = generate_mock_contrail_zones()

            # 2. Fetch Live Flights (OpenSky)
            # We import inside the block to save startup time
            from traffic.data import opensky
            
            # Bounding box for North Atlantic [min_lat, max_lat, min_lon, max_lon]
            # OpenSky format: (min_lat, min_lon, max_lat, max_lon) -> NO, traffic uses (W, S, E, N) or similar
            # opensky.api_states bbox argument is (min_latitude, max_latitude, min_longitude, max_longitude)
            bbox = (40, 60, -60, -10) 
            
            sv = opensky.api_states(bbox=bbox)
            
            if sv is not None:
                flight_df = sv.data
                flight_df = flight_df.rename(columns={"lon": "longitude", "lat": "latitude", "baroaltitude": "altitude"})
                
                # Filter valid data
                flight_df = flight_df.dropna(subset=['longitude', 'latitude', 'altitude'])
                flight_df = flight_df[flight_df['altitude'] > 6000] # Only cruise altitude
                
                # 3. INTERSECTION LOGIC (The "Smart" Part)
                # If we don't have physics engine, we check if flight is INSIDE a Google Zone
                # This is a fast geometric lookup
                
                # Create polygons from zones
                polys = [Polygon(z['path']) for z in zones_data]
                
                def check_risk(row):
                    pt = Point(row['longitude'], row['latitude'])
                    for poly in polys:
                        if poly.contains(pt):
                            return 50 # High Risk
                    return 0 # Low Risk

                flight_df['ef'] = flight_df.apply(check_risk, axis=1)
                
                total_flights = len(flight_df)
                st.success(f"Tracking {total_flights} live flights across the Atlantic.")
            else:
                st.error("OpenSky Network busy/offline. Switching to simulation.")
                data_source = "Demo Mode (Simulation)" 
                # ... (Fallback to demo would happen here normally)
                
    except Exception as e:
        st.error(f"System Error: {e}")
        flight_df = pd.DataFrame() # Empty fallback

# --- 5. COLOR LOGIC ---
def get_color(ef_value):
    if ef_value > 10:
        return [255, 0, 0, 200] # Red (Contrail Formation Likely)
    else:
        return [0, 255, 100, 200] # Green (Safe)

if not flight_df.empty:
    flight_df["color"] = flight_df["ef"].apply(get_color)

# --- 6. VISUALIZATION ---
view_state = pdk.ViewState(latitude=48.0, longitude=-30.0, zoom=3, pitch=45)

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
    get_elevation=10000, # 30,000 ft
)

flight_layer = pdk.Layer(
    "ScatterplotLayer",
    data=flight_df if not flight_df.empty else [],
    get_position=["longitude", "latitude", "altitude"],
    get_color="color",
    get_radius=8000,
    pickable=True,
    opacity=0.9,
)

r = pdk.Deck(
    layers=[zones_layer, flight_layer],
    initial_view_state=view_state,
    tooltip={"text": "Callsign: {callsign}\nAlt: {altitude}m\nRisk Level: {ef}"},
    map_style="mapbox://styles/mapbox/dark-v10"
)

with map_container:
    st.pydeck_chart(r)

# --- 7. METRICS ---
if not flight_df.empty:
    col1.metric("Live Flights Tracked", total_flights)
    col2.metric("High Risk Intersections", len(flight_df[flight_df['ef'] > 0]))
    col3.metric("Data Source", "Google API" if google_api_key else "Simulation Engine")
