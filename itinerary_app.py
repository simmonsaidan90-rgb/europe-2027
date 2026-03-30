import streamlit as st
import pandas as pd
from streamlit_calendar import calendar

# 1. Page Config
st.set_page_config(page_title="Europe 2027 Master Plan", layout="wide")

# 2. Robust Data Loading
@st.cache_data
def load_data():
    try:
        # Load and clean column headers
        df = pd.read_csv('itinerary.csv') 
        df.columns = df.columns.str.strip()
        
        # Drop completely empty rows and fix dates
        df = df.dropna(subset=['Date', 'Activity'], how='all')
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        df = df.dropna(subset=['Date']) 
        df['Date'] = df['Date'].dt.strftime('%Y-%m-%d')
        return df
    except Exception as e:
        st.error(f"Error loading CSV: {e}")
        return pd.DataFrame()

df = load_data()

# 3. Calendar Logic (M/A/N Icons + Sidebar Notes)
def create_calendar_events(df):
    events = []
    slot_icons = {"Morning": "🌅", "Afternoon": "⛅", "Night": "🌙"}
    
    for _, row in df.iterrows():
        icon = slot_icons.get(row.get('Slot', ''), "📍")
        
        # Safely get data even if columns are missing
        notes = row.get('Notes', 'No notes provided.')
        flex = row.get('Flexible', 'N/A')
        dur = row.get('Duration', 'TBD')
        
        events.append({
            "title": f"{icon} {row['Activity']}",
            "start": row['Date'],
            "end": row['Date'],
            "allDay": True,
            "extendedProps": {
                "notes": notes,
                "flex": flex,
                "duration": dur,
                "slot": row.get('Slot', 'N/A')
            }
        })
    return events

# 4. Interface Layout
st.title("🇪🇺 Grand European Tour 2027")
st.markdown("---")

if df.empty:
    st.warning("No data found in itinerary.csv. Please check your GitHub file.")
else:
    tab1, tab2 = st.tabs(["📅 Interactive Calendar", "📋 Daily Deep-Dive"])

    with tab1:
        st.subheader("Click an event to see travel details in the sidebar")
        cal_options = {
            "headerToolbar": {"left": "prev,next today", "center": "title", "right": "dayGridMonth,dayGridWeek"},
            "initialView": "dayGridMonth",
            "height": 600,
        }
        
        state = calendar(events=create_calendar_events(df), options=cal_options)
        
        # Sidebar functionality
        if state.get("eventClick"):
            event = state["eventClick"]["event"]
            st.sidebar.header("📍 Activity Details")
            st.sidebar.subheader(event["title"])
            props = event.get("extendedProps", {})
            st.sidebar.write(f"**🕒 Slot:** {props.get('slot')}")
            st.sidebar.write(f"**⌛ Duration:** {props.get('duration')}")
            st.sidebar.write(f"**♻️ Flexible:** {props.get('flex')}")
            st.sidebar.divider()
            st.sidebar.info(f"**Notes:**\n{props.get('notes')}")

    with tab2:
        st.subheader("Plan by Date")
        selected_date = st.selectbox("Choose a day:", sorted(df['Date'].unique()))
        day_plan = df[df['Date'] == selected_date]
        
        for _, row in day_plan.iterrows():
            with st.expander(f"**{row['Slot']}**: {row['Activity']} ({row.get('Duration', 'TBD')})"):
                col1, col2 = st.columns([1, 2])
                with col1:
                    st.write(f"**City:** {row['City']}")
                    st.write(f"**Flexibility:** {row['Flexible']}")
                    st.write(f"**Category:** {row.get('Type', 'Activity')}")
                with col2:
                    st.markdown("**Notes & Rich Info:**")
                    st.write(row['Notes'])
