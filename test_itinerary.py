"""
Test script for the Itinerary Engine.
Tests a 3-day trip in Tokyo with sample wishlist items.
"""

import json
from datetime import datetime
from itinerary_engine import ItineraryEngine, generate_itinerary_json

# Tokyo hotel coordinates (example: Shibuya area)
HOTEL_LAT = 35.6580
HOTEL_LNG = 139.7016

# Arrival time
ARRIVAL_DATETIME = datetime(2024, 3, 15, 14, 0)  # March 15, 2024 at 2:00 PM

# Number of days
NUM_DAYS = 3

# Sample wishlist - popular Tokyo attractions
WISHLIST = [
    "Senso-ji Temple",
    "Tokyo Skytree",
    "Shibuya Crossing",
    "Meiji Shrine",
    "Tsukiji Outer Market",
    "Tokyo Tower",
    "Ueno Park",
    "Harajuku",
    "Ginza"
]

# Database path
DB_PATH = "tabelog_japan.db"


def test_itinerary_engine():
    """
    Test the itinerary engine with a 3-day Tokyo trip.
    """
    print("="*70)
    print("TOKYO TRIP ITINERARY GENERATOR - TEST")
    print("="*70)
    print(f"\nHotel Location: Shibuya ({HOTEL_LAT}, {HOTEL_LNG})")
    print(f"Arrival: {ARRIVAL_DATETIME.strftime('%Y-%m-%d %H:%M')}")
    print(f"Duration: {NUM_DAYS} days")
    print(f"Wishlist: {len(WISHLIST)} places")
    print("\n" + "-"*70)
    
    # Create engine
    engine = ItineraryEngine(
        hotel_lat=HOTEL_LAT,
        hotel_lng=HOTEL_LNG,
        arrival_datetime=ARRIVAL_DATETIME,
        num_days=NUM_DAYS,
        wishlist=WISHLIST,
        tabelog_db=DB_PATH
    )
    
    # Generate itinerary
    print("\nGenerating itinerary...\n")
    itinerary = engine.generate_itinerary()
    
    # Display results
    print("\n" + "="*70)
    print("GENERATED ITINERARY")
    print("="*70)
    
    if not itinerary:
        print("ERROR: No itinerary generated!")
        return
    
    # Print formatted itinerary
    for day, events in itinerary.items():
        print(f"\n{day}:")
        print("-" * 70)
        for event in events:
            time_str = event.get('time', 'N/A')
            event_type = event.get('type', 'unknown')
            name = event.get('name', 'N/A')
            
            if event_type == 'arrival':
                print(f"  {time_str} - ✈️  Arrival")
            elif event_type == 'sight':
                print(f"  {time_str} - 🗼 {name}")
            elif event_type == 'meal':
                rating = event.get('tabelog_score')
                rating_str = f" (Rating: {rating:.1f})" if rating else ""
                genre = event.get('genre', '')
                genre_str = f" - {genre}" if genre else ""
                print(f"  {time_str} - 🍽️  {name}{rating_str}{genre_str}")
    
    # Save to JSON file
    output_file = "itinerary_output.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(itinerary, f, indent=2, ensure_ascii=False)
    
    print(f"\n" + "="*70)
    print(f"Itinerary saved to: {output_file}")
    print("="*70)
    
    # Statistics
    total_events = sum(len(events) for events in itinerary.values())
    total_meals = sum(1 for events in itinerary.values() 
                     for event in events if event.get('type') == 'meal')
    total_sights = sum(1 for events in itinerary.values() 
                      for event in events if event.get('type') == 'sight')
    
    print(f"\nStatistics:")
    print(f"  Total events: {total_events}")
    print(f"  Meals scheduled: {total_meals}")
    print(f"  Sights visited: {total_sights}")
    print(f"  Wishlist items covered: {total_sights}/{len(WISHLIST)}")
    print()


def test_json_output():
    """
    Test the JSON output function.
    """
    print("\n" + "="*70)
    print("TESTING JSON OUTPUT")
    print("="*70)
    
    json_output = generate_itinerary_json(
        hotel_lat=HOTEL_LAT,
        hotel_lng=HOTEL_LNG,
        arrival_datetime=ARRIVAL_DATETIME,
        num_days=2,  # Shorter test
        wishlist=["Senso-ji Temple", "Tokyo Skytree"],
        tabelog_db=DB_PATH
    )
    
    print(json_output)


if __name__ == "__main__":
    try:
        # Run main test
        test_itinerary_engine()
        
        # Optional: Test JSON output
        # test_json_output()
        
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()

