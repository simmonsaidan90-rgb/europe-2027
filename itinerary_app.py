import streamlit as st
import pandas as pd
from streamlit_calendar import calendar
import folium
from streamlit_folium import st_folium
from folium.plugins import Fullscreen

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

# --- CONSTANTS ---
CITY_COORDS = {
    "Helsinki": [60.1699, 24.9384], "Krakow": [50.0647, 19.9450],
    "Prague": [50.0755, 14.4378], "Vienna": [48.2082, 16.3738],
    "Budapest": [47.4979, 19.0402], "Rome": [41.9028, 12.4964],
    "Paris": [48.8566, 2.3522]
}

def get_weather_tip(city):
    tips = {
        "Helsinki": "❄️ **Helsinki:** Extremely Cold (-10°C). Use the underground tunnels where possible.",
        "Krakow": "🧥 **Krakow:** Freezing (0°C). Auschwitz is very exposed; windproof layers essential.",
        "Prague": "🧣 **Prague:** Chilly (2°C). Cobblestones are slippery; wear high-grip boots.",
        "Vienna": "🧤 **Vienna:** Crisp (3°C). Perfect for coffee houses. Pack formal wear for the Opera.",
        "Budapest": "💨 **Budapest:** Windy (4°C). The Danube breeze is biting. Ideal for thermal baths.",
        "Rome": "🌤️ **Rome:** Milder (10°C). High chance of 'winter sun'. Light layers recommended.",
        "Paris": "🌦️ **Paris:** Damp (8°C). Pack a compact umbrella and water-resistant coat."
    }
    return tips.get(city, "🌡️ Check local forecast for winter conditions.")

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
                        "notes": row.get('Notes', ''), 
                        "flex": row.get('Flexible', 'N/A'),
                        "dur": row.get('Duration', 'TBD'), 
                        "city": row.get('City', 'Unknown'),
                        "slot": row.get('Slot', 'N/A')
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
                st.warning(get_weather_tip(p.get('city')))
                if st.button("Close Details"):
                    st.session_state.clicked_event = None
                    st.rerun()

    # TAB 2: FULL MAP
    with tab2:
        m_full = folium.Map(location=[50.0, 15.0], zoom_start=4)
        Fullscreen().add_to(m_full)
        for city, loc in CITY_COORDS.items():
            if city in df['City'].values:
                folium.Marker(loc, popup=city, icon=folium.Icon(color='red')).add_to(m_full)
        st_folium(m_full, width=1100, height=600, key="full_map")

    # TAB 3: DAILY DEEP DIVE
    with tab3:
        selected_date = st.selectbox("Select Date:", sorted(df['Date'].unique()))
        day_data = df[df['Date'] == selected_date]
        
        if not day_data.empty:
            current_city = day_data.iloc[0]['City']
            st.subheader(f"Plan for {selected_date} in {current_city}")
            
            # Weather Tip moved to top of Daily Deep Dive
            st.warning(get_weather_tip(current_city))
            
            col_list, col_map = st.columns([1, 1])
            
            with col_list:
                for _, row in day_data.iterrows():
                    # Display Duration and Flex in the title of the expander
                    flex_status = "✅ Flexible" if str(row['Flexible']).lower() == 'yes' else "🚫 Fixed"
                    with st.expander(f"**{row['Slot']}**: {row['Activity']} ({row.get('Duration', 'TBD')})"):
                        st.write(f"**Status:** {flex_status}")
                        st.write(f"**Notes:** {row['Notes']}")
            
            with col_map:
                city_center = CITY_COORDS.get(current_city, [50.0, 15.0])
                m_daily = folium.Map(location=city_center, zoom_start=13)
                Fullscreen().add_to(m_daily)
                
                for _, row in day_data.iterrows():
                    if pd.notna(row.get('Lat')) and pd.notna(row.get('Long')):
                        folium.Marker(
                            location=[row['Lat'], row['Long']],
                            popup=row['Activity'],
                            icon=folium.Icon(color='blue', icon='info-sign')
                        ).add_to(m_daily)
                
                st_folium(m_daily, width=600, height=550, key=f"daily_map_{selected_date}")
