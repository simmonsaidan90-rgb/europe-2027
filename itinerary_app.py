import streamlit as st
import pandas as pd
from streamlit_calendar import calendar

# --- CONFIGURATION ---
st.set_page_config(page_title="Europe 2027 Itinerary", layout="wide")

# --- DATA LOADING ---
@st.cache_data
def load_data():
    # Loading the data from your uploaded file
    df = pd.read_csv('itinerary.csv')
    # Clean up empty rows if any
    df = df.dropna(subset=['Date', 'Display Name'], how='all')
    # Standardize Date format for Python (assuming D/M/YY from your file)
    df['Date'] = pd.to_datetime(df['Date'], dayfirst=True).dt.strftime('%Y-%m-%d')
    return df

df = load_data()

# --- CALENDAR EVENT PREPARATION ---
def create_calendar_events(df):
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
