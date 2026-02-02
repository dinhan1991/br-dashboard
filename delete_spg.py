#!/usr/bin/env python3
"""
Delete all SPG factory articles from database
Keep only HWA articles
"""
import psycopg2

# PostgreSQL connection
pg_url = "postgresql://postgres.nndtyhqsjpdpzgyrouaf:%40%40Lena20162023@aws-1-ap-south-1.pooler.supabase.com:6543/postgres"

pg_conn = psycopg2.connect(pg_url)
pg_cursor = pg_conn.cursor()

print("=== Deleting SPG Articles ===\n")

# Check current counts
pg_cursor.execute("SELECT factory, COUNT(*) FROM articles WHERE factory IS NOT NULL GROUP BY factory")
before_counts = pg_cursor.fetchall()
print("BEFORE - Buy Ready Articles:")
for factory, count in before_counts:
    print(f"  {factory}: {count} articles")

pg_cursor.execute("SELECT factory, COUNT(*) FROM drop_articles WHERE factory IS NOT NULL GROUP BY factory")
before_drop_counts = pg_cursor.fetchall()
print("\nBEFORE - Drop Articles:")
for factory, count in before_drop_counts:
    print(f"  {factory}: {count} articles")

# Delete SPG from articles table
pg_cursor.execute("DELETE FROM articles WHERE UPPER(factory) = 'SPG'")
deleted_articles = pg_cursor.rowcount
print(f"\n✅ Deleted {deleted_articles} SPG articles from 'articles' table")

# Delete SPG from drop_articles table
pg_cursor.execute("DELETE FROM drop_articles WHERE UPPER(factory) = 'SPG'")
deleted_drop = pg_cursor.rowcount
print(f"✅ Deleted {deleted_drop} SPG articles from 'drop_articles' table")

pg_conn.commit()

# Check after deletion
pg_cursor.execute("SELECT factory, COUNT(*) FROM articles WHERE factory IS NOT NULL GROUP BY factory")
after_counts = pg_cursor.fetchall()
print("\nAFTER - Buy Ready Articles:")
for factory, count in after_counts:
    print(f"  {factory}: {count} articles")

pg_cursor.execute("SELECT factory, COUNT(*) FROM drop_articles WHERE factory IS NOT NULL GROUP BY factory")
after_drop_counts = pg_cursor.fetchall()
print("\nAFTER - Drop Articles:")
for factory, count in after_drop_counts:
    print(f"  {factory}: {count} articles")

print(f"\n{'='*50}")
print(f"✅ COMPLETE!")
print(f"   Deleted {deleted_articles + deleted_drop} total SPG articles")
print(f"   Only HWA articles remain")
print(f"{'='*50}")

pg_conn.close()
