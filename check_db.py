#!/usr/bin/env python3
"""Check current factory statistics in database"""
import psycopg2

pg_url = "postgresql://postgres.nndtyhqsjpdpzgyrouaf:%40%40Lena20162023@aws-1-ap-south-1.pooler.supabase.com:6543/postgres"

pg_conn = psycopg2.connect(pg_url)
pg_cursor = pg_conn.cursor()

print("=== Current Database Stats ===\n")

# Buy Ready
pg_cursor.execute("SELECT factory, COUNT(*) FROM articles WHERE factory IS NOT NULL GROUP BY factory ORDER BY factory")
br_counts = pg_cursor.fetchall()
print("Buy Ready Articles:")
total_br = 0
for factory, count in br_counts:
    print(f"  {factory}: {count} articles")
    total_br += count
print(f"  TOTAL: {total_br}\n")

# Drop Report
pg_cursor.execute("SELECT factory, COUNT(*) FROM drop_articles WHERE factory IS NOT NULL GROUP BY factory ORDER BY factory")
drop_counts = pg_cursor.fetchall()
print("Drop Articles:")
total_drop = 0
for factory, count in drop_counts:
    print(f"  {factory}: {count} articles")
    total_drop += count
print(f"  TOTAL: {total_drop}\n")

# Check for any SPG remaining
pg_cursor.execute("SELECT COUNT(*) FROM articles WHERE UPPER(factory) = 'SPG'")
spg_br = pg_cursor.fetchone()[0]
pg_cursor.execute("SELECT COUNT(*) FROM drop_articles WHERE UPPER(factory) = 'SPG'")
spg_drop = pg_cursor.fetchone()[0]

print(f"{'='*50}")
if spg_br == 0 and spg_drop == 0:
    print("SUCCESS: No SPG articles found!")
    print("Only HWA articles remain")
else:
    print(f"WARNING: Still found {spg_br + spg_drop} SPG articles!")
print(f"{'='*50}")

pg_conn.close()
