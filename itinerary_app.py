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
# Tab 2: which city is currently drilled into (None = overview)
if 'tab2_selected_city' not in st.session_state:
    st.session_state.tab2_selected_city = None
if 'tab2_map_center' not in st.session_state:
    st.session_state.tab2_map_center = None
if 'tab2_map_zoom' not in st.session_state:
    st.session_state.tab2_map_zoom = 13
# Tab 3: track which activity is focused on the map, and the last selected date
if 'tab3_map_center' not in st.session_state:
    st.session_state.tab3_map_center = None
if 'tab3_map_zoom' not in st.session_state:
    st.session_state.tab3_map_zoom = 14
if 'tab3_last_date' not in st.session_state:
    st.session_state.tab3_last_date = None

# --- GLOBAL MAP CONFIG ---
# Single source of truth for map appearance and sizing.
# Individual tabs may override zoom/center but should not override tile or sizing.
MAP_CONFIG = {
    "width": "100%",          # use_container_width equivalent via st_folium
    "height": 500,
    "default_zoom": 14,
    "overview_zoom": 4,
    "overview_center": [50.0, 15.0],
    "focused_zoom": 17,       # Tab 3: zoom level when an activity is focused
}

# Slot color definitions — single source of truth for both Folium markers and
# the FullCalendar backgroundColor. Folium uses its own named palette;
# the calendar needs standard CSS hex values.
SLOT_COLORS = {
    "morning":   {"folium": "orange",     "hex": "#fd7e14"},
    "afternoon": {"folium": "blue",       "hex": "#0d6efd"},
    "night":     {"folium": "darkpurple", "hex": "#6f42c1"},
    "default":   {"folium": "red",        "hex": "#dc3545"},
    "travel":    {"folium": "red",        "hex": "#dc3545"},  # transit legs: always red
}

# --- GLOBAL HELPERS ---

def get_distance(lat1, lon1, lat2, lon2):
    """Haversine formula for distance calculation."""
    if any(v is None or (isinstance(v, float) and math.isnan(v))
           for v in [lat1, lon1, lat2, lon2]):
        return 999
    R = 6371
    dlat, dlon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def _slot_key(slot):
    slot = str(slot).lower()
    if 'morning' in slot:   return 'morning'
    if 'afternoon' in slot: return 'afternoon'
    if 'night' in slot:     return 'night'
    return 'default'

def get_marker_color(slot):
    """Returns the Folium marker color for a time slot."""
    return SLOT_COLORS[_slot_key(slot)]["folium"]

def get_event_color(slot):
    """Returns the CSS hex color for a calendar event block."""
    return SLOT_COLORS[_slot_key(slot)]["hex"]

def build_base_map(lat, lon, zoom=None):
    """Creates a Folium map with all standard features applied.

    Every tab should call this instead of constructing a folium.Map directly,
    so that tile layers, controls, and other global settings stay consistent.
    """
    if zoom is None:
        zoom = MAP_CONFIG["default_zoom"]
    m = folium.Map(location=[lat, lon], zoom_start=zoom)
    Fullscreen(
        position="topright",
        title="Expand Map",
        title_cancel="Exit Fullscreen",
        force_separate_button=True,
    ).add_to(m)
    return m

def render_map(m, key):
    """Renders a Folium map via st_folium using the global sizing config."""
    return st_folium(m, use_container_width=True, height=MAP_CONFIG["height"], key=key)

# --- DATA LOADING ---
@st.cache_data
def load_data():
    try:
        df = pd.read_csv('itinerary.csv')
        df.columns = df.columns.str.strip()

        for col in ['Duration', 'Flexible', 'Slot', 'Notes', 'Lat', 'Long', 'Type']:
            if col not in df.columns:
                df[col] = "N/A"
        # Back-fill Type for any rows that weren't tagged in the CSV
        df['Type'] = df['Type'].fillna('Activity')

        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        df = df.dropna(subset=['Date'])
        df['Date_Str'] = df['Date'].dt.strftime('%Y-%m-%d')

        for col in ['Hist_Temp', 'Hist_Rain']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        # Ensure Lat/Long are numeric
        df['Lat'] = pd.to_numeric(df['Lat'], errors='coerce')
        df['Long'] = pd.to_numeric(df['Long'], errors='coerce')

        return df
    except Exception as e:
        st.error(f"Data Load Error: {e}")
        return pd.DataFrame()

df = load_data()

# --- SIDEBAR: DATA TOOLS ---
with st.sidebar:
    st.header("🛠️ Data Tools")

    # Detect rows that have coordinates but are missing weather data
    has_coords = df['Lat'].notna() & df['Long'].notna()
    weather_cols_present = 'Hist_Temp' in df.columns and 'Hist_Rain' in df.columns
    missing_weather = has_coords & (df['Hist_Temp'].isna() if weather_cols_present else True)
    missing_count = int(missing_weather.sum())

    if missing_count > 0:
        st.warning(f"🌡️ **{missing_count} activities** have coordinates but no weather data yet.")
    else:
        st.success("🌡️ Weather data is complete.")

    col_run, col_force = st.columns(2)
    run_weather = col_run.button("Update missing", key="wx_missing", disabled=(missing_count == 0))
    force_weather = col_force.button("Re-fetch all", key="wx_force")

    if run_weather or force_weather:
        from weather_updater import update_csv
        with st.spinner(f"Fetching 5-year averages (2020–2024)… this takes ~1 min for a full run."):
            update_csv(csv_path='itinerary.csv', force=force_weather)
        st.cache_data.clear()
        st.rerun()

    st.divider()
    st.caption("Weather data: Open-Meteo archive (ERA5), 5-year mean 2020–2024.")

# Derive city centre coordinates from the CSV (median of all activity lat/longs per city).
# This means any city added to the itinerary automatically appears on the overview map.
CITY_COORDS = (
    df.dropna(subset=["Lat", "Long"])
    .groupby("City")[["Lat", "Long"]]
    .median()
    .apply(lambda r: [r["Lat"], r["Long"]], axis=1)
    .to_dict()
)

# --- APP UI ---
st.title("🇪🇺 Grand European Tour 2027")

if not df.empty:
    tab1, tab2, tab3 = st.tabs(["📅 Calendar", "🗺️ Trip Map", "📋 Daily plan"])

    # --- TAB 1: CALENDAR ---
    with tab1:
        first_date = df['Date'].min().strftime('%Y-%m-%d')
        col_cal, col_info = st.columns([2, 1])

        with col_cal:
            events = []
            for _, row in df.iterrows():
                start_time = row['Time_Fixed'] if pd.notna(row['Time_Fixed']) else "09:00"
                start_iso = f"{row['Date_Str']}T{start_time}:00"

                try:
                    dur_val = float(str(row['Duration']).lower().replace('h', ''))
                except (ValueError, AttributeError):
                    dur_val = 1.0

                end_dt = pd.to_datetime(start_iso) + pd.Timedelta(hours=dur_val)
                end_iso = end_dt.strftime('%Y-%m-%dT%H:%M:%S')

                is_travel = str(row.get('Type', '')).strip().lower() == 'travel'
                if is_travel:
                    activity_lower = str(row['Activity']).lower()
                    if 'train' in activity_lower or 'rail' in activity_lower:
                        icon = "🚆"
                    elif 'bus' in activity_lower or 'coach' in activity_lower:
                        icon = "🚌"
                    else:
                        icon = "✈️"
                else:
                    icon = {"Morning": "🌅", "Afternoon": "⛅", "Night": "🌙"}.get(row['Slot'], "📍")
                bg_color = SLOT_COLORS["travel"]["hex"] if is_travel else get_event_color(row['Slot'])

                events.append({
                    "title": f"{icon} {row['Activity']}",
                    "start": start_iso,
                    "end": end_iso,
                    "allDay": False,
                    "backgroundColor": bg_color,
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
                "height": MAP_CONFIG["height"] + 200,  # calendar is taller than maps
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
                flex_val = str(p.get('flex', '')).strip().lower()
                flex_icon = "✅ Yes" if flex_val == 'yes' else "🚫 No"
                st.write(f"**Flexibility:** {flex_icon}")
                st.info(p.get('notes'))

                if st.button("Clear Selection"):
                    st.session_state.clicked_event = None
                    st.rerun()
            else:
                st.write("💡 *Click an event on the calendar to see deep-dive details here.*")

    # --- TAB 2: OVERVIEW / CITY DRILL-DOWN MAP ---
    with tab2:
        MAP_EXCLUDE_CITIES = {"Sydney"}
        activity_counts = df.groupby('City')['Activity'].count()

        selected_city = st.session_state.tab2_selected_city

        if selected_city is None:
            # ── OVERVIEW MODE ──────────────────────────────────────────────
            st.caption("Click a city pin to explore its activities.")
            m_full = build_base_map(
                MAP_CONFIG["overview_center"][0],
                MAP_CONFIG["overview_center"][1],
                zoom=MAP_CONFIG["overview_zoom"]
            )
            for city, loc in CITY_COORDS.items():
                if city in MAP_EXCLUDE_CITIES:
                    continue
                count = activity_counts.get(city, 0)
                folium.Marker(
                    loc,
                    # tooltip is the city name only — used to detect the click below
                    tooltip=city,
                    popup=folium.Popup(f"<b>{city}</b><br>{count} activities<br><i>Click to explore</i>", max_width=180),
                    icon=folium.Icon(color='red', icon='info-sign')
                ).add_to(m_full)

            result = render_map(m_full, key="global_map_overview")

            # Detect city pin click via the tooltip text returned by st_folium
            clicked_tooltip = (result or {}).get('last_object_clicked_tooltip')
            if clicked_tooltip and clicked_tooltip in CITY_COORDS:
                st.session_state.tab2_selected_city = clicked_tooltip
                st.rerun()

        else:
            # ── CITY DRILL-DOWN MODE ───────────────────────────────────────
            col_hdr, col_back = st.columns([4, 1])
            col_hdr.subheader(f"📍 {selected_city}")
            if col_back.button("← Overview", key="tab2_back"):
                st.session_state.tab2_selected_city = None
                st.session_state.tab2_map_center = None
                st.session_state.tab2_map_zoom = 15
                st.rerun()

            city_data = df[(df['City'] == selected_city) & (df['Type'] != 'Travel')].copy()
            city_loc = CITY_COORDS[selected_city]

            # Split into map column and compact activity list column
            col_map, col_list = st.columns([3, 1])

            with col_map:
                has_pins = city_data['Lat'].notna().any() and city_data['Long'].notna().any()

                if not has_pins:
                    st.info(f"No individual activity coordinates have been added for {selected_city} yet. "
                            f"Add Lat/Long values to the CSV rows for this city to see activity pins here.")
                else:
                    # Use focused centre if set, otherwise default to city centre
                    map_center = st.session_state.tab2_map_center or city_loc
                    map_zoom = st.session_state.tab2_map_zoom

                    m_city = build_base_map(map_center[0], map_center[1], zoom=map_zoom)

                    for _, row in city_data.iterrows():
                        if pd.notna(row['Lat']) and pd.notna(row['Long']):
                            flex_icon = "✅" if str(row['Flexible']).strip().lower() == 'yes' else "🚫"
                            friendly_date = pd.to_datetime(row['Date_Str']).strftime('%-d %b %y, %a')
                            is_focused = (
                                st.session_state.tab2_map_center is not None
                                and st.session_state.tab2_map_center == [row['Lat'], row['Long']]
                            )
                            popup_html = (
                                f"<b>{row['Activity']}</b><br>"
                                f"📅 {friendly_date}<br>"
                                f"⏳ {row['Duration']}<br>"
                                f"{flex_icon} Flexible: {row['Flexible']}<br>"
                                f"<hr style='margin:4px 0'>"
                                f"<small>{row['Notes']}</small>"
                            )
                            folium.Marker(
                                [row['Lat'], row['Long']],
                                tooltip=f"{row['Slot']}: {row['Activity']}",
                                popup=folium.Popup(popup_html, max_width=260),
                                icon=folium.Icon(
                                    color=get_marker_color(row['Slot']),
                                    icon='star' if is_focused else 'info-sign'
                                )
                            ).add_to(m_city)

                    if st.session_state.tab2_map_center is not None:
                        if st.button("🔄 Reset map view", key="tab2_reset_map"):
                            st.session_state.tab2_map_center = None
                            st.session_state.tab2_map_zoom = 13
                            st.rerun()

                    render_map(m_city, key=f"city_map_{selected_city}_{map_zoom}_{map_center[0]}")

            with col_list:
                st.caption(f"{len(city_data)} activities · 🌅 Morning · ⛅ Afternoon · 🌙 Night")

                for date_str, group in city_data.groupby('Date_Str', sort=True):
                    friendly_date = pd.to_datetime(date_str).strftime('%-d %b %y, %a')
                    st.markdown(f"###### {friendly_date}")
                    for idx, (_, row) in enumerate(group.iterrows()):
                        slot_icon = {"Morning": "🌅", "Afternoon": "⛅", "Night": "🌙"}.get(row['Slot'], "📍")
                        flex_icon = "✅" if str(row['Flexible']).strip().lower() == 'yes' else "🚫"
                        has_coords = pd.notna(row['Lat']) and pd.notna(row['Long'])
                        c_name, c_btn = st.columns([5, 1])
                        c_name.markdown(f"{slot_icon} {flex_icon} {row['Activity']}")
                        if has_coords:
                            if c_btn.button("📍", key=f"tab2_focus_{date_str}_{idx}", help="Focus map on this activity"):
                                st.session_state.tab2_map_center = [row['Lat'], row['Long']]
                                st.session_state.tab2_map_zoom = MAP_CONFIG["focused_zoom"]
                                st.rerun()

    # --- TAB 3: DAILY WALKABILITY & WEATHER ---
    with tab3:
        st.header("📍 Daily Deep Dive")
        selected_date = st.selectbox(
            "Select Date:",
            sorted(df['Date_Str'].unique()),
            format_func=lambda d: pd.to_datetime(d).strftime('%-d %b %y, %a'),
            key="date_select_tab3"
        )
        day_data = df[df['Date_Str'] == selected_date].copy()

        # Reset map focus whenever the date changes
        if st.session_state.tab3_last_date != selected_date:
            st.session_state.tab3_map_center = None
            st.session_state.tab3_map_zoom = MAP_CONFIG["default_zoom"]
            st.session_state.tab3_last_date = selected_date

        if not day_data.empty:
            current_city = day_data.iloc[0]['City']
            hotel = day_data[day_data['Activity'].str.contains('Hotel|Stay|Check-in', case=False, na=False)]

            # METRIC ROW
            m1, m2, m3 = st.columns(3)

            # Walkability — guard against zero non-hotel rows
            if not hotel.empty:
                h_lat, h_lon = hotel.iloc[0]['Lat'], hotel.iloc[0]['Long']
                day_data['km'] = day_data.apply(
                    lambda r: get_distance(h_lat, h_lon, r['Lat'], r['Long']), axis=1
                )
                non_hotel = day_data[day_data['km'] > 0]
                if len(non_hotel) > 0:
                    walkable = non_hotel[non_hotel['km'] <= 1.25]
                    score = (len(walkable) / len(non_hotel)) * 100
                else:
                    score = 100
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
                for idx, (_, row) in enumerate(day_data.iterrows()):
                    slot_color = get_event_color(row['Slot'])
                    with st.expander(f"**{row['Slot']}**: {row['Activity']} ({row['Duration']})"):
                        flex_val = str(row['Flexible']).strip().lower()
                        flex_icon = "✅ Yes" if flex_val == 'yes' else "🚫 No"
                        st.write(f"**Duration:** {row['Duration']} | **Flex:** {flex_icon}")
                        if pd.notna(row['Notes']):
                            st.info(row['Notes'])
                        # Focus button: zooms the map to this activity's location
                        if pd.notna(row['Lat']) and pd.notna(row['Long']):
                            if st.button("📍 Focus on map", key=f"focus_{idx}_{selected_date}"):
                                st.session_state.tab3_map_center = [row['Lat'], row['Long']]
                                st.session_state.tab3_map_zoom = MAP_CONFIG["focused_zoom"]
                                st.rerun()

            with col_map:
                # Determine map center: use focused activity if set, else default to first row
                if st.session_state.tab3_map_center is not None:
                    map_center = st.session_state.tab3_map_center
                    map_zoom = st.session_state.tab3_map_zoom
                else:
                    first_valid = day_data[pd.notna(day_data['Lat']) & pd.notna(day_data['Long'])]
                    map_center = [first_valid.iloc[0]['Lat'], first_valid.iloc[0]['Long']] if not first_valid.empty else MAP_CONFIG["overview_center"]
                    map_zoom = MAP_CONFIG["default_zoom"]

                m_daily = build_base_map(map_center[0], map_center[1], zoom=map_zoom)

                if not hotel.empty:
                    h_lat, h_lon = hotel.iloc[0]['Lat'], hotel.iloc[0]['Long']
                    folium.Circle(
                        [h_lat, h_lon], radius=1250,
                        color='green', fill=True, fill_opacity=0.1
                    ).add_to(m_daily)
                    folium.Marker(
                        [h_lat, h_lon],
                        icon=folium.Icon(color='black', icon='home'),
                        tooltip="Hotel / Base"
                    ).add_to(m_daily)

                for _, row in day_data.iterrows():
                    if (pd.notna(row['Lat']) and pd.notna(row['Long'])
                            and "Hotel" not in str(row['Activity'])
                            and str(row.get('Type', '')).strip().lower() != 'travel'):
                        is_focused = (
                            st.session_state.tab3_map_center is not None
                            and st.session_state.tab3_map_center == [row['Lat'], row['Long']]
                        )
                        folium.Marker(
                            [row['Lat'], row['Long']],
                            popup=row['Activity'],
                            tooltip=f"{row['Slot']}: {row['Activity']}",
                            icon=folium.Icon(
                                color=get_marker_color(row['Slot']),
                                icon='star' if is_focused else 'info-sign'
                            )
                        ).add_to(m_daily)

                # Reset focus button shown only when a focus is active
                if st.session_state.tab3_map_center is not None:
                    if st.button("🔄 Reset map view", key=f"reset_map_{selected_date}"):
                        st.session_state.tab3_map_center = None
                        st.session_state.tab3_map_zoom = MAP_CONFIG["default_zoom"]
                        st.rerun()

                render_map(m_daily, key=f"map_{selected_date}_{map_zoom}_{map_center[0]}")
