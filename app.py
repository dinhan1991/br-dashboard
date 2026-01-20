import streamlit as st
import pandas as pd
import sqlite3
import os
from datetime import datetime

# Page configuration
st.set_page_config(
    page_title="BR tracking",
    page_icon="🏈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Database path
DB_PATH = os.path.join(os.path.dirname(__file__), 'data.db')

# Database functions
def init_db():
    """Initialize SQLite database"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Buy Ready table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            factory TEXT,
            sports_category TEXT,
            article_name TEXT,
            model TEXT,
            article_number TEXT UNIQUE,
            pre_confirm_date TEXT,
            leading_buy_ready_date TEXT,
            product_weight TEXT,
            mcs_status TEXT DEFAULT '',
            fgt_status TEXT DEFAULT '',
            ft_status TEXT DEFAULT '',
            wt_status TEXT DEFAULT '',
            created_at TEXT,
            updated_at TEXT
        )
    ''')
    
    # Add factory column if not exists (migration)
    try:
        cursor.execute('ALTER TABLE articles ADD COLUMN factory TEXT')
    except:
        pass
    
    # Add ft_status and wt_status columns (migration from ft_wt_status)
    try:
        cursor.execute('ALTER TABLE articles ADD COLUMN ft_status TEXT DEFAULT ""')
    except:
        pass
    try:
        cursor.execute('ALTER TABLE articles ADD COLUMN wt_status TEXT DEFAULT ""')
    except:
        pass
    
    # Add lifecycle_state column
    try:
        cursor.execute('ALTER TABLE articles ADD COLUMN lifecycle_state TEXT DEFAULT ""')
    except:
        pass
    
    # Drop Report table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS drop_articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            season TEXT,
            factory TEXT,
            sports_category TEXT,
            article_name TEXT,
            model TEXT,
            article_number TEXT,
            created_at TEXT,
            updated_at TEXT,
            UNIQUE(season, article_number)
        )
    ''')
    
    # Add factory column to drop_articles if not exists (migration)
    try:
        cursor.execute('ALTER TABLE drop_articles ADD COLUMN factory TEXT')
    except:
        pass
    
    conn.commit()
    conn.close()

def load_from_db():
    """Load Buy Ready data from database"""
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM articles ORDER BY leading_buy_ready_date ASC", conn)
    conn.close()
    return df

def load_drop_from_db():
    """Load Drop Report data from database"""
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM drop_articles ORDER BY season, sports_category", conn)
    conn.close()
    return df

def save_to_db(df_new):
    """Save Buy Ready data to database. Returns (inserted, updated, deleted, skipped, new_articles, changed_articles)"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    inserted = 0
    updated = 0
    skipped = 0
    new_articles = []  # List of new article numbers
    changed_articles = []  # List of articles with changed Leading Buy Ready Date
    
    # Get all article numbers from new file
    new_article_numbers = set()
    for _, row in df_new.iterrows():
        article_number = str(row.get('Article NUMBER', '')).strip()
        if article_number and article_number != 'nan':
            new_article_numbers.add(article_number)
    
    # Get existing articles to compare Leading Buy Ready Date
    existing_articles = {}
    cursor.execute("SELECT article_number, leading_buy_ready_date FROM articles")
    for row in cursor.fetchall():
        existing_articles[row[0]] = row[1]
    
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
            # Check if Leading Buy Ready Date changed
            old_date = existing_articles[article_number] or ''
            if old_date != str(leading_buy):
                changed_articles.append(article_number)
            
            cursor.execute('''
                UPDATE articles SET
                    factory = ?, sports_category = ?, article_name = ?, model = ?,
                    pre_confirm_date = ?, leading_buy_ready_date = ?,
                    product_weight = ?, lifecycle_state = ?, updated_at = ?
                WHERE article_number = ?
            ''', (
                str(row.get('Factory', '')),
                str(row.get('Sports Category', '')),
                str(row.get('Article NAME', '')),
                str(row.get('Model', '')),
                str(pre_confirm), str(leading_buy),
                str(row.get('Product Weight', '')),
                str(row.get('Lifecycle State', '')),
                now, article_number
            ))
            updated += 1
        else:
            new_articles.append(article_number)
            cursor.execute('''
                INSERT INTO articles (
                    factory, sports_category, article_name, model, article_number,
                    pre_confirm_date, leading_buy_ready_date, product_weight, lifecycle_state,
                    mcs_status, fgt_status, ft_status, wt_status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '', '', '', '', ?, ?)
            ''', (
                str(row.get('Factory', '')),
                str(row.get('Sports Category', '')),
                str(row.get('Article NAME', '')),
                str(row.get('Model', '')),
                article_number, str(pre_confirm), str(leading_buy),
                str(row.get('Product Weight', '')),
                str(row.get('Lifecycle State', '')),
                now, now
            ))
            inserted += 1
    
    # Delete articles not in new file
    deleted = 0
    for old_article in existing_articles.keys():
        if old_article not in new_article_numbers:
            cursor.execute("DELETE FROM articles WHERE article_number = ?", (old_article,))
            deleted += 1
    
    conn.commit()
    conn.close()
    return inserted, updated, deleted, skipped, new_articles, changed_articles

def save_drop_to_db(df_new):
    """Save Drop Report data to database"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    inserted = 0
    updated = 0
    skipped = 0
    
    for _, row in df_new.iterrows():
        article_number = str(row.get('Article NUMBER', '')).strip()
        season = str(row.get('Season', '')).strip()
        
        if not article_number or article_number == 'nan' or not season:
            skipped += 1
            continue
        
        cursor.execute("SELECT id FROM drop_articles WHERE season = ? AND article_number = ?", (season, article_number))
        existing = cursor.fetchone()
        
        now = datetime.now().isoformat()
        
        if existing:
            cursor.execute('''
                UPDATE drop_articles SET
                    factory = ?, sports_category = ?, article_name = ?, model = ?, updated_at = ?
                WHERE season = ? AND article_number = ?
            ''', (
                str(row.get('Factory', '')),
                str(row.get('Sports Category', '')),
                str(row.get('Article NAME', '')),
                str(row.get('Model', '')),
                now, season, article_number
            ))
            updated += 1
        else:
            cursor.execute('''
                INSERT INTO drop_articles (season, factory, sports_category, article_name, model, article_number, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                season,
                str(row.get('Factory', '')),
                str(row.get('Sports Category', '')),
                str(row.get('Article NAME', '')),
                str(row.get('Model', '')),
                article_number, now, now
            ))
            inserted += 1
    
    conn.commit()
    conn.close()
    return inserted, updated, skipped

def update_all_statuses(df):
    """Update all status columns from dataframe"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    
    for _, row in df.iterrows():
        article_number = str(row.get('Article NUMBER', '')).strip()
        if article_number and article_number != 'nan':
            cursor.execute('''
                UPDATE articles SET mcs_status = ?, fgt_status = ?, ft_status = ?, wt_status = ?, updated_at = ?
                WHERE article_number = ?
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
            <span class="version-tag">v2.0</span>
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
                <strong>Factory:</strong> HWA, SPG
            </p>
        </div>
    """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    # Database stats
    br_data = load_from_db()
    drop_data = load_drop_from_db()
    
    st.markdown("""
        <div class="sidebar-info">
            <h4 style="color: #e2e8f0; margin: 0 0 0.5rem 0;">💾 Database</h4>
        </div>
    """, unsafe_allow_html=True)
    
    # Factory breakdown for BR
    if len(br_data) > 0 and 'factory' in br_data.columns:
        factory_counts = br_data['factory'].value_counts()
        for factory, count in factory_counts.items():
            if factory and str(factory) != 'nan':
                st.markdown(f"""
                    <div class="factory-card">
                        <span class="factory-name">🏭 {factory}</span>
                        <span class="factory-count">{count}</span>
                    </div>
                """, unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    with col1:
        st.metric("📦 BR", len(br_data))
    with col2:
        st.metric("📉 Drop", len(drop_data))
    
    st.markdown("---")
    
    # ==================== TIMELINE IN SIDEBAR ====================
    if len(br_data) > 0:
        import re
        
        # Initialize timeline filter session state
        if 'timeline_filter' not in st.session_state:
            st.session_state.timeline_filter = None
        
        def extract_etd_date_sidebar(status_text):
            """Extract ETD date from status text"""
            if not status_text or str(status_text) == 'nan':
                return None
            match = re.search(r'ETD\s*(\d{1,2})/(\d{1,2})', str(status_text).upper())
            if match:
                month = int(match.group(1))
                day = int(match.group(2))
                year = datetime.now().year
                if month < datetime.now().month:
                    year += 1
                try:
                    return datetime(year, month, day).date()
                except:
                    return None
            return None
        
        # Extract timeline items
        timeline_items = []
        for _, row in br_data.iterrows():
            article = str(row.get('article_number', ''))
            factory = str(row.get('factory', ''))
            
            for col in ['mcs_status', 'fgt_status', 'ft_status', 'wt_status']:
                if col in br_data.columns:
                    status_val = str(row.get(col, ''))
                    etd_date = extract_etd_date_sidebar(status_val)
                    if etd_date:
                        timeline_items.append({
                            'Article': article,
                            'Factory': factory,
                            'ETD Date': etd_date,
                        })
        
        if timeline_items:
            today = datetime.now().date()
            overdue = [item for item in timeline_items if item['ETD Date'] < today]
            due_today = [item for item in timeline_items if item['ETD Date'] == today]
            upcoming = [item for item in timeline_items if item['ETD Date'] > today and item['ETD Date'] <= today + pd.Timedelta(days=7)]
            
            st.markdown("#### ⏰ Timeline")
            
            # Overdue
            if overdue:
                st.markdown(f'<div style="color: #e74c3c; font-weight: bold;">🚨 Quá hạn: {len(overdue)}</div>', unsafe_allow_html=True)
                for idx, item in enumerate(sorted(overdue, key=lambda x: x['ETD Date'])[:5]):  # Limit to 5
                    days_over = (today - item['ETD Date']).days
                    if st.button(f"⚠️ {item['Article']} (-{days_over}d)", key=f"sb_over_{idx}", use_container_width=True):
                        st.session_state.timeline_filter = item['Article']
                        st.rerun()
            
            # Today
            if due_today:
                st.markdown(f'<div style="color: #f39c12; font-weight: bold;">📅 Hôm nay: {len(due_today)}</div>', unsafe_allow_html=True)
                for idx, item in enumerate(due_today[:5]):
                    if st.button(f"🔔 {item['Article']}", key=f"sb_today_{idx}", use_container_width=True):
                        st.session_state.timeline_filter = item['Article']
                        st.rerun()
            
            # Upcoming
            if upcoming:
                st.markdown(f'<div style="color: #3498db; font-weight: bold;">📆 7 ngày tới: {len(upcoming)}</div>', unsafe_allow_html=True)
                for idx, item in enumerate(sorted(upcoming, key=lambda x: x['ETD Date'])[:5]):
                    days_left = (item['ETD Date'] - today).days
                    if st.button(f"⏳ {item['Article']} ({days_left}d)", key=f"sb_up_{idx}", use_container_width=True):
                        st.session_state.timeline_filter = item['Article']
                        st.rerun()
            
            # Clear filter button
            if st.session_state.timeline_filter:
                st.markdown("---")
                st.info(f"🔍 Filter: {st.session_state.timeline_filter}")
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
    file_type = detect_file_type(uploaded_file)
    
    if file_type == 'buy_ready':
        st.info("📋 Detected: **Buy Ready Report**")
        
        df = pd.read_excel(uploaded_file)
        col_sports = find_column(df, ['Sports Category', 'Sport Category'])
        col_factory = find_column(df, ['T1 Factory Short Code', 'T1 Factory', 'Factory Short Code', 'Factory'])
        col_article_name = find_column(df, ['Article NAME', 'Article Name'])
        col_model = find_column(df, ['Model', 'MODEL'])
        col_article_number = find_column(df, ['Article NUMBER', 'Article Number'])
        col_pre_confirm = find_column(df, ['Pre-Confirm Date', 'PreConfirm Date'])
        col_leading_buy = find_column(df, ['Leading Buy Ready Date', 'LeadingBuyReadyDate'])
        col_weight = find_column(df, ['Product Weight', 'ProductWeight'])
        col_lifecycle = find_column(df, ['Article Season Lifecycle State', 'Lifecycle State', 'Season Lifecycle State'])
        
        # Allowed factories
        ALLOWED_FACTORIES = ['HWA', 'SPG']
        
        if col_sports and col_article_number:
            df[col_sports] = df[col_sports].astype(str).str.upper().str.strip()
            df_filtered = df[df[col_sports].isin(ALLOWED_SPORTS)]
            
            # Also filter by factory if column exists
            if col_factory:
                df_filtered[col_factory] = df_filtered[col_factory].astype(str).str.upper().str.strip()
                df_filtered = df_filtered[df_filtered[col_factory].isin(ALLOWED_FACTORIES)]
            
            if len(df_filtered) > 0:
                save_data = pd.DataFrame({
                    'Factory': df_filtered[col_factory].astype(str).str.upper().str.strip() if col_factory else '',
                    'Sports Category': df_filtered[col_sports] if col_sports else '',
                    'Article NAME': df_filtered[col_article_name] if col_article_name else '',
                    'Model': df_filtered[col_model] if col_model else '',
                    'Article NUMBER': df_filtered[col_article_number] if col_article_number else '',
                    'Pre-Confirm Date': df_filtered[col_pre_confirm] if col_pre_confirm else '',
                    'Leading Buy Ready Date': df_filtered[col_leading_buy] if col_leading_buy else '',
                    'Product Weight': df_filtered[col_weight] if col_weight else '',
                    'Lifecycle State': df_filtered[col_lifecycle] if col_lifecycle else '',
                })
                
                inserted, updated, deleted, skipped, new_articles, changed_articles = save_to_db(save_data)
                
                # Store in session state for highlighting
                st.session_state.new_articles = new_articles
                st.session_state.changed_articles = changed_articles
                
                # Show summary
                msg = f"✅ **{inserted}** mới | **{updated}** cập nhật | **{deleted}** xóa | **{skipped}** bỏ qua"
                if new_articles:
                    msg += f"\n\n🆕 **Articles mới:** {', '.join(new_articles[:10])}" + ("..." if len(new_articles) > 10 else "")
                if changed_articles:
                    msg += f"\n\n📅 **Date thay đổi:** {', '.join(changed_articles[:10])}" + ("..." if len(changed_articles) > 10 else "")
                st.success(msg)
            else:
                st.warning("⚠️ Không tìm thấy data phù hợp (Sports: AMERICAN FOOTBALL, BASEBALL, SOFTBALL | Factory: HWA, SPG)")
    
    elif file_type == 'drop_report':
        # Get all sheet names
        xl = pd.ExcelFile(uploaded_file)
        sheet_names = xl.sheet_names
        
        st.info(f"📋 Detected: **Drop Report** ({len(sheet_names)} sheets: {', '.join(sheet_names)})")
        
        all_data = []
        for sheet in sheet_names:
            df_sheet = pd.read_excel(uploaded_file, sheet_name=sheet)
            col_sports = find_column(df_sheet, ['Sports Category', 'Sport Category'])
            col_factory = find_column(df_sheet, ['T1 Factory Short Code', 'T1 Factory', 'Factory Short Code', 'Factory'])
            col_article_name = find_column(df_sheet, ['Article NAME', 'Article Name'])
            col_model = find_column(df_sheet, ['Model', 'MODEL'])
            col_article_number = find_column(df_sheet, ['Article NUMBER', 'Article Number'])
            
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
                
                # Filter by sports
                if col_sports:
                    sheet_data = sheet_data[sheet_data['Sports Category'].isin(ALLOWED_SPORTS)]
                
                # Filter by factory (only HWA for Drop Report)
                ALLOWED_FACTORIES_DROP = ['HWA']
                if col_factory:
                    sheet_data = sheet_data[sheet_data['Factory'].isin(ALLOWED_FACTORIES_DROP)]
                
                if len(sheet_data) > 0:
                    all_data.append(sheet_data)
        
        if all_data:
            combined = pd.concat(all_data, ignore_index=True)
            inserted, updated, skipped = save_drop_to_db(combined)
            st.success(f"✅ **{inserted}** mới | **{updated}** cập nhật | **{skipped}** bỏ qua")
            st.rerun()

    else:
        st.warning("⚠️ Không thể xác định loại file. Tên file cần chứa 'Buy Ready' hoặc 'Drop'")

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
    
    df_br = df_br.sort_values('Leading Buy Ready Date', ascending=True, na_position='last')
    df_br = df_br.reset_index(drop=True)
    df_br.insert(0, 'STT', range(1, len(df_br) + 1))
    
    # Filters - 3 columns: Factory, Sports, Date
    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        factory_list = sorted([f for f in df_br['Factory'].unique().tolist() if f and f != 'nan'])
        selected_factory = st.selectbox("🏭 Factory", ['-- Tất cả --'] + factory_list, key='br_factory')
    with col_f2:
        sports_list = df_br['Sports Category'].unique().tolist()
        selected_sport = st.selectbox("🏈 Sports", ['-- Tất cả --'] + sports_list, key='br_sport')
    with col_f3:
        dates = df_br['Leading Buy Ready Date'].dropna().dt.date.unique()
        dates_sorted = sorted(dates) if len(dates) > 0 else []
        date_opts = ['-- Tất cả --'] + [str(d) for d in dates_sorted]
        selected_date = st.selectbox("📅 Date", date_opts, key='br_date')
    
    # Search box
    col_search, col_status = st.columns([3, 1])
    with col_search:
        search_query = st.text_input("🔍 Tìm kiếm Article", placeholder="Nhập Article NAME hoặc NUMBER...", key='br_search')
    with col_status:
        status_opts = ['-- Tất cả --', '✅ PASSED', '⏳ Chưa có', '🔴 PENDING', '🔄 Processing']
        selected_status = st.selectbox("📊 Status", status_opts, key='br_status')
    
    # Calculate Overall Status first (before filtering)
    def get_overall_status(row):
        mcs = str(row.get('MCS status', '')).upper().strip()
        fgt = str(row.get('FGT status', '')).upper().strip()
        ft = str(row.get('FT status', '')).upper().strip()
        wt = str(row.get('WT status', '')).upper().strip()
        
        # Check if all empty
        if mcs == '' and fgt == '' and ft == '' and wt == '':
            return '⏳ Chưa có'
        
        # Check if any PENDING, ETD, or SENT
        all_statuses = mcs + ' ' + fgt + ' ' + ft + ' ' + wt
        if 'PENDING' in all_statuses or 'ETD' in all_statuses or 'SENT' in all_statuses:
            return '🔴 PENDING'
        
        # Check if PASSED
        if mcs == 'APPROVED' and fgt == 'PASSED':
            return '✅ PASSED'
        
        return '🔄 Processing'
    
    df_br['Status'] = df_br.apply(get_overall_status, axis=1)
    
    df_br_filtered = df_br.copy()
    if selected_factory != '-- Tất cả --':
        df_br_filtered = df_br_filtered[df_br_filtered['Factory'] == selected_factory]
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
        
        # Load logos as base64
        logo_hwa_path = os.path.join(os.path.dirname(__file__), 'logo_hwa.png')
        logo_spg_path = os.path.join(os.path.dirname(__file__), 'logo_spg.png')
        
        logo_hwa_b64 = ""
        logo_spg_b64 = ""
        
        if os.path.exists(logo_hwa_path):
            with open(logo_hwa_path, "rb") as f:
                logo_hwa_b64 = base64.b64encode(f.read()).decode()
        if os.path.exists(logo_spg_path):
            with open(logo_spg_path, "rb") as f:
                logo_spg_b64 = base64.b64encode(f.read()).decode()
        
        factory_cols = st.columns(len(factory_counts))
        for i, (factory, count) in enumerate(factory_counts.items()):
            if factory and str(factory) != 'nan':
                with factory_cols[i]:
                    if factory == "HWA" and logo_hwa_b64:
                        logo_img = f'<img src="data:image/png;base64,{logo_hwa_b64}" style="height: 50px; margin-bottom: 10px; background: white; padding: 5px; border-radius: 8px;">'
                        color = "#4facfe"
                    elif factory == "SPG" and logo_spg_b64:
                        logo_img = f'<img src="data:image/png;base64,{logo_spg_b64}" style="height: 50px; margin-bottom: 10px; background: white; padding: 5px; border-radius: 8px;">'
                        color = "#2ecc71"
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
    
    edited_df = st.data_editor(
        df_br_filtered, use_container_width=True, num_rows="fixed",
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
    
    # Action buttons
    col_btn1, col_btn2 = st.columns([1, 4])
    with col_btn1:
        if st.button("💾 Lưu Status", type="primary", key="save_br"):
            update_all_statuses(edited_df)
            st.success("✅ Đã lưu!")
            st.rerun()
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
