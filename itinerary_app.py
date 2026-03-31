import streamlit as st
import pandas as pd
from streamlit_calendar import calendar
from datetime import datetime
import folium
from streamlit_folium import st_folium
from folium.plugins import Fullscreen
import math

# 1. Page Config
st.set_page_config(page_title="Europe 2027 Master Plan", layout="wide")

# --- SESSION STATE ---
if 'clicked_event' not in st.session_state:
    st.session_state.clicked_event = None

# --- GLOBAL HELPERS ---

def get_distance(lat1, lon1, lat2, lon2):
    """Haversine formula for distance calculation."""
    if None in [lat1, lon1, lat2, lon2] or pd.isna(lat1): return 999
    R = 6371  # Earth radius in km
    dlat, dlon = math.radians(lat2-lat1), math.radians(lon2-lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

def get_marker_color(slot):
    """Returns a specific color based on the time of day."""
    slot = str(slot).lower()
    if 'morning' in slot: return 'orange'
    if 'afternoon' in slot: return 'blue'
    if 'night' in slot: return 'darkpurple'
    return 'red'

def add_map_standard_features(map_object):
    """Applies Fullscreen and other standard features to any map."""
    Fullscreen(
        position="topright",
        title="Expand Map",
        title_cancel="Exit Fullscreen",
        force_separate_button=True,
    ).add_to(map_object)
    return map_object

# --- DATA LOADING ---
@st.cache_data
def load_data():
    try:
        df = pd.read_csv('itinerary.csv')
        df.columns = df.columns.str.strip()
        
        # Default empty values for missing columns
        for col in ['Duration', 'Flexible', 'Slot', 'Notes', 'Lat', 'Long']:
            if col not in df.columns: df[col] = "N/A"
            
        # Standardize Dates
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        df = df.dropna(subset=['Date'])
        df['Date_Str'] = df['Date'].dt.strftime('%Y-%m-%d')
        
        # Clean Weather Data (Numeric conversion)
        for col in ['Hist_Temp', 'Hist_Rain']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        return df
    except Exception as e:
        st.error(f"Data Load Error: {e}")
        return pd.DataFrame()

df = load_data()

CITY_COORDS = {
    "Helsinki": [60.1699, 24.9384], "Krakow": [50.0647, 19.9450],
    "Prague": [50.0755, 14.4378], "Vienna": [48.2082, 16.3738]
}

# --- APP UI ---
st.title("🇪🇺 Grand European Tour 2027")

if not df.empty:
    tab1, tab2, tab3 = st.tabs(["📅 Calendar", "🗺️ Full Trip Map", "📋 Daily Walkability"])

     # --- TAB 1: CALENDAR ---
    with tab1:
        first_date = df['Date'].min().strftime('%Y-%m-%d')
        col_cal, col_info = st.columns([2, 1])
        
        with col_cal:
            events = []
            for _, row in df.iterrows():
                # --- NEW TIME-BLOCK LOGIC ---
                # 1. Start Time: Use Time_Fixed column, default to 09:00 if empty
                start_time = row['Time_Fixed'] if pd.notna(row['Time_Fixed']) else "09:00"
                start_iso = f"{row['Date_Str']}T{start_time}:00"
                
                # 2. End Time: Add 'Duration' to the start time
                try:
                    # Cleans '4h' or '2.5' into a number
                    dur_val = float(str(row['Duration']).lower().replace('h', ''))
                except:
                    dur_val = 1.0 # Default to 1 hour if data is missing
                
                end_dt = pd.to_datetime(start_iso) + pd.Timedelta(hours=dur_val)
                end_iso = end_dt.strftime('%Y-%m-%dT%H:%M:%S')

                icon = {"Morning": "🌅", "Afternoon": "⛅", "Night": "🌙"}.get(row['Slot'], "📍")
                
                events.append({
                    "title": f"{icon} {row['Activity']}",
                    "start": start_iso,
                    "end": end_iso,      # This sets the height of the block
                    "allDay": False,     # This drops it into the time grid
                    "backgroundColor": get_marker_color(row['Slot']),
                    "extendedProps": {
                        "notes": row['Notes'], 
                        "flex": row['Flexible'],
                        "dur": row['Duration'], 
                        "city": row['City']
                    }
                })
            
            calendar_options = {
                "initialDate": first_date,
                "initialView": "dayGridMonth",
                "headerToolbar": {
                    "left": "prev,next today",
                    "center": "title",
                    "right": "dayGridMonth,timeGridWeek,timeGridDay"
                },
                "height": 700,
                "navLinks": True,
            }
            
            state = calendar(events=events, options=calendar_options)
            
            if state.get("eventClick"):
                st.session_state.clicked_event = state["eventClick"]["event"]
        
        with col_info:
            if st.session_state.clicked_event:
                e = st.session_state.clicked_event
                p = e.get("extendedProps", {})
                
                st.markdown(f"### {e['title']}")
                st.write(f"**📍 {p.get('city')}** | **⏳ {p.get('dur')}**")
                st.write(f"**Flexibility:** {p.get('flex')}")
                st.info(p.get('notes'))
                
                if st.button("Clear Selection"):
                    st.session_state.clicked_event = None
                    st.rerun()
            else:
                st.write("💡 *Click an event on the calendar to see deep-dive details here.*") 
    
    # --- TAB 2: OVERVIEW MAP ---
    with tab2:
        m_full = folium.Map(location=[50.0, 15.0], zoom_start=4)
        add_map_standard_features(m_full)
        for city, loc in CITY_COORDS.items():
            if city in df['City'].values:
                folium.Marker(loc, popup=city, icon=folium.Icon(color='red')).add_to(m_full)
        st_folium(m_full, width=1100, height=500, key="global_map")

    # --- TAB 3: DAILY WALKABILITY & WEATHER ---
    with tab3:
        st.header("📍 Daily Deep Dive")
        selected_date = st.selectbox("Select Date:", sorted(df['Date_Str'].unique()), key="date_select_tab3")
        day_data = df[df['Date_Str'] == selected_date].copy()

        if not day_data.empty:
            current_city = day_data.iloc[0]['City']
            hotel = day_data[day_data['Activity'].str.contains('Hotel|Stay|Check-in', case=False, na=False)]

            # METRIC ROW
            m1, m2, m3 = st.columns(3)

            # Walkability
            if not hotel.empty:
                h_lat, h_lon = hotel.iloc[0]['Lat'], hotel.iloc[0]['Long']
                day_data['km'] = day_data.apply(lambda r: get_distance(h_lat, h_lon, r['Lat'], r['Long']), axis=1)
                walkable = day_data[(day_data['km'] <= 1.25) & (day_data['km'] > 0)]
                score = (len(walkable) / (len(day_data)-1)) * 100 if len(day_data) > 1 else 100
                m1.metric("Walkability Score", f"{int(score)}%")
            else:
                m1.metric("Walkability Score", "N/A")

            # Weather
            t, r = day_data.iloc[0].get('Hist_Temp'), day_data.iloc[0].get('Hist_Rain')
            m2.metric("Avg Temp (Hist.)", f"{round(t, 1)}°C" if pd.notna(t) else "--")
            m3.metric("Avg Rain (Hist.)", f"{round(r, 1)}mm" if pd.notna(r) else "--")
            if pd.notna(r) and r > 2.0:
                st.warning(f"☔ Historically a wet day in {current_city} ({r}mm).")

            # LIST AND MAP
            col_list, col_map = st.columns([1, 1.2])
            with col_list:
                for _, row in day_data.iterrows():
                    with st.expander(f"**{row['Slot']}**: {row['Activity']}"):
                        st.write(f"**Duration:** {row['Duration']} | **Flex:** {row['Flexible']}")
                        if pd.notna(row['Notes']): st.info(row['Notes'])

            with col_map:
                m_daily = folium.Map(location=[day_data.iloc[0]['Lat'], day_data.iloc[0]['Long']], zoom_start=14)
                add_map_standard_features(m_daily)
                
                if not hotel.empty:
                    folium.Circle([h_lat, h_lon], radius=1250, color='green', fill=True, fill_opacity=0.1).add_to(m_daily)
                    folium.Marker([h_lat, h_lon], icon=folium.Icon(color='black', icon='home')).add_to(m_daily)

                for _, row in day_data.iterrows():
                    if pd.notna(row['Lat']) and "Hotel" not in row['Activity']:
                        folium.Marker(
                            [row['Lat'], row['Long']], 
                            popup=row['Activity'],
                            icon=folium.Icon(color=get_marker_color(row['Slot']), icon='info-sign')
                        ).add_to(m_daily)

                st_folium(m_daily, width=500, height=450, key=f"map_{selected_date}")