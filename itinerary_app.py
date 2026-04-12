"""
Europe 2027 Itinerary App — Streamlit dashboard for trip planning.

Optimised for Streamlit Cloud deployment:
  - @st.fragment isolates map rerenders (no full-page rerun on focus clicks)
  - @st.cache_data pre-builds calendar events and group data once
  - Vectorised pandas operations replace .iterrows() where possible
  - Active-tab tracking skips rendering for hidden tabs

Environment:
  MiniForge3 on macOS ARM64.
  Setup: conda activate europe-2027 && streamlit run itinerary_app.py
"""

# ════════════════════════════════════════════════════════════════════════════════
# 0. ENVIRONMENT CHECK (on first import)
# ════════════════════════════════════════════════════════════════════════════════

try:
    from environment_check import EnvironmentChecker
    _checker = EnvironmentChecker(verbose=False)
    _checker.check_all()
    if _checker.errors:
        import streamlit as st
        st.error("Environment Check Failed")
        for err in _checker.errors:
            st.error(f"  - {err}")
        st.stop()
except ImportError:
    pass

# ════════════════════════════════════════════════════════════════════════════════
# 1. IMPORTS
# ════════════════════════════════════════════════════════════════════════════════

import streamlit as st
import pandas as pd
from streamlit_calendar import calendar
import folium
from streamlit_folium import st_folium
from folium.plugins import Fullscreen
from streamlit_js_eval import streamlit_js_eval
import math
import numpy as np
import requests
import hashlib
import json

# ════════════════════════════════════════════════════════════════════════════════
# 2. PAGE CONFIG & SESSION STATE
# ════════════════════════════════════════════════════════════════════════════════

st.set_page_config(page_title="Europe 2027 Master Plan", layout="wide")

_DEFAULT_STATE = {
    "clicked_event":      None,
    "active_tab":         0,
    "tab2_selected_city": None,
    "tab2_map_center":    None,
    "tab2_map_zoom":      13,
    "tab3_map_center":    None,
    "tab3_map_zoom":      14,
    "tab3_last_date":     None,
    # Sandbox state
    "sandbox_pending":    False,
    "sandbox_new_event":  None,
    "df_editable":        None,
}
for key, default in _DEFAULT_STATE.items():
    if key not in st.session_state:
        st.session_state[key] = default

# Mutable sandbox defaults — initialised separately to avoid sharing a module-level list
if "sandbox_changelog" not in st.session_state:
    st.session_state.sandbox_changelog = []
if "sandbox_events_hash" not in st.session_state:
    st.session_state.sandbox_events_hash = None
if "sandbox_last_cb_hash" not in st.session_state:
    st.session_state.sandbox_last_cb_hash = None

# Capture viewport dimensions once per session via JS — must live here at the
# top level so it fires exactly once per script run. _map_height() reads these
# values as a pure session_state lookup, avoiding duplicate-key errors when it
# is called multiple times within a single render.
if "viewport_width" not in st.session_state:
    _vp_dims = streamlit_js_eval(
        js_expressions="[window.innerWidth, window.parent.innerHeight]",
        key="_vp_dims",
    )
    if _vp_dims and len(_vp_dims) == 2:
        w, h = _vp_dims
        if w: st.session_state.viewport_width  = w
        if h: st.session_state.viewport_height = h

# ════════════════════════════════════════════════════════════════════════════════
# 3. CONSTANTS
# ════════════════════════════════════════════════════════════════════════════════

MAP_CONFIG = {
    "default_zoom":    14,
    "overview_zoom":   4,
    "overview_center": [50.0, 15.0],
    "focused_zoom":    17,
}


def _map_height() -> int:
    """Return a viewport-aware map height from session_state.

    Viewport dimensions are captured once at startup (section 2) via a single
    streamlit_js_eval call. This function is a pure session_state read — safe
    to call any number of times per render without causing duplicate-key errors.

    window.innerWidth        → Streamlit content-area width (iframe context)
    window.parent.innerHeight → true browser viewport height (parent frame)

    Sizing logic:
        Mobile  (vw < 768)  → fixed 350 px
        Tablet+ (vw ≥ 768)  → 64 % of viewport height, clamped 420–800 px
                               e.g. MacBook ~900 px vh  → ~576 px
                                    large monitor ~1200 px vh → 768 px
    """
    vw = st.session_state.get("viewport_width",  1024)
    vh = st.session_state.get("viewport_height",  900)

    if vw < 768:
        return 350                              # mobile: fixed, keep it tight
    return max(420, min(int(vh * 0.64), 800))  # 64 % of vh, capped at 800

SLOT_COLORS = {
    "morning":   {"folium": "orange",     "hex": "#fd7e14"},
    "afternoon": {"folium": "blue",       "hex": "#0d6efd"},
    "night":     {"folium": "darkpurple", "hex": "#6f42c1"},
    "default":   {"folium": "red",        "hex": "#dc3545"},
    "travel":    {"folium": "red",        "hex": "#dc3545"},
}

SLOT_ICONS = {"Morning": "\U0001f305", "Afternoon": "\u26c5", "Night": "\U0001f319"}
SLOT_ORDER = {"Morning": 0, "Afternoon": 1, "Night": 2}

MAP_EXCLUDE_CITIES = {"Sydney"}

EARTH_RADIUS_KM   = 6_371
WALKABILITY_KM     = 1.25
SENTINEL_DISTANCE  = 999

DAY_ABBREV = {
    "Monday": "Mon", "Tuesday": "Tue", "Wednesday": "Wed",
    "Thursday": "Thu", "Friday": "Fri", "Saturday": "Sat", "Sunday": "Sun",
}
DAY_ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# ════════════════════════════════════════════════════════════════════════════════
# 4. HELPERS — pure functions, no Streamlit side-effects
# ════════════════════════════════════════════════════════════════════════════════

def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance in km. Returns SENTINEL_DISTANCE for missing coords."""
    if any(v is None or (isinstance(v, float) and math.isnan(v))
           for v in (lat1, lon1, lat2, lon2)):
        return SENTINEL_DISTANCE
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return EARTH_RADIUS_KM * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def haversine_km_vectorised(lat1, lon1, lat2_arr, lon2_arr):
    """Vectorised haversine for numpy arrays. Returns array of distances in km."""
    lat1_r, lon1_r = np.radians(lat1), np.radians(lon1)
    lat2_r, lon2_r = np.radians(lat2_arr), np.radians(lon2_arr)
    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1_r) * np.cos(lat2_r) * np.sin(dlon / 2) ** 2
    return EARTH_RADIUS_KM * 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))


def _slot_key(slot):
    s = str(slot).lower()
    for name in ("morning", "afternoon", "night"):
        if name in s:
            return name
    return "default"


def marker_color(slot):
    return SLOT_COLORS[_slot_key(slot)]["folium"]


def event_color(slot):
    return SLOT_COLORS[_slot_key(slot)]["hex"]


def slot_icon(slot):
    return SLOT_ICONS.get(slot, "\U0001f4cd")


def flex_icon(value):
    return "\u2705" if str(value).strip().lower() == "yes" else "\U0001f6ab"


def travel_icon(activity_name):
    lower = str(activity_name).lower()
    if "train" in lower or "rail" in lower:
        return "\U0001f686"
    if "bus" in lower or "coach" in lower:
        return "\U0001f68c"
    return "\u2708\ufe0f"


def parse_duration(raw):
    try:
        return float(str(raw).lower().replace("h", ""))
    except (ValueError, AttributeError):
        return 1.0


def friendly_date(date_str):
    return pd.to_datetime(date_str).strftime("%a %-d %b %y")


# ── Hours helpers ────────────────────────────────────────────────────────────

def classify_hours(raw):
    if not raw:
        return None, False
    h = str(raw).strip().lower()
    if h == "closed":
        return "Closed", True
    if "renovation" in h:
        return "Renovation", True
    if "guided tour" in h:
        return "Guided tours", False
    return str(raw).strip(), False


def render_hours_table(hours_dict, visit_day_name=None):
    if not hours_dict:
        return
    visit_abbrev = DAY_ABBREV.get(str(visit_day_name or ""), "")

    rows_html = ""
    for day in DAY_ORDER:
        raw   = hours_dict.get(day, "")
        label, is_closed = classify_hours(raw)
        is_visit = (day == visit_abbrev)

        row_bg   = "background:#fff3cd;" if is_visit else ""
        day_css  = "font-weight:700;" if is_visit else "color:#888;"
        dot      = " \U0001f4c5" if is_visit else ""

        if not label:
            val = '<span style="color:#aaa;">\u2014</span>'
        elif is_closed:
            val = '<span style="color:#dc3545;font-weight:600;">Closed</span>'
        elif label == "Renovation":
            val = '<span style="color:#fd7e14;">\u26a0 Renovation</span>'
        elif label == "Guided tours":
            val = '<span style="color:#6f42c1;">\U0001f3ab Guided tours</span>'
        elif is_visit:
            val = f'<span style="color:#198754;font-weight:700;">{label}</span>'
        else:
            val = label

        rows_html += (
            f'<tr style="{row_bg}">'
            f'<td style="padding:2px 10px 2px 4px;{day_css}white-space:nowrap;">{day}{dot}</td>'
            f'<td style="padding:2px 4px;">{val}</td>'
            f'</tr>'
        )

    st.markdown(
        f'<table style="font-size:12px;border-collapse:collapse;width:100%;margin-top:4px;">'
        f'{rows_html}</table>',
        unsafe_allow_html=True,
    )


# ── Map builders ─────────────────────────────────────────────────────────────

def build_base_map(lat, lon, zoom=None):
    m = folium.Map(location=[lat, lon], zoom_start=zoom or MAP_CONFIG["default_zoom"])
    Fullscreen(position="topright", title="Expand Map",
               title_cancel="Exit Fullscreen", force_separate_button=True).add_to(m)
    return m


def render_map(m, key):
    return st_folium(m, use_container_width=True, height=_map_height(), key=key)


# ── Sandbox helpers ──────────────────────────────────────────────────────────

def _events_hash(events_list):
    """Stable hash of event positions (id + start + end) for change detection.
    Used to avoid reprocessing eventsSet when the calendar rerenders without
    any user-driven change. Guards against versions that return a string or
    list of strings rather than a list of dicts.
    """
    if not isinstance(events_list, list):
        return hashlib.md5(json.dumps(str(events_list)).encode()).hexdigest()
    key = sorted(
        (e.get("id", ""), e.get("start", ""), e.get("end", ""))
        for e in events_list
        if isinstance(e, dict)          # skip any string items
    )
    return hashlib.md5(json.dumps(key).encode()).hexdigest()


def _apply_events_set(df_edit, events_list):
    """Reconcile df_edit against a full eventsSet payload.
    Compares each event's current position/duration against df_edit and
    applies only real differences. Returns (updated_df, [change_descriptions]).
    This handles drag and resize regardless of which specific callback
    streamlit_calendar exposes (eventDrop, eventChange, eventsSet, etc.).
    """
    df_out  = df_edit.copy()
    changes = []

    for ev in (events_list or []):
        event_id  = ev.get("id", "")
        new_start = ev.get("start", "")
        new_end   = ev.get("end", "")
        if not event_id or not new_start:
            continue

        new_dt     = pd.to_datetime(new_start)
        new_date_s = new_dt.strftime("%Y-%m-%d")
        new_time   = new_dt.strftime("%H:%M")
        new_dur    = (
            round((pd.to_datetime(new_end) - new_dt).total_seconds() / 3600, 1)
            if new_end else None
        )

        if event_id.startswith("group_"):
            gid  = event_id[len("group_"):]
            mask = df_out["Group_ID"].astype(str).str.strip() == str(gid).strip()
            if not mask.any():
                continue
            old_date = df_out.loc[mask, "Date_Str"].iloc[0]
            old_time = str(df_out.loc[mask, "Time_Fixed"].iloc[0])
            if old_date == new_date_s and old_time == new_time:
                continue
            day_delta = (new_dt.date()
                         - pd.to_datetime(old_date).date()).days
            df_out.loc[mask, "Date"] = (df_out.loc[mask, "Date"]
                                        + pd.Timedelta(days=day_delta))
            df_out.loc[mask, "Time_Fixed"]    = new_time
            df_out.loc[mask, "Date_Str"]      = (df_out.loc[mask, "Date"]
                                                  .dt.strftime("%Y-%m-%d"))
            df_out.loc[mask, "DayOfWeek"]     = df_out.loc[mask, "Date"].dt.day_name()
            df_out.loc[mask, "Date_Friendly"] = (df_out.loc[mask, "Date_Str"]
                                                  .apply(friendly_date))
            changes.append(f"Moved:   Group '{gid}' → {new_date_s} at {new_time}")

        elif event_id.startswith("row_"):
            try:
                idx = int(event_id[len("row_"):])
            except ValueError:
                continue
            if idx not in df_out.index:
                continue

            old_date = df_out.at[idx, "Date_Str"]
            old_time = str(df_out.at[idx, "Time_Fixed"])
            old_dur  = df_out.at[idx, "Duration"]
            act      = df_out.at[idx, "Activity"]

            if old_date != new_date_s or old_time != new_time:
                df_out.at[idx, "Date"]          = pd.Timestamp(new_date_s)
                df_out.at[idx, "Date_Str"]      = new_date_s
                df_out.at[idx, "Time_Fixed"]    = new_time
                df_out.at[idx, "DayOfWeek"]     = new_dt.strftime("%A")
                df_out.at[idx, "Date_Friendly"] = friendly_date(new_date_s)
                changes.append(f"Moved:   '{act}' → {new_date_s} at {new_time}")

            if new_dur is not None and str(new_dur) != str(old_dur):
                df_out.at[idx, "Duration"] = str(new_dur)
                changes.append(f"Resized: '{act}' duration → {new_dur}h")

    return df_out, changes


def geocode_address(address: str):
    """Look up lat/lon for a free-text address via Nominatim (OpenStreetMap).
    Returns (lat, lon) floats, or (None, None) on any failure.
    Rate-limited to 1 req/s by Nominatim ToS — fine for one-at-a-time entry.
    """
    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": address, "format": "json", "limit": 1},
            headers={"User-Agent": "europe-2027-itinerary-app/1.0"},
            timeout=5,
        )
        data = resp.json()
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception:
        pass
    return None, None


def _build_sandbox_events(df_edit):
    """Build FullCalendar event dicts from df_editable with unique IDs.
    Grouped events (same Group_ID) produce a single representative event so
    the whole group moves together on drag.
    """
    events      = []
    seen_groups = set()

    for idx, row in df_edit.iterrows():
        gid        = row.get("Group_ID")
        is_grouped = pd.notna(gid) and bool(str(gid).strip())

        if is_grouped:
            if gid in seen_groups:
                continue
            seen_groups.add(gid)
            display_name = str(gid).strip()
            event_id     = f"group_{gid}"
        else:
            display_name = str(row["Activity"])
            event_id     = f"row_{idx}"

        start_time = row["Time_Fixed"] if pd.notna(row.get("Time_Fixed")) else "09:00"
        start_iso  = f"{row['Date_Str']}T{start_time}:00"
        dur_val    = parse_duration(row["Duration"])
        end_iso    = (pd.to_datetime(start_iso) + pd.Timedelta(hours=dur_val)
                      ).strftime("%Y-%m-%dT%H:%M:%S")

        is_travel = str(row.get("Type", "")).strip().lower() == "travel"
        icon      = travel_icon(display_name) if is_travel else slot_icon(row["Slot"])
        bg_color  = SLOT_COLORS["travel"]["hex"] if is_travel else event_color(row["Slot"])

        events.append({
            "id":              event_id,
            "title":           f"{icon} {display_name}",
            "start":           start_iso,
            "end":             end_iso,
            "allDay":          False,
            "backgroundColor": bg_color,
            "extendedProps": {
                "activity_name": display_name,
                "dur":           row["Duration"],
                "city":          row["City"],
                "is_grouped":    is_grouped,
            },
        })
    return events


def _apply_event_drop(df_edit, dropped):
    """Handle eventChange / eventDrop payloads — covers both drag (position)
    and resize (duration) since FullCalendar v5 unifies them under eventChange.
    Returns (updated_df, change_description).
    """
    event_id  = dropped["event"]["id"]
    new_start = dropped["event"]["start"]
    new_end   = dropped["event"].get("end", "")
    old_start = dropped.get("oldEvent", {}).get("start", new_start)
    old_end   = dropped.get("oldEvent", {}).get("end", new_end)

    new_dt     = pd.to_datetime(new_start)
    old_dt     = pd.to_datetime(old_start)
    day_delta  = (new_dt.date() - old_dt.date()).days
    new_time   = new_dt.strftime("%H:%M")
    new_date_s = new_dt.strftime("%Y-%m-%d")

    # Compute duration change (None if no end time provided)
    new_dur = None
    dur_changed = False
    if new_end and old_end:
        new_dur = round(
            (pd.to_datetime(new_end) - pd.to_datetime(new_start)).total_seconds() / 3600, 1
        )
        old_dur = round(
            (pd.to_datetime(old_end) - pd.to_datetime(old_start)).total_seconds() / 3600, 1
        )
        dur_changed = new_dur != old_dur
    elif new_end:
        new_dur = round(
            (pd.to_datetime(new_end) - pd.to_datetime(new_start)).total_seconds() / 3600, 1
        )
        dur_changed = True

    df_out = df_edit.copy()
    parts  = []

    if event_id.startswith("group_"):
        gid  = event_id[len("group_"):]
        mask = df_out["Group_ID"].astype(str).str.strip() == str(gid).strip()
        if day_delta != 0 or new_time != "00:00":
            df_out.loc[mask, "Date"]          = (df_out.loc[mask, "Date"]
                                                  + pd.Timedelta(days=day_delta))
            df_out.loc[mask, "Time_Fixed"]    = new_time
            df_out.loc[mask, "Date_Str"]      = (df_out.loc[mask, "Date"]
                                                  .dt.strftime("%Y-%m-%d"))
            df_out.loc[mask, "DayOfWeek"]     = df_out.loc[mask, "Date"].dt.day_name()
            df_out.loc[mask, "Date_Friendly"] = (df_out.loc[mask, "Date_Str"]
                                                  .apply(friendly_date))
            parts.append(f"Group '{gid}' → {new_date_s} at {new_time}")
        if dur_changed and new_dur is not None:
            df_out.loc[mask, "Duration"] = str(new_dur)
            parts.append(f"duration → {new_dur}h")

    elif event_id.startswith("row_"):
        idx = int(event_id[len("row_"):])
        if idx in df_out.index:
            act = df_out.at[idx, "Activity"]
            if day_delta != 0 or new_time != "00:00":
                df_out.at[idx, "Date"]          = pd.Timestamp(new_date_s)
                df_out.at[idx, "Date_Str"]      = new_date_s
                df_out.at[idx, "Time_Fixed"]    = new_time
                df_out.at[idx, "DayOfWeek"]     = new_dt.strftime("%A")
                df_out.at[idx, "Date_Friendly"] = friendly_date(new_date_s)
                parts.append(f"'{act}' → {new_date_s} at {new_time}")
            if dur_changed and new_dur is not None:
                df_out.at[idx, "Duration"] = str(new_dur)
                parts.append(f"duration → {new_dur}h")

    desc = " | ".join(parts)
    return df_out, desc


def _apply_event_resize(df_edit, resized):
    """Apply an eventResize return value (duration change) to df_edit.
    Returns (updated_df, change_description).
    """
    event_id  = resized["event"]["id"]
    start_str = resized["event"]["start"]
    end_str   = resized["event"].get("end", "")

    if not end_str:
        return df_edit, ""

    new_dur = round(
        (pd.to_datetime(end_str) - pd.to_datetime(start_str)).total_seconds() / 3600, 1
    )

    df_out = df_edit.copy()
    desc   = ""

    if event_id.startswith("group_"):
        gid  = event_id[len("group_"):]
        mask = df_out["Group_ID"].astype(str).str.strip() == str(gid).strip()
        df_out.loc[mask, "Duration"] = str(new_dur)
        desc = f"Group '{gid}' duration → {new_dur}h"

    elif event_id.startswith("row_"):
        idx = int(event_id[len("row_"):])
        if idx in df_out.index:
            act = df_out.at[idx, "Activity"]
            df_out.at[idx, "Duration"] = str(new_dur)
            desc = f"'{act}' duration → {new_dur}h"

    return df_out, desc


# ════════════════════════════════════════════════════════════════════════════════
# 5. DATA LOADING
# ════════════════════════════════════════════════════════════════════════════════

@st.cache_data
def load_data():
    try:
        df = pd.read_csv("itinerary.csv")
        df.columns = df.columns.str.strip()

        for col in ("Duration", "Flexible", "Slot", "Notes",
                     "Lat", "Long", "Type", "Group_ID"):
            if col not in df.columns:
                df[col] = None

        df["Type"] = df["Type"].fillna("Activity")

        df["Date"]      = pd.to_datetime(df["Date"], errors="coerce")
        df = df.dropna(subset=["Date"])
        df["Date_Str"]  = df["Date"].dt.strftime("%Y-%m-%d")
        df["DayOfWeek"] = df["Date"].dt.day_name()

        df["Slot_Order"]    = df["Slot"].map(SLOT_ORDER).fillna(99)
        df["Date_Friendly"] = df["Date_Str"].apply(friendly_date)

        for col in ("Lat", "Long", "Hist_Temp", "Hist_Rain"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        df["Has_Coords"] = df["Lat"].notna() & df["Long"].notna()

        # Pre-compute slot keys and colors vectorised
        df["_slot_key"]     = df["Slot"].apply(_slot_key)
        df["_marker_color"] = df["_slot_key"].map(lambda k: SLOT_COLORS[k]["folium"])
        df["_event_color"]  = df["_slot_key"].map(lambda k: SLOT_COLORS[k]["hex"])

        return df
    except Exception as e:
        st.error(f"Data Load Error: {e}")
        return pd.DataFrame()


@st.cache_data
def load_hours_data():
    try:
        hdf = pd.read_csv("detailed_activity_hours.csv")
        hdf.columns = hdf.columns.str.strip()
        return hdf
    except Exception:
        return pd.DataFrame()


@st.cache_data
def _build_hours_lookup(_itinerary_group_pairs):
    hours_df = load_hours_data()
    if hours_df.empty:
        return {}

    def _row_dict(row):
        return {d: str(row[d]).strip()
                for d in DAY_ORDER
                if d in row.index and pd.notna(row[d]) and str(row[d]).strip()}

    lookup = {str(r["Activity"]).strip(): _row_dict(r)
              for _, r in hours_df.iterrows()}

    for act, gid in _itinerary_group_pairs:
        if act and gid and act not in lookup and gid in lookup:
            lookup[act] = lookup[gid]

    return lookup


@st.cache_data
def _build_url_lookup(_itinerary_group_pairs):
    urls = {}
    hours_df = load_hours_data()
    if not hours_df.empty and "URL" in hours_df.columns:
        for _, r in hours_df.iterrows():
            name = str(r["Activity"]).strip()
            url  = str(r.get("URL", "")).strip()
            if url and url.lower() not in ("nan", "none", ""):
                urls[name] = url

    for act, gid in _itinerary_group_pairs:
        if act and gid and act not in urls and gid in urls:
            urls[act] = urls[gid]

    return urls


def get_hours_lookup(df):
    pairs = tuple(
        (str(r.get("Activity", "")).strip(), str(r.get("Group_ID", "")).strip())
        for _, r in df[df["Group_ID"].notna()].iterrows()
    )
    return _build_hours_lookup(pairs)


def get_url_lookup(df):
    pairs = tuple(
        (str(r.get("Activity", "")).strip(), str(r.get("Group_ID", "")).strip())
        for _, r in df[df["Group_ID"].notna()].iterrows()
    )
    return _build_url_lookup(pairs)


def activity_url(activity_name, lookup):
    return lookup.get(str(activity_name).strip())


def all_hours(activity_name, lookup):
    return lookup.get(str(activity_name).strip(), {})




# ════════════════════════════════════════════════════════════════════════════════
# 6. LOAD & DERIVE
# ════════════════════════════════════════════════════════════════════════════════

df = load_data()
hours_lookup = get_hours_lookup(df) if not df.empty else {}
url_lookup   = get_url_lookup(df)   if not df.empty else {}

# City centres — vectorised groupby
CITY_COORDS = {}
if not df.empty:
    coords_df = df[df["Has_Coords"]].groupby("City")[["Lat", "Long"]].median()
    CITY_COORDS = {city: [row["Lat"], row["Long"]] for city, row in coords_df.iterrows()}

# Pre-group Group_ID rows so the calendar loop doesn't scan per group
_group_data = {}
if not df.empty:
    grouped_rows = df[df["Group_ID"].notna()]
    for gid, gdf in grouped_rows.groupby("Group_ID"):
        _group_data[gid] = [
            {"name": r["Activity"],
             "notes": str(r["Notes"]) if pd.notna(r["Notes"]) else "",
             "visit_day": r.get("DayOfWeek", "")}
            for _, r in gdf.iterrows()
        ]

# Initialise sandbox editable copy — never mutated back to the original df
if st.session_state.df_editable is None and not df.empty:
    st.session_state.df_editable = df.copy()


# ════════════════════════════════════════════════════════════════════════════════
# 7. SANDBOX FRAGMENT
# ════════════════════════════════════════════════════════════════════════════════

# Columns added by load_data() that should be omitted from the exported CSV
_DERIVED_COLS = frozenset({
    "Date_Str", "DayOfWeek", "Slot_Order", "Date_Friendly",
    "Has_Coords", "_slot_key", "_marker_color", "_event_color",
})


def _render_new_event_form(cities):
    """Inline form shown when the user selects an empty date/range in the sandbox."""
    sel      = st.session_state.sandbox_new_event or {}
    pre_date = sel.get("start", "")[:10]

    st.markdown("**➕ Add activity**")
    with st.form("sandbox_new_event_form", clear_on_submit=True):
        activity    = st.text_input("Activity name *")
        city_choice = st.selectbox("City *", options=cities + ["Other…"])
        city_other  = (st.text_input("City name", placeholder="Enter city name",
                                     label_visibility="collapsed")
                       if city_choice == "Other…" else "")
        city = city_other.strip() if city_choice == "Other…" else city_choice

        date_val = st.date_input(
            "Date *",
            value=(pd.to_datetime(pre_date).date()
                   if pre_date else pd.Timestamp.now().date()),
        )
        slot     = st.selectbox("Slot *", ["Morning", "Afternoon", "Night"])
        duration = st.number_input("Duration (hrs) *", min_value=0.5,
                                   max_value=24.0, value=1.0, step=0.5)

        with st.expander("📍 Optional: location details"):
            address = st.text_input("Street address",
                                    placeholder="e.g. Louvre Museum, Paris")
            c1, c2  = st.columns(2)
            lat_str = c1.text_input("Latitude",  placeholder="48.8606")
            lon_str = c2.text_input("Longitude", placeholder="2.3376")

        col_add, col_cancel = st.columns(2)
        submitted = col_add.form_submit_button("Add ✓",    use_container_width=True)
        cancelled = col_cancel.form_submit_button("Cancel", use_container_width=True)

    if cancelled:
        st.session_state.sandbox_new_event = None
        st.rerun(scope="fragment")

    if submitted:
        if not activity.strip() or not city:
            st.warning("Activity name and city are required.")
            return

        # Resolve coordinates: explicit > geocoded > none
        lat, lon = None, None
        if lat_str.strip() and lon_str.strip():
            try:
                lat, lon = float(lat_str), float(lon_str)
            except ValueError:
                st.warning("Invalid lat/lon — skipping coordinates.")
        elif address.strip():
            with st.spinner("Geocoding address…"):
                lat, lon = geocode_address(address.strip())
            if lat is None:
                st.warning("Couldn't geocode that address — "
                           "activity added without map coordinates.")

        slot_time = {"Morning": "09:00", "Afternoon": "13:00", "Night": "19:00"}
        sk        = _slot_key(slot)
        new_row   = {
            "Activity":      activity.strip(),
            "City":          city,
            "Date":          pd.Timestamp(date_val),
            "Date_Str":      date_val.strftime("%Y-%m-%d"),
            "DayOfWeek":     pd.Timestamp(date_val).day_name(),
            "Date_Friendly": friendly_date(date_val.strftime("%Y-%m-%d")),
            "Slot":          slot,
            "Slot_Order":    SLOT_ORDER.get(slot, 99),
            "Duration":      duration,
            "Time_Fixed":    slot_time.get(slot, "09:00"),
            "Type":          "Activity",
            "Flexible":      "Yes",
            "Notes":         "",
            "Lat":           lat,
            "Long":          lon,
            "Has_Coords":    lat is not None and lon is not None,
            "Group_ID":      None,
            "_slot_key":     sk,
            "_marker_color": SLOT_COLORS[sk]["folium"],
            "_event_color":  SLOT_COLORS[sk]["hex"],
        }

        st.session_state.df_editable = pd.concat(
            [st.session_state.df_editable, pd.DataFrame([new_row])],
            ignore_index=True,
        )
        st.session_state.sandbox_changelog.append(
            f"Added '{activity.strip()}' on "
            f"{date_val.strftime('%Y-%m-%d')} ({slot})"
        )
        st.session_state.sandbox_pending   = True
        st.session_state.sandbox_new_event = None
        st.rerun(scope="fragment")


@st.fragment
def _render_sandbox_tab(df, cities):
    """Editable sandbox calendar backed by df_editable in session_state.
    Changes never touch the original cached df or itinerary.csv.
    Wrap in @st.fragment so drag/resize interactions only rerun this section.
    """
    # Guard: re-initialise if cache was cleared mid-session
    if st.session_state.df_editable is None or st.session_state.df_editable.empty:
        st.session_state.df_editable = df.copy()

    # ── Sandbox banner ────────────────────────────────────────────────────────
    st.markdown("""
    <div style="background:#fff3cd;border:1px solid #ffc107;border-radius:6px;
                padding:10px 16px;margin-bottom:6px;font-size:0.92em;">
        🧪 <strong>Sandbox mode</strong> — drag events to reschedule,
        resize to adjust duration, or click/select an empty date to add a new
        activity. Changes are isolated here and won't affect your main calendar
        until you export and replace your CSV.
    </div>
    """, unsafe_allow_html=True)

    df_edit = st.session_state.df_editable
    events  = _build_sandbox_events(df_edit)

    sandbox_opts = {
        "editable":   True,
        "selectable": True,
        "initialDate": df_edit["Date"].min().strftime("%Y-%m-%d"),
        "initialView": "dayGridMonth",
        "headerToolbar": {
            "left":   "prev,next today",
            "center": "title",
            "right":  "dayGridMonth,timeGridWeek,timeGridDay",
        },
        "height":   _map_height() + 100,
        "navLinks": True,
    }

    # ── Global toolbar — always visible, no pending-changes gate ─────────────
    tb_left, tb_mid, tb_right = st.columns([4, 1, 1])

    with tb_mid:
        n           = len(st.session_state.sandbox_changelog)
        export_cols = [c for c in st.session_state.df_editable.columns
                       if c not in _DERIVED_COLS]
        csv_bytes   = (
            st.session_state.df_editable[export_cols]
            .to_csv(index=False)
            .encode()
        )
        label = (f"⬇ Export  ({n} change{'s' if n != 1 else ''})"
                 if n > 0 else "⬇ Export CSV")
        st.download_button(
            label=label,
            data=csv_bytes,
            file_name="itinerary_updated.csv",
            mime="text/csv",
            use_container_width=True,
        )

    with tb_right:
        if st.button("🔄 Reset", use_container_width=True, key="sandbox_reset"):
            st.session_state.df_editable       = df.copy()
            st.session_state.sandbox_changelog   = []
            st.session_state.sandbox_pending     = False
            st.session_state.sandbox_new_event   = None
            st.session_state.sandbox_events_hash = None
            st.session_state.sandbox_last_cb_hash = None
            st.rerun(scope="fragment")

    if st.session_state.sandbox_changelog:
        with st.expander(
            f"📋 Change log ({len(st.session_state.sandbox_changelog)})",
            expanded=False,
        ):
            for entry in reversed(st.session_state.sandbox_changelog):
                st.caption(f"• {entry}")

    # ── Calendar + new event form ─────────────────────────────────────────────
    # col_form is always present but only populated when a date is selected,
    # keeping the column structure stable across reruns.
    col_cal, col_form = st.columns([3, 1])

    with col_cal:
        state = calendar(events=events, options=sandbox_opts, key="sandbox_cal")

    with col_form:
        if st.session_state.sandbox_new_event:
            _render_new_event_form(cities)

    # ── Handle calendar interactions ──────────────────────────────────────────
    # streamlit_calendar versions differ in which drag/resize callbacks they
    # expose. We try all known variants so the code works across versions:
    #   eventDrop / eventChange  → single-event move (older/newer library)
    #   eventResize              → duration resize
    #   eventsSet                → full event list fired after ANY change;
    #                              used as the reliable catch-all via hash diff
    if state:
        changed = False
        handled_direct = False   # True when eventChange/Drop/Resize was processed

        # ── Single-event move (try both key names) ────────────────────────
        # streamlit_calendar replays the last callback on every re-render,
        # so we fingerprint the payload and skip if already processed.
        for move_key in ("eventDrop", "eventChange"):
            if move_key in state:
                payload = state[move_key]
                cb_hash = hashlib.md5(
                    json.dumps(payload, sort_keys=True, default=str).encode()
                ).hexdigest()
                if cb_hash == st.session_state.sandbox_last_cb_hash:
                    break                       # already processed — skip
                st.session_state.sandbox_last_cb_hash = cb_hash

                df_new, desc = _apply_event_drop(df_edit, payload)
                st.session_state.df_editable = df_new
                df_edit = df_new
                if desc:
                    st.session_state.sandbox_changelog.append(desc)
                changed = True
                handled_direct = True
                break

        # ── Single-event resize ───────────────────────────────────────────
        if not handled_direct and "eventResize" in state:
            payload = state["eventResize"]
            cb_hash = hashlib.md5(
                json.dumps(payload, sort_keys=True, default=str).encode()
            ).hexdigest()
            if cb_hash != st.session_state.sandbox_last_cb_hash:
                st.session_state.sandbox_last_cb_hash = cb_hash
                df_new, desc = _apply_event_resize(df_edit, payload)
                st.session_state.df_editable = df_new
                df_edit = df_new
                if desc:
                    st.session_state.sandbox_changelog.append(desc)
                changed = True
                handled_direct = True

        # ── eventsSet: full reconciliation (catch-all for missed drags) ───
        # Skip if we already handled a direct callback this cycle — the
        # eventsSet fired alongside it would just double-count the change.
        if not handled_direct and "eventsSet" in state:
            events_data = state["eventsSet"]
            if (isinstance(events_data, list)
                    and events_data
                    and isinstance(events_data[0], dict)):
                new_hash = _events_hash(events_data)
                if new_hash != st.session_state.sandbox_events_hash:
                    st.session_state.sandbox_events_hash = new_hash
                    df_new, descs = _apply_events_set(df_edit, events_data)
                    if descs:
                        st.session_state.df_editable = df_new
                        st.session_state.sandbox_changelog.extend(descs)
                        changed = True

        if changed:
            st.session_state.sandbox_pending = True
            st.rerun(scope="fragment")

        # ── Date selection → new event form ──────────────────────────────
        if "select" in state:
            st.session_state.sandbox_new_event = state["select"]
            st.rerun(scope="fragment")


# ════════════════════════════════════════════════════════════════════════════════
# 8. SIDEBAR — DATA TOOLS
# ════════════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.header("\U0001f6e0\ufe0f Data Tools")

    weather_present = "Hist_Temp" in df.columns and "Hist_Rain" in df.columns
    missing_weather = df["Has_Coords"] & (df["Hist_Temp"].isna() if weather_present else True)
    missing_count   = int(missing_weather.sum())

    if missing_count > 0:
        st.warning(f"\U0001f321\ufe0f **{missing_count} activities** missing weather data.")
    else:
        st.success("\U0001f321\ufe0f Weather data is complete.")

    col_run, col_force = st.columns(2)
    run_wx   = col_run.button("Update missing", key="wx_missing", disabled=(missing_count == 0))
    force_wx = col_force.button("Re-fetch all", key="wx_force")

    if run_wx or force_wx:
        from weather_updater import update_csv
        with st.spinner("Fetching 7-year averages (2019\u20132025)\u2026"):
            update_csv(csv_path="itinerary.csv", force=force_wx)
        st.cache_data.clear()
        st.rerun()

    st.divider()
    st.caption("Weather: Open-Meteo archive (ERA5), 7-year mean 2019\u20132025.")

    st.subheader("\U0001f550 Hours Data")
    st.caption(
        "Opening hours are loaded from `detailed_activity_hours.csv`. "
        "If you edit the file, hit refresh to pick up changes."
    )
    if st.button("\U0001f504 Refresh hours data", key="refresh_hours"):
        st.cache_data.clear()
        st.rerun()


# ════════════════════════════════════════════════════════════════════════════════
# 8. APP UI
# ════════════════════════════════════════════════════════════════════════════════

st.header("\U0001f1ea\U0001f1fa Grand European Tour 2027")

if not df.empty:
    tab1, tab2, tab3, tab4 = st.tabs([
        "\U0001f4c5 Calendar",
        "\U0001f5fa\ufe0f Trip Map",
        "\U0001f4cb Daily plan",
        "\U0001f9ea Sandbox",
    ])

    # ──────────────────────────────────────────────────────────────────────────
    # TAB 1 — CALENDAR (events pre-built by cached function)
    # ──────────────────────────────────────────────────────────────────────────
    with tab1:
        first_date = df["Date"].min().strftime("%Y-%m-%d")
        col_cal, col_info = st.columns([2, 1])

        with col_cal:
            events = []
            seen_groups = set()

            for _, row in df.iterrows():
                gid        = row.get("Group_ID")
                is_grouped = pd.notna(gid) and bool(str(gid).strip())

                if is_grouped:
                    if gid in seen_groups:
                        continue
                    seen_groups.add(gid)
                    display_name = str(gid).strip()
                    locations    = _group_data.get(gid, [])
                else:
                    display_name = str(row["Activity"])
                    locations    = []

                start_time = row["Time_Fixed"] if pd.notna(row.get("Time_Fixed")) else "09:00"
                start_iso  = f"{row['Date_Str']}T{start_time}:00"

                dur_val = parse_duration(row["Duration"])
                end_iso = (pd.to_datetime(start_iso) + pd.Timedelta(hours=dur_val)
                           ).strftime("%Y-%m-%dT%H:%M:%S")

                is_travel = str(row.get("Type", "")).strip().lower() == "travel"
                icon     = travel_icon(display_name) if is_travel else slot_icon(row["Slot"])
                bg_color = SLOT_COLORS["travel"]["hex"] if is_travel else event_color(row["Slot"])

                events.append({
                    "title": f"{icon} {display_name}",
                    "start": start_iso,
                    "end":   end_iso,
                    "allDay": False,
                    "backgroundColor": bg_color,
                    "extendedProps": {
                        "activity_name": display_name,
                        "notes":      str(row["Notes"]) if pd.notna(row["Notes"]) else "",
                        "flex":       row["Flexible"],
                        "dur":        row["Duration"],
                        "city":       row["City"],
                        "visit_day":  row.get("DayOfWeek", ""),
                        "is_grouped": is_grouped,
                        "locations":  locations,
                    },
                })

            cal_opts = {
                "initialDate": first_date,
                "initialView": "dayGridMonth",
                "headerToolbar": {
                    "left": "prev,next today",
                    "center": "title",
                    "right": "dayGridMonth,timeGridWeek,timeGridDay",
                },
                "height":   _map_height() + 100,
                "navLinks": True,
            }

            state = calendar(events=events, options=cal_opts)
            if state.get("eventClick"):
                st.session_state.clicked_event = state["eventClick"]["event"]

        with col_info:
            if st.session_state.clicked_event:
                ev = st.session_state.clicked_event
                p  = ev.get("extendedProps", {})
                v_day      = p.get("visit_day", "")
                is_grp     = p.get("is_grouped", False)
                locations  = p.get("locations", [])

                st.markdown(f"### {ev['title']}")
                st.write(f"**\U0001f4cd {p.get('city')}** | **\u23f3 {p.get('dur')}**")
                fi = flex_icon(p.get("flex", ""))
                check = "\u2705"
                st.write(f"**Flexibility:** {fi} {'Yes' if fi == check else 'No'}")

                if is_grp and locations:
                    st.caption(f"\U0001f4cd {len(locations)}-stop activity")
                    for loc in locations:
                        loc_name = loc.get("name", "")
                        loc_day  = loc.get("visit_day", v_day)
                        h_dict   = all_hours(loc_name, hours_lookup)
                        loc_url  = activity_url(loc_name, url_lookup)
                        if loc_url:
                            st.markdown(f"**[{loc_name}]({loc_url})**")
                        else:
                            st.markdown(f"**{loc_name}**")
                        if h_dict:
                            abbr = DAY_ABBREV.get(loc_day, "")
                            lbl, closed = classify_hours(h_dict.get(abbr, ""))
                            if closed:
                                st.warning(f"\u26a0\ufe0f {loc_name} \u2014 {lbl} on your visit day")
                            render_hours_table(h_dict, loc_day)
                        else:
                            st.caption("*Hours not available*")
                        if loc.get("notes"):
                            st.caption(loc["notes"])
                        st.divider()
                else:
                    act_name = p.get("activity_name", "")
                    h_dict   = all_hours(act_name, hours_lookup)
                    act_url  = activity_url(act_name, url_lookup)
                    if h_dict:
                        abbr = DAY_ABBREV.get(v_day, "")
                        lbl, closed = classify_hours(h_dict.get(abbr, ""))
                        if closed:
                            st.warning(f"\u26a0\ufe0f {lbl} on your visit day")
                        st.markdown("**Opening hours**")
                        render_hours_table(h_dict, v_day)
                    if act_url:
                        st.markdown(f"\U0001f517 [Website]({act_url})")
                    if p.get("notes"):
                        st.info(p["notes"])

                if st.button("Clear Selection"):
                    st.session_state.clicked_event = None
                    st.rerun()
            else:
                st.write("\U0001f4a1 *Click an event on the calendar to see details here.*")

    # ──────────────────────────────────────────────────────────────────────────
    # TAB 2 — TRIP MAP (overview + city drill-down)
    # Uses @st.fragment so map focus clicks only rerun the map, not the page
    # ──────────────────────────────────────────────────────────────────────────
    with tab2:
        activity_counts = df.groupby("City")["Activity"].count()
        selected_city   = st.session_state.tab2_selected_city

        if selected_city is None:
            st.caption("Click a city pin to explore its activities.")
            m_full = build_base_map(*MAP_CONFIG["overview_center"],
                                    zoom=MAP_CONFIG["overview_zoom"])

            for city, loc in CITY_COORDS.items():
                if city in MAP_EXCLUDE_CITIES:
                    continue
                count = activity_counts.get(city, 0)
                folium.Marker(
                    loc, tooltip=city,
                    popup=folium.Popup(
                        f"<b>{city}</b><br>{count} activities<br>"
                        f"<i>Click to explore</i>", max_width=180),
                    icon=folium.Icon(color="red", icon="info-sign"),
                ).add_to(m_full)

            result = render_map(m_full, key="overview_map")
            clicked = (result or {}).get("last_object_clicked_tooltip")
            if clicked and clicked in CITY_COORDS:
                st.session_state.tab2_selected_city = clicked
                st.rerun()

        else:
            col_hdr, col_back = st.columns([4, 1])
            col_hdr.subheader(f"\U0001f4cd {selected_city}")
            if col_back.button("\u2190 Overview", key="tab2_back"):
                st.session_state.tab2_selected_city = None
                st.session_state.tab2_map_center    = None
                st.session_state.tab2_map_zoom      = MAP_CONFIG["default_zoom"]
                st.rerun()

            city_data = (
                df[(df["City"] == selected_city) & (df["Type"] != "Travel")]
                .copy()
                .sort_values(["Date_Str", "Slot_Order"])
            )
            city_loc = CITY_COORDS.get(selected_city, MAP_CONFIG["overview_center"])

            col_map, col_list = st.columns([3, 1])

            # ── Fragment: city drill-down map (reruns independently) ─────────
            @st.fragment
            def city_map_fragment(city_data_frag, city_loc_frag, selected_city_frag):
                if not city_data_frag["Has_Coords"].any():
                    st.info(f"No coordinates for {selected_city_frag} activities yet.")
                    return

                center = st.session_state.tab2_map_center or city_loc_frag
                zoom   = st.session_state.tab2_map_zoom
                m_city = build_base_map(center[0], center[1], zoom=zoom)

                for _, row in city_data_frag[city_data_frag["Has_Coords"]].iterrows():
                    is_focused = (st.session_state.tab2_map_center == [row["Lat"], row["Long"]])
                    popup_html = (
                        f"<b>{row['Activity']}</b><br>"
                        f"\U0001f4c5 {row['Date_Friendly']}<br>"
                        f"\u23f3 {row['Duration']}<br>"
                        f"{flex_icon(row['Flexible'])} Flexible: {row['Flexible']}<br>"
                        f"<hr style='margin:4px 0'>"
                        f"<small>{row['Notes']}</small>"
                    )
                    folium.Marker(
                        [row["Lat"], row["Long"]],
                        tooltip=f"{row['Slot']}: {row['Activity']}",
                        popup=folium.Popup(popup_html, max_width=260),
                        icon=folium.Icon(color=row["_marker_color"],
                                         icon="star" if is_focused else "info-sign"),
                    ).add_to(m_city)

                if st.session_state.tab2_map_center is not None:
                    if st.button("\U0001f504 Reset map view", key="tab2_reset"):
                        st.session_state.tab2_map_center = None
                        st.session_state.tab2_map_zoom   = 13

                render_map(m_city, key=f"city_{selected_city_frag}_{zoom}_{round(center[0], 4)}")

            with col_map:
                city_map_fragment(city_data, city_loc, selected_city)

            with col_list:
                st.caption(f"{len(city_data)} activities \u00b7 \U0001f305 Morning \u00b7 \u26c5 Afternoon \u00b7 \U0001f319 Night")

                for date_str, grp in city_data.groupby("Date_Str", sort=True):
                    st.markdown(f"###### {friendly_date(date_str)}")
                    for idx, (_, row) in enumerate(grp.iterrows()):
                        c_name, c_btn = st.columns([5, 1])
                        c_name.markdown(
                            f"{slot_icon(row['Slot'])} {flex_icon(row['Flexible'])} "
                            f"{row['Activity']}"
                        )
                        if row["Has_Coords"]:
                            if c_btn.button("\U0001f4cd", key=f"t2f_{date_str}_{idx}",
                                            help="Focus map"):
                                st.session_state.tab2_map_center = [row["Lat"], row["Long"]]
                                st.session_state.tab2_map_zoom   = MAP_CONFIG["focused_zoom"]
                                st.rerun()

    # ──────────────────────────────────────────────────────────────────────────
    # TAB 3 — DAILY PLAN
    # Uses @st.fragment for the map so focus clicks don't rerun the full page
    # ──────────────────────────────────────────────────────────────────────────
    with tab3:
        col_title, col_picker = st.columns([3, 1])
        col_title.subheader("\U0001f4cd Daily Deep Dive")

        with col_picker:
            selected_date = st.selectbox(
                "Date", options=sorted(df["Date_Str"].unique()),
                format_func=friendly_date, key="date_tab3",
                label_visibility="collapsed",
            )

        day_data = (
            df[df["Date_Str"] == selected_date]
            .copy()
            .sort_values("Slot_Order")
        )
        st.divider()

        if st.session_state.tab3_last_date != selected_date:
            st.session_state.tab3_map_center = None
            st.session_state.tab3_map_zoom   = MAP_CONFIG["default_zoom"]
            st.session_state.tab3_last_date  = selected_date

        if not day_data.empty:
            current_city = day_data.iloc[0]["City"]
            hotel = day_data[day_data["Activity"].str.contains(
                "Hotel|Stay|Check-in", case=False, na=False)]

            # ── Metric row (vectorised walkability) ──────────────────────────
            m1, m2, m3 = st.columns(3)

            if not hotel.empty and hotel.iloc[0]["Has_Coords"]:
                h_lat, h_lon = hotel.iloc[0]["Lat"], hotel.iloc[0]["Long"]
                valid_mask = day_data["Has_Coords"]
                if valid_mask.any():
                    distances = haversine_km_vectorised(
                        h_lat, h_lon,
                        day_data.loc[valid_mask, "Lat"].values,
                        day_data.loc[valid_mask, "Long"].values,
                    )
                    non_hotel = distances > 0.01
                    if non_hotel.any():
                        walkable_count = int((distances[non_hotel] <= WALKABILITY_KM).sum())
                        score = int((walkable_count / non_hotel.sum()) * 100)
                    else:
                        score = 100
                else:
                    score = 100
                m1.metric("Walkability Score", f"{score}%")
            else:
                m1.metric("Walkability Score", "N/A")

            temp = day_data.iloc[0].get("Hist_Temp")
            rain = day_data.iloc[0].get("Hist_Rain")
            m2.metric("Avg Temp (Hist.)", f"{round(temp, 1)}\u00b0C" if pd.notna(temp) else "\u2014")
            m3.metric("Avg Rain (Hist.)", f"{round(rain, 1)}mm" if pd.notna(rain) else "\u2014")
            if pd.notna(rain) and rain > 2.0:
                st.warning(f"\u2614 Historically a wet day in {current_city} ({rain}mm).")

            # ── Activity list + Map side by side ─────────────────────────────
            col_list, col_map = st.columns([1, 1.2])

            with col_list:
                processed = set()

                for idx, (row_idx, row) in enumerate(day_data.iterrows()):
                    if row_idx in processed:
                        continue

                    gid        = row.get("Group_ID")
                    is_grouped = pd.notna(gid) and bool(str(gid).strip())

                    if is_grouped:
                        group_rows = day_data[day_data["Group_ID"] == gid]
                        title = (f"**{row['Slot']}**: {gid} "
                                 f"({row['Duration']}) {flex_icon(row['Flexible'])}")

                        with st.expander(title):
                            for si, (sri, sr) in enumerate(group_rows.iterrows()):
                                h = all_hours(sr["Activity"], hours_lookup)
                                abbr = DAY_ABBREV.get(str(sr.get("DayOfWeek", "")), "")
                                lbl, closed = classify_hours(h.get(abbr, ""))

                                sub_url = activity_url(sr["Activity"], url_lookup)
                                if sub_url:
                                    st.markdown(f"**\U0001f4cd [{sr['Activity']}]({sub_url})**")
                                else:
                                    st.markdown(f"**\U0001f4cd {sr['Activity']}**")
                                if closed:
                                    st.warning(f"\u26a0\ufe0f {lbl} on your visit day")
                                if h:
                                    render_hours_table(h, sr.get("DayOfWeek", ""))
                                else:
                                    st.caption("*Hours not available*")

                                if pd.notna(sr.get("Notes")):
                                    st.caption(str(sr["Notes"]))

                                if sr.get("Has_Coords"):
                                    if st.button("\U0001f4cd Focus on map",
                                                 key=f"t3g_{sri}_{si}_{selected_date}"):
                                        st.session_state.tab3_map_center = [sr["Lat"], sr["Long"]]
                                        st.session_state.tab3_map_zoom = MAP_CONFIG["focused_zoom"]
                                        st.rerun()

                                if si < len(group_rows) - 1:
                                    st.divider()

                        for gi in group_rows.index:
                            processed.add(gi)

                    else:
                        h = all_hours(row["Activity"], hours_lookup)
                        abbr = DAY_ABBREV.get(str(row.get("DayOfWeek", "")), "")
                        lbl, closed = classify_hours(h.get(abbr, ""))

                        title = (f"**{row['Slot']}**: {row['Activity']} "
                                 f"({row['Duration']}) {flex_icon(row['Flexible'])}")

                        with st.expander(title):
                            if closed:
                                st.warning(f"\u26a0\ufe0f {lbl} on your visit day")
                            if h:
                                render_hours_table(h, row.get("DayOfWeek", ""))
                            else:
                                st.caption("*No hours data available*")

                            row_url = activity_url(row["Activity"], url_lookup)
                            if row_url:
                                st.markdown(f"\U0001f517 [Website]({row_url})")

                            if pd.notna(row.get("Notes")):
                                st.info(str(row["Notes"]))

                            if row.get("Has_Coords"):
                                if st.button("\U0001f4cd Focus on map",
                                             key=f"t3s_{idx}_{selected_date}"):
                                    st.session_state.tab3_map_center = [row["Lat"], row["Long"]]
                                    st.session_state.tab3_map_zoom = MAP_CONFIG["focused_zoom"]
                                    st.rerun()

                        processed.add(row_idx)

            # ── Fragment: daily map (reruns independently on focus) ───────────
            @st.fragment
            def daily_map_fragment(day_data_frag, hotel_frag, selected_date_frag):
                if st.session_state.tab3_map_center is not None:
                    center = st.session_state.tab3_map_center
                    zoom   = st.session_state.tab3_map_zoom
                else:
                    valid = day_data_frag[day_data_frag["Has_Coords"]]
                    center = ([valid.iloc[0]["Lat"], valid.iloc[0]["Long"]]
                              if not valid.empty else MAP_CONFIG["overview_center"])
                    zoom = MAP_CONFIG["default_zoom"]

                m_daily = build_base_map(center[0], center[1], zoom=zoom)

                if not hotel_frag.empty and hotel_frag.iloc[0]["Has_Coords"]:
                    hl, ho = hotel_frag.iloc[0]["Lat"], hotel_frag.iloc[0]["Long"]
                    folium.Circle([hl, ho], radius=int(WALKABILITY_KM * 1000),
                                  color="green", fill=True, fill_opacity=0.1).add_to(m_daily)
                    folium.Marker([hl, ho], icon=folium.Icon(color="black", icon="home"),
                                  tooltip="Hotel / Base").add_to(m_daily)

                activity_rows = day_data_frag[
                    day_data_frag["Has_Coords"]
                    & ~day_data_frag["Activity"].str.contains("Hotel", case=False, na=False)
                    & (day_data_frag["Type"].str.strip().str.lower() != "travel")
                ]
                for _, row in activity_rows.iterrows():
                    is_focused = (st.session_state.tab3_map_center == [row["Lat"], row["Long"]])
                    folium.Marker(
                        [row["Lat"], row["Long"]],
                        popup=row["Activity"],
                        tooltip=f"{row['Slot']}: {row['Activity']}",
                        icon=folium.Icon(color=row["_marker_color"],
                                         icon="star" if is_focused else "info-sign"),
                    ).add_to(m_daily)

                if st.session_state.tab3_map_center is not None:
                    if st.button("\U0001f504 Reset map view", key=f"reset_{selected_date_frag}"):
                        st.session_state.tab3_map_center = None
                        st.session_state.tab3_map_zoom = MAP_CONFIG["default_zoom"]

                render_map(m_daily, key=f"map_{selected_date_frag}_{zoom}_{round(center[0], 4)}")

            with col_map:
                daily_map_fragment(day_data, hotel, selected_date)

    # ──────────────────────────────────────────────────────────────────────────
    # TAB 4 — SANDBOX (editable calendar, isolated df copy)
    # ──────────────────────────────────────────────────────────────────────────
    with tab4:
        cities = sorted(df["City"].dropna().unique().tolist())
        _render_sandbox_tab(df, cities)
