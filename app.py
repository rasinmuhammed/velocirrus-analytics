import streamlit as st
import pandas as pd
import pydeck as pdk
import numpy as np
import requests
from datetime import datetime, timedelta
from shapely.geometry import Point, Polygon

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Velocirrus Analytics",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 2. HELPER FUNCTIONS ---

@st.cache_data(ttl=300) # Cache data for 5 mins to avoid hitting API limits
def get_opensky_data():
    """
    Fetches live flight data directly from OpenSky REST API.
    Replaces the heavy 'traffic' library.
    """
    # North Atlantic Bounding Box
    # lamin, lomin, lamax, lomax
    url = "https://opensky-network.org/api/states/all"
    params = {
        "lamin": 40.0,
        "lamax": 60.0,
        "lomin": -60.0,
        "lomax": -10.0
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        json_data = response.json()
        
        # OpenSky returns a list of lists. We need to map them to columns.
        col_names = ["icao24", "callsign", "origin_country", "time_position", 
                     "last_contact", "longitude", "latitude", "baro_altitude", 
                     "on_ground", "velocity", "true_track", "vertical_rate", 
                     "sensors", "geo_altitude", "squawk", "spi", "position_source"]
        
        if json_data['states'] is None:
            return pd.DataFrame(columns=col_names)
            
        df = pd.DataFrame(json_data['states'], columns=col_names)
        
        # Clean data: Ensure numerics and remove nulls
        df = df.dropna(subset=["longitude", "latitude", "baro_altitude"])
        df["baro_altitude"] = pd.to_numeric(df["baro_altitude"])
        
        # Filter for cruising altitude (approx > 20,000 ft / 6000m)
        df = df[df["baro_altitude"] > 6000]
        
        return df
        
    except Exception as e:
        st.sidebar.error(f"OpenSky API Error: {e}")
        return None

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
        
        zones = []
        if 'features' in data:
            for feature in data['features']:
                coords = feature['geometry']['coordinates'][0] 
                zones.append({
                    "path": coords,
                    "color": [255, 0, 0, 120],
                    "name": "Google Predicted CLZ"
                })
        return zones
    except Exception as e:
        st.sidebar.error(f"Google API Error: {str(e)}")
        return None

@st.cache_data
def generate_mock_contrail_zones():
    """Fallback mock zones"""
    p1 = [[-40, 45], [-30, 45], [-30, 50], [-40, 50], [-40, 45]]
    p2 = [[-20, 48], [-15, 48], [-15, 52], [-20, 52], [-20, 48]]
    return [
        {"name": "Zone Alpha (Simulated)", "path": p1, "color": [255, 0, 0, 100]},
        {"name": "Zone Beta (Simulated)", "path": p2, "color": [255, 140, 0, 100]}
    ]

# --- 3. SIDEBAR & CONTROLS ---
st.sidebar.header("🛸 Velocirrus Flight Deck")

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

flight_df = pd.DataFrame() # Initialize empty
zones_data = []
total_flights = 0

# --- LOGIC BRANCHING ---
if data_source == "Demo Mode (Simulation)":
    flight_df = pd.DataFrame({
        "longitude": np.linspace(-0.45, -73.77, 100),
        "latitude": np.linspace(51.47, 40.64, 100),
        "altitude": np.linspace(10668, 11887, 100),
        "callsign": ["DEMO"] * 100, # Added callsign for tooltip
        "ef": [50 * np.sin(i/10) if 30 < i < 70 else 0 for i in range(100)]
    })
    zones_data = generate_mock_contrail_zones()
    total_flights = 1

else:
    # --- LIVE DATA EXECUTION ---
    with st.spinner("Scanning Atmosphere & Traffic..."):
        # 1. Contrail Zones
        current_time = datetime.utcnow().isoformat() + "Z"
        
        if google_api_key:
            real_zones = get_google_contrail_zones(google_api_key, current_time)
            if real_zones:
                zones_data = real_zones
                st.toast("Connected to Google Contrails API", icon="☁️")
            else:
                zones_data = generate_mock_contrail_zones()
        else:
            zones_data = generate_mock_contrail_zones()

        # 2. Live Flights (Direct API Call)
        live_df = get_opensky_data()
        
        if live_df is not None and not live_df.empty:
            flight_df = live_df.rename(columns={"baro_altitude": "altitude"})
            
            # 3. Intersection Logic
            polys = [Polygon(z['path']) for z in zones_data]
            
            def check_risk(row):
                # Check if flight point is inside any Contrail Zone polygon
                pt = Point(row['longitude'], row['latitude'])
                for poly in polys:
                    if poly.contains(pt):
                        return 50 # High Risk
                return 0 # Low Risk

            if not flight_df.empty:
                flight_df['ef'] = flight_df.apply(check_risk, axis=1)
                total_flights = len(flight_df)
                st.success(f"Tracking {total_flights} live flights.")
        else:
            st.warning("No live flights found in zone or API limit reached. Showing Simulation.")
            # Fallback to simulation if live data fails
            flight_df = pd.DataFrame({
                "longitude": np.linspace(-0.45, -73.77, 100),
                "latitude": np.linspace(51.47, 40.64, 100),
                "altitude": np.linspace(10668, 11887, 100),
                "callsign": ["SIMULATED"] * 100,
                "ef": [50 * np.sin(i/10) if 30 < i < 70 else 0 for i in range(100)]
            })
            zones_data = generate_mock_contrail_zones()
            total_flights = 1

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
    data=flight_df,
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