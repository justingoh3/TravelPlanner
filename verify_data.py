"""
Verification script to read and display restaurant data from the database.
"""

import sqlite3
import pandas as pd

DB_NAME = 'tabelog_japan.db'

def verify_data():
    """
    Query the database and display top 10 restaurants by rating.
    """
    try:
        conn = sqlite3.connect(DB_NAME)
        
        # Query top 10 restaurants by rating
        query = """
            SELECT name, tabelog_rating, review_count, district, area, genre, url 
            FROM restaurants 
            ORDER BY tabelog_rating DESC 
            LIMIT 10
        """
        
        df = pd.read_sql_query(query, conn)
        
        if df.empty:
            print("No data found in the database.")
            print("Run scraper.py first to collect restaurant data.")
        else:
            print("\n" + "="*120)
            print("TOP 10 RESTAURANTS BY TABELOG RATING")
            print("="*120)
            # Format for better readability
            pd.set_option('display.max_columns', None)
            pd.set_option('display.width', None)
            pd.set_option('display.max_colwidth', 30)
            print(df.to_string(index=False))
            print("="*120)
            
            # Show summary statistics
            total = len(pd.read_sql_query('SELECT * FROM restaurants', conn))
            print(f"\nTotal restaurants in database: {total}")
            
            # Show breakdown by district
            district_query = """
                SELECT district, COUNT(*) as count, 
                       AVG(tabelog_rating) as avg_rating,
                       MAX(tabelog_rating) as max_rating
                FROM restaurants 
                WHERE district IS NOT NULL
                GROUP BY district
                ORDER BY count DESC
            """
            district_df = pd.read_sql_query(district_query, conn)
            
            if not district_df.empty:
                print("\n" + "="*120)
                print("RESTAURANTS BY DISTRICT")
                print("="*120)
                print(district_df.to_string(index=False))
                print("="*120)
        
        conn.close()
        
    except sqlite3.OperationalError as e:
        print(f"Database error: {e}")
        print("Make sure you've run scraper.py first to create the database.")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    verify_data()

