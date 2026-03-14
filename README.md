# Tokyo Travel Planner

python main.py
npm run dev

A comprehensive travel planning system for Tokyo that generates optimized day-by-day itineraries with restaurant recommendations from Tabelog.


## Features

- **Web Scraping**: Scrapes restaurant data from Tabelog (English)
- **Geocoding**: Adds coordinates to restaurants using Google Geocoding API
- **Itinerary Generation**: Creates optimized day-by-day travel plans
- **Distance Matrix Integration**: Uses real transit times from Google Distance Matrix API
- **Web API**: FastAPI backend for itinerary generation
- **Interactive Frontend**: Next.js app with Google Maps visualization

## Project Structure

```
TravelPlanner/
├── scraper.py              # Tabelog web scraper
├── geocode_data.py         # Geocoding script for restaurants
├── itinerary_engine.py     # Core itinerary generation engine
├── main.py                 # FastAPI backend server
├── verify_data.py          # Database verification script
├── test_itinerary.py       # Test script for itinerary engine
├── tabelog_japan.db        # SQLite database (generated)
├── requirements.txt        # Python dependencies
├── frontend/               # Next.js frontend application
│   ├── pages/
│   ├── components/
│   └── package.json
└── .env                    # Environment variables (create from .env.example)
```

## Setup

### 1. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Create a `.env` file:
```bash
MAPS_API_KEY=your_google_maps_api_key_here
```

### 3. Scrape Restaurant Data

```bash
python scraper.py
```

This will:
- Scrape restaurants from Tokyo districts
- Filter to top 50 per district
- Save to `tabelog_japan.db`

### 4. Geocode Restaurants

```bash
python geocode_data.py
```

This adds latitude/longitude coordinates to all restaurants.

### 5. Start the Backend API

```bash
python main.py
```

The API will run on `http://localhost:8000`

### 6. Start the Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local
# Edit .env.local and add your Google Maps API key
npm run dev
```

The frontend will run on `http://localhost:3000`

## API Endpoints

### POST `/api/generate`

Generate a travel itinerary.

**Request:**
```json
{
  "hotel_address": "Shibuya, Tokyo, Japan",
  "arrival_time": "2024-03-15T14:00:00",
  "days": 3,
  "wishlist_items": ["Senso-ji Temple", "Tokyo Skytree", "Shibuya Crossing"]
}
```

**Response:**
```json
{
  "itinerary": {
    "Day 1": [
      {
        "time": "14:00",
        "type": "arrival"
      },
      {
        "time": "15:30",
        "type": "sight",
        "name": "Senso-ji Temple",
        "latitude": 35.7148,
        "longitude": 139.7967,
        "travel_time_seconds": 1800,
        "travel_text": "30 mins via transit",
        "travel_mode": "transit"
      }
    ]
  },
  "hotel_location": {
    "address": "Shibuya, Tokyo, Japan",
    "latitude": 35.6580,
    "longitude": 139.7016
  }
}
```

## Database Schema

The `restaurants` table includes:
- `id`: Primary key
- `name`: Restaurant name
- `tabelog_rating`: Rating (0-5)
- `review_count`: Number of reviews
- `area`: Area/neighborhood
- `district`: District (Shibuya, Ginza, etc.)
- `genre`: Cuisine type
- `url`: Tabelog URL
- `budget_dinner`: Dinner budget
- `budget_lunch`: Lunch budget
- `latitude`: Geocoded latitude
- `longitude`: Geocoded longitude
- `geocoding_status`: Status of geocoding

## Technologies Used

- **Backend**: Python, FastAPI, SQLite, BeautifulSoup, geopy, googlemaps
- **Frontend**: Next.js, React, Tailwind CSS, @vis.gl/react-google-maps
- **APIs**: Google Maps (Geocoding, Distance Matrix), Tabelog

## Notes

- The scraper includes 3-7 second delays between requests to be respectful
- Geocoding cache saves API costs by caching addresses
- Itinerary engine uses greedy nearest neighbor algorithm for optimization
- Each day is capped at 8 hours of active time
- Transit times include a 10-minute buffer for walking/waiting

