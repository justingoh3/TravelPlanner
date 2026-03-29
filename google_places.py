import os
import googlemaps
from dotenv import load_dotenv

load_dotenv()

def get_google_recommendations(location: str, radius: int = 2000, place_type: str = "restaurant", min_rating: float = 4.0):
    """
    Fetches recommended places from Google Places API based on minimum rating.
    """
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        raise ValueError("Missing GOOGLE_MAPS_API_KEY environment variable.")

    gmaps = googlemaps.Client(key=api_key)
    
    # First, geocode the location to get lat/lng
    geocode_result = gmaps.geocode(location)
    if not geocode_result:
        return []
        
    lat_lng = geocode_result[0]['geometry']['location']
    
    # Search for places nearby
    places_result = gmaps.places_nearby(
        location=lat_lng,
        radius=radius,
        type=place_type
    )
    
    recommendations = []
    
    for place in places_result.get('results', []):
        rating = place.get('rating', 0)
        user_ratings_total = place.get('user_ratings_total', 0)
        
        # Only recommend places that meet the minimum rating and have a decent number of reviews
        if rating >= min_rating and user_ratings_total > 10:
            
            # Fetch deeper details (including up to 5 reviews)
            place_id = place['place_id']
            details = gmaps.place(place_id, fields=["name", "rating", "formatted_phone_number", "website", "reviews", "url"])
            
            recommendations.append({
                "name": details['result'].get('name'),
                "rating": details['result'].get('rating'),
                "total_reviews": user_ratings_total,
                "url": details['result'].get('url'),
                "reviews": [rev.get("text") for rev in details['result'].get('reviews', [])][:3] # top 3 reviews
            })
            
    # Sort by highest rating first
    recommendations.sort(key=lambda x: x['rating'], reverse=True)
    return recommendations

if __name__ == "__main__":
    recs = get_google_recommendations("Shibuya, Tokyo", min_rating=4.5)
    for r in recs:
        print(f"{r['name']} - {r['rating']} stars ({r['total_reviews']} reviews)")
        print(f"URL: {r['url']}")
        print("Top Review:", r['reviews'][0] if r['reviews'] else "No text review")
        print("-" * 40)
