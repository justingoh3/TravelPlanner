# Testing Guide for Tabelog Scraper

## Step 1: Install Dependencies

First, make sure you have Python 3.7+ installed. Then install the required packages:

```bash
pip install -r requirements.txt
```
`
Or install individually:
```bash
pip install requests beautifulsoup4 fake-useragent pandas
```

## Step 2: Run the Scraper

Run the main scraper script:

```bash
python scraper.py
```

**What to expect:**
- The script will create `tabelog_japan.db` automatically
- You'll see log messages showing progress
- It will scrape 2 pages of "Sushi" restaurants in Tokyo
- Between pages, it waits 3-7 seconds (to be polite)
- Total time: ~10-20 seconds for 2 pages

**Expected output:**
```
2024-01-XX XX:XX:XX - INFO - Database 'tabelog_japan.db' initialized successfully
2024-01-XX XX:XX:XX - INFO - Starting Tabelog scraper...
2024-01-XX XX:XX:XX - INFO - Scraping page 1 for keyword 'Sushi'...
2024-01-XX XX:XX:XX - INFO - Found X restaurant listings on page 1
2024-01-XX XX:XX:XX - INFO - Saved: Restaurant Name (Rating: 4.25)
...
```

## Step 3: Verify the Data

After scraping, check what was collected:

```bash
python verify_data.py
```

**Expected output:**
```
====================================================================================================
TOP 10 RESTAURANTS BY TABELOG RATING
====================================================================================================
   id                    name  tabelog_rating  review_count  area  genre  ...
   1         Some Sushi Place            4.85           234  Shibuya  Sushi  ...
   2      Another Restaurant            4.72           189  Ginza    Sushi  ...
...
```

## Step 4: Check the Database Directly (Optional)

You can also inspect the database using SQLite:

```bash
sqlite3 tabelog_japan.db
```

Then run SQL queries:
```sql
-- Count total restaurants
SELECT COUNT(*) FROM restaurants;

-- See all columns
SELECT * FROM restaurants LIMIT 5;

-- Find restaurants with ratings above 4.0
SELECT name, tabelog_rating, area FROM restaurants 
WHERE tabelog_rating > 4.0 
ORDER BY tabelog_rating DESC;

-- Exit
.quit
```

## Troubleshooting

### Issue: "No restaurants found" or ratings are 0.0/None

**Cause:** CSS selectors may have changed on Tabelog's website.

**Solution:**
1. Open https://tabelog.com/en/tokyo/rstLst/?sa=&sk=Sushi in your browser
2. Right-click on a restaurant name → Inspect Element
3. Look for the class names used for:
   - Restaurant container
   - Restaurant name
   - Rating value
4. Update the selectors in `scraper.py` in the `scrape_restaurant_page()` function

### Issue: Connection errors or timeouts

**Cause:** Network issues or Tabelog blocking requests.

**Solution:**
- Increase the delay between requests (currently 3-7 seconds)
- Check your internet connection
- Try running again later (may be temporary rate limiting)

### Issue: "Module not found" errors

**Solution:**
```bash
pip install --upgrade requests beautifulsoup4 fake-useragent pandas
```

### Issue: Database locked errors

**Solution:**
- Make sure no other process is using the database
- Close any SQLite viewers
- The script should handle this automatically, but if it persists, delete `tabelog_japan.db` and run again

## Testing with Different Keywords

You can modify the scraper to test different keywords. Edit the bottom of `scraper.py`:

```python
if __name__ == "__main__":
    # Test with different keywords
    scrape_tabelog(keyword="Ramen", max_pages=2, area="tokyo")
    # or
    scrape_tabelog(keyword="Tempura", max_pages=1, area="osaka")
```

## Quick Test Script

For a quick test, you can also create a minimal test:

```python
# quick_test.py
from scraper import init_database, scrape_tabelog

# Test with just 1 page
scrape_tabelog(keyword="Sushi", max_pages=1, area="tokyo")
```


