import os
from datetime import datetime, timedelta
from flask import Flask, request, render_template
import mysql.connector
from dotenv import load_dotenv
from rapidfuzz import fuzz

load_dotenv()

app = Flask(__name__, template_folder='templates', static_folder='static')

def get_db_connection():
    """Membuat koneksi ke Aiven MySQL dengan timeout aman"""
    return mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", 26070)),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        connect_timeout=5
    )

@app.route('/init-db')
def init_db():
    """Rute sekali pakai untuk membuat tabel database di Aiven MySQL"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        create_table_query = """
        CREATE TABLE IF NOT EXISTS artikel_kesehatan (
            id INT AUTO_INCREMENT PRIMARY KEY,
            title VARCHAR(255) NOT NULL,
            summary TEXT,
            source VARCHAR(100) NOT NULL,
            url VARCHAR(500) NOT NULL UNIQUE,
            image_url VARCHAR(500),
            published_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """
        cursor.execute(create_table_query)
        conn.commit()
        cursor.close()
        conn.close()
        return "SUKSES: Tabel 'artikel_kesehatan' berhasil dibuat di Aiven MySQL!", 200
    except Exception as e:
        return f"GAGAL membuat tabel: {str(e)}", 500

def cleanup_old_articles(cursor, conn):
    """FITUR 3: Auto Clean-up Storage (Hapus artikel > 1 tahun / 365 hari)"""
    try:
        one_year_ago = datetime.now() - timedelta(days=365)
        cleanup_query = "DELETE FROM artikel_kesehatan WHERE published_at < %s OR created_at < %s"
        cursor.execute(cleanup_query, (one_year_ago, one_year_ago))
        conn.commit()
    except Exception as e:
        print(f"[Auto Cleanup Warning]: {e}")

def get_synonyms_and_keywords(query):
    """FITUR 2: Smart Search Dictionary (Sinonim & Penanganan Typo Khusus Medis)"""
    q = query.lower().strip()
    synonym_map = {
        'sakit gula': 'diabetes',
        'diabtes': 'diabetes',
        'diabet': 'diabetes',
        'kencing manis': 'diabetes',
        'paru': 'tbc',
        'tuberkulosis': 'tbc',
        'demam berdarah': 'dbd',
        'dengue': 'dbd',
        'darah tinggi': 'hipertensi',
        'tekanan darah': 'hipertensi',
        'jantung': 'kardiovaskular',
        'mental': 'depresi',
        'cemas': 'ansietas',
        'stres': 'mental',
        'vaksinasi': 'vaksin',
        'imunisasi': 'vaksin'
    }
    
    matched_keywords = [q]
    for key, val in synonym_map.items():
        if key in q or q in key:
            matched_keywords.extend([key, val])
            
    return list(set(matched_keywords))

@app.route('/run-scraper')
def run_scraper():
    """Rute untuk memicu scraper.py secara otomatis"""
    try:
        from scraper import scrape_kesehatan
        scrape_kesehatan()
        return "SUKSES: Proses RSS scraping berhasil dijalankan!", 200
    except Exception as e:
        return f"SCRAPER NOTICE: Berjalan dengan kendala: {str(e)}", 200

@app.route('/')
def index():
    query = request.args.get('q', '').strip()
    category = request.args.get('category', '').strip()
    sort_by = request.args.get('sort', 'latest').strip()

    articles = []
    trending_articles = []
    db_connected = True

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # 1. Jalankan Pembersihan Artikel Lama (>1 Tahun)
        cleanup_old_articles(cursor, conn)

        # 2. Logika Query Utama & Smart Search dengan RapidFuzz + Pecah Kata
        if query:
            cursor.execute("SELECT * FROM artikel_kesehatan")
            all_articles = cursor.fetchall()
            
            search_keywords = get_synonyms_and_keywords(query)
            q_lower = query.lower().strip()
            filtered_articles = []

            for art in all_articles:
                title_text = art['title'] or ""
                summary_text = art['summary'] or ""
                full_text = f"{title_text} {summary_text}".lower()
                
                # 1. Cek sinonim dasar
                match_keyword = any(kw in full_text for kw in search_keywords)
                match_substring = q_lower in full_text
                
                # 2. Cek kemiripan per kata (Memecah judul/summary menjadi kata-kata terpisah)
                # Cara ini membuat typo seperti "jantng" dicocokkan langsung dengan kata "jantung" di dalam teks
                words_in_article = full_text.split()
                max_score = 0
                
                for word in words_in_article:
                    # Hitung kemiripan ejaan antar kata menggunakan ratio
                    score = fuzz.ratio(q_lower, word)
                    if score > max_score:
                        max_score = score
                
                # Jika panjang query minimal 4 huruf, beri toleransi skor 65 (cukup untuk mengatasi huruf vokal yang hilang seperti "jantng")
                min_threshold = 60 if len(q_lower) >= 4 else 80
                
                if match_keyword or match_substring or max_score >= min_threshold:
                    art['search_score'] = max_score
                    filtered_articles.append(art)
            
            # Urutkan berdasarkan tingkat kemiripan tertinggi
            filtered_articles = sorted(filtered_articles, key=lambda x: x.get('search_score', 0), reverse=True)
            articles = filtered_articles
        else:
            # Query standar jika tidak sedang mencari (berdasarkan kategori & sorting)
            sql = "SELECT * FROM artikel_kesehatan WHERE 1=1"
            params = []

            # Category Filtering Logic
            if category:
                category_map = {
                    'penyakit': ['vaksin', 'virus', 'infeksi', 'dbd', 'mpox', 'covid', 'flu', 'demam', 'tbc'],
                    'mental': ['depresi', 'stres', 'cemas', 'mental', 'jiwa', 'psikologi', 'ansietas'],
                    'gaya_hidup': ['olahraga', 'tidur', 'rokok', 'hidup', 'gigi', 'kulit', 'fitness'],
                    'nutrisi': ['diet', 'makanan', 'vitamin', 'gizi', 'nutrisi', 'buah', 'sayur', 'obesitas'],
                    'medis': ['rumah sakit', 'dokter', 'obat', 'operasi', 'medis', 'jantung', 'diabetes', 'hipertensi']
                }
                keywords = category_map.get(category, [])
                if keywords:
                    cat_conditions = " OR ".join(["title LIKE %s OR summary LIKE %s" for _ in keywords])
                    sql += f" AND ({cat_conditions})"
                    for kw in keywords:
                        params.extend([f"%{kw}%", f"%{kw}%"])

            # Sorting logic
            if sort_by == 'trending':
                sql += " ORDER BY id DESC LIMIT 10"
            else:
                sql += " ORDER BY published_at DESC, id DESC LIMIT 20"

            cursor.execute(sql, tuple(params))
            articles = cursor.fetchall()

        # Jika user melakukan pencarian dan sekaligus memilih kategori, filter lagi hasilnya
        if query and category:
            category_map = {
                'penyakit': ['vaksin', 'virus', 'infeksi', 'dbd', 'mpox', 'covid', 'flu', 'demam', 'tbc'],
                'mental': ['depresi', 'stres', 'cemas', 'mental', 'jiwa', 'psikologi', 'ansietas'],
                'gaya_hidup': ['olahraga', 'tidur', 'rokok', 'hidup', 'gigi', 'kulit', 'fitness'],
                'nutrisi': ['diet', 'makanan', 'vitamin', 'gizi', 'nutrisi', 'buah', 'sayur', 'obesitas'],
                'medis': ['rumah sakit', 'dokter', 'obat', 'operasi', 'medis', 'jantung', 'diabetes', 'hipertensi']
            }
            cat_keywords = category_map.get(category, [])
            articles = [art for art in articles if any(ck in f"{art['title']} {art['summary']}".lower() for ck in cat_keywords)]

        # Sorting manual khusus hasil pencarian gabungan
        if query and sort_by == 'latest':
            articles = sorted(articles, key=lambda x: x.get('published_at', datetime.min), reverse=True)

        # Isu Populer untuk Sidebar
        cursor.execute("SELECT * FROM artikel_kesehatan ORDER BY id DESC LIMIT 5")
        trending_articles = cursor.fetchall()

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"[Database Error]: {e}")
        db_connected = False

    return render_template(
        'index.html',
        articles=articles,
        trending_articles=trending_articles,
        search_query=query,
        active_category=category,
        sort_by=sort_by,
        db_connected=db_connected
    )

if __name__ == '__main__':
    app.run(debug=True)
