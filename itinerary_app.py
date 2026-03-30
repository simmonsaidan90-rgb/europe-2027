import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from datetime import datetime

# --- CONFIGURATION ---
st.set_page_config(page_title="Europe 2027", layout="wide")

# --- DATA ---
# Generic data for the "Public" dashboard
trip_data = [
    {"City": "Helsinki", "Hotel": "Hotel St. George", "Lat": 60.165, "Lon": 24.940, "Budget": 330},
    {"City": "Krakow", "Hotel": "Hotel Stary", "Lat": 50.061, "Lon": 19.937, "Budget": 394},
    {"City": "Prague", "Hotel": "The Julius", "Lat": 50.087, "Lon": 14.421, "Budget": 352},
    {"City": "Vienna", "Hotel": "Hotel Sacher", "Lat": 48.203, "Lon": 16.369, "Budget": 768},
    {"City": "Budapest", "Hotel": "Anantara New York Palace", "Lat": 47.498, "Lon": 19.070, "Budget": 388},
    {"City": "Rome", "Hotel": "Eitch Borromini", "Lat": 41.899, "Lon": 12.473, "Budget": 355},
]
df = pd.DataFrame(trip_data)

st.title("🇪🇺 Grand European Tour 2027")
st.markdown("---")

# --- LAYOUT ---
tab1, tab2, tab3 = st.tabs(["🗺️ Map & Logistics", "🌡️ Weather Strategy", "📝 Daily Itinerary"])

with tab1:
    st.header("Home Bases")
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.write("Our selected romantic & historic stays:")
        st.dataframe(df[['City', 'Hotel', 'Budget']], hide_index=True)
        st.metric("Total Accommodation Est.", f"${df['Budget'].sum() * 3:,.2f} AUD") # Rough 3-night avg

    with col2:
        # Map centering on Central Europe
        m = folium.Map(location=[50.0, 15.0], zoom_start=4)
        for _, row in df.iterrows():
            folium.Marker(
                [row['Lat'], row['Lon']], 
                popup=f"{row['Hotel']}, {row['City']}",
                tooltip=row['City'],
                icon=folium.Icon(color='red', icon='info-sign')
            ).add_to(m)
        st_folium(m, width=700, height=400)

with tab2:
    st.header("The 'Pack-o-Meter'")
    st.info("Historical Averages for Jan 01 - Jan 15 (Last 5 Years)")
    # Here you would eventually add the Meteostat API calls
    st.write("💡 **Tip:** Based on current trends, expect -5°C in Krakow and a much milder 10°C in Rome.")
    
    st.checkbox("Show Heavy Winter Gear List")
    st.checkbox("Show Formal Wear (for Vienna Opera/Sacher)")

with tab3:
    st.header("The Master Plan")
    selected_city = st.selectbox("Select a City to see the plan:", df['City'])
    
    # Example logic for showing specific itinerary details
    if selected_city == "Vienna":
        st.write("- **Jan 06:** Flak Towers (Morning) & HGM Museum (Afternoon)")
        st.write("- **Jan 07:** Mauthausen Concentration Camp (Full Day)")
        st.write("- **Jan 08:** Austrian Parliament & Sisi Museum")
    elif selected_city == "Budapest":
        st.write("- **Jan 09:** Gellért Thermal Baths on arrival")
        st.write("- **Jan 10:** Jewish Quarter & House of Terror")
