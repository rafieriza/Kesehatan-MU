import os
import math
from flask import Flask, request, jsonify, render_template
import mysql.connector
from dotenv import load_dotenv

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
def home():
    return render_template('index.html')

@app.route('/api/articles', methods=['GET'])
def get_articles():
    page = int(request.args.get('page', 1))
    limit = int(request.args.get('limit', 10))
    search = request.args.get('q', '').strip()
    sumber = request.args.get('sumber', '').strip()
    offset = (page - 1) * limit

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        params = []
        where_clauses = []

        # Fitur Smart Search menggunakan FULLTEXT MySQL
        if search:
            where_clauses.append("MATCH(judul, ringkasan) AGAINST(%s IN BOOLEAN MODE)")
            params.append(f"*{search}*")

        if sumber:
            where_clauses.append("sumber_portal = %s")
            params.append(sumber)

        where_sql = " WHERE " + " AND ".join(where_clauses) if where_clauses else ""

        # Hitung total artikel buat pagination
        count_query = f"SELECT COUNT(*) as total FROM artikel_kesehatan{where_sql}"
        cursor.execute(count_query, params)
        total_items = cursor.fetchone()['total']

        # Query ambil daftar artikel
        query = f"""
            SELECT id, judul, ringkasan, sumber_portal, url_artikel, url_gambar, tanggal_terbit 
            FROM artikel_kesehatan
            {where_sql}
            ORDER BY tanggal_terbit DESC 
            LIMIT %s OFFSET %s
        """
        params.extend([limit, offset])
        cursor.execute(query, params)
        articles = cursor.fetchall()

        cursor.close()
        conn.close()

        return jsonify({
            'status': 'success',
            'data': articles,
            'pagination': {
                'page': page,
                'limit': limit,
                'total_items': total_items,
                'total_pages': math.ceil(total_items / limit) if limit > 0 else 1
            }
        })

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
