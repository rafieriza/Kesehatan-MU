import os
import math
from flask import Flask, request, jsonify, render_template
import mysql.connector
from dotenv import load_dotenv

# Load local .env if it exists (safe for local development, ignored on Vercel)
load_dotenv()

app = Flask(__name__, template_folder='templates', static_folder='static')

def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", 26070)),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME")
    )

@app.route('/')
def index():
    query = request.args.get('q', '').strip()
    category = request.args.get('category', '').strip()
    sort_by = request.args.get('sort', 'latest').strip()

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    sql = "SELECT * FROM artikel_kesehatan WHERE 1=1"
    params = []

    # Logika Pencarian Kata Kunci
    if query:
        sql += " AND (title LIKE %s OR summary LIKE %s)"
        params.extend([f"%{query}%", f"%{query}%"])

    # Logika Filter Kategori Berdasarkan Kata Kunci
    if category:
        category_map = {
            'penyakit': ['vaksin', 'virus', 'infeksi', 'dbd', 'mpox', 'covid', 'flu', 'demam'],
            'mental': ['depresi', 'stres', 'cemas', 'mental', 'jiwa', 'psikologi'],
            'gaya_hidup': ['olahraga', 'tidur', 'rokok', 'hidup', 'gigi', 'kulit'],
            'nutrisi': ['diet', 'makanan', 'vitamin', 'gizi', 'nutrisi', 'buah', 'sayur'],
            'medis': ['rumah sakit', 'dokter', 'obat', 'operasi', 'medis', 'jantung', 'diabetes']
        }
        keywords = category_map.get(category, [])
        if keywords:
            cat_conditions = " OR ".join(["title LIKE %s OR summary LIKE %s" for _ in keywords])
            sql += f" AND ({cat_conditions})"
            for kw in keywords:
                params.extend([f"%{kw}%", f"%{kw}%"])

    # Logika Pengurutan (Terbaru vs Trending)
    if sort_by == 'trending':
        sql += " ORDER BY id DESC LIMIT 10"
    else:
        sql += " ORDER BY published_at DESC, id DESC LIMIT 20"

    cursor.execute(sql, tuple(params))
    articles = cursor.fetchall()

    # Mengambil Top 5 Isu Populer untuk Sidebar Kanan
    cursor.execute("SELECT * FROM artikel_kesehatan ORDER BY id DESC LIMIT 5")
    trending_articles = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        'index.html',
        articles=articles,
        trending_articles=trending_articles,
        search_query=query,
        active_category=category,
        sort_by=sort_by
    )

if __name__ == '__main__':
    app.run(debug=True)
