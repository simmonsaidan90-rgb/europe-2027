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
        df = df.dropna(subset=['Date', 'Activity'], how='all')
        # Handle the specific CSV date format
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
        "Helsinki": "❄️ **Helsinki Strategy:** Extremely Cold (-10°C). Use the underground tunnels where possible. Double socks.",
        "Krakow": "🧥 **Krakow Strategy:** Freezing (0°C). Auschwitz is very exposed; you need a windproof outer layer.",
        "Prague": "🧣 **Prague Strategy:** Chilly (2°C). Cobblestones are slippery. Woolen insoles are a game changer.",
        "Vienna": "🧤 **Vienna Strategy:** Crisp (3°C). Perfect for coffee houses. Pack one 'Grand' outfit for the Sacher/Opera.",
        "Budapest": "💨 **Budapest Strategy:** Windy (4°C). The Danube breeze is biting. Ideal for thermal bath days.",
        "Rome": "🌤️ **Rome Strategy:** Milder (10°C). High chance of 'winter sun'. A light scarf and layers are perfect.",
        "Paris": "🌦️ **Paris Strategy:** Damp (8°C). Pack a compact umbrella. Dress is 'casual chic'—darker colors fit in better."
    }
    return tips.get(city, "🌡️ Check local forecast for winter conditions.")

# --- APP LAYOUT ---
st.title("🇪🇺 Grand European Tour 2027")

if df.empty:
    st.warning("Please check your itinerary.csv on GitHub.")
else:
    tab1, tab2, tab3 = st.tabs(["📅 Calendar & Details", "🗺️ Full Trip Map", "📋 Daily Deep-Dive"])

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
                st.write(f"**📍 {props.get('city')}** | **⏳ {props.get('dur')}**")
                st.info(props.get('notes'))
                st.warning(get_weather_tip(props.get('city')))
                if st.button("Close Details"):
                    st.session_state.clicked_event = None
                    st.rerun()
            else:
                st.write("Click a calendar event for notes.")

    # TAB 2: FULL MAP
    with tab2:
        m_full = folium.Map(location=[50.0, 15.0], zoom_start=4)
        for city, loc in CITY_COORDS.items():
            if city in df['City'].values:
                folium.Marker(loc, popup=city, icon=folium.Icon(color='red')).add_to(m_full)
        st_folium(m_full, width=1000, height=500, key="full_map")

    # TAB 3: DAILY DEEP DIVE (With Daily Weather & Map)
    with tab3:
        selected_date = st.selectbox("Select a day to visualize:", sorted(df['Date'].unique()))
        day_data = df[df['Date'] == selected_date]
        
        if not day_data.empty:
            current_city = day_data.iloc[0]['City']
            
            # Header Row: Weather & City Info
            st.subheader(f"Plan for {selected_date} in {current_city}")
            st.info(get_weather_tip(current_city))
            
            col_list, col_map = st.columns([1, 1])
            
            with col_list:
                for _, row in day_data.iterrows():
                    with st.expander(f"**{row['Slot']}**: {row['Activity']}"):
                        st.write(f"**Duration:** {row.get('Duration', 'TBD')}")
                        st.write(f"**Flexible:** {row.get('Flexible', 'N/A')}")
                        st.write(row['Notes'])
            
            with col_map:
                # Daily Map Logic
                city_center = CITY_COORDS.get(current_city, [50.0, 15.0])
                m_daily = folium.Map(location=city_center, zoom_start=13)
                
                # Add a marker for the day's activity
                # (Note: In future you can add Lat/Long columns to the CSV for specific sites!)
                folium.Marker(
                    city_center, 
                    popup=f"Today's Base: {current_city}",
                    icon=folium.Icon(color='blue', icon='home')
                ).add_to(m_daily)
                
                st_folium(m_daily, width=500, height=400, key=f"map_{selected_date}")        "Prague": "🧣 Chilly (2°C). Cobblestones are slippery when icy. Wear grip shoes.",
        "Vienna": "🧤 Crisp (3°C). Formal wear needed for Opera/Sacher. Wool coat recommended.",
        "Budapest": "💨 Windy/Cold (4°C). Thermal baths are great, but bring a warm robe for the walk back.",
        "Rome": "🌤️ Milder (10°C). Light jacket and umbrella for winter rain.",
        "Paris": "🌦️ Damp (8°C). Stylish layers and a trench coat or umbrella."
    }
    return tips.get(city, "🌡️ Check local forecast for winter conditions.")

# 4. Interface Layout
st.title("🇪🇺 Grand European Tour 2027")

if df.empty:
    st.warning("Please check your itinerary.csv on GitHub.")
else:
    tab1, tab2, tab3 = st.tabs(["📅 Calendar & Details", "🗺️ Trip Map", "📋 Daily Deep-Dive"])

    with tab1:
        col_cal, col_info = st.columns([2, 1])
        
        with col_cal:
            cal_options = {
                "headerToolbar": {"left": "prev,next today", "center": "title", "right": "dayGridMonth,dayGridWeek"},
                "initialView": "dayGridMonth",
                "height": 650,
            }
            # Create events for calendar
            events = []
            for _, row in df.iterrows():
                icon = {"Morning": "🌅", "Afternoon": "⛅", "Night": "🌙"}.get(row.get('Slot'), "📍")
                events.append({
                    "title": f"{icon} {row['Activity']}",
                    "start": row['Date'],
                    "end": row['Date'],
                    "allDay": True,
                    "extendedProps": {
                        "notes": row.get('Notes', ''),
                        "flex": row.get('Flexible', 'N/A'),
                        "dur": row.get('Duration', 'TBD'),
                        "city": row.get('City', 'Unknown'),
                        "slot": row.get('Slot', 'N/A')
                    }
                })
            
            state = calendar(events=events, options=cal_options)
            
            # Update Session State if an event is clicked
            if state.get("eventClick"):
                st.session_state.clicked_event = state["eventClick"]["event"]

        with col_info:
            st.subheader("📝 Activity Details")
            if st.session_state.clicked_event:
                event = st.session_state.clicked_event
                props = event.get("extendedProps", {})
                
                st.markdown(f"### {event['title']}")
                st.write(f"**📍 City:** {props.get('city')}")
                st.write(f"**🕒 Slot:** {props.get('slot')} ({props.get('dur')})")
                st.write(f"**♻️ Flexible:** {props.get('flex')}")
                
                st.divider()
                st.info(f"**Notes:**\n{props.get('notes')}")
                
                st.subheader("🌡️ Packing/Weather Tip")
                st.warning(get_weather_tip(props.get('city')))
                
                if st.button("Clear Selection"):
                    st.session_state.clicked_event = None
                    st.rerun()
            else:
                st.write("Click an event on the calendar to see notes and weather tips here.")

    with tab2:
        st.header("Global Logistics Map")
        # Define city coordinates for the map
        coords = {
            "Helsinki": [60.1699, 24.9384], "Krakow": [50.0647, 19.9450],
            "Prague": [50.0755, 14.4378], "Vienna": [48.2082, 16.3738],
            "Budapest": [47.4979, 19.0402], "Rome": [41.9028, 12.4964],
            "Paris": [48.8566, 2.3522]
        }
        
        m = folium.Map(location=[50.0, 15.0], zoom_start=4)
        for city, loc in coords.items():
            if city in df['City'].values:
                folium.Marker(loc, popup=city, tooltip=city).add_to(m)
        
        st_folium(m, width=1000, height=500)

    with tab3:
        st.subheader("Detailed Day Search")
        selected_date = st.selectbox("View full day summary:", sorted(df['Date'].unique()))
        day_rows = df[df['Date'] == selected_date]
        for _, row in day_rows.iterrows():
            with st.expander(f"{row['Slot']}: {row['Activity']}"):
                st.write(row['Notes'])
