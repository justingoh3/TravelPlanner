from itinerary_engine import ItineraryEngine
from datetime import datetime

itinerary = {
    "Day 1": [
        {"type": "sight", "name": "A", "latitude": 35.6, "longitude": 139.7},
        {"type": "sight", "name": "B", "latitude": 35.65, "longitude": 139.75}
    ]
}

engine = ItineraryEngine(
    hotel_lat=35.6895, 
    hotel_lng=139.6917, 
    arrival_datetime=datetime.now(),
    num_days=1,
    wishlist=[],
    tabelog_db="tabelog_japan.db"
)
new_itinerary = engine.recalculate(itinerary)
print(new_itinerary)
