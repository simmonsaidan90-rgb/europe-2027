import streamlit as st
import pandas as pd
from streamlit_calendar import calendar
import folium
from streamlit_folium import st_folium
from folium.plugins import Fullscreen  # New Import for Full Screen

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
                if st.button("Close Details"):
                    st.session_state.clicked_event = None
                    st.rerun()

    # TAB 2: FULL MAP (Now with Fullscreen)
    with tab2:
        st.subheader("Overview Map")
        m_full = folium.Map(location=[50.0, 15.0], zoom_start=4)
        
        # ADD FULLSCREEN BUTTON
        Fullscreen(position="topleft", title="Expand Map", title_cancel="Exit Fullscreen").add_to(m_full)
        
        for city, loc in CITY_COORDS.items():
            if city in df['City'].values:
                folium.Marker(loc, popup=city, icon=folium.Icon(color='red')).add_to(m_full)
        st_folium(m_full, width=1100, height=600, key="full_map")

    # TAB 3: DAILY DEEP DIVE (Now with Fullscreen)
    with tab3:
        selected_date = st.selectbox("Select Date:", sorted(df['Date'].unique()))
        day_data = df[df['Date'] == selected_date]
        
        if not day_data.empty:
            current_city = day_data.iloc[0]['City']
            st.subheader(f"Plan for {selected_date} in {current_city}")
            col_list, col_map = st.columns([1, 1])
            
            with col_list:
                for _, row in day_data.iterrows():
                    with st.expander(f"**{row['Slot']}**: {row['Activity']}"):
                        st.write(row['Notes'])
            
            with col_map:
                city_center = CITY_COORDS.get(current_city, [50.0, 15.0])
                m_daily = folium.Map(location=city_center, zoom_start=13)
                
                # ADD FULLSCREEN BUTTON
                Fullscreen(position="topleft").add_to(m_daily)
                
                for _, row in day_data.iterrows():
                    if pd.notna(row.get('Lat')) and pd.notna(row.get('Long')):
                        folium.Marker(
                            location=[row['Lat'], row['Long']],
                            popup=row['Activity'],
                            icon=folium.Icon(color='blue', icon='info-sign')
                        ).add_to(m_daily)
                
                st_folium(m_daily, width=600, height=550, key=f"daily_map_{selected_date}")
