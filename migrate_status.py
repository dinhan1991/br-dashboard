#!/usr/bin/env python3
"""
Migrate status data from SQLite to PostgreSQL
"""
import sqlite3
import psycopg2
import os

# PostgreSQL connection using secrets
pg_url = "postgresql://postgres.nndtyhqsjpdpzgyrouaf:%40%40Lena20162023@aws-1-ap-south-1.pooler.supabase.com:6543/postgres"

# SQLite connection
sqlite_conn = sqlite3.connect('data.db')
sqlite_cursor = sqlite_conn.cursor()

# PostgreSQL connection
pg_conn = psycopg2.connect(pg_url)
pg_cursor = pg_conn.cursor()

# Get all articles with status from SQLite
sqlite_cursor.execute("""
    SELECT article_number, mcs_status, fgt_status, ft_status, wt_status 
    FROM articles
""")

migrated = 0
skipped = 0

for row in sqlite_cursor.fetchall():
    article_number, mcs_status, fgt_status, ft_status, wt_status = row
    
    # Check if article exists in PostgreSQL
    pg_cursor.execute("SELECT id FROM articles WHERE article_number = %s", (article_number,))
    existing = pg_cursor.fetchone()
    
    if existing:
        # Update status fields
        pg_cursor.execute("""
            UPDATE articles SET
                mcs_status = %s,
                fgt_status = %s,
                ft_status = %s,
                wt_status = %s
            WHERE article_number = %s
        """, (mcs_status or '', fgt_status or '', ft_status or '', wt_status or '', article_number))
        migrated += 1
        print(f"[OK] Migrated {article_number}: MCS={mcs_status}, FGT={fgt_status}, FT={ft_status}, WT={wt_status}")
    else:
        skipped += 1
        print(f"[SKIP] {article_number} (not found in PostgreSQL)")

pg_conn.commit()

print(f"\n{'='*60}")
print(f"Migration complete!")
print(f"  Migrated: {migrated} articles")
print(f"  Skipped: {skipped} articles")
print(f"{'='*60}")

sqlite_conn.close()
pg_conn.close()
