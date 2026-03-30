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
                    st.write(row['Notes'])def create_calendar_events(df):
    events = []
    for _, row in df.iterrows():
        # Map M/A/N to display titles or colors if desired
        slot_prefix = {"M": "🌅 Morning", "A": "⛅ Afternoon", "N": "🌙 Night"}.get(row['Time (General)'], "")
        
        events.append({
            "title": f"{slot_prefix}: {row['Display Name']}",
            "start": row['Date'],
            "end": row['Date'],
            "resourceId": row['City'],
            "allDay": True,
            "extendedProps": {
                "notes": row['Notes'],
                "flex": row['Flexible'],
                "duration": row['Duration']
            }
        })
    return events

# --- APP LAYOUT ---
st.title("🇪🇺 Europe 2027: Interactive Plan")

tab1, tab2 = st.tabs(["📅 Monthly Calendar", "📋 Daily Deep-Dive"])

with tab1:
    st.header("Trip Overview")
    calendar_options = {
        "headerToolbar": {
            "left": "today prev,next",
            "center": "title",
            "right": "dayGridMonth,dayGridWeek"
        },
        "initialView": "dayGridMonth",
    }
    
    # Render the calendar with events from your CSV
    state = calendar(events=create_calendar_events(df), options=calendar_options)
    
    # Interactive Sidebar Logic
    if state.get("eventClick"):
        event = state["eventClick"]["event"]
        st.sidebar.subheader(event["title"])
        props = event.get("extendedProps", {})
        st.sidebar.write(f"**Duration:** {props.get('duration', 'N/A')}")
        st.sidebar.write(f"**Flexible:** {props.get('flex', 'N/A')}")
        st.sidebar.info(f"**Notes:** {props.get('notes', 'No specific notes.')}")

with tab2:
    st.header("Morning, Afternoon, Night Breakdown")
    
    # Filter by Date
    available_dates = sorted(df['Date'].unique())
    selected_date = st.selectbox("Select a date to view rich details:", available_dates)
    
    day_plan = df[df['Date'] == selected_date].sort_values(by='Time (General)', ascending=False) # Simple sort N->M
    
    if day_plan.empty:
        st.write("No activities scheduled for this day.")
    else:
        for _, row in day_plan.iterrows():
            slot_label = {"M": "Morning", "A": "Afternoon", "N": "Night"}.get(row['Time (General)'], "Other")
            
            # Using Expanders for "Rich Information" as requested
            with st.expander(f"**{slot_label}**: {row['Display Name']} ({row['Duration']})"):
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**City:** {row['City']}")
                    st.write(f"**Flexible:** {row['Flexible']}")
                with col2:
                    if pd.notna(row['Notes']):
                        st.markdown(f"**Important Notes:**\n{row['Notes']}")
                    else:
                        st.write("*No additional notes for this slot.*")

# Optional: Map View could go here in a Tab 3
