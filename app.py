import streamlit as st
import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from datetime import datetime
import plotly.graph_objects as go

# Page configuration
st.set_page_config(
    page_title="BR tracking",
    page_icon="🏈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Database connection helper
def get_db_connection():
    """Get PostgreSQL database connection from Streamlit secrets or environment"""
    try:
        # Try Streamlit secrets first (for cloud deployment)
        db_url = st.secrets["database"]["url"]
    except:
        # Fallback to environment variable for local development
        db_url = os.getenv("DATABASE_URL", "")
    
    if not db_url:
        st.error("⚠️ Database URL not configured. Please add database URL to Streamlit secrets.")
        st.stop()
    
    return psycopg2.connect(db_url)

# Database functions
def init_db():
    """Initialize PostgreSQL database"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Buy Ready table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS articles (
            id SERIAL PRIMARY KEY,
            factory VARCHAR(100),
            sports_category VARCHAR(100),
            article_name TEXT,
            model VARCHAR(100),
            article_number VARCHAR(100) UNIQUE,
            pre_confirm_date VARCHAR(50),
            leading_buy_ready_date VARCHAR(50),
            product_weight VARCHAR(100),
            mcs_status VARCHAR(50) DEFAULT '',
            fgt_status VARCHAR(50) DEFAULT '',
            ft_status VARCHAR(50) DEFAULT '',
            wt_status VARCHAR(50) DEFAULT '',
            lifecycle_state VARCHAR(100) DEFAULT '',
            created_at TIMESTAMP,
            updated_at TIMESTAMP
        )
    ''')
    
    # Drop Report table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS drop_articles (
            id SERIAL PRIMARY KEY,
            season VARCHAR(100),
            factory VARCHAR(100),
            sports_category VARCHAR(100),
            article_name TEXT,
            model VARCHAR(100),
            article_number VARCHAR(100),
            created_at TIMESTAMP,
            updated_at TIMESTAMP,
            UNIQUE(season, article_number)
        )
    ''')
    
    # Archive table for completed Buy Ready articles
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS archived_articles (
            id SERIAL PRIMARY KEY,
            factory VARCHAR(100),
            sports_category VARCHAR(100),
            article_name TEXT,
            model VARCHAR(100),
            article_number VARCHAR(100),
            leading_buy_ready_date VARCHAR(50),
            mcs_status VARCHAR(50),
            fgt_status VARCHAR(50),
            ft_status VARCHAR(50),
            wt_status VARCHAR(50),
            archived_at TIMESTAMP,
            original_created_at TIMESTAMP
        )
    ''')
    
    # Archive table for completed Drop articles
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS archived_drop_articles (
            id SERIAL PRIMARY KEY,
            season VARCHAR(100),
            factory VARCHAR(100),
            sports_category VARCHAR(100),
            article_name TEXT,
            model VARCHAR(100),
            article_number VARCHAR(100),
            archived_at TIMESTAMP,
            original_created_at TIMESTAMP
        )
    ''')
    
    conn.commit()
    cursor.close()
    conn.close()

@st.cache_data(ttl=60)  # Cache for 60 seconds
def load_from_db():
    """Load Buy Ready data from database"""
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM articles ORDER BY leading_buy_ready_date ASC", conn)
    conn.close()
    return df

@st.cache_data(ttl=60)  # Cache for 60 seconds
def load_drop_from_db():
    """Load Drop Report data from database"""
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM drop_articles ORDER BY season, sports_category", conn)
    conn.close()
    return df

@st.cache_data(ttl=60)
def load_archived_br():
    """Load archived Buy Ready articles"""
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM archived_articles ORDER BY archived_at DESC", conn)
    conn.close()
    return df

@st.cache_data(ttl=60)
def load_archived_drop():
    """Load archived Drop articles"""
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM archived_drop_articles ORDER BY archived_at DESC", conn)
    conn.close()
    return df

def safe_str(val, default=''):
    """Convert value to string safely - return empty string for NaN/None instead of 'nan'"""
    if val is None or (isinstance(val, float) and pd.isna(val)) or pd.isna(val):
        return default
    s = str(val).strip()
    if s.lower() == 'nan' or s.lower() == 'none' or s.lower() == 'nat':
        return default
    return s

def save_to_db(df_new):
    """Save Buy Ready data to database. Returns (inserted, updated, unchanged, skipped, new_articles, changed_articles, archived_list)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    inserted = 0
    updated = 0  # Actually changed
    unchanged = 0  # Existed but no data change
    skipped = 0
    new_articles = []  # List of new article numbers
    changed_articles = {}  # {article_number: [list of changes]}
    
    # Get all article numbers from new file
    new_article_numbers = set()
    for _, row in df_new.iterrows():
        article_number = str(row.get('Article NUMBER', '')).strip()
        if article_number and article_number != 'nan':
            new_article_numbers.add(article_number)
    
    # Get existing articles with full data for comparison
    existing_articles = {}
    cursor.execute("""SELECT article_number, article_name, model, sports_category, 
                      pre_confirm_date, leading_buy_ready_date, factory FROM articles""")
    for row in cursor.fetchall():
        existing_articles[row[0]] = {
            'article_name': row[1] or '', 'model': row[2] or '',
            'sports_category': row[3] or '', 'pre_confirm_date': row[4] or '',
            'leading_buy_ready_date': row[5] or '', 'factory': row[6] or '',
        }
    
    for _, row in df_new.iterrows():
        article_number = str(row.get('Article NUMBER', '')).strip()
        if not article_number or article_number == 'nan':
            skipped += 1
            continue
        
        now = datetime.now().isoformat()
        
        pre_confirm = row.get('Pre-Confirm Date', '')
        leading_buy = row.get('Leading Buy Ready Date', '')
        
        if pd.notna(pre_confirm) and hasattr(pre_confirm, 'isoformat'):
            pre_confirm = pre_confirm.isoformat()
        elif pd.isna(pre_confirm):
            pre_confirm = ''
            
        if pd.notna(leading_buy) and hasattr(leading_buy, 'isoformat'):
            leading_buy = leading_buy.isoformat()
        elif pd.isna(leading_buy):
            leading_buy = ''
        
        if article_number in existing_articles:
            old = existing_articles[article_number]
            new_article_name = safe_str(row.get('Article NAME', ''))
            new_model = safe_str(row.get('Model', ''))
            new_leading = safe_str(leading_buy)
            new_preconfirm = safe_str(pre_confirm)
            
            # Detect actual changes
            changes = []
            if old['leading_buy_ready_date'] != new_leading:
                old_br = old['leading_buy_ready_date'][:10] if old['leading_buy_ready_date'] else '\u2014'
                new_br = new_leading[:10] if new_leading else '\u2014'
                changes.append(f"BR Date: {old_br} \u2192 {new_br}")
            if old['pre_confirm_date'] != new_preconfirm:
                changes.append("Pre-Confirm changed")
            if new_article_name and old['article_name'] != new_article_name:
                old_name = old['article_name'] or '\u2014'
                changes.append(f"Name: {old_name} \u2192 {new_article_name}")
            if old['model'] != new_model:
                old_model = old['model'] or '\u2014'
                changes.append(f"Model: {old_model} \u2192 {new_model}")
            
            # Build dynamic UPDATE
            update_fields = {
                'factory': safe_str(row.get('Factory', '')),
                'sports_category': safe_str(row.get('Sports Category', '')),
                'model': new_model,
                'pre_confirm_date': new_preconfirm,
                'leading_buy_ready_date': new_leading,
                'updated_at': now,
            }
            
            if new_article_name:
                update_fields['article_name'] = new_article_name
            
            weight_val = row.get('Product Weight')
            lifecycle_val = row.get('Lifecycle State')
            if weight_val is not None and not (isinstance(weight_val, float) and pd.isna(weight_val)):
                update_fields['product_weight'] = str(weight_val)
            if lifecycle_val is not None and not (isinstance(lifecycle_val, float) and pd.isna(lifecycle_val)):
                update_fields['lifecycle_state'] = str(lifecycle_val)
            
            set_clause = ', '.join([f'{k} = %s' for k in update_fields.keys()])
            values = list(update_fields.values()) + [article_number]
            cursor.execute(f'''UPDATE articles SET {set_clause} WHERE article_number = %s''', values)
            
            if changes:
                updated += 1
                changed_articles[article_number] = changes
            else:
                unchanged += 1
        else:
            new_articles.append(article_number)
            cursor.execute('''
                INSERT INTO articles (
                    factory, sports_category, article_name, model, article_number,
                    pre_confirm_date, leading_buy_ready_date, product_weight, lifecycle_state,
                    mcs_status, fgt_status, ft_status, wt_status, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, '', '', '', '', %s, %s)
            ''', (
                safe_str(row.get('Factory', '')),
                safe_str(row.get('Sports Category', '')),
                safe_str(row.get('Article NAME', '')),
                safe_str(row.get('Model', '')),
                article_number, safe_str(pre_confirm), safe_str(leading_buy),
                safe_str(row.get('Product Weight', '')),
                safe_str(row.get('Lifecycle State', '')),
                now, now
            ))
            inserted += 1
    
    # Archive articles not in new file (completed articles)
    archived = 0
    archived_list = []
    for old_article in existing_articles.keys():
        if old_article not in new_article_numbers:
            # Move to archive instead of delete
            cursor.execute('''
                INSERT INTO archived_articles (
                    factory, sports_category, article_name, model, article_number,
                    leading_buy_ready_date, mcs_status, fgt_status, ft_status, wt_status,
                    archived_at, original_created_at
                )
                SELECT factory, sports_category, article_name, model, article_number,
                       leading_buy_ready_date, mcs_status, fgt_status, ft_status, wt_status,
                       NOW(), created_at
                FROM articles WHERE article_number = %s
            ''', (old_article,))
            cursor.execute("DELETE FROM articles WHERE article_number = %s", (old_article,))
            archived += 1
            archived_list.append(old_article)
    
    conn.commit()
    conn.close()
    return inserted, updated, unchanged, skipped, new_articles, changed_articles, archived_list

def save_drop_to_db(df_new):
    """Save Drop Report data to database. Returns (inserted, updated, unchanged, archived, skipped, new_articles, changed_articles, archived_list)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    inserted = 0
    updated = 0  # Actually changed
    unchanged = 0
    skipped = 0
    new_articles = []  # Track new article numbers
    changed_articles = {}  # {article_number: [changes]}
    
    # Get all season+article combinations from new file
    new_article_keys = set()
    for _, row in df_new.iterrows():
        article_number = str(row.get('Article NUMBER', '')).strip()
        season = str(row.get('Season', '')).strip()
        if article_number and article_number != 'nan' and season:
            new_article_keys.add((season, article_number))
    
    # Get existing articles with full data
    existing_articles = {}
    cursor.execute("SELECT season, article_number, id, article_name, model, sports_category FROM drop_articles")
    for row in cursor.fetchall():
        existing_articles[(row[0], row[1])] = {
            'id': row[2], 'article_name': row[3] or '',
            'model': row[4] or '', 'sports_category': row[5] or '',
        }
    
    for _, row in df_new.iterrows():
        article_number = str(row.get('Article NUMBER', '')).strip()
        season = str(row.get('Season', '')).strip()
        
        if not article_number or article_number == 'nan' or not season:
            skipped += 1
            continue
        
        now = datetime.now().isoformat()
        key = (season, article_number)
        
        if key in existing_articles:
            old = existing_articles[key]
            new_drop_name = safe_str(row.get('Article NAME', ''))
            new_model = safe_str(row.get('Model', ''))
            
            # Detect actual changes
            changes = []
            if new_drop_name and old['article_name'] != new_drop_name:
                old_name = old['article_name'] or '\u2014'
                changes.append(f"Name: {old_name} \u2192 {new_drop_name}")
            if old['model'] != new_model:
                old_mdl = old['model'] or '\u2014'
                changes.append(f"Model: {old_mdl} \u2192 {new_model}")
            
            # Build dynamic UPDATE
            drop_update = {
                'factory': safe_str(row.get('Factory', '')),
                'sports_category': safe_str(row.get('Sports Category', '')),
                'model': new_model,
                'updated_at': now,
            }
            if new_drop_name:
                drop_update['article_name'] = new_drop_name
            
            set_clause = ', '.join([f'{k} = %s' for k in drop_update.keys()])
            values = list(drop_update.values()) + [season, article_number]
            cursor.execute(f'''UPDATE drop_articles SET {set_clause} WHERE season = %s AND article_number = %s''', values)
            
            if changes:
                updated += 1
                changed_articles[article_number] = changes
            else:
                unchanged += 1
        else:
            new_articles.append(article_number)  # Track as NEW
            cursor.execute('''
                INSERT INTO drop_articles (season, factory, sports_category, article_name, model, article_number, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ''', (
                season,
                safe_str(row.get('Factory', '')),
                safe_str(row.get('Sports Category', '')),
                safe_str(row.get('Article NAME', '')),
                safe_str(row.get('Model', '')),
                article_number, now, now
            ))
            inserted += 1
    
    # Archive articles not in new file (completed)
    archived = 0
    archived_list = []
    for old_key in existing_articles.keys():
        if old_key not in new_article_keys:
            season, article_number = old_key
            # Move to archive
            cursor.execute('''
                INSERT INTO archived_drop_articles (
                    season, factory, sports_category, article_name, model, article_number,
                    archived_at, original_created_at
                )
                SELECT season, factory, sports_category, article_name, model, article_number,
                       NOW(), created_at
                FROM drop_articles WHERE season = %s AND article_number = %s
            ''', (season, article_number))
            cursor.execute("DELETE FROM drop_articles WHERE season = %s AND article_number = %s", (season, article_number))
            archived += 1
            archived_list.append(article_number)
    
    conn.commit()
    conn.close()
    return inserted, updated, unchanged, archived, skipped, new_articles, changed_articles, archived_list

def update_all_statuses(df):
    """Update all status columns from dataframe"""
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    
    for _, row in df.iterrows():
        article_number = str(row.get('Article NUMBER', '')).strip()
        if article_number and article_number != 'nan':
            cursor.execute('''
                UPDATE articles SET mcs_status = %s, fgt_status = %s, ft_status = %s, wt_status = %s, updated_at = %s
                WHERE article_number = %s
            ''', (
                str(row.get('MCS status', '')),
                str(row.get('FGT status', '')),
                str(row.get('FT status', '')),
                str(row.get('WT status', '')),
                now, article_number
            ))
    
    conn.commit()
    conn.close()

# Initialize database
init_db()

# Sports categories
ALLOWED_SPORTS = ['AMERICAN FOOTBALL', 'BASEBALL', 'SOFTBALL']

# Allowed factories (HWA only)
ALLOWED_FACTORIES = ['HWA']

# Helper functions
def find_column(df, possible_names):
    df_columns_lower = {col.lower().strip(): col for col in df.columns}
    for name in possible_names:
        if name.lower().strip() in df_columns_lower:
            return df_columns_lower[name.lower().strip()]
    return None

def detect_file_type(file):
    """Detect if file is Buy Ready or Drop Report based on filename"""
    filename = file.name.lower()
    
    if 'buy ready' in filename or 'buyready' in filename or 'buy_ready' in filename:
        return 'buy_ready'
    elif 'drop' in filename:
        return 'drop_report'
    else:
        return 'unknown'

# Custom CSS - Enhanced UI
st.markdown("""
<style>
    .main { background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%); }
    
    .stat-card {
        background: linear-gradient(145deg, #1e3a5f, #1a2d47);
        border-radius: 20px; padding: 1.5rem;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
        border: 1px solid rgba(255, 255, 255, 0.1);
        text-align: center; transition: all 0.3s ease;
    }
    .stat-card:hover { transform: translateY(-5px); box-shadow: 0 12px 40px rgba(0, 0, 0, 0.4); }
    .stat-number {
        font-size: 2.5rem; font-weight: 700;
        background: linear-gradient(90deg, #00d2ff 0%, #3a7bd5 100%);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    }
    .stat-label { font-size: 0.95rem; color: #a0aec0; margin-top: 0.5rem; }
    
    .factory-card {
        background: linear-gradient(145deg, #2d3748, #1a202c);
        border-radius: 15px; padding: 1rem 1.5rem;
        border-left: 4px solid #667eea;
        margin-bottom: 0.5rem;
        display: flex; justify-content: space-between; align-items: center;
    }
    .factory-name { color: #e2e8f0; font-weight: 600; font-size: 1.1rem; }
    .factory-count { 
        background: linear-gradient(90deg, #667eea, #764ba2);
        padding: 0.3rem 0.8rem; border-radius: 20px;
        color: white; font-weight: bold;
    }
    
    hr { border: none; height: 2px; background: linear-gradient(90deg, transparent, #667eea, transparent); margin: 2rem 0; }
    
    .section-header { 
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        font-size: 1.8rem; font-weight: bold;
        display: flex; align-items: center; gap: 0.5rem;
    }
    
    .timestamp {
        color: #718096; font-size: 0.85rem;
        padding: 0.5rem 1rem;
        background: rgba(255,255,255,0.05);
        border-radius: 10px;
        display: inline-block;
        margin-bottom: 1rem;
    }
    
    .sidebar-info {
        background: linear-gradient(145deg, rgba(102, 126, 234, 0.1), rgba(118, 75, 162, 0.1));
        border-radius: 15px; padding: 1rem;
        border: 1px solid rgba(102, 126, 234, 0.3);
        margin-bottom: 1rem;
    }
    
    .version-tag {
        background: linear-gradient(90deg, #667eea, #764ba2);
        color: white; padding: 0.2rem 0.6rem;
        border-radius: 10px; font-size: 0.75rem;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# Header with Banner
import base64

# Load banner image
banner_path = os.path.join(os.path.dirname(__file__), 'banner.png')
if os.path.exists(banner_path):
    with open(banner_path, "rb") as f:
        banner_data = base64.b64encode(f.read()).decode()
    st.markdown(f'''
        <div style="text-align: center; margin-bottom: 1rem;">
            <img src="data:image/png;base64,{banner_data}" style="max-width: 100%; height: auto; border-radius: 15px; box-shadow: 0 4px 20px rgba(0,0,0,0.3);">
        </div>
    ''', unsafe_allow_html=True)

st.markdown("<p style='text-align: center; color: #a0aec0; font-size: 1.1rem; margin-bottom: 2rem;'>Upload Buy Ready Report hoặc Drop Report</p>", unsafe_allow_html=True)

# Sidebar - Enhanced
with st.sidebar:
    # Header with version
    st.markdown("""
        <div style="text-align: center; margin-bottom: 1rem;">
            <h2 style="color: #667eea; margin: 0;">🏈 BR Tracking</h2>
            <span class="version-tag">v3.4</span>
        </div>
    """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    # File uploader
    uploaded_file = st.file_uploader(
        "📁 Upload file Excel",
        type=['xlsx', 'xls', 'xlsm'],
        help="Auto-detect Buy Ready hoặc Drop Report"
    )
    
    st.markdown("---")
    
    # Filter info
    st.markdown("""
        <div class="sidebar-info">
            <h4 style="color: #e2e8f0; margin: 0 0 0.5rem 0;">🔍 Auto Filter</h4>
            <p style="color: #a0aec0; margin: 0; font-size: 0.9rem;">
                <strong>Sports:</strong> AM.Football, Baseball, Softball<br>
                <strong>Factory:</strong> HWA Only
            </p>
        </div>
    """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    # Database stats - V3 Design
    br_data = load_from_db()
    drop_data = load_drop_from_db()
    
    st.markdown("""
        <div class="sidebar-info">
            <h4 style="color: #e2e8f0; margin: 0 0 1rem 0;">💾 Database</h4>
        </div>
    """, unsafe_allow_html=True)
    
    # Modern stat cards for BR and DROP
    st.markdown(f"""
        <div style="
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 1rem;
            border-radius: 12px;
            margin-bottom: 0.75rem;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
        ">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <div style="color: #e2e8f0; font-size: 0.85rem; margin-bottom: 0.25rem;">📦 Buy Ready</div>
                    <div style="color: white; font-size: 2rem; font-weight: 700;">{len(br_data)}</div>
                </div>
                <div style="font-size: 2.5rem; opacity: 0.3;">📦</div>
            </div>
        </div>
        
        <div style="
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
            padding: 1rem;
            border-radius: 12px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
        ">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <div style="color: #e2e8f0; font-size: 0.85rem; margin-bottom: 0.25rem;">📉 Drop Report</div>
                    <div style="color: white; font-size: 2rem; font-weight: 700;">{len(drop_data)}</div>
                </div>
                <div style="font-size: 2.5rem; opacity: 0.3;">📉</div>
            </div>
        </div>
    """, unsafe_allow_html=True)
    
    # Archive Section - V3.2
    try:
        archived_br = load_archived_br()
        archived_drop = load_archived_drop()
        
        if len(archived_br) > 0 or len(archived_drop) > 0:
            st.markdown("""
                <div style="margin-top: 0.75rem;">
                    <div style="
                        background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
                        padding: 1rem;
                        border-radius: 12px;
                        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
                    ">
                        <div style="color: #e2e8f0; font-size: 0.85rem; margin-bottom: 0.5rem;">📦 Archive (Hoàn thành)</div>
                        <div style="display: flex; gap: 1rem;">
            """, unsafe_allow_html=True)
            st.markdown(f"""
                            <div style="text-align: center;">
                                <div style="color: white; font-size: 1.5rem; font-weight: 700;">{len(archived_br)}</div>
                                <div style="color: #d1fae5; font-size: 0.7rem;">BR</div>
                            </div>
                            <div style="text-align: center;">
                                <div style="color: white; font-size: 1.5rem; font-weight: 700;">{len(archived_drop)}</div>
                                <div style="color: #d1fae5; font-size: 0.7rem;">DROP</div>
                            </div>
                        </div>
                    </div>
                </div>
            """, unsafe_allow_html=True)
            
            # Export Archive button
            if st.button("📤 Export Archive", key="export_archive"):
                import io
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    if len(archived_br) > 0:
                        # Format BR columns to match original upload
                        br_export = archived_br.rename(columns={
                            'factory': 'Factory',
                            'sports_category': 'Sports Category',
                            'article_name': 'Article NAME',
                            'model': 'Model',
                            'article_number': 'Article NUMBER',
                            'leading_buy_ready_date': 'Leading Buy Ready Date',
                            'mcs_status': 'MCS status',
                            'fgt_status': 'FGT status',
                            'ft_status': 'FT status',
                            'wt_status': 'WT status',
                            'archived_at': 'Archived At'
                        })
                        # Select only relevant columns
                        br_cols = ['Factory', 'Sports Category', 'Article NAME', 'Model', 
                                   'Article NUMBER', 'Leading Buy Ready Date', 'MCS status', 
                                   'FGT status', 'FT status', 'WT status', 'Archived At']
                        br_export = br_export[[c for c in br_cols if c in br_export.columns]]
                        br_export.to_excel(writer, sheet_name='BR Archive', index=False)
                    
                    if len(archived_drop) > 0:
                        # Format DROP columns to match original upload
                        drop_export = archived_drop.rename(columns={
                            'season': 'Season',
                            'factory': 'Factory',
                            'sports_category': 'Sports Category',
                            'article_name': 'Article NAME',
                            'model': 'Model',
                            'article_number': 'Article NUMBER',
                            'archived_at': 'Archived At'
                        })
                        # Select only relevant columns
                        drop_cols = ['Season', 'Factory', 'Sports Category', 'Article NAME', 
                                     'Model', 'Article NUMBER', 'Archived At']
                        drop_export = drop_export[[c for c in drop_cols if c in drop_export.columns]]
                        drop_export.to_excel(writer, sheet_name='DROP Archive', index=False)
                
                output.seek(0)
                st.download_button(
                    label="⬇️ Download Archive.xlsx",
                    data=output.getvalue(),
                    file_name=f"archive_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
    except Exception as e:
        pass  # Archive tables might not exist yet
    
    st.markdown("---")
    
    # ==================== TIMELINE IN SIDEBAR ====================
    if len(br_data) > 0:
        import re
        
        # Initialize timeline filter session state
        if 'timeline_filter' not in st.session_state:
            st.session_state.timeline_filter = None
        
        def extract_date_from_status(status_text):
            """Extract ETD or ETC date from status text. Returns (date, type) or (None, None)"""
            if not status_text or str(status_text) == 'nan':
                return None, None
            text_upper = str(status_text).upper()
            # Check for ETC first (ETC = Estimated Time of Completion)
            match_etc = re.search(r'ETC\s*(\d{1,2})/(\d{1,2})', text_upper)
            if match_etc:
                month = int(match_etc.group(1))
                day = int(match_etc.group(2))
                year = datetime.now().year
                # Smart year detection: if date is more than 6 months in the past, assume next year
                try:
                    candidate = datetime(year, month, day).date()
                    if (datetime.now().date() - candidate).days > 180:
                        candidate = datetime(year + 1, month, day).date()
                    return candidate, 'ETC'
                except:
                    pass
            # Check for ETC without date (just keyword)
            if 'ETC' in text_upper and not match_etc:
                return None, 'ETC'
            # Check for ETD (Estimated Time of Delivery)
            match_etd = re.search(r'ETD\s*(\d{1,2})/(\d{1,2})', text_upper)
            if match_etd:
                month = int(match_etd.group(1))
                day = int(match_etd.group(2))
                year = datetime.now().year
                try:
                    candidate = datetime(year, month, day).date()
                    if (datetime.now().date() - candidate).days > 180:
                        candidate = datetime(year + 1, month, day).date()
                    return candidate, 'ETD'
                except:
                    pass
            return None, None
        
        # Step label map: abbreviation → full name (Footwear industry)
        col_label_map = {'mcs_status': 'MCS', 'fgt_status': 'FGT', 'ft_status': 'FT', 'wt_status': 'WT'}
        col_fullname_map = {
            'MCS': 'Material Confirmation Sheet',
            'FGT': 'Finished Good Testing',
            'FT': 'Fit Trial',
            'WT': 'Wear Test'
        }
        
        # Extract timeline items (ETD) and pending items (ETC)
        timeline_items = []
        pending_items = []  # ETC items
        for _, row in br_data.iterrows():
            article = str(row.get('article_number', ''))
            factory = str(row.get('factory', ''))
            
            for col in ['mcs_status', 'fgt_status', 'ft_status', 'wt_status']:
                if col in br_data.columns:
                    status_val = str(row.get(col, ''))
                    extracted_date, date_type = extract_date_from_status(status_val)
                    step_label = col_label_map.get(col, col)
                    if date_type == 'ETC':
                        pending_items.append({
                            'Article': article,
                            'Factory': factory,
                            'ETC Date': extracted_date,
                            'Step': step_label,
                            'Status': status_val,
                        })
                    elif date_type == 'ETD' and extracted_date:
                        timeline_items.append({
                            'Article': article,
                            'Factory': factory,
                            'ETD Date': extracted_date,
                        })
        
        if timeline_items or pending_items:
            today = datetime.now().date()
            
            # Timeline header with premium styling
            st.markdown("""
                <div style="
                    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
                    border: 1px solid rgba(102, 126, 234, 0.3);
                    border-radius: 12px; padding: 0.8rem 1rem; margin-bottom: 0.8rem;
                    text-align: center;
                ">
                    <span style="font-size: 1.3rem;">⏰</span>
                    <span style="color: #e2e8f0; font-weight: 700; font-size: 1.1rem; margin-left: 0.3rem;">Timeline</span>
                </div>
            """, unsafe_allow_html=True)
            
            # === Split ETC items into OVERDUE vs PENDING ===
            if pending_items:
                # Deduplicate by article
                pending_by_article = {}
                for item in pending_items:
                    art = item['Article']
                    if art not in pending_by_article:
                        pending_by_article[art] = {'steps': [], 'date': item.get('ETC Date'), 'status': item.get('Status', '')}
                    pending_by_article[art]['steps'].append(item['Step'])
                    if item.get('ETC Date') and not pending_by_article[art]['date']:
                        pending_by_article[art]['date'] = item['ETC Date']
                
                # Split into overdue and pending
                etc_overdue = {}
                etc_pending = {}
                etc_no_date = {}
                for art, info in pending_by_article.items():
                    if info['date'] and info['date'] < today:
                        etc_overdue[art] = info
                    elif info['date'] and info['date'] >= today:
                        etc_pending[art] = info
                    else:
                        etc_no_date[art] = info
                
                # ── 🚨 OVERDUE ETC Section ── 
                if etc_overdue:
                    st.markdown(f"""
                        <div style="
                            background: linear-gradient(135deg, #e53e3e 0%, #c53030 100%);
                            border-radius: 10px; padding: 0.6rem 0.8rem; margin-bottom: 0.5rem;
                            display: flex; align-items: center; justify-content: space-between;
                        ">
                            <span style="color: white; font-weight: 700; font-size: 0.85rem;">
                                🚨 OVERDUE
                            </span>
                            <span style="
                                background: rgba(255,255,255,0.25); color: white;
                                padding: 0.15rem 0.5rem; border-radius: 12px;
                                font-weight: 700; font-size: 0.8rem;
                            ">{len(etc_overdue)}</span>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    # Sort by most overdue first
                    sorted_overdue = sorted(etc_overdue.items(), key=lambda x: x[1]['date'])
                    for idx, (article, info) in enumerate(sorted_overdue[:8]):
                        days_over = (today - info['date']).days
                        steps_str = ', '.join(info['steps'])
                        date_display = info['date'].strftime('%m/%d')
                        
                        st.markdown(f"""
                            <style>
                                @keyframes pulse-red {{
                                    0%, 100% {{ opacity: 1; }}
                                    50% {{ opacity: 0.7; }}
                                }}
                            </style>
                        """, unsafe_allow_html=True)
                        
                        if st.button(
                            f"🔴 {article} [{steps_str}] ({date_display}) · -{days_over}d",
                            key=f"sb_etc_over_{idx}",
                            use_container_width=True
                        ):
                            st.session_state.timeline_filter = article
                            st.rerun()
                
                # ── ⏳ PENDING ETC Section ──
                pending_display = {**etc_pending, **etc_no_date}
                if pending_display:
                    st.markdown(f"""
                        <div style="
                            background: linear-gradient(135deg, #d69e2e 0%, #b7791f 100%);
                            border-radius: 10px; padding: 0.6rem 0.8rem; margin-bottom: 0.5rem;
                            margin-top: 0.5rem;
                            display: flex; align-items: center; justify-content: space-between;
                        ">
                            <span style="color: white; font-weight: 700; font-size: 0.85rem;">
                                ⏳ PENDING
                            </span>
                            <span style="
                                background: rgba(255,255,255,0.25); color: white;
                                padding: 0.15rem 0.5rem; border-radius: 12px;
                                font-weight: 700; font-size: 0.8rem;
                            ">{len(pending_display)}</span>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    # Sort by earliest ETC date first (no-date items at the end)
                    sorted_pending = sorted(
                        pending_display.items(),
                        key=lambda x: x[1]['date'] if x[1]['date'] else datetime(2099, 12, 31).date()
                    )
                    for idx, (article, info) in enumerate(sorted_pending[:8]):
                        steps_str = ', '.join(info['steps'])
                        if info['date']:
                            days_until = (info['date'] - today).days
                            date_display = info['date'].strftime('%m/%d')
                            label = f"🟡 {article} [{steps_str}] ({date_display}) · {days_until}d"
                        else:
                            label = f"🟡 {article} [{steps_str}]"
                        
                        if st.button(label, key=f"sb_etc_pend_{idx}", use_container_width=True):
                            st.session_state.timeline_filter = article
                            st.rerun()
            
            # === ETD Timeline Section ===
            if timeline_items:
                overdue = [item for item in timeline_items if item['ETD Date'] < today]
                due_today = [item for item in timeline_items if item['ETD Date'] == today]
                upcoming = [item for item in timeline_items if item['ETD Date'] > today and item['ETD Date'] <= today + pd.Timedelta(days=7)]
                
                # ETD Overdue
                if overdue:
                    st.markdown(f"""
                        <div style="
                            background: linear-gradient(135deg, #9b2c2c 0%, #742a2a 100%);
                            border-radius: 10px; padding: 0.6rem 0.8rem; margin: 0.5rem 0;
                            display: flex; align-items: center; justify-content: space-between;
                        ">
                            <span style="color: white; font-weight: 700; font-size: 0.85rem;">
                                🚨 ETD Quá hạn
                            </span>
                            <span style="
                                background: rgba(255,255,255,0.25); color: white;
                                padding: 0.15rem 0.5rem; border-radius: 12px;
                                font-weight: 700; font-size: 0.8rem;
                            ">{len(overdue)}</span>
                        </div>
                    """, unsafe_allow_html=True)
                    for idx, item in enumerate(sorted(overdue, key=lambda x: x['ETD Date'])[:5]):
                        days_over = (today - item['ETD Date']).days
                        if st.button(f"⚠️ {item['Article']} (-{days_over}d)", key=f"sb_over_{idx}", use_container_width=True):
                            st.session_state.timeline_filter = item['Article']
                            st.rerun()
                
                # ETD Today
                if due_today:
                    st.markdown(f"""
                        <div style="
                            background: linear-gradient(135deg, #d69e2e 0%, #b7791f 100%);
                            border-radius: 10px; padding: 0.6rem 0.8rem; margin: 0.5rem 0;
                            display: flex; align-items: center; justify-content: space-between;
                        ">
                            <span style="color: white; font-weight: 700; font-size: 0.85rem;">
                                📅 Hôm nay
                            </span>
                            <span style="
                                background: rgba(255,255,255,0.25); color: white;
                                padding: 0.15rem 0.5rem; border-radius: 12px;
                                font-weight: 700; font-size: 0.8rem;
                            ">{len(due_today)}</span>
                        </div>
                    """, unsafe_allow_html=True)
                    for idx, item in enumerate(due_today[:5]):
                        if st.button(f"🔔 {item['Article']}", key=f"sb_today_{idx}", use_container_width=True):
                            st.session_state.timeline_filter = item['Article']
                            st.rerun()
                
                # ETD Upcoming 7 days
                if upcoming:
                    st.markdown(f"""
                        <div style="
                            background: linear-gradient(135deg, #2b6cb0 0%, #2c5282 100%);
                            border-radius: 10px; padding: 0.6rem 0.8rem; margin: 0.5rem 0;
                            display: flex; align-items: center; justify-content: space-between;
                        ">
                            <span style="color: white; font-weight: 700; font-size: 0.85rem;">
                                📆 7 ngày tới
                            </span>
                            <span style="
                                background: rgba(255,255,255,0.25); color: white;
                                padding: 0.15rem 0.5rem; border-radius: 12px;
                                font-weight: 700; font-size: 0.8rem;
                            ">{len(upcoming)}</span>
                        </div>
                    """, unsafe_allow_html=True)
                    for idx, item in enumerate(sorted(upcoming, key=lambda x: x['ETD Date'])[:5]):
                        days_left = (item['ETD Date'] - today).days
                        if st.button(f"⏳ {item['Article']} ({days_left}d)", key=f"sb_up_{idx}", use_container_width=True):
                            st.session_state.timeline_filter = item['Article']
                            st.rerun()
            
            # Clear filter button
            if st.session_state.timeline_filter:
                st.markdown("---")
                st.markdown(f"""
                    <div style="
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        border-radius: 8px; padding: 0.5rem 0.8rem;
                        color: white; font-size: 0.85rem; text-align: center;
                    ">🔍 Filter: <b>{st.session_state.timeline_filter}</b></div>
                """, unsafe_allow_html=True)
                if st.button("❌ Xóa filter", key="sb_clear", use_container_width=True):
                    st.session_state.timeline_filter = None
                    st.rerun()
            
            st.markdown("---")
    
    # Footer
    st.markdown("""
        <div style="text-align: center; color: #718096; font-size: 0.8rem;">
            <p>Made with ❤️ using Streamlit</p>
            <p style="margin-top: 0.5rem;">© 2026 US Sports Team</p>
        </div>
    """, unsafe_allow_html=True)

# Process uploaded file
if uploaded_file is not None:
    # Guard: skip re-processing if this exact file was already processed
    file_key = f"{uploaded_file.name}_{uploaded_file.size}"
    already_processed = st.session_state.get('last_processed_file') == file_key
    
    file_type = detect_file_type(uploaded_file)
    print(f"[DEBUG] File uploaded: {uploaded_file.name}, detected type: {file_type}, already_processed: {already_processed}")
    
    if already_processed:
        # Show the stored result from the processing
        last_result = st.session_state.get('last_process_result', '')
        last_result_type = st.session_state.get('last_process_result_type', 'success')
        if last_result:
            if last_result_type == 'info':
                st.info(last_result)
            else:
                st.success(last_result)
    elif file_type == 'unknown':
        st.warning("⚠️ Không thể xác định loại file. Tên file cần chứa 'Buy Ready' hoặc 'Drop'")
    
    elif file_type == 'buy_ready':
        st.info("📋 Detected: **Buy Ready Report**")
        
        try:
            df = pd.read_excel(uploaded_file)
            print(f"[DEBUG] Excel loaded: {len(df)} rows, columns: {list(df.columns)}")
            
            col_sports = find_column(df, ['Sports Category', 'Sport Category'])
            col_factory = find_column(df, ['T1 Factory Short Code', 'T1 Factory', 'Factory Short Code', 'Factory'])
            col_article_name = find_column(df, ['Model Name Short', 'Article NAME', 'Article Name'])
            col_model = find_column(df, ['Model', 'MODEL'])
            col_article_number = find_column(df, ['Article NUMBER', 'Article Number', 'Article'])
            col_pre_confirm = find_column(df, ['Pre-Confirm Date', 'PreConfirm Date'])
            col_leading_buy = find_column(df, ['Leading Buy Ready Date', 'LeadingBuyReadyDate'])
            col_weight = find_column(df, ['Product Weight', 'ProductWeight', 'Product Weight (g)', 'Weight', 'Prod Weight'])
            col_lifecycle = find_column(df, ['Article Season Lifecycle State', 'Lifecycle State', 'Season Lifecycle State', 'LifecycleState'])
            
            print(f"[DEBUG] Column mapping: sports={col_sports}, factory={col_factory}, article_name={col_article_name}, model={col_model}, article_number={col_article_number}")
            print(f"[DEBUG] Extra columns: pre_confirm={col_pre_confirm}, leading_buy={col_leading_buy}, weight={col_weight}, lifecycle={col_lifecycle}")
            
            # Debug: warn about unmapped columns
            unmapped = []
            if not col_weight:
                unmapped.append('Product Weight')
            if not col_lifecycle:
                unmapped.append('Lifecycle State')
            if unmapped:
                st.warning(f"⚠️ Không tìm thấy cột: **{', '.join(unmapped)}** trong file Excel. Dữ liệu cũ sẽ được giữ nguyên.\n\nCác cột trong file: {', '.join(df.columns.tolist())}")
            
            # Allowed factories (HWA only - matches global constant)
            ALLOWED_FACTORIES = ['HWA']
            
            if col_sports and col_article_number:
                df[col_sports] = df[col_sports].astype(str).str.upper().str.strip()
                df_filtered = df[df[col_sports].isin(ALLOWED_SPORTS)]
                print(f"[DEBUG] After sports filter: {len(df_filtered)} rows (from {len(df)})")
                
                unique_sports = df[col_sports].unique().tolist()
                print(f"[DEBUG] Unique sports in file: {unique_sports}")
                
                # Also filter by factory if column exists
                if col_factory:
                    df_filtered[col_factory] = df_filtered[col_factory].astype(str).str.upper().str.strip()
                    before_factory = len(df_filtered)
                    df_filtered = df_filtered[df_filtered[col_factory].isin(ALLOWED_FACTORIES)]
                    print(f"[DEBUG] After factory filter: {len(df_filtered)} rows (from {before_factory})")
                    if before_factory > 0 and len(df_filtered) == 0:
                        unique_factories = df[col_factory].astype(str).str.upper().str.strip().unique().tolist()
                        print(f"[DEBUG] Unique factories in file: {unique_factories}")
                        st.warning(f"⚠️ Factory filter loại hết data. Các factory trong file: {', '.join(unique_factories[:20])}")
                
                if len(df_filtered) > 0:
                    save_data = pd.DataFrame({
                        'Factory': df_filtered[col_factory].astype(str).str.upper().str.strip() if col_factory else '',
                        'Sports Category': df_filtered[col_sports] if col_sports else '',
                        'Article NAME': df_filtered[col_article_name] if col_article_name else '',
                        'Model': df_filtered[col_model] if col_model else '',
                        'Article NUMBER': df_filtered[col_article_number] if col_article_number else '',
                        'Pre-Confirm Date': df_filtered[col_pre_confirm] if col_pre_confirm else '',
                        'Leading Buy Ready Date': df_filtered[col_leading_buy] if col_leading_buy else '',
                        'Product Weight': df_filtered[col_weight] if col_weight else None,
                        'Lifecycle State': df_filtered[col_lifecycle] if col_lifecycle else None,
                    })
                    
                    print(f"[DEBUG] Saving {len(save_data)} rows to DB...")
                    inserted, updated, unchanged, skipped, new_articles, changed_articles, archived_list = save_to_db(save_data)
                    print(f"[DEBUG] Save result: inserted={inserted}, updated={updated}, unchanged={unchanged}, archived={len(archived_list)}, skipped={skipped}")
                    
                    # Store in session state for highlighting
                    st.session_state.new_articles = new_articles
                    st.session_state.changed_articles = list(changed_articles.keys())
                    
                    # Show summary
                    total_changes = inserted + updated + len(archived_list)
                    if total_changes == 0:
                        result_msg = f"ℹ️ **Không có thay đổi nào.** {unchanged} articles giữ nguyên, {skipped} bỏ qua."
                        st.session_state['last_process_result'] = result_msg
                        st.session_state['last_process_result_type'] = 'info'
                    else:
                        result_msg = f"✅ **Buy Ready Report** — **{inserted}** mới | **{updated}** thay đổi | **{unchanged}** giữ nguyên | **{len(archived_list)}** archived"
                        if new_articles:
                            result_msg += f"\n\n🆕 **Articles mới:** {', '.join(new_articles[:15])}" + ("..." if len(new_articles) > 15 else "")
                        if changed_articles:
                            result_msg += f"\n\n📝 **Articles thay đổi:**"
                            for art, changes in list(changed_articles.items())[:15]:
                                result_msg += f"\n- `{art}`: {' | '.join(changes)}"
                            if len(changed_articles) > 15:
                                result_msg += f"\n- ...và {len(changed_articles) - 15} articles khác"
                        if archived_list:
                            result_msg += f"\n\n📦 **Archived (hoàn thành):** {', '.join(archived_list[:10])}" + ("..." if len(archived_list) > 10 else "")
                        st.session_state['last_process_result'] = result_msg
                        st.session_state['last_process_result_type'] = 'success'
                    st.session_state['last_processed_file'] = file_key
                    st.rerun()
                else:
                    st.warning("⚠️ Không tìm thấy data phù hợp (Sports: AMERICAN FOOTBALL, BASEBALL, SOFTBALL | Factory: HWA)")
            else:
                st.error(f"❌ Không tìm thấy cột bắt buộc: Sports Category={'✅' if col_sports else '❌'}, Article Number={'✅' if col_article_number else '❌'}\n\nCác cột trong file: {', '.join(df.columns.tolist())}")
        except Exception as e:
            st.error(f"❌ Lỗi xử lý Buy Ready Report: {str(e)}")
            print(f"[DEBUG] Buy Ready ERROR: {e}")
            import traceback
            traceback.print_exc()
    
    elif file_type == 'drop_report':  # noqa
        # Get all sheet names
        xl = pd.ExcelFile(uploaded_file)
        sheet_names = xl.sheet_names
        
        st.info(f"📋 Detected: **Drop Report** ({len(sheet_names)} sheets: {', '.join(sheet_names)})")
        print(f"[DEBUG] Drop Report: {len(sheet_names)} sheets: {sheet_names}")
        
        all_data = []
        try:
            for sheet in sheet_names:
                df_sheet = pd.read_excel(uploaded_file, sheet_name=sheet)
                print(f"[DEBUG] Sheet '{sheet}': {len(df_sheet)} rows, columns: {list(df_sheet.columns)}")
                
                col_sports = find_column(df_sheet, ['Sports Category', 'Sport Category'])
                col_factory = find_column(df_sheet, ['T1 Factory Short Code', 'T1 Factory', 'Factory Short Code', 'Factory'])
                col_article_name = find_column(df_sheet, ['Model Name Short', 'Article NAME', 'Article Name'])
                col_model = find_column(df_sheet, ['Model', 'MODEL'])
                col_article_number = find_column(df_sheet, ['Article NUMBER', 'Article Number', 'Article'])
                
                print(f"[DEBUG] Sheet '{sheet}' columns: sports={col_sports}, factory={col_factory}, article_name={col_article_name}, article_number={col_article_number}")
                
                if col_article_number:
                    # Get all data from sheet
                    sheet_data = pd.DataFrame({
                        'Season': sheet,
                        'Factory': df_sheet[col_factory].astype(str).str.upper().str.strip() if col_factory else '',
                        'Sports Category': df_sheet[col_sports].astype(str).str.upper().str.strip() if col_sports else '',
                        'Article NAME': df_sheet[col_article_name] if col_article_name else '',
                        'Model': df_sheet[col_model] if col_model else '',
                        'Article NUMBER': df_sheet[col_article_number] if col_article_number else '',
                    })
                    
                    before_sports = len(sheet_data)
                    # Filter by sports
                    if col_sports:
                        unique_sports = sheet_data['Sports Category'].unique().tolist()
                        print(f"[DEBUG] Sheet '{sheet}' unique sports: {unique_sports}")
                        sheet_data = sheet_data[sheet_data['Sports Category'].isin(ALLOWED_SPORTS)]
                    print(f"[DEBUG] Sheet '{sheet}' after sports filter: {len(sheet_data)} rows (from {before_sports})")
                    
                    # Filter by factory (only HWA for Drop Report)
                    ALLOWED_FACTORIES_DROP = ['HWA']
                    if col_factory:
                        before_factory = len(sheet_data)
                        unique_factories = sheet_data['Factory'].unique().tolist()
                        print(f"[DEBUG] Sheet '{sheet}' unique factories: {unique_factories}")
                        sheet_data = sheet_data[sheet_data['Factory'].isin(ALLOWED_FACTORIES_DROP)]
                        print(f"[DEBUG] Sheet '{sheet}' after factory filter: {len(sheet_data)} rows (from {before_factory})")
                    
                    if len(sheet_data) > 0:
                        all_data.append(sheet_data)
                        print(f"[DEBUG] Sheet '{sheet}': {len(sheet_data)} rows added to save list")
                    else:
                        print(f"[DEBUG] Sheet '{sheet}': 0 rows after filtering - SKIPPED")
                else:
                    print(f"[DEBUG] Sheet '{sheet}': col_article_number not found - SKIPPED")
            
            if all_data:
                combined = pd.concat(all_data, ignore_index=True)
                print(f"[DEBUG] Total Drop rows to save: {len(combined)}")
                inserted, updated, unchanged, archived, skipped, new_articles, changed_articles, archived_list = save_drop_to_db(combined)
                print(f"[DEBUG] Drop save result: inserted={inserted}, updated={updated}, unchanged={unchanged}, archived={archived}, skipped={skipped}")
                
                # Store new articles for DROP highlighting
                st.session_state.drop_new_articles = new_articles
                
                total_changes = inserted + updated + archived
                if total_changes == 0:
                    result_msg = f"ℹ️ **Không có thay đổi nào.** {unchanged} articles giữ nguyên, {skipped} bỏ qua."
                    st.session_state['last_process_result'] = result_msg
                    st.session_state['last_process_result_type'] = 'info'
                else:
                    result_msg = f"✅ **Drop Report** — **{inserted}** mới | **{updated}** thay đổi | **{unchanged}** giữ nguyên | **{archived}** archived"
                    if new_articles:
                        result_msg += f"\n\n🆕 **Articles mới:** {', '.join(new_articles[:15])}" + ("..." if len(new_articles) > 15 else "")
                    if changed_articles:
                        result_msg += f"\n\n📝 **Articles thay đổi:**"
                        for art, changes in list(changed_articles.items())[:15]:
                            result_msg += f"\n- `{art}`: {' | '.join(changes)}"
                        if len(changed_articles) > 15:
                            result_msg += f"\n- ...và {len(changed_articles) - 15} articles khác"
                    if archived_list:
                        result_msg += f"\n\n📦 **Archived:** {', '.join(archived_list[:10])}" + ("..." if len(archived_list) > 10 else "")
                    st.session_state['last_process_result'] = result_msg
                    st.session_state['last_process_result_type'] = 'success'
                st.session_state['last_processed_file'] = file_key
                st.rerun()
            else:
                st.warning("⚠️ Drop Report: Không tìm thấy data phù hợp sau khi filter (Sports: AMERICAN FOOTBALL, BASEBALL, SOFTBALL | Factory: HWA)")
                print("[DEBUG] Drop Report: all_data is empty after filtering all sheets")
        except Exception as e:
            st.error(f"❌ Lỗi xử lý Drop Report: {str(e)}")
            print(f"[DEBUG] Drop Report ERROR: {e}")
            import traceback
            traceback.print_exc()

    # 'unknown' file_type is handled above in the guard block

# ==================== BR SECTION ====================
br_data = load_from_db()

if len(br_data) > 0:
    st.markdown("---")
    
    # Section header with timestamp
    col_header, col_time = st.columns([3, 1])
    with col_header:
        st.markdown("<h2 class='section-header'>📦 Buy Ready Report</h2>", unsafe_allow_html=True)
    with col_time:
        current_time = datetime.now().strftime("%d/%m/%Y %H:%M")
        st.markdown(f"<div class='timestamp'>🕐 Cập nhật: {current_time}</div>", unsafe_allow_html=True)
    
    # Check if columns exist
    has_factory = 'factory' in br_data.columns
    has_ft = 'ft_status' in br_data.columns
    has_wt = 'wt_status' in br_data.columns
    has_lifecycle = 'lifecycle_state' in br_data.columns
    
    df_br = pd.DataFrame({
        'Factory': br_data['factory'] if has_factory else '',
        'Sports Category': br_data['sports_category'],
        'Lifecycle State': br_data['lifecycle_state'] if has_lifecycle else '',
        'Article NAME': br_data['article_name'],
        'Model': br_data['model'],
        'Article NUMBER': br_data['article_number'],
        'Pre-Confirm Date': pd.to_datetime(br_data['pre_confirm_date'], errors='coerce'),
        'Leading Buy Ready Date': pd.to_datetime(br_data['leading_buy_ready_date'], errors='coerce'),
        'Product Weight': br_data['product_weight'],
        'MCS status': br_data['mcs_status'],
        'FGT status': br_data['fgt_status'],
        'FT status': br_data['ft_status'] if has_ft else '',
        'WT status': br_data['wt_status'] if has_wt else '',
    })
    
    # Add Change indicator column based on session state
    new_articles = st.session_state.get('new_articles', [])
    changed_articles = st.session_state.get('changed_articles', [])
    
    def get_change_indicator(article_number):
        if article_number in new_articles:
            return '🆕 NEW'
        elif article_number in changed_articles:
            return '📅 Changed'
        return ''
    
    df_br['Change'] = df_br['Article NUMBER'].apply(get_change_indicator)
    
    df_br = df_br.sort_values(
        by=['Leading Buy Ready Date', 'Model', 'Article NAME'],
        ascending=[True, True, True],
        na_position='last'
    )
    df_br = df_br.reset_index(drop=True)
    df_br.insert(0, 'STT', range(1, len(df_br) + 1))
    
    # Filters - Reorganized 2x2 layout (Factory removed - HWA only)
    st.markdown("#### 🔍 Bộ lọc")
    
    # Check if chart click set a filter — directly set selectbox session state keys
    chart_selected_date = st.session_state.get('chart_active_date', None)
    chart_selected_sport = st.session_state.get('chart_active_sport', None)
    
    # Show active chart filter banner + clear button
    if chart_selected_date or chart_selected_sport:
        filter_parts = []
        if chart_selected_date:
            filter_parts.append(f"📅 {chart_selected_date}")
        if chart_selected_sport:
            filter_parts.append(f"🏈 {chart_selected_sport}")
        col_banner, col_clear = st.columns([4, 1])
        with col_banner:
            st.info(f"📊 Chart filter active: {' | '.join(filter_parts)}")
        with col_clear:
            if st.button("❌ Clear filter", key='clear_chart_filter'):
                st.session_state.pop('chart_active_date', None)
                st.session_state.pop('chart_active_sport', None)
                st.session_state['br_date'] = '-- Tất cả --'
                st.session_state['br_sport'] = '-- Tất cả --'
                st.rerun()
    
    # Row 1: Sports + Date
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        sports_list = df_br['Sports Category'].unique().tolist()
        selected_sport = st.selectbox("🏈 Sports Category", ['-- Tất cả --'] + sports_list, key='br_sport')
    with col_f2:
        dates = df_br['Leading Buy Ready Date'].dropna().dt.date.unique()
        dates_sorted = sorted(dates) if len(dates) > 0 else []
        date_opts = ['-- Tất cả --'] + [str(d) for d in dates_sorted]
        selected_date = st.selectbox("📅 Leading Buy Ready Date", date_opts, key='br_date')
    
    # Row 2: Search + Status
    col_f3, col_f4 = st.columns(2)
    with col_f3:
        search_query = st.text_input("🔍 Tìm kiếm Article", placeholder="Nhập Article NAME hoặc NUMBER...", key='br_search')
    with col_f4:
        status_opts = ['-- Tất cả --', '✅ PASSED', '⏳ NOT YET UPDATED', '🔴 PENDING', '🔄 Processing']
        selected_status = st.selectbox("📊 Overall Status", status_opts, key='br_status')
    
    st.markdown("---")
    
    # Calculate Overall Status first (before filtering)
    def get_overall_status(row):
        mcs = str(row.get('MCS status', '')).upper().strip()
        fgt = str(row.get('FGT status', '')).upper().strip()
        ft = str(row.get('FT status', '')).upper().strip()
        wt = str(row.get('WT status', '')).upper().strip()
        
        # Check if all empty
        if mcs == '' and fgt == '' and ft == '' and wt == '':
            return '⏳ NOT YET UPDATED'
        
        # Check if any PENDING, ETD, ETC, or SENT
        all_statuses = mcs + ' ' + fgt + ' ' + ft + ' ' + wt
        if 'PENDING' in all_statuses or 'ETD' in all_statuses or 'ETC' in all_statuses or 'SENT' in all_statuses:
            return '🔴 PENDING'
        
        # Check if PASSED - fgt can be 'PASSED', 'PASSED (FD approved)', etc.
        if mcs == 'APPROVED' and fgt.startswith('PASSED'):
            return '✅ PASSED'
        
        return '🔄 Processing'
    
    df_br['Status'] = df_br.apply(get_overall_status, axis=1)
    
    # Apply filters (Factory filter removed)
    df_br_filtered = df_br.copy()
    if selected_sport != '-- Tất cả --':
        df_br_filtered = df_br_filtered[df_br_filtered['Sports Category'] == selected_sport]
    if selected_date != '-- Tất cả --':
        target_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
        df_br_filtered = df_br_filtered[df_br_filtered['Leading Buy Ready Date'].dt.date == target_date]
    if selected_status != '-- Tất cả --':
        df_br_filtered = df_br_filtered[df_br_filtered['Status'] == selected_status]
    
    # Apply search filter
    if search_query:
        search_lower = search_query.lower().strip()
        df_br_filtered = df_br_filtered[
            df_br_filtered['Article NAME'].astype(str).str.lower().str.contains(search_lower, na=False) |
            df_br_filtered['Article NUMBER'].astype(str).str.lower().str.contains(search_lower, na=False) |
            df_br_filtered['Model'].astype(str).str.lower().str.contains(search_lower, na=False)
        ]
    
    df_br_filtered = df_br_filtered.reset_index(drop=True)
    df_br_filtered['STT'] = range(1, len(df_br_filtered) + 1)
    
    # ==================== ANALYTICS SECTION (V3.1) ====================
    with st.expander("📊 Analytics Dashboard", expanded=True):
        if len(df_br_filtered) > 0:
            col_chart1, col_chart2 = st.columns(2)
            
            # Chart 1: Status Distribution (Donut)
            with col_chart1:
                st.markdown("##### 📈 Status Distribution")
                status_counts = df_br_filtered['Status'].value_counts()
                
                # Define colors matching V3 theme (map with emojis for values)
                color_map = {
                    '✅ PASSED': '#10b981',           # green
                    '🔄 Processing': '#667eea',        # purple
                    '🔴 PENDING': '#f59e0b',           # yellow
                    '⏳ NOT YET UPDATED': '#a0aec0'    # gray
                }
                
                # Clean labels (remove emojis for chart display)
                label_map = {
                    '✅ PASSED': 'PASSED',
                    '🔄 Processing': 'Processing',
                    '🔴 PENDING': 'PENDING',
                    '⏳ NOT YET UPDATED': 'NOT YET UPDATED'
                }
                
                colors = [color_map.get(status, '#a0aec0') for status in status_counts.index]
                clean_labels = [label_map.get(status, status) for status in status_counts.index]
                
                fig_status = go.Figure(data=[go.Pie(
                    labels=clean_labels,
                    values=status_counts.values,
                    hole=0.5,  # Donut chart
                    marker=dict(colors=colors, line=dict(color='#1a1a2e', width=2)),
                    textfont=dict(size=14, color='white'),
                    hovertemplate='<b>%{label}</b><br>Count: %{value}<br>%{percent}<extra></extra>'
                )])
                
                fig_status.update_layout(
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    font=dict(color='#e2e8f0'),
                    showlegend=True,
                    legend=dict(
                        orientation="h",
                        yanchor="bottom",
                        y=-0.2,
                        xanchor="center",
                        x=0.5,
                        font=dict(size=12)
                    ),
                    height=350,
                    margin=dict(t=30, b=20, l=20, r=20)
                )
                
                st.plotly_chart(fig_status, use_container_width=True)
            
            # Chart 2: Article Count by Date & Sport (Grouped Bar)
            with col_chart2:
                st.markdown("##### 📅 Articles by Date & Sport")
                
                # Create Dugout category (Baseball + Softball)
                # Use FULL data (df_br) so chart always shows all dates for clicking
                df_timeline = df_br.copy()
                df_timeline['Sport Group'] = df_timeline['Sports Category'].apply(
                    lambda x: 'American Football' if x == 'AMERICAN FOOTBALL' else 'Dugout'
                )
                
                # Group by date and sport
                timeline_grouped = df_timeline.groupby([
                    df_timeline['Leading Buy Ready Date'].dt.date,
                    'Sport Group'
                ]).size().reset_index(name='count')
                timeline_grouped.columns = ['date', 'sport', 'count']
                timeline_grouped = timeline_grouped.sort_values('date')
                
                # Format dates for display (mm/dd/yyyy)
                timeline_grouped['date_label'] = timeline_grouped['date'].apply(
                    lambda d: d.strftime('%m/%d/%Y') if d else ''
                )
                
                fig_grouped = go.Figure()
                
                # American Football bars
                af_data = timeline_grouped[timeline_grouped['sport'] == 'American Football']
                if len(af_data) > 0:
                    fig_grouped.add_trace(go.Bar(
                        y=af_data['date_label'],
                        x=af_data['count'],
                        name='🏈 Am. Football',
                        orientation='h',
                        marker=dict(color='#f5576c', line=dict(color='#1a1a2e', width=1)),
                        text=af_data['count'],
                        textposition='auto',
                        textfont=dict(size=12, color='white'),
                        hovertemplate='<b>Am. Football</b><br>%{y}<br>Count: %{x}<extra></extra>'
                    ))
                
                # Dugout bars
                dugout_data = timeline_grouped[timeline_grouped['sport'] == 'Dugout']
                if len(dugout_data) > 0:
                    fig_grouped.add_trace(go.Bar(
                        y=dugout_data['date_label'],
                        x=dugout_data['count'],
                        name='⚾ Dugout',
                        orientation='h',
                        marker=dict(color='#38ef7d', line=dict(color='#1a1a2e', width=1)),
                        text=dugout_data['count'],
                        textposition='auto',
                        textfont=dict(size=12, color='white'),
                        hovertemplate='<b>Dugout</b><br>%{y}<br>Count: %{x}<extra></extra>'
                    ))
                
                # Get all unique date labels sorted by actual date
                all_dates = timeline_grouped.sort_values('date')['date_label'].unique().tolist()
                
                fig_grouped.update_layout(
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    font=dict(color='#e2e8f0'),
                    barmode='group',  # Group bars side by side
                    xaxis=dict(
                        showgrid=True,
                        gridcolor='rgba(160, 174, 192, 0.1)',
                        title='Article Count',
                        tickmode='linear',
                        dtick=1
                    ),
                    yaxis=dict(
                        showgrid=False,
                        title='Buy Ready Date',
                        categoryorder='array',
                        categoryarray=all_dates
                    ),
                    height=400,
                    margin=dict(t=30, b=40, l=100, r=20),
                    legend=dict(
                        orientation='h',
                        yanchor='bottom',
                        y=1.02,
                        xanchor='center',
                        x=0.5
                    )
                )
                
                # Interactive chart - click to filter
                event = st.plotly_chart(fig_grouped, use_container_width=True, on_select='rerun', key='chart_date_sport')
                
                # Handle chart click events — on_select='rerun' already triggers rerun
                # so we just set the filter values here, NO extra st.rerun() needed
                if event and event.selection and event.selection.points:
                    point = event.selection.points[0]
                    clicked_date = point.get('y', None)  # date_label like '04/06/2026'
                    curve_num = point.get('curve_number', 0)
                    clicked_sport = 'American Football' if curve_num == 0 else 'Dugout'
                    
                    # Only update if this is a new click (different from current filter)
                    current_date = st.session_state.get('chart_active_date', None)
                    current_sport = st.session_state.get('chart_active_sport', None)
                    if clicked_date != current_date or clicked_sport != current_sport:
                        # Set banner display keys
                        st.session_state['chart_active_date'] = clicked_date
                        st.session_state['chart_active_sport'] = clicked_sport
                        # Set selectbox values directly
                        if clicked_date:
                            try:
                                from datetime import datetime as dt_parse
                                parsed = dt_parse.strptime(clicked_date, '%m/%d/%Y').date()
                                st.session_state['br_date'] = str(parsed)
                            except:
                                pass
                        if clicked_sport == 'American Football':
                            st.session_state['br_sport'] = 'AMERICAN FOOTBALL'
                        else:
                            st.session_state['br_sport'] = '-- Tất cả --'
                        st.rerun()
            
            # Chart 3: DONE vs PENDING Overview (V3.3)
            st.markdown("---")
            st.markdown("##### 📊 Signing Progress Overview")
            
            try:
                archived_br_data = load_archived_br()
                done_count = len(archived_br_data)
            except:
                done_count = 0
            
            pending_count = len(df_br_filtered)
            total_count = done_count + pending_count
            
            col_progress1, col_progress2 = st.columns(2)
            
            with col_progress1:
                # Progress bar chart
                fig_progress = go.Figure()
                
                fig_progress.add_trace(go.Bar(
                    y=['Articles'],
                    x=[done_count],
                    name='✅ DONE (Archived)',
                    orientation='h',
                    marker=dict(color='#10b981'),
                    text=[f'{done_count} DONE'],
                    textposition='inside',
                    textfont=dict(size=14, color='white'),
                    hovertemplate='<b>DONE</b><br>Count: %{x}<extra></extra>'
                ))
                
                fig_progress.add_trace(go.Bar(
                    y=['Articles'],
                    x=[pending_count],
                    name='🔴 PENDING (Current)',
                    orientation='h',
                    marker=dict(color='#f59e0b'),
                    text=[f'{pending_count} PENDING'],
                    textposition='inside',
                    textfont=dict(size=14, color='white'),
                    hovertemplate='<b>PENDING</b><br>Count: %{x}<extra></extra>'
                ))
                
                fig_progress.update_layout(
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    font=dict(color='#e2e8f0'),
                    barmode='stack',
                    xaxis=dict(
                        showgrid=True,
                        gridcolor='rgba(160, 174, 192, 0.1)',
                        title='Article Count'
                    ),
                    yaxis=dict(showgrid=False, showticklabels=False),
                    height=180,
                    margin=dict(t=30, b=30, l=20, r=20),
                    legend=dict(
                        orientation='h',
                        yanchor='bottom',
                        y=1.02,
                        xanchor='center',
                        x=0.5
                    )
                )
                
                st.plotly_chart(fig_progress, use_container_width=True)
            
            with col_progress2:
                # Stats cards
                if total_count > 0:
                    done_pct = (done_count / total_count) * 100
                else:
                    done_pct = 0
                
                st.markdown(f"""
                    <div style="display: flex; gap: 1rem; height: 100%;">
                        <div style="
                            flex: 1;
                            background: linear-gradient(135deg, #10b981 0%, #059669 100%);
                            padding: 1rem;
                            border-radius: 12px;
                            text-align: center;
                        ">
                            <div style="color: #d1fae5; font-size: 0.85rem;">✅ DONE</div>
                            <div style="color: white; font-size: 2rem; font-weight: 700;">{done_count}</div>
                            <div style="color: #d1fae5; font-size: 0.85rem;">{done_pct:.1f}%</div>
                        </div>
                        <div style="
                            flex: 1;
                            background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
                            padding: 1rem;
                            border-radius: 12px;
                            text-align: center;
                        ">
                            <div style="color: #fef3c7; font-size: 0.85rem;">🔴 PENDING</div>
                            <div style="color: white; font-size: 2rem; font-weight: 700;">{pending_count}</div>
                            <div style="color: #fef3c7; font-size: 0.85rem;">{100-done_pct:.1f}%</div>
                        </div>
                    </div>
                """, unsafe_allow_html=True)
        else:
            st.info("📊 No data available for analytics. Upload a file or adjust filters.")
    
    st.markdown("---")
    
    # Sports Stats
    st.markdown("#### 🏆 Thống kê theo Sports")
    col1, col2, col3, col4 = st.columns(4)
    sports_counts = df_br_filtered['Sports Category'].value_counts()
    
    with col1:
        st.markdown(f'<div class="stat-card"><div class="stat-number">{len(df_br_filtered)}</div><div class="stat-label">Tổng cộng</div></div>', unsafe_allow_html=True)
    with col2:
        st.markdown(f'<div class="stat-card"><div class="stat-number" style="background: linear-gradient(90deg, #f093fb 0%, #f5576c 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">{sports_counts.get("AMERICAN FOOTBALL", 0)}</div><div class="stat-label">🏈 Am. Football</div></div>', unsafe_allow_html=True)
    with col3:
        st.markdown(f'<div class="stat-card"><div class="stat-number" style="background: linear-gradient(90deg, #11998e 0%, #38ef7d 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">{sports_counts.get("BASEBALL", 0)}</div><div class="stat-label">⚾ Baseball</div></div>', unsafe_allow_html=True)
    with col4:
        st.markdown(f'<div class="stat-card"><div class="stat-number" style="background: linear-gradient(90deg, #667eea 0%, #764ba2 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">{sports_counts.get("SOFTBALL", 0)}</div><div class="stat-label">🥎 Softball</div></div>', unsafe_allow_html=True)
    
    # Factory Stats with Logos
    factory_counts = df_br_filtered['Factory'].value_counts()
    if len(factory_counts) > 0:
        st.markdown("#### 🏭 Thống kê theo Factory")
        
        # Load HWA logo
        logo_hwa_path = os.path.join(os.path.dirname(__file__), 'logo_hwa.png')
        logo_hwa_b64 = ""
        
        if os.path.exists(logo_hwa_path):
            with open(logo_hwa_path, "rb") as f:
                logo_hwa_b64 = base64.b64encode(f.read()).decode()
        
        factory_cols = st.columns(len(factory_counts))
        for i, (factory, count) in enumerate(factory_counts.items()):
            if factory and str(factory) != 'nan':
                with factory_cols[i]:
                    if factory == "HWA" and logo_hwa_b64:
                        logo_img = f'<img src="data:image/png;base64,{logo_hwa_b64}" style="height: 50px; margin-bottom: 10px; background: white; padding: 5px; border-radius: 8px;">'
                        color = "#4facfe"
                    else:
                        logo_img = '<div style="font-size: 2rem; margin-bottom: 10px;">🏭</div>'
                        color = "#667eea"
                    
                    st.markdown(f'''
<div class="stat-card" style="border-top: 3px solid {color};">
    {logo_img}
    <div style="font-size: 2.5rem; font-weight: 700; color: {color};">{count}</div>
    <div class="stat-label">{factory}</div>
</div>''', unsafe_allow_html=True)
    
    
    # ==================== TABLE SECTION ====================
    st.markdown("#### 📋 Bảng dữ liệu")
    
    # Apply timeline filter from sidebar
    if 'timeline_filter' in st.session_state and st.session_state.timeline_filter:
        df_br_filtered = df_br_filtered[
            df_br_filtered['Article NUMBER'].astype(str).str.contains(st.session_state.timeline_filter, na=False)
        ]
        df_br_filtered = df_br_filtered.reset_index(drop=True)
        df_br_filtered['STT'] = range(1, len(df_br_filtered) + 1)
    
    # Fragment to isolate data_editor reruns (performance optimization)
    @st.fragment
    def render_editable_table(df_filtered):
        """Render data editor in isolated fragment to prevent full app rerun"""
        edited_df = st.data_editor(
            df_filtered, use_container_width=True, num_rows="fixed",
            column_config={
                "STT": st.column_config.NumberColumn("STT", disabled=True, width="small"),
                "Change": st.column_config.TextColumn("Change", disabled=True, width="small"),
                "Factory": st.column_config.TextColumn("Factory", disabled=True),
                "Sports Category": st.column_config.TextColumn("Sports Category", disabled=True),
                "Lifecycle State": st.column_config.TextColumn("Lifecycle State", disabled=True),
                "Article NAME": st.column_config.TextColumn("Article NAME", disabled=True),
                "Model": st.column_config.TextColumn("Model", disabled=True),
                "Article NUMBER": st.column_config.TextColumn("Article NUMBER", disabled=True),
                "Pre-Confirm Date": st.column_config.DateColumn("Pre-Confirm Date", disabled=True),
                "Leading Buy Ready Date": st.column_config.DateColumn("Leading Buy Ready Date", disabled=True),
                "Product Weight": st.column_config.TextColumn("Product Weight", disabled=True),
                "MCS status": st.column_config.TextColumn("MCS status"),
                "FGT status": st.column_config.TextColumn("FGT status"),
                "FT status": st.column_config.TextColumn("FT status"),
                "WT status": st.column_config.TextColumn("WT status"),
                "Status": st.column_config.TextColumn("Status", disabled=True),
            },
            hide_index=True, height=400, key="br_editor"
        )
        
        # Manual save with scroll position preservation
        col_btn1, col_btn2 = st.columns([1, 4])
        with col_btn1:
            if st.button("💾 Lưu Status", type="primary", key="save_br"):
                update_all_statuses(edited_df)
                st.success("✅ Đã lưu! (Giữ nguyên vị trí)")
                # No st.rerun() to preserve scroll position
        
        with col_btn2:
            # Download BR data
            @st.cache_data
            def convert_br_to_excel(df):
                from io import BytesIO
                output = BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df.to_excel(writer, index=False, sheet_name='Buy Ready')
                return output.getvalue()
            
            br_excel = convert_br_to_excel(edited_df)
            st.download_button(
                label="📥 Tải xuống BR",
                data=br_excel,
                file_name=f"buy_ready_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="download_br"
            )
    
    # Render the fragment
    render_editable_table(df_br_filtered)

# ==================== DROP SECTION (Always show) ====================
st.markdown("---")

# Section header with timestamp
col_header_drop, col_time_drop = st.columns([3, 1])
with col_header_drop:
    st.markdown("<h2 class='section-header'>📉 Drop Report</h2>", unsafe_allow_html=True)
with col_time_drop:
    current_time_drop = datetime.now().strftime("%d/%m/%Y %H:%M")
    st.markdown(f"<div class='timestamp'>🕐 Cập nhật: {current_time_drop}</div>", unsafe_allow_html=True)

drop_data = load_drop_from_db()

if len(drop_data) > 0:
    has_factory = 'factory' in drop_data.columns
    
    df_drop = pd.DataFrame({
        'Season': drop_data['season'],
        'Factory': drop_data['factory'] if has_factory else '',
        'Sports Category': drop_data['sports_category'],
        'Article NAME': drop_data['article_name'],
        'Model': drop_data['model'],
        'Article NUMBER': drop_data['article_number'],
    })
    
    # Filter only HWA factory for Drop Report
    df_drop = df_drop[df_drop['Factory'] == 'HWA']
    
    # Remove Factory column since only HWA is shown
    df_drop = df_drop.drop(columns=['Factory'])
    
    # Custom sort: Season (SS→FW chronological), then Model, then Article NAME
    def season_sort_key(season):
        """Convert season like 'SS 2027', 'FW 2026', 'SS27', 'FW27' to sortable number.
        SS = 0, FW = 1 within each year. E.g. SS26=260, FW26=261, SS27=270, FW27=271"""
        s = str(season).strip().upper()
        prefix = 0 if s.startswith('SS') else 1
        # Extract year number - could be 2-digit or 4-digit
        import re
        year_match = re.search(r'(\d+)', s)
        if year_match:
            year = int(year_match.group(1))
            if year > 100:  # 4-digit year like 2027
                year = year % 100
            return year * 10 + prefix
        return 9999  # Unknown seasons go last
    
    df_drop['_season_sort'] = df_drop['Season'].apply(season_sort_key)
    df_drop = df_drop.sort_values(
        by=['_season_sort', 'Model', 'Article NAME'],
        ascending=[True, True, True],
        na_position='last'
    )
    df_drop = df_drop.drop(columns=['_season_sort'])
    
    df_drop = df_drop.reset_index(drop=True)
    df_drop.insert(0, 'STT', range(1, len(df_drop) + 1))
    
    # Filters (only Season and Sports, no Factory since it's always HWA)
    col_d1, col_d2 = st.columns(2)
    with col_d1:
        seasons = sorted(df_drop['Season'].unique().tolist())
        selected_season = st.selectbox("📅 Season", ['-- Tất cả --'] + seasons, key='drop_season')
    with col_d2:
        sports_drop = df_drop['Sports Category'].unique().tolist()
        selected_sport_drop = st.selectbox("🏈 Sports", ['-- Tất cả --'] + sports_drop, key='drop_sport')
    
    df_drop_filtered = df_drop.copy()
    if selected_season != '-- Tất cả --':
        df_drop_filtered = df_drop_filtered[df_drop_filtered['Season'] == selected_season]
    if selected_sport_drop != '-- Tất cả --':
        df_drop_filtered = df_drop_filtered[df_drop_filtered['Sports Category'] == selected_sport_drop]
    
    df_drop_filtered = df_drop_filtered.reset_index(drop=True)
    df_drop_filtered['STT'] = range(1, len(df_drop_filtered) + 1)
    
    # Stats
    st.markdown("#### 🏆 Thống kê theo Sports")
    col1, col2, col3, col4 = st.columns(4)
    drop_counts = df_drop_filtered['Sports Category'].value_counts()
    
    with col1:
        st.markdown(f'<div class="stat-card"><div class="stat-number">{len(df_drop_filtered)}</div><div class="stat-label">Tổng cộng</div></div>', unsafe_allow_html=True)
    with col2:
        st.markdown(f'<div class="stat-card"><div class="stat-number" style="background: linear-gradient(90deg, #f093fb 0%, #f5576c 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">{drop_counts.get("AMERICAN FOOTBALL", 0)}</div><div class="stat-label">🏈 Am. Football</div></div>', unsafe_allow_html=True)
    with col3:
        st.markdown(f'<div class="stat-card"><div class="stat-number" style="background: linear-gradient(90deg, #11998e 0%, #38ef7d 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">{drop_counts.get("BASEBALL", 0)}</div><div class="stat-label">⚾ Baseball</div></div>', unsafe_allow_html=True)
    with col4:
        st.markdown(f'<div class="stat-card"><div class="stat-number" style="background: linear-gradient(90deg, #667eea 0%, #764ba2 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">{drop_counts.get("SOFTBALL", 0)}</div><div class="stat-label">🥎 Softball</div></div>', unsafe_allow_html=True)
    
    # Table
    st.markdown("#### 📋 Bảng dữ liệu")
    st.dataframe(df_drop_filtered, use_container_width=True, height=400, hide_index=True)
    
    # Download button
    @st.cache_data
    def convert_drop_to_excel(df):
        from io import BytesIO
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Drop Report')
        return output.getvalue()
    
    drop_excel = convert_drop_to_excel(df_drop_filtered)
    st.download_button(
        label="📥 Tải xuống Drop Report",
        data=drop_excel,
        file_name=f"drop_report_{datetime.now().strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="download_drop"
    )

else:
    # Empty state for Drop
    col_d1, col_d2 = st.columns(2)
    with col_d1:
        st.selectbox("📅 Season", ['-- Tất cả --'], key='drop_season_empty', disabled=True)
    with col_d2:
        st.selectbox("🏈 Sports", ['-- Tất cả --'], key='drop_sport_empty', disabled=True)
    
    # Empty stats
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown('<div class="stat-card"><div class="stat-number">0</div><div class="stat-label">Tổng</div></div>', unsafe_allow_html=True)
    with col2:
        st.markdown('<div class="stat-card"><div class="stat-number" style="background: linear-gradient(90deg, #f093fb 0%, #f5576c 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">0</div><div class="stat-label">🏈 Am. Football</div></div>', unsafe_allow_html=True)
    with col3:
        st.markdown('<div class="stat-card"><div class="stat-number" style="background: linear-gradient(90deg, #11998e 0%, #38ef7d 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">0</div><div class="stat-label">⚾ Baseball</div></div>', unsafe_allow_html=True)
    with col4:
        st.markdown('<div class="stat-card"><div class="stat-number" style="background: linear-gradient(90deg, #667eea 0%, #764ba2 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">0</div><div class="stat-label">🥎 Softball</div></div>', unsafe_allow_html=True)
    
    # Empty table
    empty_df = pd.DataFrame(columns=['STT', 'Season', 'Sports Category', 'Article NAME', 'Model', 'Article NUMBER'])
    st.dataframe(empty_df, use_container_width=True, height=200, hide_index=True)
    st.info("📋 Upload file Drop Report để hiển thị dữ liệu")
