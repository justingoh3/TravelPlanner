"""
Geocoding script for restaurant data using Google Geocoding API.
Adds latitude, longitude, and geocoding status to the database.
"""

import sqlite3
import time
import logging
import os
from typing import Optional, Tuple
from dotenv import load_dotenv
from geopy.geocoders import GoogleV3
from geopy.exc import GeocoderTimedOut, GeocoderServiceError, GeocoderQuotaExceeded

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Database file name
DB_NAME = 'tabelog_japan.db'

# Google Maps API Key
GOOGLE_API_KEY = os.getenv('MAPS_API_KEY')

if not GOOGLE_API_KEY:
    raise ValueError(
        "MAPS_API_KEY not found in environment variables. "
        "Please create a .env file with your Google Maps API key."
    )


def init_geocoding_columns():
    """
    Initialize database columns for geocoding data.
    Adds latitude, longitude, and geocoding_status columns if they don't exist.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Check existing columns
    cursor.execute("PRAGMA table_info(restaurants)")
    columns = [column[1] for column in cursor.fetchall()]
    
    # Add latitude column if missing
    if 'latitude' not in columns:
        logger.info("Adding 'latitude' column to database...")
        cursor.execute('ALTER TABLE restaurants ADD COLUMN latitude REAL')
    
    # Add longitude column if missing
    if 'longitude' not in columns:
        logger.info("Adding 'longitude' column to database...")
        cursor.execute('ALTER TABLE restaurants ADD COLUMN longitude REAL')
    
    # Add geocoding_status column if missing
    if 'geocoding_status' not in columns:
        logger.info("Adding 'geocoding_status' column to database...")
        cursor.execute('ALTER TABLE restaurants ADD COLUMN geocoding_status TEXT')
    
    # Add index for faster queries
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_geocoding_status 
        ON restaurants(geocoding_status)
    ''')
    
    conn.commit()
    conn.close()
    logger.info("Geocoding columns initialized successfully")


def geocode_restaurant(geocoder: GoogleV3, name: str, area: Optional[str], 
                     district: Optional[str]) -> Tuple[Optional[float], Optional[float], str]:
    """
    Geocode a restaurant using Google Geocoding API.
    
    Args:
        geocoder: GoogleV3 geocoder instance
        name: Restaurant name
        area: Area/neighborhood name
        district: District name (e.g., Shibuya, Ginza)
        
    Returns:
        Tuple of (latitude, longitude, status)
        Status can be: 'SUCCESS', 'AREA_ONLY', 'NEEDS_MANUAL_CHECK'
    """
    # Primary query: "{name}, {area}, Tokyo, Japan"
    if area:
        query = f"{name}, {area}, Tokyo, Japan"
    elif district:
        query = f"{name}, {district}, Tokyo, Japan"
    else:
        query = f"{name}, Tokyo, Japan"
    
    try:
        logger.debug(f"Geocoding: {query}")
        location = geocoder.geocode(query, language='en', timeout=10)
        
        if location:
            logger.info(f"✓ Found: {name} at ({location.latitude:.6f}, {location.longitude:.6f})")
            return location.latitude, location.longitude, 'SUCCESS'
        
        # If restaurant not found, try geocoding just the area/district
        logger.warning(f"Restaurant '{name}' not found, trying area only...")
        
        area_query = None
        if district:
            area_query = f"{district}, Tokyo, Japan"
        elif area:
            area_query = f"{area}, Tokyo, Japan"
        
        if area_query:
            location = geocoder.geocode(area_query, language='en', timeout=10)
            if location:
                logger.info(f"✓ Found area for '{name}': {area_query} at ({location.latitude:.6f}, {location.longitude:.6f})")
                return location.latitude, location.longitude, 'AREA_ONLY'
        
        # If area geocoding also fails, mark for manual check
        logger.warning(f"✗ Could not geocode '{name}' - marking for manual check")
        return None, None, 'NEEDS_MANUAL_CHECK'
        
    except GeocoderTimedOut:
        logger.error(f"Timeout geocoding '{name}' - will retry")
        return None, None, 'RETRY'
    except GeocoderQuotaExceeded:
        logger.error("Google Geocoding API quota exceeded!")
        raise
    except GeocoderServiceError as e:
        logger.error(f"Google Geocoding API error for '{name}': {e}")
        return None, None, 'NEEDS_MANUAL_CHECK'
    except Exception as e:
        logger.error(f"Unexpected error geocoding '{name}': {e}")
        return None, None, 'NEEDS_MANUAL_CHECK'


def geocode_all_restaurants(delay_seconds: float = 0.1, retry_failed: bool = True):
    """
    Geocode all restaurants in the database that don't have coordinates yet.
    
    Args:
        delay_seconds: Delay between API calls to respect rate limits (default: 0.1s)
        retry_failed: Whether to retry restaurants with RETRY status (default: True)
    """
    # Initialize geocoding columns
    init_geocoding_columns()
    
    # Initialize Google Geocoder
    geocoder = GoogleV3(api_key=GOOGLE_API_KEY)
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    try:
        # Get restaurants that need geocoding
        if retry_failed:
            cursor.execute('''
                SELECT id, name, area, district 
                FROM restaurants 
                WHERE latitude IS NULL OR longitude IS NULL 
                   OR geocoding_status IS NULL
                   OR geocoding_status = 'RETRY'
                ORDER BY id
            ''')
        else:
            cursor.execute('''
                SELECT id, name, area, district 
                FROM restaurants 
                WHERE latitude IS NULL OR longitude IS NULL 
                   OR geocoding_status IS NULL
                ORDER BY id
            ''')
        
        restaurants = cursor.fetchall()
        total = len(restaurants)
        
        if total == 0:
            logger.info("All restaurants already geocoded!")
            return
        
        logger.info(f"Found {total} restaurants to geocode...")
        
        success_count = 0
        area_only_count = 0
        failed_count = 0
        retry_count = 0
        
        for idx, (rest_id, name, area, district) in enumerate(restaurants, 1):
            logger.info(f"[{idx}/{total}] Processing: {name}")
            
            try:
                lat, lon, status = geocode_restaurant(geocoder, name, area, district)
                
                # Update database
                cursor.execute('''
                    UPDATE restaurants 
                    SET latitude = ?, longitude = ?, geocoding_status = ?
                    WHERE id = ?
                ''', (lat, lon, status, rest_id))
                
                conn.commit()
                
                # Track statistics
                if status == 'SUCCESS':
                    success_count += 1
                elif status == 'AREA_ONLY':
                    area_only_count += 1
                elif status == 'NEEDS_MANUAL_CHECK':
                    failed_count += 1
                elif status == 'RETRY':
                    retry_count += 1
                
                # Rate limiting - be polite to Google's API
                if idx < total:
                    time.sleep(delay_seconds)
                    
            except GeocoderQuotaExceeded:
                logger.error("API quota exceeded! Stopping geocoding.")
                break
            except Exception as e:
                logger.error(f"Error processing restaurant ID {rest_id}: {e}")
                # Mark as needs manual check
                cursor.execute('''
                    UPDATE restaurants 
                    SET geocoding_status = 'NEEDS_MANUAL_CHECK'
                    WHERE id = ?
                ''', (rest_id,))
                conn.commit()
                failed_count += 1
                continue
        
        # Print summary
        logger.info("\n" + "="*60)
        logger.info("GEOCODING SUMMARY")
        logger.info("="*60)
        logger.info(f"Total processed: {total}")
        logger.info(f"Successfully geocoded: {success_count}")
        logger.info(f"Area-only geocoded: {area_only_count}")
        logger.info(f"Needs manual check: {failed_count}")
        if retry_count > 0:
            logger.info(f"Retry needed: {retry_count}")
        logger.info("="*60)
        
        # Show restaurants that need manual check
        cursor.execute('''
            SELECT name, area, district 
            FROM restaurants 
            WHERE geocoding_status = 'NEEDS_MANUAL_CHECK'
            LIMIT 10
        ''')
        needs_check = cursor.fetchall()
        
        if needs_check:
            logger.info(f"\nSample restaurants needing manual check ({len(needs_check)} shown):")
            for name, area, district in needs_check:
                logger.info(f"  - {name} ({area or district or 'Unknown area'})")
        
    finally:
        conn.close()


def get_geocoding_stats():
    """
    Print statistics about geocoding status.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            SELECT 
                geocoding_status,
                COUNT(*) as count
            FROM restaurants
            GROUP BY geocoding_status
            ORDER BY count DESC
        ''')
        
        results = cursor.fetchall()
        
        print("\n" + "="*60)
        print("GEOCODING STATUS SUMMARY")
        print("="*60)
        
        if results:
            for status, count in results:
                status_display = status if status else 'NOT_STARTED'
                print(f"{status_display:20} : {count:4} restaurants")
        else:
            print("No geocoding data found. Run geocode_data.py first.")
        
        print("="*60)
        
        # Show success rate
        cursor.execute('SELECT COUNT(*) FROM restaurants WHERE latitude IS NOT NULL')
        geocoded = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM restaurants')
        total = cursor.fetchone()[0]
        
        if total > 0:
            success_rate = (geocoded / total) * 100
            print(f"\nGeocoding success rate: {success_rate:.1f}% ({geocoded}/{total})")
        
    finally:
        conn.close()


if __name__ == "__main__":
    logger.info("Starting geocoding process...")
    logger.info(f"Using Google Maps API Key: {GOOGLE_API_KEY[:10]}...")
    
    try:
        # Geocode all restaurants
        geocode_all_restaurants(delay_seconds=0.1, retry_failed=True)
        
        # Show statistics
        get_geocoding_stats()
        
        logger.info("Geocoding process completed!")
        
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        logger.error("Please create a .env file with your MAPS_API_KEY")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise

