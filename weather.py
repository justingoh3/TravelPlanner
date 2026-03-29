import requests
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

def get_weather_forecast(lat: float, lng: float, start_date: datetime, num_days: int):
    """
    Fetches the weather forecast using Open-Meteo API.
    Returns a dictionary mapping date strings (YYYY-MM-DD) to weather conditions.
    """
    # Open-Meteo provides up to 16 days of forecast.
    # If the trip is further out, we might just return historical averages or 'unknown'
    
    end_date = start_date + timedelta(days=num_days - 1)
    
    # We can only fetch up to 16 days ahead realistically
    max_forecast_date = datetime.now() + timedelta(days=15)
    
    if start_date > max_forecast_date:
        logger.warning("Trip is too far in the future for an accurate forecast. Defaulting to clear weather.")
        return {}

    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lng}&daily=weather_code,precipitation_probability_max&timezone=auto&start_date={start_date.strftime('%Y-%m-%d')}&end_date={end_date.strftime('%Y-%m-%d')}"
    
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        
        daily = data.get('daily', {})
        times = daily.get('time', [])
        weather_codes = daily.get('weather_code', [])
        precip_probs = daily.get('precipitation_probability_max', [])
        
        forecast = {}
        for i in range(len(times)):
            date_str = times[i]
            code = weather_codes[i] if i < len(weather_codes) else 0
            precip = precip_probs[i] if i < len(precip_probs) else 0
            
            # WMO Weather interpretation codes
            # 0-3: Clear/Cloudy
            # 45-48: Fog
            # 51-67: Drizzle/Rain
            # 71-77: Snow
            # 80-99: Showers/Thunderstorm
            is_rainy = code >= 50 or precip > 50
            
            forecast[date_str] = {
                'code': code,
                'is_rainy': is_rainy,
                'precip_prob': precip
            }
            
        return forecast
    except Exception as e:
        logger.error(f"Failed to fetch weather forecast: {e}")
        return {}
