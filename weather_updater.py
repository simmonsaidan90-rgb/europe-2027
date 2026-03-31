import pandas as pd
import requests
import time

def get_open_meteo_weather(lat, lon, date_str):
    """Fetch historical weather from Open-Meteo API"""
    try:
        # Open-Meteo uses YYYY-MM-DD. We'll check 2024 for a recent historical baseline.
        year_to_check = "2024" 
        month_day = date_str[5:] # Grabs the MM-DD part
        formatted_date = f"{year_to_check}-{month_day}"
        
        url = f"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}&start_date={formatted_date}&end_date={formatted_date}&daily=temperature_2m_mean,precipitation_sum&timezone=GMT"
        
        response = requests.get(url)
        data = response.json()
        
        if "daily" in data:
            temp = data["daily"]["temperature_2m_mean"][0]
            rain = data["daily"]["precipitation_sum"][0]
            return temp, rain
    except Exception as e:
        print(f"❌ API Error: {e}")
    return None, None

def update_csv():
    df = pd.read_csv('itinerary.csv')
    print("🚀 Starting Weather Injection via Open-Meteo...")
    
    for index, row in df.iterrows():
        if pd.notna(row['Lat']) and pd.notna(row['Long']):
            # Fetch weather
            temp, rain = get_open_meteo_weather(row['Lat'], row['Long'], row['Date'])
            
            if temp is not None:
                df.at[index, 'Hist_Temp'] = temp
                df.at[index, 'Hist_Rain'] = rain
                print(f"✅ {row['Date']} ({row['City']}): {temp}°C, {rain}mm")
            
            # Tiny sleep to be polite to the free API
            time.sleep(0.2)
            
    df.to_csv('itinerary.csv', index=False)
    print("✨ SUCCESS! Your CSV is updated.")

update_csv()