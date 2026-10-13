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

@app.route('/run-scraper-1')
def run_scraper_1():
    """Rute Batch 1 untuk memicu scraper bagian pertama"""
    try:
        from scraper import scrape_kesehatan
        scrape_kesehatan(batch=1)
        return "SUKSES: RSS Scraping Batch 1 Berhasil!", 200
    except Exception as e:
        return f"SCRAPER NOTICE (Batch 1): {str(e)}", 200

@app.route('/run-scraper-2')
def run_scraper_2():
    """Rute Batch 2 untuk memicu scraper bagian kedua"""
    try:
        from scraper import scrape_kesehatan
        scrape_kesehatan(batch=2)
        return "SUKSES: RSS Scraping Batch 2 Berhasil!", 200
    except Exception as e:
        return f"SCRAPER NOTICE (Batch 2): {str(e)}", 200

@app.route('/keep-alive')
def keep_alive():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchall()
        cursor.close()
        conn.close()
        return "Database Keep-Alive Sukses!", 200
    except Exception as e:
        return f"Error Keep-Alive: {str(e)}", 500

@app.route('/reset-db')
def reset_db():
    """Menghapus semua data artikel untuk memulai ulang dari bersih"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("TRUNCATE TABLE artikel_kesehatan;")
        conn.commit()
        cursor.close()
        conn.close()
        return "SUKSES: Seluruh database berhasil dibersihkan (Reset Total)!", 200
    except Exception as e:
        return f"GAGAL reset database: {str(e)}", 500

@app.route('/delete-article/<int:article_id>')
def delete_article(article_id):
    """Menghapus artikel spesifik yang salah sasaran berdasarkan ID-nya"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM artikel_kesehatan WHERE id = %s", (article_id,))
        conn.commit()
        affected_rows = cursor.rowcount
        cursor.close()
        conn.close()
        
        if affected_rows > 0:
            return f"SUKSES: Artikel dengan ID {article_id} berhasil dihapus dari database!", 200
        else:
            return f"INFO: Artikel dengan ID {article_id} tidak ditemukan (mungkin sudah terhapus).", 404
    except Exception as e:
        return f"GAGAL menghapus artikel: {str(e)}", 500

@app.route('/admin-artikel')
def admin_artikel():
    """Halaman panel admin sederhana untuk melihat, mencari, dan menghapus artikel yang salah sasaran"""
    search_query = request.args.get('q', '').strip()
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        if search_query:
            sql = "SELECT id, title, source, published_at FROM artikel_kesehatan WHERE title LIKE %s OR source LIKE %s ORDER BY id DESC LIMIT 100"
            cursor.execute(sql, (f"%{search_query}%", f"%{search_query}%"))
        else:
            cursor.execute("SELECT id, title, source, published_at FROM artikel_kesehatan ORDER BY id DESC LIMIT 50")
            
        articles = cursor.fetchall()
        cursor.close()
        conn.close()
    except Exception as e:
        articles = []
        print(f"[Admin Error]: {e}")

    html_content = f"""
    <!DOCTYPE html>
    <html lang="id">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Panel Admin - Kesehatan-MU</title>
        <style>
            body {{ font-family: Arial, sans-serif; background: #f4f6f8; padding: 20px; color: #333; }}
            h2 {{ color: #0d9488; margin-top: 5px; }}
            .header-container {{ display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; margin-bottom: 15px; }}
            .search-box {{ display: flex; gap: 8px; }}
            .search-input {{ padding: 8px 12px; border: 1px solid #ccc; border-radius: 6px; font-size: 14px; width: 250px; outline: none; }}
            .search-input:focus {{ border-color: #0d9488; }}
            .btn-search {{ background-color: #0d9488; color: white; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-weight: bold; font-size: 14px; }}
            .btn-search:hover {{ background-color: #0f766e; }}
            .btn-reset {{ background-color: #6b7280; color: white; border: none; padding: 8px 12px; border-radius: 6px; text-decoration: none; font-size: 14px; }}
            table {{ width: 100%; border-collapse: collapse; background: white; margin-top: 10px; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
            th, td {{ padding: 12px 15px; text-align: left; border-bottom: 1px solid #eee; }}
            th {{ background-color: #0d9488; color: white; }}
            tr:hover {{ background-color: #f9fafb; }}
            .btn-hapus {{ background-color: #ef4444; color: white; padding: 6px 12px; border: none; border-radius: 4px; cursor: pointer; text-decoration: none; font-size: 14px; display: inline-block; }}
            .btn-hapus:hover {{ background-color: #dc2626; }}
            .back-link {{ display: inline-block; margin-bottom: 15px; color: #0d9488; text-decoration: none; font-weight: bold; }}
        </style>
    </head>
    <body>
        <a href="/" class="back-link">&larr; Kembali ke Beranda Kesehatan-MU</a>
        
        <div class="header-container">
            <div>
                <h2>Panel Moderasi Artikel (Hapus Artikel Nyasar)</h2>
                <p style="margin: 0; color: #666; font-size: 14px;">Cari artikel yang salah sasaran berdasarkan judul atau sumber, lalu klik tombol Hapus.</p>
            </div>
            
            <form action="/admin-artikel" method="GET" class="search-box">
                <input type="text" name="q" value="{search_query}" placeholder="Cari judul / sumber..." class="search-input">
                <button type="submit" class="btn-search">Cari</button>
                {"<a href='/admin-artikel' class='btn-reset'>Reset</a>" if search_query else ""}
            </form>
        </div>

        <table>
            <thead>
                <tr>
                    <th style="width: 80px;">ID</th>
                    <th>Judul Artikel</th>
                    <th style="width: 160px;">Sumber</th>
                    <th style="width: 180px;">Tanggal Terbit</th>
                    <th style="width: 100px;">Aksi</th>
                </tr>
            </thead>
            <tbody>
    """
    
    if articles:
        for art in articles:
            html_content += f"""
                <tr>
                    <td>{art['id']}</td>
                    <td>{art['title']}</td>
                    <td><b>{art['source']}</b></td>
                    <td>{art['published_at']}</td>
                    <td><a href="/delete-article/{art['id']}" class="btn-hapus" onclick="return confirm('Yakin mau hapus artikel ini?')">Hapus</a></td>
                </tr>
            """
    else:
        html_content += f"""
                <tr>
                    <td colspan="5" style="text-align: center; color: #777; padding: 20px;">
                        {"Artikel dengan kata kunci '" + search_query + "' tidak ditemukan." if search_query else "Tidak ada artikel atau database gagal dimuat."}
                    </td>
                </tr>
        """
        
    html_content += """
            </tbody>
        </table>
    </body>
    </html>
    """
    return html_content

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

# Master kamus kategori
CATEGORY_MAP = {
    'penyakit_menular': [
        'vaksin', 'virus', 'infeksi', 'dbd', 'demam berdarah', 'mpox', 'covid', 'flu', 'demam', 
        'tbc', 'tuberculosis', 'cacar', 'tifus', 'tipes', 'malaria', 'hiv', 'aids', 'hepatitis', 
        'tetanus', 'pneumonia', 'ispa', 'rabies', 'leptospirosis', 'bakteri', 'wabah', 'pandemi', 
        'endemi', 'menular', 'penularan', 'tertular', 'kusta', 'scabies', 'kudis', 'cacingan',
        'anthrax', 'flu burung', 'chikungunya', 'zoonosis', 'klaster'
    ],
    'penyakit_kronis': [
        'kanker', 'tumor', 'diabetes', 'kencing manis', 'jantung', 'stroke', 'hipertensi', 
        'darah tinggi', 'kolesterol', 'asam urat', 'kista', 'miom', 'gagal ginjal', 'batu ginjal', 
        'asma', 'gout', 'osteoporosis', 'rematik', 'artritis', 'autoimun', 'lupus', 'alzheimer', 
        'demensia', 'parkinson', 'epilepsi', 'amandel', 'sinusitis', 'varises', 'hernia', 
        'pembuluh darah', 'kronis'
    ],
    'mental': [
        'depresi', 'stres', 'cemas', 'mental', 'jiwa', 'psikologi', 'ansietas', 'anxiety', 'trauma', 
        'skizofrenia', 'bipolar', 'autisme', 'adhd', 'panic attack', 'halusinasi', 'psikiater', 
        'psikolog', 'mental health', 'emosi', 'burnout', 'tekanan batin'
    ],
    'gaya_hidup': [
        'olahraga', 'tidur', 'rokok', 'hidup', 'gigi', 'kulit', 'fitness', 'insomnia', 'jerawat', 
        'dermatitis', 'eksim', 'karies', 'plak gigi', 'gusi', 'aerobik', 'gym', 'jalan kaki', 
        'sepeda', 'vape', 'alkohol', 'begadang', 'gaya hidup', 'kebugaran', 'sedentari'
    ],
    'nutrisi': [
        'diet', 'makanan', 'vitamin', 'gizi', 'nutrisi', 'buah', 'sayur', 'obesitas', 'kalori', 
        'kegemukan', 'karbohidrat', 'protein', 'lemak', 'serat', 'suplemen', 'hidrasi', 'air putih', 
        'stunting', 'kurang gizi', 'malnutrisi', 'gula darah', 'puasa'
    ],
    'medis': [
        'rumah sakit', 'dokter', 'obat', 'operasi', 'medis', 'klinik', 'puskesmas', 
        'perawat', 'bidan', 'apotek', 'laboratorium', 'faskes', 'igd', 'icu', 'rawat inap', 
        'rawat jalan', 'rekam medis', 'rujukan', 'diagnosis', 'bedah', 'terapi', 'rehabilitasi', 
        'ambulan', 'screening', 'antibiotik', 'resep dokter', 'dosis'
    ],
    'ibu_anak': [
        'kehamilan', 'hamil', 'janin', 'kandungan', 'melahirkan', 'persalinan', 'nifas', 'asi', 
        'menyusui', 'kb', 'kontrasepsi', 'kespro', 'menstruasi', 'haid', 'pms', 'kesuburan', 
        'infertil', 'pcos', 'pediatri', 'tumbuh kembang', 'imunisasi', 'balita', 'bayi', 'anak'
    ],
    'kebijakan_kesehatan': [
        'bpjs', 'kemenkes', 'menkes', 'jkn', 'kis', 'faskes 1', 'iuran', 'klaim rs', 'subsidi', 
        'regulasi', 'pemerintah', 'anggaran kesehatan', 'kebijakan medis'
    ]
}

@app.route('/')
def index():
    """Halaman Utama Beranda dengan dukungan Smart Search, Kategori, Region, dan Pagination"""
    query = request.args.get('q', '').strip()
    category = request.args.get('category', '').strip()
    region = request.args.get('region', '').strip()
    sort_by = request.args.get('sort', 'random').strip()

    articles = []
    trending_articles = []
    db_connected = True
    page = 1
    total_pages = 1

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # 1. Jalankan Pembersihan Artikel Lama (>1 Tahun)
        cleanup_old_articles(cursor, conn)

        # 2. Logika Query Utama & Smart Search (Judul, Summary, Sumber, & Tanggal Terbit)
        if query:
            cursor.execute("SELECT * FROM artikel_kesehatan")
            all_articles = cursor.fetchall()
            
            search_keywords = get_synonyms_and_keywords(query)
            q_lower = query.lower().strip()
            filtered_articles = []

            for art in all_articles:
                title_text = art['title'] or ""
                summary_text = art['summary'] or ""
                source_text = art['source'] or ""
                published_str = art['published_at'].strftime('%d %b %Y %Y-%m-%d') if art.get('published_at') else ""
                
                title_lower = title_text.lower()
                summary_lower = summary_text.lower()
                source_lower = source_text.lower()
                published_lower = published_str.lower()
                
                score = 0
                matched = False
                
                if q_lower in source_lower:
                    matched = True
                    score = 120
                elif q_lower in published_lower:
                    matched = True
                    score = 110
                elif any(kw in title_lower or kw in summary_lower for kw in search_keywords) or q_lower in title_lower or q_lower in summary_lower:
                    matched = True
                    score = 100 if q_lower in title_lower else 80
                else:
                    all_words = (title_lower + " " + summary_lower).split()
                    max_word_score = 0
                    
                    for w in all_words:
                        if abs(len(w) - len(q_lower)) <= 2:
                            s = fuzz.ratio(q_lower, w)
                            if s > max_word_score:
                                max_word_score = s
                    
                    if max_word_score >= 75:
                        matched = True
                        title_words = title_lower.split()
                        in_title = any(abs(len(w) - len(q_lower)) <= 2 and fuzz.ratio(q_lower, w) >= 75 for w in title_words)
                        score = max_word_score + (30 if in_title else 0)

                if matched:
                    art['search_score'] = score
                    filtered_articles.append(art)
            
            filtered_articles = sorted(filtered_articles, key=lambda x: x.get('search_score', 0), reverse=True)
            articles = filtered_articles
        else:
            # Query standar untuk Home, Isu Terbaru, Kategori, atau Region
            sql = "SELECT * FROM artikel_kesehatan WHERE 1=1"
            params = []

            # Category Filtering Logic
            if category:
                keywords = CATEGORY_MAP.get(category, [])
                if keywords:
                    cat_conditions = " OR ".join(["title LIKE %s OR summary LIKE %s" for _ in keywords])
                    sql += f" AND ({cat_conditions})"
                    for kw in keywords:
                        params.extend([f"%{kw}%", f"%{kw}%"])

            # Region Filtering Logic (Internasional vs Lokal)
            if region == 'international':
                sql += " AND source IN ('ScienceDaily', 'Medical Xpress')"
            elif region == 'local':
                sql += " AND source NOT IN ('ScienceDaily', 'Medical Xpress')"

            # Tangkap nomor halaman untuk pagination
            try:
                page = int(request.args.get('page', 1))
                if page < 1: page = 1
            except ValueError:
                page = 1
                
            per_page = 20
            offset = (page - 1) * per_page

            # Hitung total artikel jika sort latest, kategori, atau region aktif
            if sort_by == 'latest' or category or region:
                count_sql = "SELECT COUNT(*) as total FROM artikel_kesehatan WHERE 1=1"
                count_params = []

                if category:
                    keywords = CATEGORY_MAP.get(category, [])
                    if keywords:
                        cat_conditions = " OR ".join(["title LIKE %s OR summary LIKE %s" for _ in keywords])
                        count_sql += f" AND ({cat_conditions})"
                        for kw in keywords:
                            count_params.extend([f"%{kw}%", f"%{kw}%"])

                if region == 'international':
                    count_sql += " AND source IN ('ScienceDaily', 'Medical Xpress')"
                elif region == 'local':
                    count_sql += " AND source NOT IN ('ScienceDaily', 'Medical Xpress')"

                cursor.execute(count_sql, tuple(count_params))
                res_count = cursor.fetchone()
                total_articles = res_count['total'] if res_count else 0
                total_pages = (total_articles + per_page - 1) // per_page
                if total_pages < 1: total_pages = 1

            # Sorting logic & Pagination
            if sort_by == 'trending':
                sql += " ORDER BY id DESC LIMIT 10"
            elif sort_by == 'latest' or category or region:
                sql += " ORDER BY published_at DESC, id DESC LIMIT %s OFFSET %s"
                params.extend([per_page, offset])
            else:
                # Home Utama: Random dan KECUALIKAN ScienceDaily jika tidak sedang di-filter region
                if not region:
                    sql += " AND source != 'ScienceDaily'"
                sql += " ORDER BY RAND() LIMIT 20"

            cursor.execute(sql, tuple(params))
            articles = cursor.fetchall()

        if query and category:
            cat_keywords = CATEGORY_MAP.get(category, [])
            articles = [art for art in articles if any(ck in f"{art['title']} {art['summary']}".lower() for ck in cat_keywords)]

        if query and sort_by == 'latest':
            articles = sorted(articles, key=lambda x: x.get('published_at', datetime.min), reverse=True)

        # Isu Populer untuk Sidebar (Selalu dieksekusi agar sidebar tidak pernah kosong)
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
        region=region,
        sort_by=sort_by,
        db_connected=db_connected,
        current_page=page,
        total_pages=total_pages
    )

if __name__ == '__main__':
    app.run(debug=True)
    
