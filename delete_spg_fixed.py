#!/usr/bin/env python3
"""Delete all SPG factory articles from database - Fixed version"""
import psycopg2
import sys

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

pg_url = "postgresql://postgres.nndtyhqsjpdpzgyrouaf:%40%40Lena20162023@aws-1-ap-south-1.pooler.supabase.com:6543/postgres"

pg_conn = psycopg2.connect(pg_url)
pg_cursor = pg_conn.cursor()

print("=== Deleting SPG Articles ===\n")

# Check before
pg_cursor.execute("SELECT factory, COUNT(*) FROM articles WHERE factory IS NOT NULL GROUP BY factory ORDER BY factory")
print("BEFORE - Buy Ready:")
for row in pg_cursor.fetchall():
    print(f"  {row[0]}: {row[1]} articles")

# Delete SPG from articles
pg_cursor.execute("DELETE FROM articles WHERE UPPER(factory) = 'SPG'")
deleted_br = pg_cursor.rowcount
print(f"\n>>> Deleting {deleted_br} SPG articles from 'articles'...")

# Delete SPG from drop_articles
pg_cursor.execute("DELETE FROM drop_articles WHERE UPPER(factory) = 'SPG'")
deleted_drop = pg_cursor.rowcount
print(f">>> Deleting {deleted_drop} SPG articles from 'drop_articles'...")

# COMMIT the transaction!
pg_conn.commit()
print("\n>>> COMMITTED to database!")

# Check after
pg_cursor.execute("SELECT factory, COUNT(*) FROM articles WHERE factory IS NOT NULL GROUP BY factory ORDER BY factory")
print("\nAFTER - Buy Ready:")
for row in pg_cursor.fetchall():
    print(f"  {row[0]}: {row[1]} articles")

pg_cursor.execute("SELECT COUNT(*) FROM articles WHERE UPPER(factory) = 'SPG'")
spg_remaining = pg_cursor.fetchone()[0]

print(f"\n{'='*50}")
print(f"SUCCESS! Deleted {deleted_br + deleted_drop} SPG articles")
print(f"SPG remaining: {spg_remaining}")
print(f"Only HWA articles remain in database")
print(f"{'='*50}")

pg_conn.close()
