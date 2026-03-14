"""
Tabelog Restaurant Scraper for Japan Trip Planner
Robust, fault-tolerant scraper with heavy throttling to avoid IP bans.
"""

import sqlite3
import time
import random
import re
import logging
from typing import Optional, Dict, List
import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Database file name
DB_NAME = 'tabelog_japan.db'

# Fallback User-Agent list if fake_useragent fails
FALLBACK_USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15'
]


def init_database():
    """
    Initialize SQLite database and create restaurants table if it doesn't exist.
    Also handles migration to add district column if table exists without it.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Create table if it doesn't exist
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS restaurants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            tabelog_rating REAL,
            review_count INTEGER,
            area TEXT,
            district TEXT,
            genre TEXT,
            url TEXT UNIQUE,
            budget_dinner TEXT,
            budget_lunch TEXT
        )
    ''')
    
    # Check if district column exists, if not add it (migration for existing databases)
    cursor.execute("PRAGMA table_info(restaurants)")
    columns = [column[1] for column in cursor.fetchall()]
    
    if 'district' not in columns:
        logger.info("Adding 'district' column to existing database...")
        cursor.execute('ALTER TABLE restaurants ADD COLUMN district TEXT')
        conn.commit()
        logger.info("Migration complete: 'district' column added")
    
    # Add index for faster queries by district and rating
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_district_rating 
        ON restaurants(district, tabelog_rating DESC)
    ''')
    
    conn.commit()
    conn.close()
    logger.info(f"Database '{DB_NAME}' initialized successfully")


def get_random_header() -> Dict[str, str]:
    """
    Returns a dictionary with a random User-Agent header.
    Falls back to hardcoded list if fake_useragent fails.
    """
    try:
        ua = UserAgent()
        user_agent = ua.random
    except Exception as e:
        logger.warning(f"Failed to get random User-Agent from fake_useragent: {e}. Using fallback.")
        user_agent = random.choice(FALLBACK_USER_AGENTS)
    
    return {
        'User-Agent': user_agent,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }


def clean_rating(text: Optional[str]) -> Optional[float]:
    """
    Robustly converts string rating (e.g., "3.55") to float.
    Handles various formats and edge cases.
    
    Args:
        text: String containing rating value
        
    Returns:
        Float rating or None if conversion fails
    """
    if not text:
        return None
    
    try:
        # Remove whitespace and extract numeric value
        cleaned = re.sub(r'[^\d.]', '', str(text).strip())
        if cleaned:
            rating = float(cleaned)
            # Tabelog ratings are typically 0-5, validate range
            if 0 <= rating <= 5:
                return rating
            else:
                logger.warning(f"Rating {rating} out of expected range (0-5)")
                return None
        return None
    except (ValueError, AttributeError) as e:
        logger.warning(f"Failed to convert rating '{text}' to float: {e}")
        return None


def extract_review_count(text: Optional[str]) -> Optional[int]:
    """
    Extract review count from text (e.g., "1,234 reviews" -> 1234).
    """
    if not text:
        return None
    
    try:
        # Remove commas and extract numbers
        numbers = re.findall(r'\d+', str(text).replace(',', ''))
        if numbers:
            return int(''.join(numbers))
        return None
    except (ValueError, AttributeError) as e:
        logger.warning(f"Failed to extract review count from '{text}': {e}")
        return None


def extract_budget(text: Optional[str]) -> Optional[str]:
    """
    Extract budget information from text.
    """
    if not text:
        return None
    return str(text).strip()


def identify_district(area_text: Optional[str]) -> Optional[str]:
    """
    Identify Tokyo district from area text.
    Common Tokyo districts/wards for travel planning.
    """
    if not area_text:
        return None
    
    area_lower = area_text.lower()
    
    # Popular Tokyo districts/areas for tourists
    TOKYO_DISTRICTS = {
        'shibuya': 'Shibuya',
        'ginza': 'Ginza',
        'shinjuku': 'Shinjuku',
        'roppongi': 'Roppongi',
        'harajuku': 'Harajuku',
        'akihabara': 'Akihabara',
        'ueno': 'Ueno',
        'asakusa': 'Asakusa',
        'ikebukuro': 'Ikebukuro',
        'ebisu': 'Ebisu',
        'omotesando': 'Omotesando',
        'aoyama': 'Aoyama',
        'tsukiji': 'Tsukiji',
        'marunouchi': 'Marunouchi',
        'odaiba': 'Odaiba',
        'kanda': 'Kanda',
        'nishi-azabu': 'Nishi-Azabu',
        'hiroo': 'Hiroo',
        'meguro': 'Meguro',
        'nakameguro': 'Nakameguro'
    }
    
    # Check for exact matches or partial matches
    for key, district in TOKYO_DISTRICTS.items():
        if key in area_lower or district.lower() in area_lower:
            return district
    
    return None


def scrape_restaurant_page(soup: BeautifulSoup, base_url: str = "https://tabelog.com") -> Optional[Dict]:
    """
    Extract restaurant data from a single restaurant listing element.
    
    Note: CSS selectors may change if Tabelog updates their HTML structure.
    If ratings come back as 0.0 or None, inspect the live HTML to find new selectors.
    
    Args:
        soup: BeautifulSoup object of a restaurant listing element
        base_url: Base URL for constructing absolute URLs
        
    Returns:
        Dictionary with restaurant data or None if extraction fails
    """
    restaurant_data = {}
    
    try:
        # Restaurant name
        # Selector might be: .list-rst__rst-name-target, .list-rst__name, or similar
        name_elem = soup.select_one('.list-rst__rst-name-target, .list-rst__name, a[class*="rst-name"]')
        if name_elem:
            restaurant_data['name'] = name_elem.get_text(strip=True)
            # Extract URL from name link
            href = name_elem.get('href', '')
            if href:
                restaurant_data['url'] = base_url + href if href.startswith('/') else href
        else:
            logger.warning("Could not find restaurant name element")
            return None
        
        # Rating - CRITICAL: This selector is most likely to change
        # Common selectors: .list-rst__rating-val, .c-rating__val, .rating-val
        rating_elem = soup.select_one('.list-rst__rating-val, .c-rating__val, .rating-val, [class*="rating"]')
        if rating_elem:
            rating_text = rating_elem.get_text(strip=True)
            restaurant_data['tabelog_rating'] = clean_rating(rating_text)
        else:
            logger.warning(f"Could not find rating element for {restaurant_data.get('name', 'unknown')}")
            restaurant_data['tabelog_rating'] = None
        
        # Review count
        # Selector might be: .list-rst__rvw-count, .c-rating__review, or similar
        review_elem = soup.select_one('.list-rst__rvw-count, .c-rating__review, [class*="review"]')
        if review_elem:
            review_text = review_elem.get_text(strip=True)
            restaurant_data['review_count'] = extract_review_count(review_text)
        else:
            restaurant_data['review_count'] = None
        
        # Area and Genre
        # Selector might be: .list-rst__area-genre, .list-rst__area, .list-rst__genre
        area_genre_elem = soup.select_one('.list-rst__area-genre, .list-rst__area, [class*="area-genre"]')
        if area_genre_elem:
            area_genre_text = area_genre_elem.get_text(strip=True)
            # Try to split area and genre (format varies)
            parts = [p.strip() for p in area_genre_text.split('/')]
            if len(parts) >= 1:
                restaurant_data['area'] = parts[0]
            if len(parts) >= 2:
                restaurant_data['genre'] = parts[1]
            else:
                restaurant_data['area'] = area_genre_text
                restaurant_data['genre'] = None
        else:
            restaurant_data['area'] = None
            restaurant_data['genre'] = None
        
        # Identify district from area text
        restaurant_data['district'] = identify_district(restaurant_data.get('area'))
        
        # Budget - Dinner and Lunch
        # Selectors might be: .list-rst__budget, .c-rating__budget, or similar
        budget_elem = soup.select_one('.list-rst__budget, .c-rating__budget, [class*="budget"]')
        if budget_elem:
            budget_text = budget_elem.get_text(strip=True)
            # Try to parse dinner/lunch from text (format varies)
            if 'Dinner' in budget_text or 'ディナー' in budget_text:
                restaurant_data['budget_dinner'] = extract_budget(budget_text)
            else:
                restaurant_data['budget_dinner'] = None
            restaurant_data['budget_lunch'] = None  # May need separate selector
        else:
            restaurant_data['budget_dinner'] = None
            restaurant_data['budget_lunch'] = None
        
        return restaurant_data
        
    except Exception as e:
        logger.error(f"Error extracting restaurant data: {e}")
        return None


def scrape_tabelog(keyword: str, max_pages: int = 3, area: str = "tokyo"):
    """
    Main scraping function for Tabelog restaurant listings.
    
    Args:
        keyword: Search keyword (e.g., "Sushi", "Ramen")
        max_pages: Maximum number of pages to scrape (default: 3)
        area: Area code (default: "tokyo")
    """
    init_database()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    base_url = f"https://tabelog.com/en/{area}/rstLst/"
    scraped_count = 0
    
    try:
        for page in range(1, max_pages + 1):
            logger.info(f"Scraping page {page} for keyword '{keyword}'...")
            
            # Construct URL with search parameters
            # Tabelog URL format may vary - adjust as needed
            if page == 1:
                url = f"{base_url}?sa=&sk={keyword}"
            else:
                url = f"{base_url}{page}/?sa=&sk={keyword}"
            
            try:
                # Get random headers for this request
                headers = get_random_header()
                
                # Make request with timeout
                response = requests.get(url, headers=headers, timeout=15)
                response.raise_for_status()
                
                # Parse HTML
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Find restaurant containers - use more specific selectors
                # Try specific selectors first to avoid matching nested elements
                restaurant_containers = soup.select('li.list-rst, div.list-rst')
                
                if not restaurant_containers:
                    # Try alternative: look for list items with restaurant class
                    restaurant_containers = soup.find_all('li', class_=lambda x: x and 'list-rst' in str(x))
                
                if not restaurant_containers:
                    logger.warning(f"No restaurant containers found on page {page}. Selectors may have changed.")
                    # Last resort: find by link pattern (restaurant URLs)
                    all_links = soup.find_all('a', href=re.compile(r'/tokyo/[A-Z0-9]+/'))
                    # Get unique parent containers
                    seen_containers = set()
                    restaurant_containers = []
                    for link in all_links:
                        parent = link.find_parent(['li', 'div'], class_=lambda x: x and 'rst' in str(x).lower())
                        if parent and id(parent) not in seen_containers:
                            seen_containers.add(id(parent))
                            restaurant_containers.append(parent)
                
                if not restaurant_containers:
                    logger.warning(f"Still no restaurants found on page {page}. Skipping page.")
                    continue
                
                logger.info(f"Found {len(restaurant_containers)} restaurant listings on page {page}")
                
                # Extract data from each restaurant
                for container in restaurant_containers:
                    try:
                        restaurant_data = scrape_restaurant_page(container, base_url="https://tabelog.com")
                        
                        if restaurant_data and restaurant_data.get('name'):
                            # Insert into database (INSERT OR IGNORE to avoid duplicates)
                            cursor.execute('''
                                INSERT OR IGNORE INTO restaurants 
                                (name, tabelog_rating, review_count, area, district, genre, url, budget_dinner, budget_lunch)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (
                                restaurant_data.get('name'),
                                restaurant_data.get('tabelog_rating'),
                                restaurant_data.get('review_count'),
                                restaurant_data.get('area'),
                                restaurant_data.get('district'),
                                restaurant_data.get('genre'),
                                restaurant_data.get('url'),
                                restaurant_data.get('budget_dinner'),
                                restaurant_data.get('budget_lunch')
                            ))
                            
                            if cursor.rowcount > 0:
                                scraped_count += 1
                                logger.info(f"Saved: {restaurant_data.get('name')} (Rating: {restaurant_data.get('tabelog_rating')})")
                            else:
                                logger.debug(f"Duplicate skipped: {restaurant_data.get('name')}")
                        
                    except Exception as e:
                        logger.error(f"Error processing restaurant container: {e}")
                        continue
                
                conn.commit()
                
                # Heavy throttling: 3-7 seconds delay between pages
                if page < max_pages:
                    delay = random.uniform(3, 7)
                    logger.info(f"Waiting {delay:.2f} seconds before next page...")
                    time.sleep(delay)
                
            except requests.RequestException as e:
                logger.error(f"Network error on page {page}: {e}")
                continue
            except Exception as e:
                logger.error(f"Unexpected error on page {page}: {e}")
                continue
        
        logger.info(f"Scraping completed. Total restaurants saved: {scraped_count}")
        
    finally:
        conn.close()


def filter_top_by_district(max_per_district: int = 50):
    """
    Filter restaurants to keep only top N per district based on rating.
    This function removes restaurants beyond the top N for each district.
    
    Args:
        max_per_district: Maximum restaurants to keep per district (default: 50)
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    try:
        # Get all districts
        cursor.execute('SELECT DISTINCT district FROM restaurants WHERE district IS NOT NULL')
        districts = [row[0] for row in cursor.fetchall()]
        
        logger.info(f"Filtering restaurants for {len(districts)} districts...")
        
        total_removed = 0
        for district in districts:
            # Get all restaurants for this district, ordered by rating
            # SQLite doesn't support NULLS LAST, so we use COALESCE to put NULLs at end
            cursor.execute('''
                SELECT id FROM restaurants 
                WHERE district = ? 
                ORDER BY COALESCE(tabelog_rating, 0) DESC, 
                         COALESCE(review_count, 0) DESC
            ''', (district,))
            
            all_ids = [row[0] for row in cursor.fetchall()]
            
            if len(all_ids) > max_per_district:
                # Keep top N, delete the rest
                ids_to_keep = all_ids[:max_per_district]
                ids_to_remove = all_ids[max_per_district:]
                
                placeholders = ','.join('?' * len(ids_to_remove))
                cursor.execute(f'''
                    DELETE FROM restaurants 
                    WHERE id IN ({placeholders})
                ''', ids_to_remove)
                
                removed = cursor.rowcount
                total_removed += removed
                logger.info(f"District {district}: Kept {len(ids_to_keep)}, Removed {removed} (kept top {max_per_district})")
            else:
                logger.info(f"District {district}: {len(all_ids)} restaurants (under limit, all kept)")
        
        conn.commit()
        logger.info(f"Filtering complete. Total restaurants removed: {total_removed}")
        
    finally:
        conn.close()


def scrape_tokyo_districts(keyword: str = "", max_pages: int = 5, max_per_district: int = 50):
    """
    Scrape restaurants from Tokyo and organize by district.
    Scrapes multiple pages, then filters to top N per district.
    
    Args:
        keyword: Optional search keyword (empty string for all restaurants)
        max_pages: Maximum pages to scrape (default: 5)
        max_per_district: Maximum restaurants to keep per district (default: 50)
    """
    logger.info("="*60)
    logger.info("Starting Tokyo district-based scraping...")
    logger.info("="*60)
    
    # Step 1: Scrape restaurants (using existing working method)
    logger.info(f"Step 1: Scraping {max_pages} pages from Tokyo...")
    scrape_tabelog(keyword=keyword, max_pages=max_pages, area="tokyo")
    
    # Step 2: Filter to top N per district
    logger.info(f"\nStep 2: Filtering to top {max_per_district} restaurants per district...")
    filter_top_by_district(max_per_district=max_per_district)
    
    # Step 3: Show summary
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT district, COUNT(*) as count, 
               AVG(tabelog_rating) as avg_rating,
               MAX(tabelog_rating) as max_rating
        FROM restaurants 
        WHERE district IS NOT NULL
        GROUP BY district
        ORDER BY count DESC
    ''')
    
    results = cursor.fetchall()
    conn.close()
    
    logger.info("\n" + "="*60)
    logger.info("SCRAPING SUMMARY BY DISTRICT")
    logger.info("="*60)
    for district, count, avg_rating, max_rating in results:
        logger.info(f"{district:15} | Count: {count:3} | Avg Rating: {avg_rating:.2f} | Max Rating: {max_rating:.2f}")
    logger.info("="*60)


if __name__ == "__main__":
    # Option 1: Scrape all restaurants and organize by district
    logger.info("Starting Tabelog scraper for Tokyo districts...")
    scrape_tokyo_districts(keyword="", max_pages=5, max_per_district=50)
    logger.info("Scraper finished.")
    
    # Option 2: If you want to scrape by specific keyword, uncomment:
    # scrape_tokyo_districts(keyword="Sushi", max_pages=3, max_per_district=50)

