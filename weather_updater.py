import pandas as pd
import requests
import time

# Years to average over. Adjust the window here if you want e.g. 2021-2025 later.
HISTORY_YEARS = [2019, 2020, 2021, 2022, 2023, 2024, 2025]


def get_open_meteo_weather(lat, lon, date_str):
    """
    Fetch a multi-year historical average from the Open-Meteo archive API.

    For each year in HISTORY_YEARS, queries the same calendar day (MM-DD) and
    averages the results. This gives a much more reliable baseline than a
    single-year snapshot, smoothing out anomalous years like the warm 2024
    European winter.

    Returns (avg_temp_celsius, avg_rain_mm) or (None, None) on failure.
    """
    month_day = date_str[5:]  # Extract MM-DD from YYYY-MM-DD
    temps, rains = [], []

    for year in HISTORY_YEARS:
        formatted_date = f"{year}-{month_day}"
        url = (
            f"https://archive-api.open-meteo.com/v1/archive"
            f"?latitude={lat}&longitude={lon}"
            f"&start_date={formatted_date}&end_date={formatted_date}"
            f"&daily=temperature_2m_mean,precipitation_sum&timezone=GMT"
        )
        try:
            response = requests.get(url, timeout=10)
            data = response.json()
            if "daily" in data:
                t = data["daily"]["temperature_2m_mean"][0]
                r = data["daily"]["precipitation_sum"][0]
                if t is not None:
                    temps.append(t)
                if r is not None:
                    rains.append(r)
        except Exception as e:
            print(f"    ⚠️  {year} error for {formatted_date}: {e}")

        # Polite pause between calls to the free API
        time.sleep(0.15)

    if not temps:
        return None, None

    avg_temp = round(sum(temps) / len(temps), 1)
    avg_rain = round(sum(rains) / len(rains), 1) if rains else None
    return avg_temp, avg_rain


def update_csv(csv_path='itinerary.csv', force=False):
    """
    Read the CSV, fetch multi-year average weather for any row that has coordinates
    but is missing Hist_Temp (or all rows if force=True), then write back.

    Parameters
    ----------
    csv_path : str
        Path to the itinerary CSV file.
    force : bool
        If True, re-fetch weather for every row that has coordinates,
        even if Hist_Temp is already populated.
    """
    df = pd.read_csv(csv_path)
    df.columns = df.columns.str.strip()

    # Ensure weather columns exist
    for col in ['Hist_Temp', 'Hist_Rain']:
        if col not in df.columns:
            df[col] = None

    df['Lat'] = pd.to_numeric(df['Lat'], errors='coerce')
    df['Long'] = pd.to_numeric(df['Long'], errors='coerce')
    df['Hist_Temp'] = pd.to_numeric(df['Hist_Temp'], errors='coerce')
    df['Hist_Rain'] = pd.to_numeric(df['Hist_Rain'], errors='coerce')

    has_coords = df['Lat'].notna() & df['Long'].notna()
    if force:
        to_update = df[has_coords]
    else:
        to_update = df[has_coords & df['Hist_Temp'].isna()]

    total = len(to_update)
    if total == 0:
        print("✅ All rows already have weather data. Use force=True to re-fetch.")
        return

    print(f"🚀 Fetching {len(HISTORY_YEARS)}-year averages ({min(HISTORY_YEARS)}–{max(HISTORY_YEARS)}) "
          f"for {total} rows...")

    updated = 0
    for index, row in to_update.iterrows():
        temp, rain = get_open_meteo_weather(row['Lat'], row['Long'], str(row['Date']))

        if temp is not None:
            df.at[index, 'Hist_Temp'] = temp
            df.at[index, 'Hist_Rain'] = rain
            updated += 1
            print(f"  ✅ {row['Date']} – {row['City']}: {temp}°C, {rain}mm "
                  f"(avg of {len(HISTORY_YEARS)} years)")
        else:
            print(f"  ❌ {row['Date']} – {row['City']}: no data returned")

    df.to_csv(csv_path, index=False)
    print(f"\n✨ Done. {updated}/{total} rows updated → {csv_path}")


# Only runs when the script is executed directly (not when imported by the app).
if __name__ == "__main__":
    update_csv()
