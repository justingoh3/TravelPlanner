"""
FastAPI server for itinerary generation API.
"""

import json
import os
import logging
from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI, HTTPException

from fastapi.responses import Response
from ics import Calendar, Event as IcsEvent

from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from geopy.geocoders import GoogleV3
from itinerary_engine import ItineraryEngine

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(title="Tokyo Travel Planner API")

# Enable CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Geocoding cache file
CACHE_FILE = "geocoding_cache.json"

# Load geocoding cache
geocoding_cache = {}
if os.path.exists(CACHE_FILE):
    try:
        with open(CACHE_FILE, 'r') as f:
            geocoding_cache = json.load(f)
        logger.info(f"Loaded {len(geocoding_cache)} cached geocoding results")
    except Exception as e:
        logger.warning(f"Could not load geocoding cache: {e}")
        geocoding_cache = {}


def save_geocoding_cache():
    """Save geocoding cache to file."""
    try:
        with open(CACHE_FILE, 'w') as f:
            json.dump(geocoding_cache, f, indent=2)
    except Exception as e:
        logger.error(f"Could not save geocoding cache: {e}")


def geocode_address(address: str) -> Optional[tuple]:
    """
    Geocode an address, using cache if available.
    
    Args:
        address: Address string to geocode
        
    Returns:
        Tuple of (latitude, longitude) or None
    """
    # Check cache first
    if address in geocoding_cache:
        cached = geocoding_cache[address]
        logger.info(f"Using cached geocoding for: {address}")
        return (cached['lat'], cached['lng'])
    
    # Geocode using Google API
    api_key = os.getenv('MAPS_API_KEY')
    if not api_key:
        raise HTTPException(status_code=500, detail="Google Maps API key not configured")
    
    try:
        geocoder = GoogleV3(api_key=api_key)
        location = geocoder.geocode(address, language='en', timeout=10)
        
        if location:
            coords = (location.latitude, location.longitude)
            # Save to cache
            geocoding_cache[address] = {
                'lat': location.latitude,
                'lng': location.longitude
            }
            save_geocoding_cache()
            logger.info(f"Geocoded and cached: {address} -> ({location.latitude}, {location.longitude})")
            return coords
        else:
            logger.warning(f"Could not geocode: {address}")
            return None
    except Exception as e:
        logger.error(f"Error geocoding {address}: {e}")
        return None


# Request/Response models
class ItineraryRequest(BaseModel):
    hotel_address: str
    arrival_time: str  # ISO format: "2024-03-15T14:00:00"
    departure_flight_time: str  # ISO format: "2024-03-18T16:00:00" (REQUIRED for day calculation)
    wishlist_items: List[str]
    interests: Optional[List[str]] = []  # e.g. ['anime_manga', 'shopping']
    pacing: Optional[str] = "balanced"  # 'relaxed', 'balanced', or 'packed'


class ItineraryResponse(BaseModel):
    itinerary: dict
    hotel_location: dict
    message: str


class RecalculateRequest(BaseModel):
    hotel_address: str
    arrival_time: str
    itinerary: dict
    pacing: Optional[str] = "balanced"

class ExportRequest(BaseModel):
    hotel_address: str
    arrival_time: str
    itinerary: dict

class SwapRequest(BaseModel):
    hotel_address: str
    arrival_time: str
    itinerary: dict
    day_key: str
    item_index: int
    pacing: Optional[str] = "balanced"



@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "message": "Tokyo Travel Planner API"}


@app.post("/api/generate", response_model=ItineraryResponse)
async def generate_itinerary(request: ItineraryRequest):
    """
    Generate a travel itinerary.
    
    Args:
        request: ItineraryRequest with hotel address, arrival time, days, and wishlist
        
    Returns:
        ItineraryResponse with generated itinerary
    """
    try:
        # Geocode hotel address
        logger.info(f"Geocoding hotel: {request.hotel_address}")
        hotel_coords = geocode_address(request.hotel_address)
        
        if not hotel_coords:
            raise HTTPException(
                status_code=400,
                detail=f"Could not geocode hotel address: {request.hotel_address}"
            )
        
        hotel_lat, hotel_lng = hotel_coords
        
        # Parse arrival time
        try:
            arrival_datetime = datetime.fromisoformat(request.arrival_time.replace('Z', '+00:00'))
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid arrival_time format. Use ISO format: {e}"
            )
        
        # Parse departure flight time (REQUIRED for day calculation)
        try:
            departure_flight_datetime = datetime.fromisoformat(request.departure_flight_time.replace('Z', '+00:00'))
            logger.info(f"Departure flight time set: {departure_flight_datetime}")
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid departure_flight_time format. Use ISO format: {e}"
            )
        
        # TASK 1: Automatically calculate num_days from arrival and departure
        # Calculate the difference in calendar days
        if departure_flight_datetime < arrival_datetime:
            raise HTTPException(
                status_code=400,
                detail="Departure flight time must be after arrival time"
            )
        
        # Calculate calendar days difference
        # If arrival is Friday 14:00 and departure is Sunday 16:00, that's 3 days (Fri, Sat, Sun)
        arrival_date = arrival_datetime.date()
        departure_date = departure_flight_datetime.date()
        num_days = (departure_date - arrival_date).days + 1  # +1 to include both start and end days
        
        if num_days < 1:
            raise HTTPException(
                status_code=400,
                detail="Trip must span at least 1 day"
            )
        
        logger.info(f"Calculated {num_days} days from {arrival_date} to {departure_date}")
        
        # Database path
        db_path = "tabelog_japan.db"
        if not os.path.exists(db_path):
            raise HTTPException(
                status_code=500,
                detail="Restaurant database not found. Run scraper.py first."
            )
        
        # Generate itinerary
        logger.info(f"Generating {num_days}-day itinerary for {len(request.wishlist_items)} items")
        engine = ItineraryEngine(
            hotel_lat=hotel_lat,
            hotel_lng=hotel_lng,
            arrival_datetime=arrival_datetime,
            num_days=num_days,
            wishlist=request.wishlist_items,
            tabelog_db=db_path,
            departure_flight_time=departure_flight_datetime,
            interests=request.interests or []
        )
        
        itinerary = engine.generate_itinerary()
        
        if not itinerary:
            raise HTTPException(
                status_code=500,
                detail="Failed to generate itinerary. Check wishlist items and try again."
            )
        
        return ItineraryResponse(
            itinerary=itinerary,
            hotel_location={
                "address": request.hotel_address,
                "latitude": hotel_lat,
                "longitude": hotel_lng
            },
            message="Itinerary generated successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating itinerary: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


@app.post("/api/recalculate", response_model=ItineraryResponse)
async def recalculate_itinerary(request: RecalculateRequest):
    """
    Recalculates travel times and timestamps for an edited itinerary.
    Useful when a user drags/drops or swaps places between days.
    """
    try:
        hotel_coords = geocode_address(request.hotel_address)
        if not hotel_coords:
            raise HTTPException(status_code=400, detail="Could not geocode hotel")
        hotel_lat, hotel_lng = hotel_coords
        
        arrival_dt = datetime.fromisoformat(request.arrival_time.replace('Z', '+00:00'))
        
        # Initialize ItineraryEngine for recalculation (only basic parameters needed for travel time calc)
        engine = ItineraryEngine(
            hotel_lat=hotel_lat, 
            hotel_lng=hotel_lng, 
            arrival_datetime=arrival_dt,
            num_days=len(request.itinerary),
            wishlist=[],
            tabelog_db="tabelog_japan.db",
            pacing=request.pacing
        )
        
        new_itinerary = engine.recalculate(request.itinerary)
        
        return ItineraryResponse(
            itinerary=new_itinerary,
            hotel_location={"latitude": hotel_lat, "longitude": hotel_lng, "address": request.hotel_address},
            message="Recalculated travel times successfully"
        )
    except Exception as e:
        logger.error(f"Error recalculating: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/swap", response_model=ItineraryResponse)
async def swap_itinerary_item(request: SwapRequest):
    try:
        hotel_coords = geocode_address(request.hotel_address)
        if not hotel_coords:
            raise HTTPException(status_code=400, detail="Could not geocode hotel")
        hotel_lat, hotel_lng = hotel_coords
        
        arrival_dt = datetime.fromisoformat(request.arrival_time.replace('Z', '+00:00'))
        
        engine = ItineraryEngine(
            hotel_lat=hotel_lat, 
            hotel_lng=hotel_lng, 
            arrival_datetime=arrival_dt,
            num_days=len(request.itinerary),
            wishlist=[],
            tabelog_db="tabelog_japan.db",
            pacing=request.pacing
        )
        
        new_itinerary = engine.swap_item(request.itinerary, request.day_key, request.item_index)
        
        return ItineraryResponse(
            itinerary=new_itinerary,
            hotel_location={"latitude": hotel_lat, "longitude": hotel_lng, "address": request.hotel_address},
            message="Swapped item successfully"
        )
    except Exception as e:
        logger.error(f"Error swapping: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/export")
async def export_itinerary_ics(request: ExportRequest):
    """
    Generates an .ics file from the itinerary for Google Calendar / Apple Calendar.
    """
    try:
        cal = Calendar()
        
        arrival_dt = datetime.fromisoformat(request.arrival_time.replace('Z', '+00:00'))
        # Ensure we have a pure date context for incrementing days
        base_date = arrival_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        
        for day_key, events in request.itinerary.items():
            # e.g. "Day 1" -> 1
            try:
                day_num = int(day_key.replace("Day ", ""))
            except:
                day_num = 1
                
            day_date = base_date + timedelta(days=day_num - 1)
            
            for item in events:
                if not item.get("time") or not item.get("name"):
                    continue
                    
                # Parse "HH:MM"
                time_str = item["time"]
                try:
                    hours, minutes = map(int, time_str.split(":"))
                except:
                    continue
                    
                start_time = day_date.replace(hour=hours, minute=minutes)
                
                # Default duration to 1 hour if not provided
                duration_hours = float(item.get("duration_hours", 1.0))
                end_time = start_time + timedelta(hours=duration_hours)
                
                e = IcsEvent()
                
                # Title formatting
                prefix = ""
                if item.get("type") == "meal":
                    prefix = "🍽 "
                elif item.get("type") == "arrival":
                    prefix = "🛬 "
                else:
                    prefix = "📍 "
                
                e.name = f"{prefix}{item['name']}"
                e.begin = start_time
                e.end = end_time
                
                # Description
                desc_lines = []
                if item.get("is_recommendation"):
                    desc_lines.append("✨ Suggested Activity")
                    
                if item.get("travel_text"):
                    desc_lines.append(f"Transit: {item['travel_text']}")
                    
                if item.get("url"):
                    desc_lines.append(f"Google Maps: {item['url']}")
                    
                e.description = "\n".join(desc_lines)
                
                cal.events.add(e)
                
        ics_content = str(cal)
        return Response(
            content=ics_content,
            media_type="text/calendar",
            headers={
                "Content-Disposition": "attachment; filename=tokyo_itinerary.ics"
            }
        )
    except Exception as e:
        logger.error(f"Error exporting to ICS: {e}")
        raise HTTPException(status_code=500, detail=str(e))
