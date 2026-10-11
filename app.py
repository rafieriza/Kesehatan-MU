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

@app.route('/run-scraper')
def run_scraper():
    """Rute untuk memicu scraper.py secara otomatis"""
    try:
        from scraper import scrape_kesehatan
        scrape_kesehatan()
        return "SUKSES: Proses RSS scraping berhasil dijalankan!", 200
    except Exception as e:
        return f"SCRAPER NOTICE: Berjalan dengan kendala: {str(e)}", 200

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
        # Mengosongkan isi tabel dan mereset ID auto increment ke 1
        cursor.execute("TRUNCATE TABLE artikel_kesehatan;")
        conn.commit()
        cursor.close()
        conn.close()
        return "SUKSES: Seluruh database berhasil dibersihkan (Reset Total)!", 200
    except Exception as e:
        return f"GAGAL reset database: {str(e)}", 500

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

# Master kamus kategori dengan penambahan filter baru
CATEGORY_MAP = {
    # --- BARU: PENYAKIT MENULAR (Wabah, Infeksi, Virus, Bakteri) ---
    'penyakit_menular': [
        'vaksin', 'virus', 'infeksi', 'dbd', 'demam berdarah', 'mpox', 'covid', 'flu', 'demam', 
        'tbc', 'tuberculosis', 'cacar', 'tifus', 'tipes', 'malaria', 'hiv', 'aids', 'hepatitis', 
        'tetanus', 'pneumonia', 'ispa', 'rabies', 'leptospirosis', 'bakteri', 'wabah', 'pandemi', 
        'endemi', 'menular', 'penularan', 'tertular', 'kusta', 'scabies', 'kudis', 'cacingan',
        'anthrax', 'flu burung', 'chikungunya', 'zoonosis', 'klaster'
    ],

    # --- BARU: PENYAKIT TIDAK MENULAR / KRONIS ---
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
    query = request.args.get('q', '').strip()
    category = request.args.get('category', '').strip()
    # Default sort diubah ke 'random' untuk halaman Home
    sort_by = request.args.get('sort', 'random').strip()

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
                title_lower = title_text.lower()
                summary_lower = summary_text.lower()
                
                score = 0
                matched = False
                
                # 1. Cek kecocokan langsung (Sinonim atau Substring di Judul/Summary)
                if any(kw in title_lower or kw in summary_lower for kw in search_keywords) or q_lower in title_lower or q_lower in summary_lower:
                    matched = True
                    # Beri skor tinggi jika kata ditemukan langsung di judul, lebih rendah jika di summary
                    score = 100 if q_lower in title_lower else 80
                else:
                    # 2. Cek Fuzzy per-kata dengan filter panjang huruf yang mirip (selisih maksimal 2 huruf)
                    all_words = (title_lower + " " + summary_lower).split()
                    max_word_score = 0
                    
                    for w in all_words:
                        # Hanya bandingkan kata yang panjangnya mirip agar tidak meloloskan kata random
                        if abs(len(w) - len(q_lower)) <= 2:
                            s = fuzz.ratio(q_lower, w)
                            if s > max_word_score:
                                max_word_score = s
                    
                    # Ambang batas ketat (minimal 75 untuk word match)
                    if max_word_score >= 75:
                        matched = True
                        # Cek apakah kecocokan typo ada di bagian Judul (berikan bonus nilai agar prioritas di atas)
                        title_words = title_lower.split()
                        in_title = any(abs(len(w) - len(q_lower)) <= 2 and fuzz.ratio(q_lower, w) >= 75 for w in title_words)
                        score = max_word_score + (30 if in_title else 0)

                # Hanya masukkan artikel yang benar-benar 'matched'
                if matched:
                    art['search_score'] = score
                    filtered_articles.append(art)
            
            # Urutkan dari skor tertinggi (Paling akurat & diutamakan yang dari judul)
            filtered_articles = sorted(filtered_articles, key=lambda x: x.get('search_score', 0), reverse=True)
            articles = filtered_articles
        else:
            # Query standar jika tidak sedang mencari (berdasarkan kategori & sorting)
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

            # Sorting logic yang disesuaikan
            if sort_by == 'trending':
                sql += " ORDER BY id DESC LIMIT 10"
            elif sort_by == 'latest'or category:
                # Isu Terbaru ATAU saat sedang membuka Kategori: Berdasarkan urutan waktu masuk paling fresh
                sql += " ORDER BY published_at DESC, id DESC LIMIT 20"
            else:
                # Home Utama: Diambil secara acak (Random) dari database
                sql += " ORDER BY RAND() LIMIT 20"

            cursor.execute(sql, tuple(params))
            articles = cursor.fetchall()

        # Jika user melakukan pencarian dan sekaligus memilih kategori, filter lagi hasilnya
        if query and category:
            cat_keywords = CATEGORY_MAP.get(category, [])
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
