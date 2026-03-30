import streamlit as st
import pandas as pd
from streamlit_calendar import calendar
import folium
from streamlit_folium import st_folium

# 1. Page Config
st.set_page_config(page_title="Europe 2027 Master Plan", layout="wide")

# --- SESSION STATE ---
if 'clicked_event' not in st.session_state:
    st.session_state.clicked_event = None

# --- DATA LOADING ---
@st.cache_data
def load_data():
    try:
        df = pd.read_csv('itinerary.csv') 
        df.columns = df.columns.str.strip()
        
        # Convert Lat/Long to numeric, forcing errors to NaN (so it doesn't crash)
        if 'Lat' in df.columns and 'Long' in df.columns:
            df['Lat'] = pd.to_numeric(df['Lat'], errors='coerce')
            df['Long'] = pd.to_numeric(df['Long'], errors='coerce')
            
        df = df.dropna(subset=['Date', 'Activity'], how='all')
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        df = df.dropna(subset=['Date']) 
        df['Date'] = df['Date'].dt.strftime('%Y-%m-%d')
        return df
    except Exception as e:
        st.error(f"Error loading CSV: {e}")
        return pd.DataFrame()

df = load_data()

# --- CONSTANTS & HELPERS ---
CITY_COORDS = {
    "Helsinki": [60.1699, 24.9384], "Krakow": [50.0647, 19.9450],
    "Prague": [50.0755, 14.4378], "Vienna": [48.2082, 16.3738],
    "Budapest": [47.4979, 19.0402], "Rome": [41.9028, 12.4964],
    "Paris": [48.8566, 2.3522]
}

def get_weather_tip(city):
    tips = {
        "Helsinki": "❄️ **Helsinki:** Extremely Cold (-10°C).",
        "Krakow": "🧥 **Krakow:** Freezing (0°C). Auschwitz is exposed.",
        "Prague": "🧣 **Prague:** Chilly (2°C). Cobblestones are slippery.",
        "Vienna": "🧤 **Vienna:** Crisp (3°C). Sacher/Opera readiness.",
        "Budapest": "💨 **Budapest:** Windy (4°C). Thermal bath season.",
        "Rome": "🌤️ **Rome:** Milder (10°C). Winter sun.",
        "Paris": "🌦️ **Paris:** Damp (8°C). Pack an umbrella."
    }
    return tips.get(city, "🌡️ Check local forecast.")

# --- APP LAYOUT ---
st.title("🇪🇺 Grand European Tour 2027")

if df.empty:
    st.warning("Please check your itinerary.csv on GitHub.")
else:
    tab1, tab2, tab3 = st.tabs(["📅 Calendar", "🗺️ Full Trip Map", "📋 Daily Deep-Dive"])

    # TAB 1: CALENDAR
    with tab1:
        col_cal, col_info = st.columns([2, 1])
        with col_cal:
            events = []
            for _, row in df.iterrows():
                icon = {"Morning": "🌅", "Afternoon": "⛅", "Night": "🌙"}.get(row.get('Slot'), "📍")
                events.append({
                    "title": f"{icon} {row['Activity']}",
                    "start": row['Date'], "end": row['Date'], "allDay": True,
                    "extendedProps": {
                        "notes": row.get('Notes', ''), "flex": row.get('Flexible', 'N/A'),
                        "dur": row.get('Duration', 'TBD'), "city": row.get('City', 'Unknown'),
                        "slot": row.get('Slot', 'N/A')
                    }
                })
            state = calendar(events=events, options={"initialView": "dayGridMonth", "height": 600})
            if state.get("eventClick"):
                st.session_state.clicked_event = state["eventClick"]["event"]

        with col_info:
            if st.session_state.clicked_event:
                e = st.session_state.clicked_event
                props = e.get("extendedProps", {})
                st.markdown(f"### {e['title']}")
                st.info(props.get('notes'))
                st.warning(get_weather_tip(props.get('city')))
                if st.button("Close Details"):
                    st.session_state.clicked_event = None
                    st.rerun()

    # TAB 2: FULL MAP
    with tab2:
        m_full = folium.Map(location=[50.0, 15.0], zoom_start=4)
        for city, loc in CITY_COORDS.items():
            if city in df['City'].values:
                folium.Marker(loc, popup=city, icon=folium.Icon(color='red')).add_to(m_full)
        st_folium(m_full, width=1000, height=600, key="full_map")

    # TAB 3: DAILY DEEP DIVE
    with tab3:
        selected_date = st.selectbox("Select Date:", sorted(df['Date'].unique()))
        day_data = df[df['Date'] == selected_date]
        
        if not day_data.empty:
            current_city = day_data.iloc[0]['City']
            st.subheader(f"Plan for {selected_date} in {current_city}")
            
            col_list, col_map = st.columns([1, 1])
            
            with col_list:
                st.info(get_weather_tip(current_city))
                for _, row in day_data.iterrows():
                    with st.expander(f"**{row['Slot']}**: {row['Activity']}"):
                        st.write(row['Notes'])
            
            with col_map:
                city_center = CITY_COORDS.get(current_city, [50.0, 15.0])
                m_daily = folium.Map(location=city_center, zoom_start=13)
                
                # Check for pins
                pins_added = 0
                for _, row in day_data.iterrows():
                    if pd.notna(row.get('Lat')) and pd.notna(row.get('Long')):
                        folium.Marker(
                            location=[row['Lat'], row['Long']],
                            popup=row['Activity'],
                            icon=folium.Icon(color='blue', icon='info-sign')
                        ).add_to(m_daily)
                        pins_added += 1
                
                # If no pins found, show the city center marker
                if pins_added == 0:
                    folium.Marker(city_center, popup="City Center", icon=folium.Icon(color='gray')).add_to(m_daily)
                
                st_folium(m_daily, width=600, height=550, key=f"daily_map_{selected_date}")
