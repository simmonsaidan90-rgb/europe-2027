import streamlit as st
import pandas as pd
from streamlit_calendar import calendar
import folium
from streamlit_folium import st_folium
from folium.plugins import Fullscreen
from meteostat import Point, Daily
from datetime import datetime

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
        
        # Clean coordinates
        if 'Lat' in df.columns and 'Long' in df.columns:
            df['Lat'] = pd.to_numeric(df['Lat'], errors='coerce')
            df['Long'] = pd.to_numeric(df['Long'], errors='coerce')
            
        # Standardize Dates
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        df = df.dropna(subset=['Date', 'Activity'], how='all')
        df = df.dropna(subset=['Date']) 
        df['Date_Str'] = df['Date'].dt.strftime('%Y-%m-%d')
        return df
    except Exception as e:
        st.error(f"Error loading CSV: {e}")
        return pd.DataFrame()

df = load_data()

# --- CONSTANTS ---
CITY_COORDS = {
    "Helsinki": [60.1699, 24.9384], "Krakow": [50.0647, 19.9450],
    "Prague": [50.0755, 14.4378], "Vienna": [48.2082, 16.3738],
    "Budapest": [47.4979, 19.0402], "Rome": [41.9028, 12.4964],
    "Paris": [48.8566, 2.3522]
}

# --- WEATHER LOGIC ---
@st.cache_data
def get_historical_weather(city, date_obj):
    try:
        # Check the same day/month in 2024 for a reality check
        check_date = datetime(2024, date_obj.month, date_obj.day)
        coords = CITY_COORDS.get(city)
        if not coords: return None
        
        location = Point(coords[0], coords[1])
        data = Daily(location, check_date, check_date)
        data = data.fetch()
        
        if not data.empty:
            return {
                "temp": round(data.iloc[0]['tavg'], 1),
                "min": round(data.iloc[0]['tmin'], 1),
                "max": round(data.iloc[0]['tmax'], 1)
            }
    except:
        return None

def get_strategy_tip(city):
    tips = {
        "Helsinki": "❄️ **Helsinki:** Heavy thermals. Use underground tunnels.",
        "Krakow": "🧥 **Krakow:** Auschwitz is windy/exposed. Windproof outer layer is key.",
        "Prague": "🧣 **Prague:** Slippery stones. Boots with deep tread/grip.",
        "Vienna": "🧤 **Vienna:** Coffee house breaks are essential. One 'Grand' outfit for Sacher.",
        "Budapest": "💨 **Budapest:** River wind is biting. Bring a warm robe for the Baths.",
        "Rome": "🌤️ **Rome:** Milder sun. Layers and a good scarf.",
        "Paris": "🌦️ **Paris:** Damp cold. Water-resistant coat and compact umbrella."
    }
    return tips.get(city, "🌡️ Check local winter packing guides.")

# --- APP LAYOUT ---
st.title("🇪🇺 Grand European Tour 2027")

if df.empty:
    st.warning("Please check your itinerary.csv on GitHub.")
else:
    tab1, tab2, tab3 = st.tabs(["📅 Calendar", "🗺️ Full Trip Map", "📋 Daily Deep-Dive"])

    # --- TAB 1: CALENDAR ---
    with tab1:
        col_cal, col_info = st.columns([2, 1])
        with col_cal:
            events = []
            for _, row in df.iterrows():
                icon = {"Morning": "🌅", "Afternoon": "⛅", "Night": "🌙"}.get(row.get('Slot'), "📍")
                events.append({
                    "title": f"{icon} {row['Activity']}",
                    "start": row['Date_Str'], "end": row['Date_Str'], "allDay": True,
                    "extendedProps": {
                        "notes": row.get('Notes', ''), 
                        "flex": row.get('Flexible', 'N/A'),
                        "dur": row.get('Duration', 'TBD'),
                        "city": row.get('City', 'Unknown'),
                        "date_obj": row['Date']
                    }
                })
            state = calendar(events=events, options={"initialView": "dayGridMonth", "height": 600})
            if state.get("eventClick"):
                st.session_state.clicked_event = state["eventClick"]["event"]
        
        with col_info:
            if st.session_state.clicked_event:
                e = st.session_state.clicked_event
                p = e.get("extendedProps", {})
                st.markdown(f"### {e['title']}")
                st.write(f"**⌛ Duration:** {p.get('dur')} | **♻️ Flexible:** {p.get('flex')}")
                st.info(p.get('notes'))
                st.warning(get_strategy_tip(p.get('city')))
                if st.button("Close Details"):
                    st.session_state.clicked_event = None
                    st.rerun()
            else:
                st.write("Click an event to see notes.")

    # --- TAB 2: OVERVIEW MAP ---
    with tab2:
        st.subheader("Global Logistics Map")
        m_full = folium.Map(location=[50.0, 15.0], zoom_start=4)
        Fullscreen().add_to(m_full)
        for city, loc in CITY_COORDS.items():
            if city in df['City'].values:
                folium.Marker(loc, popup=city, icon=folium.Icon(color='red')).add_to(m_full)
        st_folium(m_full, width=1100, height=600, key="full_map")

    # --- TAB 3: DAILY DEEP DIVE ---
    with tab3:
        selected_date_str = st.selectbox("Select Date:", sorted(df['Date_Str'].unique()))
        day_data = df[df['Date_Str'] == selected_date_str]
        
        if not day_data.empty:
            current_city = day_data.iloc[0]['City']
            dt_obj = day_data.iloc[0]['Date']
            
            st.subheader(f"Plan for {selected_date_str} in {current_city}")
            
            # Historical Weather Metric Row
            weather = get_historical_weather(current_city, dt_obj)
            if weather:
                w1, w2, w3 = st.columns(3)
                w1.metric("Historical Avg", f"{weather['temp']}°C")
                w2.metric("Typical Low", f"{weather['min']}°C")
                w3.metric("Typical High", f"{weather['max']}°C")
                if weather['min'] < 0:
                    st.snow()
                    st.warning(f"❄️ Historical Reality: Expect sub-zero temps. {get_strategy_tip(current_city)}")
                else:
                    st.info(get_strategy_tip(current_city))
            
            col_list, col_map = st.columns([1, 1])
            with col_list:
                for _, row in day_data.iterrows():
                    flex_icon = "✅" if str(row['Flexible']).lower() == 'yes' else "🚫"
                    with st.expander(f"**{row['Slot']}**: {row['Activity']} ({row.get('Duration', 'TBD')})"):
                        st.write(f"**Flexibility:** {flex_icon}")
                        st.write(f"**Notes:** {row['Notes']}")
            
            with col_map:
                city_center = CITY_COORDS.get(current_city, [50.0, 15.0])
                m_daily = folium.Map(location=city_center, zoom_start=13)
                Fullscreen().add_to(m_daily)
                for _, row in day_data.iterrows():
                    if pd.notna(row.get('Lat')) and pd.notna(row.get('Long')):
                        folium.Marker(
                            [row['Lat'], row['Long']], 
                            popup=row['Activity'],
                            icon=folium.Icon(color='blue', icon='info-sign')
                        ).add_to(m_daily)
                st_folium(m_daily, width=600, height=550, key=f"map_{selected_date_str}")
