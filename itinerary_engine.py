"""
Itinerary Engine for generating day-by-day travel plans.
Uses greedy nearest neighbor algorithm for distance optimization.
"""

import sqlite3
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple, Set
from geopy.distance import geodesic
from geopy.geocoders import GoogleV3
import googlemaps
import os
from dotenv import load_dotenv
import random

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Google Maps API Key for geocoding wishlist items
GOOGLE_API_KEY = os.getenv('MAPS_API_KEY')

# Maps user interest tags to Google Places API parameters for targeted recommendations
INTEREST_MAP = {
    "temples_shrines": {"type": "place_of_worship", "keyword": "shrine"},
    "anime_manga": {"keyword": "anime", "type": "store"},
    "nature_parks": {"type": "park"},
    "shopping": {"type": "shopping_mall"},
    "foodie": {"type": "restaurant"},
    "history": {"type": "museum", "keyword": "history"},
}


class ItineraryEngine:
    """
    Generates optimized day-by-day travel itineraries.
    """
    
    def __init__(self, hotel_lat: float, hotel_lng: float, arrival_datetime: datetime,
                 num_days: int, wishlist: List[str], tabelog_db: str,
                 departure_flight_time: Optional[datetime] = None,
                 interests: Optional[List[str]] = None):
        """
        Initialize the itinerary engine.
        
        Args:
            hotel_lat: Hotel latitude
            hotel_lng: Hotel longitude
            arrival_datetime: When the trip starts
            num_days: Number of days for the trip
            wishlist: List of place names to visit
            tabelog_db: Path to SQLite database
            departure_flight_time: When the flight departs (for airport constraint)
            interests: User-selected interest tags (e.g. ['anime_manga', 'shopping'])
        """
        self.hotel_lat = hotel_lat
        self.hotel_lng = hotel_lng
        self.arrival_datetime = arrival_datetime
        self.num_days = num_days
        self.wishlist = wishlist
        self.db_path = tabelog_db
        self.departure_flight_time = departure_flight_time
        self.interests = interests or []
        
        # Time constraints
        self.active_hours_start = 9  # 09:00
        self.active_hours_end = 21   # 21:00
        self.lunch_start = 12        # 12:00
        self.lunch_end = 14          # 14:00
        self.dinner_start = 18       # 18:00
        self.dinner_end = 20         # 20:00
        
        # Activity durations (in hours)
        self.sightseeing_duration = 1.5  # 1.5 hours per sight
        self.meal_duration = 1.0         # 1 hour for meals
        self.travel_buffer = 0.5          # 0.5 hours buffer between activities
        
        # Day capping - limit active time per day
        self.max_active_hours_per_day = 8.0  # Maximum 8 hours of active time per day
        
        # Initialize geocoder and Google Maps client if API key available
        self.geocoder = None
        self.gmaps = None
        if GOOGLE_API_KEY:
            try:
                self.geocoder = GoogleV3(api_key=GOOGLE_API_KEY)
                self.gmaps = googlemaps.Client(key=GOOGLE_API_KEY)
            except Exception as e:
                logger.warning(f"Could not initialize Google services: {e}")
    
    def geocode_place(self, place_name: str) -> Optional[Tuple[float, float]]:
        """
        Geocode a place name to get coordinates.
        
        Args:
            place_name: Name of the place
            
        Returns:
            Tuple of (latitude, longitude) or None if not found
        """
        if not self.geocoder:
            logger.warning("Geocoder not available, cannot geocode wishlist items")
            return None
        
        try:
            # Try with Tokyo context
            query = f"{place_name}, Tokyo, Japan"
            location = self.geocoder.geocode(query, language='en', timeout=10)
            if location:
                logger.info(f"Geocoded '{place_name}': ({location.latitude:.6f}, {location.longitude:.6f})")
                return (location.latitude, location.longitude)
            else:
                logger.warning(f"Could not geocode '{place_name}'")
                return None
        except Exception as e:
            logger.error(f"Error geocoding '{place_name}': {e}")
            return None
    
    def get_distance_km(self, lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        """
        Calculate distance between two coordinates in kilometers.
        Used only for clustering; next-best-location uses transit time via distance_matrix.
        """
        return geodesic((lat1, lng1), (lat2, lng2)).kilometers
    
    def get_transit_durations_matrix(self, origin_lat: float, origin_lng: float,
                                      destinations: List[Tuple[float, float]],
                                      departure_time: datetime) -> List[Tuple[int, int]]:
        """
        Get transit durations from origin to multiple destinations using Distance Matrix API.
        Crucial for picking next location by real transit time, not geographic distance.
        
        Args:
            origin_lat, origin_lng: Origin coordinates
            destinations: List of (lat, lng) tuples
            departure_time: When to depart (required for transit routing)
            
        Returns:
            List of (index, duration_seconds) for reachable destinations.
            Unreachable destinations are excluded. Sorted by duration ascending.
        """
        if not self.gmaps or not destinations:
            return []
        
        # Distance Matrix API allows max 25 destinations per request
        results = []
        for i in range(0, len(destinations), 25):
            batch = destinations[i:i + 25]
            try:
                matrix = self.gmaps.distance_matrix(
                    origins=[(origin_lat, origin_lng)],
                    destinations=[(lat, lng) for lat, lng in batch],
                    mode='transit',
                    departure_time=departure_time,
                    language='en'
                )
                if matrix.get('status') != 'OK':
                    continue
                rows = matrix.get('rows', [])
                if not rows:
                    continue
                for j, elem in enumerate(rows[0].get('elements', [])):
                    if elem.get('status') == 'OK' and 'duration' in elem:
                        duration_sec = elem['duration']['value']
                        results.append((i + j, duration_sec))
            except Exception as e:
                logger.debug(f"Distance matrix error for batch {i}: {e}")
        
        results.sort(key=lambda x: x[1])
        return results
    
    def get_travel_time(self, origin_lat: float, origin_lng: float,
                       dest_lat: float, dest_lng: float, mode: str = 'transit',
                       departure_time: Optional[datetime] = None) -> Optional[Dict]:
        """
        Get actual travel time using Google Directions API for transit details.
        Prioritizes transit, with dynamic buffering and walking comparison.
        
        Args:
            origin_lat, origin_lng: Origin coordinates
            dest_lat, dest_lng: Destination coordinates
            mode: Transportation mode ('transit', 'walking', 'driving', 'bicycling')
            departure_time: When to depart (REQUIRED for transit routing). If None, uses current time.
            
        Returns:
            Dictionary with:
            - travel_time_seconds: Travel time in seconds (including buffers)
            - travel_time_hours: Travel time in hours
            - travel_text: Human-readable description (e.g., "24 mins via Yamanote Line")
            - duration_text: Formatted duration from API (e.g., "24 mins")
            - transit_line: Transit line name (e.g., "Yamanote Line") or None
            - mode: Transportation mode used ('transit' or 'walking')
            - steps: List of transit steps (if transit)
        """
        # Station buffer for large stations like Shinjuku/Shibuya
        STATION_BUFFER_SECONDS = 600  # 10 minutes for transit
        WALKING_BUFFER_SECONDS = 300  # 5 minutes for walking
        
        if not self.gmaps:
            # Fallback to distance-based estimate if API not available
            distance = self.get_distance_km(origin_lat, origin_lng, dest_lat, dest_lng)
            estimated_hours = max(0.25, min(1.5, distance / 10))
            estimated_seconds = int(estimated_hours * 3600) + STATION_BUFFER_SECONDS
            logger.debug(f"Using estimated travel time: {estimated_hours:.2f} hours")
            return {
                'travel_time_seconds': estimated_seconds,
                'travel_time_hours': estimated_seconds / 3600.0,
                'travel_text': f"{estimated_seconds // 60} mins (estimated)",
                'duration_text': f"{estimated_seconds // 60} mins",
                'transit_line': None,
                'mode': 'transit',
                'steps': []
            }
        
        try:
            origin = (origin_lat, origin_lng)
            destination = (dest_lat, dest_lng)
            
            # Use provided departure time or current time
            if departure_time is None:
                departure_time = datetime.now()
            
            transit_result = None
            walking_result = None
            
            # TASK 1: Try transit first (REQUIRED mode='transit' with departure_time)
            if mode == 'transit':
                try:
                    # Use Directions API to get transit line details
                    directions_result = self.gmaps.directions(
                        origin=origin,
                        destination=destination,
                        mode='transit',
                        departure_time=departure_time,
                        language='en',
                        alternatives=False
                    )
                    
                    if directions_result and len(directions_result) > 0:
                        route = directions_result[0]
                        leg = route['legs'][0]
                        
                        # Get duration in seconds
                        transit_duration_seconds = leg['duration']['value']
                        transit_duration_text = leg['duration']['text']
                        
                        # Extract transit line information
                        transit_line = None
                        transit_steps = []
                        
                        for step in leg.get('steps', []):
                            if step['travel_mode'] == 'TRANSIT':
                                transit_details = step.get('transit_details', {})
                                line = transit_details.get('line', {})
                                line_name = line.get('short_name') or line.get('name', '')
                                if line_name:
                                    transit_line = line_name
                                    transit_steps.append({
                                        'line': line_name,
                                        'headsign': transit_details.get('headsign', ''),
                                        'departure_stop': transit_details.get('departure_stop', {}).get('name', ''),
                                        'arrival_stop': transit_details.get('arrival_stop', {}).get('name', '')
                                    })
                        
                        # TASK 3: Add 10-minute station buffer for transit
                        transit_total_seconds = transit_duration_seconds + STATION_BUFFER_SECONDS
                        transit_result = {
                            'duration_seconds': transit_duration_seconds,
                            'total_seconds': transit_total_seconds,
                            'duration_text': transit_duration_text,
                            'transit_line': transit_line,
                            'steps': transit_steps
                        }
                        
                        logger.debug(f"Transit: {transit_duration_text} via {transit_line or 'transit'}")
                        
                except Exception as e:
                    logger.debug(f"Transit Directions API error: {e}")
            
            # TASK 2: Dynamic Buffering - If transit < 15 mins, compare with walking
            should_compare_walking = False
            if transit_result and transit_result['duration_seconds'] < 900:  # 15 minutes
                should_compare_walking = True
                logger.debug("Transit < 15 mins, comparing with walking...")
            
            # Get walking time for comparison or fallback
            try:
                walking_directions = self.gmaps.directions(
                    origin=origin,
                    destination=destination,
                    mode='walking',
                    language='en'
                )
                
                if walking_directions and len(walking_directions) > 0:
                    walking_leg = walking_directions[0]['legs'][0]
                    walking_duration_seconds = walking_leg['duration']['value']
                    walking_duration_text = walking_leg['duration']['text']
                    walking_total_seconds = walking_duration_seconds + WALKING_BUFFER_SECONDS
                    
                    walking_result = {
                        'duration_seconds': walking_duration_seconds,
                        'total_seconds': walking_total_seconds,
                        'duration_text': walking_duration_text
                    }
                    
                    logger.debug(f"Walking: {walking_duration_text}")
            except Exception as e:
                logger.debug(f"Walking Directions API error: {e}")
            
            # TASK 2: Pick the minimum if transit < 15 mins
            if should_compare_walking and transit_result and walking_result:
                if walking_result['total_seconds'] < transit_result['total_seconds']:
                    logger.info(f"Walking ({walking_result['duration_text']}) is faster than transit, using walking")
                    return {
                        'travel_time_seconds': walking_result['total_seconds'],
                        'travel_time_hours': walking_result['total_seconds'] / 3600.0,
                        'travel_text': f"{walking_result['total_seconds'] // 60} mins walking",
                        'duration_text': walking_result['duration_text'],
                        'transit_line': None,
                        'mode': 'walking',
                        'steps': []
                    }
            
            # Use transit result if available
            if transit_result:
                transit_line_text = f" via {transit_result['transit_line']}" if transit_result['transit_line'] else " via transit"
                travel_text = f"{transit_result['total_seconds'] // 60} mins{transit_line_text}"
                
                return {
                    'travel_time_seconds': transit_result['total_seconds'],
                    'travel_time_hours': transit_result['total_seconds'] / 3600.0,
                    'travel_text': travel_text,
                    'duration_text': transit_result['duration_text'],
                    'transit_line': transit_result['transit_line'],
                    'mode': 'transit',
                    'steps': transit_result['steps']
                }
            
            # Fallback to walking if transit failed
            if walking_result:
                return {
                    'travel_time_seconds': walking_result['total_seconds'],
                    'travel_time_hours': walking_result['total_seconds'] / 3600.0,
                    'travel_text': f"{walking_result['total_seconds'] // 60} mins walking",
                    'duration_text': walking_result['duration_text'],
                    'transit_line': None,
                    'mode': 'walking',
                    'steps': []
                }
            
            # Final fallback: distance-based estimate
            logger.debug("All API calls failed, using distance-based estimate")
            distance = self.get_distance_km(origin_lat, origin_lng, dest_lat, dest_lng)
            estimated_hours = max(0.25, min(1.5, distance / 10))
            estimated_seconds = int(estimated_hours * 3600) + STATION_BUFFER_SECONDS
            return {
                'travel_time_seconds': estimated_seconds,
                'travel_time_hours': estimated_seconds / 3600.0,
                'travel_text': f"{estimated_seconds // 60} mins (estimated)",
                'duration_text': f"{estimated_seconds // 60} mins",
                'transit_line': None,
                'mode': 'transit',
                'steps': []
            }
                
        except Exception as e:
            logger.error(f"Error getting travel time: {e}")
            # Fallback to distance-based estimate
            distance = self.get_distance_km(origin_lat, origin_lng, dest_lat, dest_lng)
            estimated_hours = max(0.25, min(1.5, distance / 10))
            estimated_seconds = int(estimated_hours * 3600) + STATION_BUFFER_SECONDS
            return {
                'travel_time_seconds': estimated_seconds,
                'travel_time_hours': estimated_seconds / 3600.0,
                'travel_text': f"{estimated_seconds // 60} mins (estimated)",
                'duration_text': f"{estimated_seconds // 60} mins",
                'transit_line': None,
                'mode': 'transit',
                'steps': []
            }
    
    def find_nearest_restaurant(self, lat: float, lng: float, meal_type: str = "lunch",
                               min_rating: float = 3.5, exclude_name: Optional[str] = None,
                               departure_time: Optional[datetime] = None) -> Optional[Dict]:
        """
        Find the nearest restaurant from database near given coordinates.
        
        Args:
            lat: Latitude
            lng: Longitude
            meal_type: "lunch" or "dinner"
            min_rating: Minimum tabelog rating (default: 3.5)
            exclude_name: Restaurant name to exclude (e.g., if just visited)
            
        Returns:
            Dictionary with restaurant info or None
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            # Query restaurants with coordinates and good ratings
            # Prioritize restaurants with rating > min_rating
            if exclude_name:
                cursor.execute('''
                    SELECT name, tabelog_rating, latitude, longitude, district, genre
                    FROM restaurants
                    WHERE latitude IS NOT NULL 
                      AND longitude IS NOT NULL
                      AND name != ?
                      AND (tabelog_rating IS NULL OR tabelog_rating >= ?)
                    ORDER BY 
                        CASE WHEN tabelog_rating >= ? THEN 0 ELSE 1 END,
                        COALESCE(tabelog_rating, 0) DESC
                    LIMIT 100
                ''', (exclude_name, min_rating, min_rating))
            else:
                cursor.execute('''
                    SELECT name, tabelog_rating, latitude, longitude, district, genre
                    FROM restaurants
                    WHERE latitude IS NOT NULL 
                      AND longitude IS NOT NULL
                      AND (tabelog_rating IS NULL OR tabelog_rating >= ?)
                    ORDER BY 
                        CASE WHEN tabelog_rating >= ? THEN 0 ELSE 1 END,
                        COALESCE(tabelog_rating, 0) DESC
                    LIMIT 100
                ''', (min_rating, min_rating))
            
            restaurants = cursor.fetchall()
            
            if not restaurants:
                logger.warning("No restaurants found in database")
                return None
            
            # Find nearest by transit time (limit to 25 for Distance Matrix batch)
            dep_time = departure_time or datetime.now()
            candidates = [(r[0], r[1], r[2], r[3], r[4], r[5]) for r in restaurants[:25]]
            destinations = [(r[2], r[3]) for r in candidates]
            
            nearest = None
            if self.gmaps:
                duration_pairs = self.get_transit_durations_matrix(lat, lng, destinations, dep_time)
                if duration_pairs:
                    best_idx = duration_pairs[0][0]
                    name, rating, rest_lat, rest_lng, district, genre = candidates[best_idx]
                    nearest = {
                        'name': name,
                        'tabelog_rating': rating,
                        'latitude': rest_lat,
                        'longitude': rest_lng,
                        'district': district,
                        'genre': genre,
                        'distance_km': None
                    }
            
            # Fallback to geodesic if API unavailable
            if not nearest:
                min_distance = float('inf')
                for name, rating, rest_lat, rest_lng, district, genre in restaurants:
                    distance = self.get_distance_km(lat, lng, rest_lat, rest_lng)
                    if distance < min_distance:
                        min_distance = distance
                        nearest = {
                            'name': name,
                            'tabelog_rating': rating,
                            'latitude': rest_lat,
                            'longitude': rest_lng,
                            'district': district,
                            'genre': genre,
                            'distance_km': distance
                        }
            
            if nearest:
                logger.info(f"Found nearest restaurant: {nearest['name']}")
            
            return nearest
            
        finally:
            conn.close()
    
    def find_nearest_wishlist_item(self, current_lat: float, current_lng: float,
                                   unvisited: List[Tuple[str, float, float]],
                                   departure_time: Optional[datetime] = None) -> Optional[Tuple[str, float, float]]:
        """
        Find the next-best wishlist item using transit time (not geographic distance).
        Uses Google Distance Matrix API with mode='transit' and departure_time.
        
        Args:
            current_lat: Current latitude
            current_lng: Current longitude
            unvisited: List of (name, lat, lng) tuples
            departure_time: When we would depart (required for transit routing)
            
        Returns:
            Tuple of (name, lat, lng) or None
        """
        if not unvisited:
            return None
        
        dep_time = departure_time or datetime.now()
        destinations = [(lat, lng) for _, lat, lng in unvisited]
        
        if self.gmaps:
            duration_pairs = self.get_transit_durations_matrix(
                current_lat, current_lng, destinations, dep_time
            )
            if duration_pairs:
                best_idx = duration_pairs[0][0]
                return unvisited[best_idx]
        
        # Fallback to geodesic if API unavailable
        nearest = None
        min_distance = float('inf')
        for name, lat, lng in unvisited:
            distance = self.get_distance_km(current_lat, current_lng, lat, lng)
            if distance < min_distance:
                min_distance = distance
                nearest = (name, lat, lng)
        return nearest
    
    def calculate_active_hours(self, day_events: List[Dict]) -> float:
        """
        Calculate total active hours from day events.
        Includes travel time, sightseeing duration, and meal duration.
        Excludes arrival and transport-only events.
        
        Args:
            day_events: List of event dictionaries for a day
            
        Returns:
            Total active hours as float
        """
        total_hours = 0.0
        
        for event in day_events:
            event_type = event.get('type')
            
            # Skip arrival and transport-only events
            if event_type in ['arrival', 'transport']:
                continue
            
            # Add travel time
            travel_seconds = event.get('travel_time_seconds', 0)
            total_hours += travel_seconds / 3600.0
            
            # Add activity duration
            if event_type == 'sight':
                total_hours += self.sightseeing_duration
            elif event_type == 'meal':
                total_hours += self.meal_duration
        
        return total_hours
    
    def get_last_location(self, day_events: List[Dict]) -> Tuple[float, float]:
        """
        Get the last location from day events.
        
        Args:
            day_events: List of event dictionaries for a day
            
        Returns:
            Tuple of (latitude, longitude) or hotel coordinates if no events
        """
        # Find last event with coordinates
        for event in reversed(day_events):
            if event.get('latitude') and event.get('longitude'):
                return (event['latitude'], event['longitude'])
        
        # Fallback to hotel
        return (self.hotel_lat, self.hotel_lng)
    
    def get_place_id(self, place_name: str, lat: float, lng: float) -> Optional[str]:
        """
        Get place_id from Google Places API using text search.
        
        Args:
            place_name: Name of the place
            lat, lng: Coordinates for context
            
        Returns:
            place_id or None
        """
        if not self.gmaps:
            return None
        
        try:
            result = self.gmaps.places_nearby(
                location=(lat, lng),
                radius=1000,  # 1km radius
                keyword=place_name,
                language='en'
            )
            
            if result.get('status') == 'OK' and result.get('results'):
                # Return the first result's place_id
                return result['results'][0].get('place_id')
        except Exception as e:
            logger.debug(f"Could not get place_id for {place_name}: {e}")
        
        return None
    
    def is_place_open(self, place_id: str, visit_time: datetime) -> bool:
        """
        TASK 1: Check if a place is open at the given time using Google Places API.
        
        Args:
            place_id: Google Places place_id
            visit_time: When we want to visit
            
        Returns:
            True if open, False if closed or unknown
        """
        if not self.gmaps or not place_id:
            return True  # Assume open if we can't check
        
        try:
            place_details = self.gmaps.place(
                place_id=place_id,
                fields=['opening_hours']
            )
            
            if place_details.get('status') != 'OK':
                return True  # Assume open if API error
            
            opening_hours = place_details.get('result', {}).get('opening_hours')
            if not opening_hours:
                return True  # No hours data, assume open
            
            # Check if place is open at visit_time
            # Google Places API returns opening_hours with periods
            # For simplicity, we'll check if it's currently open
            # In production, you'd parse the periods for the specific day/time
            is_open_now = opening_hours.get('open_now', True)
            
            # TODO: Parse periods to check specific visit_time
            # For now, return open_now as approximation
            return is_open_now
            
        except Exception as e:
            logger.debug(f"Error checking opening hours for place_id {place_id}: {e}")
            return True  # Assume open on error
    
    def cluster_wishlist_items(self, wishlist_coords: List[Tuple[str, float, float]], 
                              num_clusters: int) -> List[List[Tuple[str, float, float]]]:
        """
        TASK 4: Use K-Means clustering to group wishlist items by location.
        
        Args:
            wishlist_coords: List of (name, lat, lng) tuples
            num_clusters: Number of clusters (days)
            
        Returns:
            List of clusters, each containing (name, lat, lng) tuples
        """
        if len(wishlist_coords) <= num_clusters:
            # If we have fewer items than clusters, put one per cluster
            clusters = [[item] for item in wishlist_coords]
            # Fill remaining clusters with empty lists
            while len(clusters) < num_clusters:
                clusters.append([])
            return clusters
        
        # Simple K-Means implementation
        # Initialize centroids randomly
        centroids = random.sample(wishlist_coords, num_clusters)
        centroids = [(lat, lng) for _, lat, lng in centroids]
        
        # Iterate until convergence
        for _ in range(10):  # Max 10 iterations
            # Assign items to nearest centroid
            clusters = [[] for _ in range(num_clusters)]
            for item in wishlist_coords:
                _, item_lat, item_lng = item
                min_dist = float('inf')
                nearest_cluster = 0
                for i, (cent_lat, cent_lng) in enumerate(centroids):
                    dist = self.get_distance_km(item_lat, item_lng, cent_lat, cent_lng)
                    if dist < min_dist:
                        min_dist = dist
                        nearest_cluster = i
                clusters[nearest_cluster].append(item)
            
            # Update centroids
            new_centroids = []
            for cluster in clusters:
                if cluster:
                    avg_lat = sum(lat for _, lat, _ in cluster) / len(cluster)
                    avg_lng = sum(lng for _, lng, _ in cluster) / len(cluster)
                    new_centroids.append((avg_lat, avg_lng))
                else:
                    # Keep old centroid if cluster is empty
                    new_centroids.append(centroids[len(new_centroids)])
            
            # Check convergence
            if all(self.get_distance_km(c1[0], c1[1], c2[0], c2[1]) < 0.1 
                   for c1, c2 in zip(centroids, new_centroids)):
                break
            
            centroids = new_centroids
        
        return clusters
    
    def get_recommendations(self, location_lat: float, location_lng: float,
                           visited_place_ids: Set[str] = None,
                           interest_tag: Optional[str] = None,
                           rotation_index: int = 0,
                           sort_by_transit_from: Optional[Tuple[float, float]] = None,
                           departure_time: Optional[datetime] = None) -> List[Dict]:
        """
        Get high-quality recommendations near a location using Google Places API.
        Uses user interests for targeted filtering when available.
        Optionally sorts by transit time from origin when sort_by_transit_from + departure_time provided.
        
        Args:
            location_lat, location_lng: Coordinates of the last visited place (or hotel)
            visited_place_ids: Set of place_ids already visited (to avoid duplicates)
            interest_tag: Specific interest tag to use (e.g. 'nature_parks')
            rotation_index: Used to rotate through interests when no tag specified (e.g. day index)
            sort_by_transit_from: (origin_lat, origin_lng) to sort results by transit duration
            departure_time: When we would depart (for transit-based sorting)
            
        Returns:
            List of recommendation dictionaries with name, lat, lng, place_id, rating, etc.
        """
        if not self.gmaps:
            return []
        
        if visited_place_ids is None:
            visited_place_ids = set()
        
        # Build Places API params: rotate through user interests, fallback to tourist_attraction
        places_params = {
            "location": (location_lat, location_lng),
            "radius": 3000,  # 3km radius
            "language": "en"
        }
        
        if interest_tag and interest_tag in INTEREST_MAP:
            interest_config = INTEREST_MAP[interest_tag]
            if "type" in interest_config:
                places_params["type"] = interest_config["type"]
            if "keyword" in interest_config:
                places_params["keyword"] = interest_config["keyword"]
        elif self.interests:
            # Rotate through user's interests based on rotation_index
            tag = self.interests[rotation_index % len(self.interests)]
            if tag in INTEREST_MAP:
                interest_config = INTEREST_MAP[tag]
                if "type" in interest_config:
                    places_params["type"] = interest_config["type"]
                if "keyword" in interest_config:
                    places_params["keyword"] = interest_config["keyword"]
        
        # Default: generic tourist attractions
        if "type" not in places_params:
            places_params["type"] = "tourist_attraction"
        
        try:
            result = self.gmaps.places_nearby(**places_params)
            
            if result.get('status') != 'OK':
                logger.debug(f"Places API error: {result.get('status')}")
                return []
            
            recommendations = []
            for place in result.get('results', []):
                place_id = place.get('place_id')
                
                # CRITICAL: Skip if already visited
                if not place_id or place_id in visited_place_ids:
                    continue
                
                # Rating Check: Only accept places with rating > 4.0 and user_ratings_total > 500
                rating = place.get('rating')
                user_ratings_total = place.get('user_ratings_total', 0)
                
                if not rating or rating <= 4.0:
                    continue
                if user_ratings_total < 500:
                    continue
                
                location = place.get('geometry', {}).get('location', {})
                recommendations.append({
                    'name': place.get('name', 'Unknown'),
                    'latitude': location.get('lat'),
                    'longitude': location.get('lng'),
                    'place_id': place_id,
                    'rating': rating,
                    'user_ratings_total': user_ratings_total,
                    'types': place.get('types', []),
                    'vicinity': place.get('vicinity', '')
                })
            
            # Sort by transit time when origin + departure_time provided (pick lowest duration)
            if (recommendations and sort_by_transit_from and departure_time and self.gmaps):
                origin_lat, origin_lng = sort_by_transit_from
                destinations = [(r['latitude'], r['longitude']) for r in recommendations]
                duration_pairs = self.get_transit_durations_matrix(
                    origin_lat, origin_lng, destinations, departure_time
                )
                if duration_pairs:
                    # Reorder by ascending transit duration (index, duration)
                    ordered = [recommendations[idx] for idx, _ in duration_pairs]
                    recommendations = ordered
            
            logger.info(f"Found {len(recommendations)} high-quality recommendations near ({location_lat:.4f}, {location_lng:.4f})")
            return recommendations[:3]
            
        except Exception as e:
            logger.error(f"Error getting recommendations: {e}")
            return []
    
    def discover_attractions(self, center_lat: float, center_lng: float, 
                             radius_km: float = 5.0, limit: int = 3,
                             visited_place_ids: Set[str] = None,
                             rotation_index: int = 0,
                             sort_by_transit_from: Optional[Tuple[float, float]] = None,
                             departure_time: Optional[datetime] = None) -> List[Dict]:
        """
        Discover tourist attractions near a location using Google Places API.
        Uses get_recommendations with interest-based rotation and optional transit-time sorting.
        
        Args:
            center_lat, center_lng: Center location to search near
            radius_km: Search radius in kilometers (ignored, uses 3km)
            limit: Maximum number of attractions to return
            visited_place_ids: Set of place_ids already visited (to avoid duplicates)
            rotation_index: Used to rotate through user interests (e.g. day number)
            sort_by_transit_from: (origin_lat, origin_lng) to sort by transit duration
            departure_time: When we would depart (for transit-based sorting)
            
        Returns:
            List of attraction dictionaries with name, lat, lng, place_id
        """
        return self.get_recommendations(
            center_lat, center_lng, visited_place_ids, rotation_index=rotation_index,
            sort_by_transit_from=sort_by_transit_from, departure_time=departure_time
        )[:limit]
    
    def generate_itinerary(self) -> Dict:
        """
        Generate the complete itinerary.
        
        Returns:
            Dictionary with day-by-day itinerary in JSON format
        """
        logger.info("Starting itinerary generation...")
        
        # Geocode wishlist items and get place_ids
        wishlist_coords = []
        wishlist_place_ids = {}  # Map place_name -> place_id
        
        for place in self.wishlist:
            coords = self.geocode_place(place)
            if coords:
                lat, lng = coords
                # Try to get place_id for opening hours check
                place_id = self.get_place_id(place, lat, lng)
                if place_id:
                    wishlist_place_ids[place] = place_id
                wishlist_coords.append((place, lat, lng))
            else:
                logger.warning(f"Skipping '{place}' - could not geocode")
        
        if not wishlist_coords:
            logger.error("No wishlist items could be geocoded!")
            return {}
        
        logger.info(f"Successfully geocoded {len(wishlist_coords)}/{len(self.wishlist)} wishlist items")
        
        # TASK 4: Cluster wishlist items by location using K-Means
        clusters = self.cluster_wishlist_items(wishlist_coords, self.num_days)
        logger.info(f"Clustered wishlist into {len(clusters)} groups")
        
        # Initialize itinerary
        itinerary = {}
        unvisited = wishlist_coords.copy()
        deferred_items = []  # Items deferred due to closed hours
        visited_place_ids = set()  # Track visited place_ids for discovery mode
        
        # Start from hotel
        current_lat = self.hotel_lat
        current_lng = self.hotel_lng
        
        # Calculate airport constraint for final day
        airport_stop_time = None
        airport_lat = None
        airport_lng = None
        if self.departure_flight_time:
            # Final day must end 4 hours before departure
            airport_stop_time = self.departure_flight_time - timedelta(hours=4)
            logger.info(f"Airport constraint: Final day must end by {airport_stop_time.strftime('%Y-%m-%d %H:%M')} (4 hours before flight)")
            
            # TASK 3: Geocode airport coordinates (try both Narita and Haneda)
            if self.geocoder:
                for airport_name in ["Narita International Airport, Tokyo", "Haneda Airport, Tokyo"]:
                    try:
                        location = self.geocoder.geocode(airport_name, language='en', timeout=10)
                        if location:
                            airport_lat = location.latitude
                            airport_lng = location.longitude
                            logger.info(f"Airport geocoded: {airport_name} -> ({airport_lat:.6f}, {airport_lng:.6f})")
                            break
                    except Exception as e:
                        logger.warning(f"Could not geocode {airport_name}: {e}")
                if not airport_lat:
                    logger.warning("Could not geocode airport, using default Narita coordinates")
                    airport_lat, airport_lng = 35.7720, 140.3929  # Narita default
            else:
                # Default to Narita if geocoder not available
                airport_lat, airport_lng = 35.7720, 140.3929
                logger.info("Using default airport coordinates (Narita)")
        
        # Process each day
        for day_num in range(1, self.num_days + 1):
            day_key = f"Day {day_num}"
            day_events = []
            
            # Determine start time
            if day_num == 1:
                # First day starts from arrival time
                current_time = self.arrival_datetime
                # If arrival is before active hours, start at active hours
                if current_time.hour < self.active_hours_start:
                    current_time = current_time.replace(hour=self.active_hours_start, minute=0, second=0)
            else:
                # Other days start at active hours
                current_time = current_time.replace(hour=self.active_hours_start, minute=0, second=0)
                current_time += timedelta(days=1)
            
            # Add arrival event for first day
            if day_num == 1:
                day_events.append({
                    "time": current_time.strftime("%H:%M"),
                    "type": "arrival"
                })
            
            logger.info(f"\nGenerating {day_key}...")
            
            # TASK 4: Get cluster center for this day (for discovery mode)
            cluster_center_lat = self.hotel_lat
            cluster_center_lng = self.hotel_lng
            if day_num <= len(clusters) and clusters[day_num - 1]:
                # Use cluster center as anchor
                cluster_items = clusters[day_num - 1]
                cluster_center_lat = sum(lat for _, lat, _ in cluster_items) / len(cluster_items)
                cluster_center_lng = sum(lng for _, lng, _ in cluster_items) / len(cluster_items)
                logger.info(f"Using cluster center ({cluster_center_lat:.4f}, {cluster_center_lng:.4f}) for {day_key}")
            
            # Track meal scheduling for this day
            lunch_scheduled = False
            dinner_scheduled = False
            last_restaurant_name = None
            last_activity_end_time = current_time  # TASK 2: Track last activity end time
            
            # Track active time for day capping
            day_start_time = current_time
            active_time_used = 0.0  # Hours of active time used today
            
            # Determine end time for this day (airport constraint for final day)
            day_end_time = None
            if day_num == self.num_days and airport_stop_time:
                # Final day: use airport stop time if earlier than normal end time
                normal_end = current_time.replace(hour=self.active_hours_end, minute=0, second=0)
                day_end_time = min(airport_stop_time, normal_end)
                logger.info(f"Final day end time: {day_end_time.strftime('%H:%M')} (airport constraint)")
            else:
                day_end_time = current_time.replace(hour=self.active_hours_end, minute=0, second=0)
            
            # Process activities until end of active hours or day is full
            while (current_time < day_end_time and 
                   unvisited and 
                   active_time_used < self.max_active_hours_per_day):
                # Check if it's lunch time and we haven't scheduled lunch yet
                # Only schedule if current time is between 12:00 and 14:00
                if (not lunch_scheduled and 
                    self.lunch_start <= current_time.hour < self.lunch_end and
                    active_time_used + self.meal_duration <= self.max_active_hours_per_day):
                    # Get travel time to restaurant
                    restaurant = self.find_nearest_restaurant(current_lat, current_lng, "lunch", 
                                                              exclude_name=last_restaurant_name,
                                                              departure_time=current_time)
                    if restaurant:
                        travel_info = self.get_travel_time(current_lat, current_lng,
                                                          restaurant['latitude'], restaurant['longitude'],
                                                          departure_time=current_time)
                        if travel_info:
                            # Add travel time
                            travel_hours = travel_info['travel_time_hours']
                            current_time += timedelta(hours=travel_hours)
                            active_time_used += travel_hours
                            
                            day_events.append({
                                "time": current_time.strftime("%H:%M"),
                                "type": "meal",
                                "name": restaurant['name'],
                                "tabelog_score": restaurant['tabelog_rating'],
                                "genre": restaurant.get('genre'),
                                "district": restaurant.get('district'),
                                "latitude": restaurant['latitude'],
                                "longitude": restaurant['longitude'],
                                "travel_time_seconds": travel_info['travel_time_seconds'],
                                "travel_text": travel_info['travel_text'],
                                "duration_text": travel_info.get('duration_text', travel_info['travel_text']),
                                "transit_line": travel_info.get('transit_line'),
                                "travel_mode": travel_info['mode']
                            })
                            # Update current location to restaurant
                            current_lat = restaurant['latitude']
                            current_lng = restaurant['longitude']
                            last_restaurant_name = restaurant['name']
                            lunch_scheduled = True
                            current_time += timedelta(hours=self.meal_duration)
                            active_time_used += self.meal_duration
                            continue
                
                # Check if it's dinner time and we haven't scheduled dinner yet
                # Only schedule if current time is between 18:00 and 20:00
                # Also check airport constraint: don't schedule dinner if it would go past day_end_time
                if (not dinner_scheduled and 
                    self.dinner_start <= current_time.hour < self.dinner_end and
                    current_time + timedelta(hours=self.meal_duration) <= day_end_time and
                    active_time_used + self.meal_duration <= self.max_active_hours_per_day):
                    # Find nearest restaurant for dinner (prefer near hotel if late)
                    if current_time.hour >= 19:
                        # Try to find restaurant near hotel
                        restaurant = self.find_nearest_restaurant(self.hotel_lat, self.hotel_lng, "dinner",
                                                                  exclude_name=last_restaurant_name,
                                                                  departure_time=current_time)
                        dest_lat, dest_lng = self.hotel_lat, self.hotel_lng
                    else:
                        restaurant = self.find_nearest_restaurant(current_lat, current_lng, "dinner",
                                                                  exclude_name=last_restaurant_name,
                                                                  departure_time=current_time)
                        dest_lat, dest_lng = current_lat, current_lng
                    
                    if restaurant:
                        travel_info = self.get_travel_time(dest_lat, dest_lng,
                                                          restaurant['latitude'], restaurant['longitude'],
                                                          departure_time=current_time)
                        if travel_info:
                            # Add travel time
                            travel_hours = travel_info['travel_time_hours']
                            current_time += timedelta(hours=travel_hours)
                            active_time_used += travel_hours
                            
                            day_events.append({
                                "time": current_time.strftime("%H:%M"),
                                "type": "meal",
                                "name": restaurant['name'],
                                "tabelog_score": restaurant['tabelog_rating'],
                                "genre": restaurant.get('genre'),
                                "district": restaurant.get('district'),
                                "latitude": restaurant['latitude'],
                                "longitude": restaurant['longitude'],
                                "travel_time_seconds": travel_info['travel_time_seconds'],
                                "travel_text": travel_info['travel_text'],
                                "duration_text": travel_info.get('duration_text', travel_info['travel_text']),
                                "transit_line": travel_info.get('transit_line'),
                                "travel_mode": travel_info['mode']
                            })
                            # Update current location to restaurant
                            current_lat = restaurant['latitude']
                            current_lng = restaurant['longitude']
                            last_restaurant_name = restaurant['name']
                            dinner_scheduled = True
                            current_time += timedelta(hours=self.meal_duration)
                            active_time_used += self.meal_duration
                            continue
                
                # Find nearest unvisited wishlist item (including deferred items)
                all_unvisited = unvisited + deferred_items
                nearest = self.find_nearest_wishlist_item(current_lat, current_lng, all_unvisited,
                                                          departure_time=current_time)
                
                if nearest:
                    name, lat, lng = nearest
                    
                    # TASK 1: Check opening hours before scheduling
                    place_id = wishlist_place_ids.get(name)
                    visit_time = current_time + timedelta(hours=self.sightseeing_duration)  # Time after travel
                    
                    if place_id:
                        is_open = self.is_place_open(place_id, visit_time)
                        if not is_open:
                            logger.info(f"{name} is closed at {visit_time.strftime('%H:%M')}, deferring to next day")
                            if nearest in unvisited:
                                unvisited.remove(nearest)
                            if nearest not in deferred_items:
                                deferred_items.append(nearest)
                            continue
                    
                    # Get actual travel time using Distance Matrix API
                    travel_info = self.get_travel_time(current_lat, current_lng, lat, lng,
                                                      departure_time=current_time)
                    
                    if travel_info:
                        travel_hours = travel_info['travel_time_hours']
                        # Check if adding this activity would exceed day cap
                        total_time_needed = travel_hours + self.sightseeing_duration
                        if active_time_used + total_time_needed > self.max_active_hours_per_day:
                            # Day is full, stop and let activities spill to next day
                            logger.info(f"{day_key} is full ({active_time_used:.2f}/{self.max_active_hours_per_day} hours used). "
                                      f"Remaining activities will continue on next day.")
                            break
                        
                        # Add travel time
                        current_time += timedelta(hours=travel_hours)
                        active_time_used += travel_hours
                        
                        # Add sightseeing event with travel details
                        day_events.append({
                            "time": current_time.strftime("%H:%M"),
                            "type": "sight",
                            "name": name,
                            "latitude": lat,
                            "longitude": lng,
                            "travel_time_seconds": travel_info['travel_time_seconds'],
                            "travel_text": travel_info['travel_text'],
                            "duration_text": travel_info.get('duration_text', travel_info['travel_text']),
                            "transit_line": travel_info.get('transit_line'),
                            "travel_mode": travel_info['mode']
                        })
                        
                        # Update location and track place_id
                        current_lat = lat
                        current_lng = lng
                        if place_id:
                            visited_place_ids.add(place_id)
                        
                        # Remove from unvisited/deferred
                        if nearest in unvisited:
                            unvisited.remove(nearest)
                        if nearest in deferred_items:
                            deferred_items.remove(nearest)
                        
                        # Add activity duration
                        current_time += timedelta(hours=self.sightseeing_duration)
                        active_time_used += self.sightseeing_duration
                        last_activity_end_time = current_time  # Update last activity end time
                    else:
                        # If travel time couldn't be calculated, skip this item
                        logger.warning(f"Could not calculate travel time to {name}, skipping")
                        if nearest in unvisited:
                            unvisited.remove(nearest)
                        if nearest in deferred_items:
                            deferred_items.remove(nearest)
                else:
                    break
            
            # TASK 3: Discovery Mode - If wishlist exhausted or day is empty, find nearby attractions
            # This runs AFTER the main loop, so it works even when unvisited is empty
            # Count real activities (excluding arrival event)
            real_activities = [e for e in day_events if e.get('type') in ['sight', 'meal']]
            
            if (not unvisited and not deferred_items) or len(real_activities) == 0:
                # Day is empty or wishlist exhausted, use discovery mode
                logger.info(f"{day_key}: Entering Discovery Mode (wishlist exhausted or day empty)...")
                
                # Morning: Search near cluster center (or hotel if no cluster)
                discovery_center_lat = cluster_center_lat
                discovery_center_lng = cluster_center_lng
                
                # Limit to 3 attractions per day; rotate through interests by day; sort by transit from current location
                attractions = self.discover_attractions(
                    discovery_center_lat, discovery_center_lng,
                    radius_km=5.0, limit=3, visited_place_ids=visited_place_ids,
                    rotation_index=day_num - 1,
                    sort_by_transit_from=(current_lat, current_lng),
                    departure_time=current_time
                )
                
                for attraction in attractions:
                    if active_time_used >= self.max_active_hours_per_day or current_time >= day_end_time:
                        break
                    
                    att_lat = attraction['latitude']
                    att_lng = attraction['longitude']
                    att_name = attraction['name']
                    att_place_id = attraction.get('place_id')
                    
                    # Check opening hours
                    visit_time = current_time + timedelta(hours=self.sightseeing_duration)
                    if att_place_id:
                        is_open = self.is_place_open(att_place_id, visit_time)
                        if not is_open:
                            logger.debug(f"Skipping {att_name} - closed at {visit_time.strftime('%H:%M')}")
                            continue
                    
                    # Get travel time
                    travel_info = self.get_travel_time(current_lat, current_lng, att_lat, att_lng,
                                                      departure_time=current_time)
                    
                    if travel_info:
                        travel_hours = travel_info['travel_time_hours']
                        total_time_needed = travel_hours + self.sightseeing_duration
                        
                        if active_time_used + total_time_needed > self.max_active_hours_per_day:
                            break
                        if current_time + timedelta(hours=total_time_needed) > day_end_time:
                            break
                        
                        current_time += timedelta(hours=travel_hours)
                        active_time_used += travel_hours
                        
                        day_events.append({
                            "time": current_time.strftime("%H:%M"),
                            "type": "sight",
                            "name": att_name,
                            "latitude": att_lat,
                            "longitude": att_lng,
                            "travel_time_seconds": travel_info['travel_time_seconds'],
                            "travel_text": travel_info['travel_text'],
                            "duration_text": travel_info.get('duration_text', travel_info['travel_text']),
                            "transit_line": travel_info.get('transit_line'),
                            "travel_mode": travel_info['mode'],
                            "is_recommendation": True  # TASK 3: Mark as recommendation
                        })
                        
                        current_lat = att_lat
                        current_lng = att_lng
                        if att_place_id:
                            visited_place_ids.add(att_place_id)
                        
                        current_time += timedelta(hours=self.sightseeing_duration)
                        active_time_used += self.sightseeing_duration
                        last_activity_end_time = current_time
                        
                        logger.info(f"Added discovered attraction: {att_name} at {current_time.strftime('%H:%M')}")
            
            # TASK 2: Gap Filler Loop - Ensure each day has at least 6 hours of content
            active_hours = self.calculate_active_hours(day_events)
            logger.info(f"{day_key}: Current active hours: {active_hours:.2f}")
            
            max_gap_fill_iterations = 10  # Prevent infinite loops
            iteration = 0
            
            while active_hours < 6.0 and iteration < max_gap_fill_iterations:
                iteration += 1
                logger.info(f"{day_key}: Gap filling iteration {iteration} (active_hours: {active_hours:.2f} < 6.0)")
                
                # Get last location
                last_lat, last_lng = self.get_last_location(day_events)
                
                # Get recommendations near last location; sort by transit time from current location
                new_places = self.get_recommendations(
                    last_lat, last_lng, visited_place_ids, rotation_index=day_num - 1 + iteration,
                    sort_by_transit_from=(last_lat, last_lng), departure_time=current_time
                )
                
                if not new_places:
                    logger.info(f"{day_key}: No more recommendations found nearby, stopping gap fill")
                    break
                
                # Pick the best one (first in list, already sorted by prominence)
                best_place = new_places[0]
                att_lat = best_place['latitude']
                att_lng = best_place['longitude']
                att_name = best_place['name']
                att_place_id = best_place['place_id']
                
                # Check opening hours
                visit_time = current_time + timedelta(hours=self.sightseeing_duration)
                if att_place_id:
                    is_open = self.is_place_open(att_place_id, visit_time)
                    if not is_open:
                        logger.debug(f"Skipping {att_name} - closed at {visit_time.strftime('%H:%M')}")
                        visited_place_ids.add(att_place_id)  # Mark as visited to skip next time
                        continue
                
                # Get travel time
                travel_info = self.get_travel_time(
                    last_lat, last_lng, att_lat, att_lng,
                    departure_time=current_time
                )
                
                if not travel_info:
                    logger.warning(f"Could not calculate travel time to {att_name}")
                    visited_place_ids.add(att_place_id)
                    continue
                
                travel_hours = travel_info['travel_time_hours']
                total_time_needed = travel_hours + self.sightseeing_duration
                
                # Check if it fits
                if active_time_used + total_time_needed > self.max_active_hours_per_day:
                    logger.info(f"{day_key}: Cannot add more activities (would exceed max hours)")
                    break
                
                if current_time + timedelta(hours=total_time_needed) > day_end_time:
                    logger.info(f"{day_key}: Cannot add more activities (would exceed day end time)")
                    break
                
                # Add travel time
                current_time += timedelta(hours=travel_hours)
                active_time_used += travel_hours
                
                # Add event to day
                day_events.append({
                    "time": current_time.strftime("%H:%M"),
                    "type": "sight",
                    "name": att_name,
                    "latitude": att_lat,
                    "longitude": att_lng,
                    "travel_time_seconds": travel_info['travel_time_seconds'],
                    "travel_text": travel_info['travel_text'],
                    "duration_text": travel_info.get('duration_text', travel_info['travel_text']),
                    "transit_line": travel_info.get('transit_line'),
                    "travel_mode": travel_info['mode'],
                    "is_recommendation": True,  # TASK 3: Mark as recommendation
                    "rating": best_place.get('rating'),
                    "user_ratings_total": best_place.get('user_ratings_total')
                })
                
                # Update location and tracking
                current_lat = att_lat
                current_lng = att_lng
                visited_place_ids.add(att_place_id)
                
                # Add activity duration
                current_time += timedelta(hours=self.sightseeing_duration)
                active_time_used += self.sightseeing_duration
                last_activity_end_time = current_time
                
                # Recalculate active hours
                active_hours = self.calculate_active_hours(day_events)
                
                logger.info(f"Added recommendation: {att_name} (rating: {best_place.get('rating')}, {best_place.get('user_ratings_total')} reviews) at {current_time.strftime('%H:%M')}. New active hours: {active_hours:.2f}")
            
            if active_hours >= 6.0:
                logger.info(f"{day_key}: Gap fill complete! Active hours: {active_hours:.2f}")
            else:
                logger.info(f"{day_key}: Gap fill stopped. Final active hours: {active_hours:.2f}")
            
            # TASK 2: Dinner Guarantee - Check if last activity ended after 18:00
            # This should ALWAYS run at the end of each day, regardless of whether activities were scheduled
            if not dinner_scheduled:
                # Use last_activity_end_time if we have activities, otherwise use current_time
                check_time = last_activity_end_time if last_activity_end_time > current_time else current_time
                
                # If we have no activities, start from a reasonable dinner time
                if len(day_events) == 0 or (day_num == 1 and len(day_events) == 1 and day_events[0].get('type') == 'arrival'):
                    # No real activities yet, set check_time to dinner start time
                    check_time = check_time.replace(hour=self.dinner_start, minute=0, second=0)
                
                if check_time.hour >= self.dinner_start:
                    logger.info(f"{day_key}: Ensuring dinner is scheduled (check_time: {check_time.strftime('%H:%M')})")
                    
                    # Find restaurant near last location (or hotel if very late or no activities)
                    search_lat = current_lat if len(day_events) > 0 else self.hotel_lat
                    search_lng = current_lng if len(day_events) > 0 else self.hotel_lng
                    
                    if check_time.hour >= 20 or len(day_events) == 0:
                        # Very late or no activities, prefer restaurant near hotel
                        search_lat = self.hotel_lat
                        search_lng = self.hotel_lng
                    
                    restaurant = self.find_nearest_restaurant(
                        search_lat, search_lng, "dinner",
                        min_rating=3.5,
                        exclude_name=last_restaurant_name,
                        departure_time=check_time
                    )
                    
                    if restaurant:
                        travel_info = self.get_travel_time(
                            search_lat, search_lng,
                            restaurant['latitude'], restaurant['longitude'],
                            departure_time=check_time
                        )
                        if travel_info:
                            travel_hours = travel_info['travel_time_seconds'] / 3600.0
                            dinner_time = check_time + timedelta(seconds=travel_info['travel_time_seconds'])
                            
                            # Only add if it fits within day constraints
                            if dinner_time <= day_end_time:
                                day_events.append({
                                    "time": dinner_time.strftime("%H:%M"),
                                    "type": "meal",
                                    "name": restaurant['name'],
                                    "tabelog_score": restaurant['tabelog_rating'],
                                    "genre": restaurant.get('genre'),
                                    "district": restaurant.get('district'),
                                    "latitude": restaurant['latitude'],
                                    "longitude": restaurant['longitude'],
                                    "travel_time_seconds": travel_info['travel_time_seconds'],
                                    "travel_text": travel_info['travel_text'],
                                    "duration_text": travel_info.get('duration_text', travel_info['travel_text']),
                                    "transit_line": travel_info.get('transit_line'),
                                    "travel_mode": travel_info['mode']
                                })
                                dinner_scheduled = True
                                logger.info(f"Added dinner guarantee: {restaurant['name']} at {dinner_time.strftime('%H:%M')}")
                            else:
                                logger.warning(f"Cannot fit dinner guarantee within day constraints (dinner_time: {dinner_time.strftime('%H:%M')}, day_end: {day_end_time.strftime('%H:%M')})")
                        else:
                            logger.warning(f"Could not calculate travel time to restaurant for dinner guarantee")
                    else:
                        logger.warning(f"Could not find restaurant for dinner guarantee")
                else:
                    logger.debug(f"{day_key}: No dinner needed (check_time: {check_time.strftime('%H:%M')} < {self.dinner_start}:00)")
            
            # TASK 3: On final day, add airport routing if departure_flight_time is set
            if day_num == self.num_days and airport_stop_time and airport_lat and airport_lng:
                # Calculate travel time from last location (or hotel) to airport
                last_location_lat = current_lat
                last_location_lng = current_lng
                
                # Ensure we have enough time to get to airport
                if current_time < airport_stop_time:
                    airport_travel_info = self.get_travel_time(
                        last_location_lat, last_location_lng,
                        airport_lat, airport_lng,
                        mode='transit',
                        departure_time=current_time
                    )
                    
                    if airport_travel_info:
                        airport_arrival_time = current_time + timedelta(seconds=airport_travel_info['travel_time_seconds'])
                        
                        # Only add if we can make it to airport on time
                        if airport_arrival_time <= airport_stop_time:
                            day_events.append({
                                "time": current_time.strftime("%H:%M"),
                                "type": "transport",
                                "name": "Travel to Airport",
                                "latitude": airport_lat,
                                "longitude": airport_lng,
                                "travel_time_seconds": airport_travel_info['travel_time_seconds'],
                                "travel_text": airport_travel_info['travel_text'],
                                "duration_text": airport_travel_info.get('duration_text', airport_travel_info['travel_text']),
                                "transit_line": airport_travel_info.get('transit_line'),
                                "travel_mode": airport_travel_info['mode']
                            })
                            logger.info(f"Added airport routing: {airport_travel_info['travel_text']}")
                        else:
                            logger.warning(f"Cannot reach airport on time. Need to leave earlier.")
            
            itinerary[day_key] = day_events
            logger.info(f"{day_key}: {len(day_events)} events scheduled, "
                       f"{active_time_used:.2f}/{self.max_active_hours_per_day} hours used")
        
        # Summary
        total_events = sum(len(events) for events in itinerary.values())
        visited = len(self.wishlist) - len(unvisited)
        logger.info(f"\nItinerary complete: {total_events} total events, {visited}/{len(self.wishlist)} wishlist items visited")
        
        return itinerary


def generate_itinerary_json(hotel_lat: float, hotel_lng: float, arrival_datetime: datetime,
                            num_days: int, wishlist: List[str], tabelog_db: str) -> str:
    """
    Convenience function to generate itinerary and return as JSON string.
    
    Args:
        hotel_lat: Hotel latitude
        hotel_lng: Hotel longitude
        arrival_datetime: When the trip starts
        num_days: Number of days
        wishlist: List of place names
        tabelog_db: Path to database
        
    Returns:
        JSON string of itinerary
    """
    engine = ItineraryEngine(hotel_lat, hotel_lng, arrival_datetime, num_days, wishlist, tabelog_db)
    itinerary = engine.generate_itinerary()
    return json.dumps(itinerary, indent=2, ensure_ascii=False)

