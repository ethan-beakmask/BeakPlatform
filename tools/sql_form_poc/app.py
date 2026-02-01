"""
SQL Form POC - Flask 應用
驗證動態 SQL → form.io → CRUD 概念
"""

import re
import functools
from datetime import date, datetime
from decimal import Decimal

import psycopg2
from psycopg2.pool import SimpleConnectionPool
from flask import Flask, jsonify, request, render_template, abort

from converter import (
    get_table_columns, columns_to_formio, merge_layout,
    extract_data_from_submission, normalize_date_value,
    AUTO_SKIP_COLUMNS, AUTO_READONLY_COLUMNS, TYPE_MAP,
)

app = Flask(__name__)

# ---------- DB 連線池 ----------

DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'dbname': 'beakplatform_dev',
    'user': 'beakplatform',
    'password': 'postgres123',
}

pool = SimpleConnectionPool(minconn=1, maxconn=5, **DB_CONFIG)


def get_conn():
    return pool.getconn()


def put_conn(conn):
    pool.putconn(conn)


# ---------- JSON Provider (Flask 3.x) ----------

class CustomJSONProvider(Flask.json_provider_class):
    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


app.json_provider_class = CustomJSONProvider
app.json = CustomJSONProvider(app)

# ---------- 資料表白名單 ----------

TABLE_PATTERN = re.compile(r'^fw_data_[a-z0-9_]+$')


def validate_table(f):
    """裝飾器：驗證 table_name 是否合法"""
    @functools.wraps(f)
    def wrapper(table_name, *args, **kwargs):
        if not TABLE_PATTERN.match(table_name):
            abort(400, description=f"非法的資料表名稱: {table_name}")
        # 確認表存在
        conn = get_conn()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = %s
            """, (table_name,))
            if not cur.fetchone():
                abort(404, description=f"資料表不存在: {table_name}")
        finally:
            put_conn(conn)
        return f(table_name, *args, **kwargs)
    return wrapper


# ---------- 工具函式 ----------

def _get_sql_column_keys(cursor, table_name):
    """取得資料表所有欄位名稱 (排除 AUTO_SKIP)"""
    cols = get_table_columns(cursor, table_name)
    return {c[0] for c in cols} - AUTO_SKIP_COLUMNS


def _get_column_types(cursor, table_name):
    """取得欄位 → 資料型別對應"""
    cols = get_table_columns(cursor, table_name)
    return {c[0]: c[1] for c in cols}


def _coerce_value(value, data_type, col_name):
    """將前端值轉換為合適的 SQL 值"""
    # 空字串處理：非文字欄位轉 None
    if isinstance(value, str) and value.strip() == '':
        if data_type not in ('character varying', 'varchar', 'text'):
            return None

    # 日期欄位
    if data_type == 'date':
        return normalize_date_value(value)

    # boolean
    if data_type == 'boolean':
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ('true', '1', 'yes')
        return bool(value)

    return value


# ---------- API: 資料表列表 ----------

@app.route('/api/tables')
def api_list_tables():
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name LIKE 'fw\\_data\\_%'
            ORDER BY table_name
        """)
        tables = [row[0] for row in cur.fetchall()]
        return jsonify(tables)
    finally:
        put_conn(conn)


# ---------- API: Schema ----------

@app.route('/api/tables/<table_name>/schema')
@validate_table
def api_get_schema(table_name):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cols = get_table_columns(cur, table_name)
        schema = columns_to_formio(cols)
        return jsonify(schema)
    finally:
        put_conn(conn)


# ---------- API: Layout ----------

@app.route('/api/tables/<table_name>/layout', methods=['GET'])
@validate_table
def api_get_layout(table_name):
    conn = get_conn()
    try:
        cur = conn.cursor()

        # 取得自動 schema
        cols = get_table_columns(cur, table_name)
        auto_schema = columns_to_formio(cols)
        sql_column_keys = {c[0] for c in cols} - AUTO_SKIP_COLUMNS

        # 取得已存 layout
        cur.execute(
            "SELECT layout FROM fw_sql_form_layouts WHERE table_name = %s",
            (table_name,)
        )
        row = cur.fetchone()
        saved_layout = row[0] if row else None

        # 合併
        merged, warnings = merge_layout(saved_layout, auto_schema, sql_column_keys)

        return jsonify({
            'layout': merged,
            'warnings': warnings,
            'has_saved_layout': saved_layout is not None,
        })
    finally:
        put_conn(conn)


@app.route('/api/tables/<table_name>/layout', methods=['POST'])
@validate_table
def api_save_layout(table_name):
    conn = get_conn()
    try:
        cur = conn.cursor()
        layout = request.get_json()

        cur.execute("""
            INSERT INTO fw_sql_form_layouts (table_name, layout, updated_at)
            VALUES (%s, %s::jsonb, NOW())
            ON CONFLICT (table_name)
            DO UPDATE SET layout = EXCLUDED.layout, updated_at = NOW()
        """, (table_name, jsonify(layout).get_data(as_text=True)))

        conn.commit()
        return jsonify({'ok': True})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        put_conn(conn)


@app.route('/api/tables/<table_name>/layout', methods=['DELETE'])
@validate_table
def api_delete_layout(table_name):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM fw_sql_form_layouts WHERE table_name = %s",
            (table_name,)
        )
        conn.commit()
        return jsonify({'ok': True, 'deleted': cur.rowcount > 0})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        put_conn(conn)


# ---------- API: Data CRUD ----------

@app.route('/api/tables/<table_name>/data', methods=['GET'])
@validate_table
def api_list_data(table_name):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            f'SELECT * FROM "{table_name}" ORDER BY id DESC LIMIT 10'
        )
        columns = [desc[0] for desc in cur.description]
        rows = [dict(zip(columns, row)) for row in cur.fetchall()]
        return jsonify(rows)
    finally:
        put_conn(conn)


@app.route('/api/tables/<table_name>/data', methods=['POST'])
@validate_table
def api_create_data(table_name):
    conn = get_conn()
    try:
        cur = conn.cursor()
        submission = request.get_json()

        sql_keys = _get_sql_column_keys(cur, table_name)
        col_types = _get_column_types(cur, table_name)
        data = extract_data_from_submission(submission, sql_keys)

        if not data:
            return jsonify({'error': '沒有有效的欄位資料'}), 400

        # 轉換值
        for key in list(data.keys()):
            data[key] = _coerce_value(data[key], col_types.get(key, ''), key)

        cols = list(data.keys())
        vals = list(data.values())
        placeholders = ', '.join(['%s'] * len(cols))
        col_str = ', '.join(f'"{c}"' for c in cols)

        cur.execute(
            f'INSERT INTO "{table_name}" ({col_str}) VALUES ({placeholders}) RETURNING id',
            vals
        )
        new_id = cur.fetchone()[0]
        conn.commit()
        return jsonify({'ok': True, 'id': new_id}), 201
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        put_conn(conn)


@app.route('/api/tables/<table_name>/data/<int:row_id>', methods=['GET'])
@validate_table
def api_get_data(table_name, row_id):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(f'SELECT * FROM "{table_name}" WHERE id = %s', (row_id,))
        row = cur.fetchone()
        if not row:
            return jsonify({'error': '資料不存在'}), 404
        columns = [desc[0] for desc in cur.description]
        return jsonify(dict(zip(columns, row)))
    finally:
        put_conn(conn)


@app.route('/api/tables/<table_name>/data/<int:row_id>', methods=['PUT'])
@validate_table
def api_update_data(table_name, row_id):
    conn = get_conn()
    try:
        cur = conn.cursor()
        submission = request.get_json()

        sql_keys = _get_sql_column_keys(cur, table_name)
        col_types = _get_column_types(cur, table_name)
        data = extract_data_from_submission(submission, sql_keys)

        if not data:
            return jsonify({'error': '沒有有效的欄位資料'}), 400

        # 轉換值
        for key in list(data.keys()):
            data[key] = _coerce_value(data[key], col_types.get(key, ''), key)

        set_parts = [f'"{k}" = %s' for k in data.keys()]
        vals = list(data.values()) + [row_id]

        cur.execute(
            f'UPDATE "{table_name}" SET {", ".join(set_parts)} WHERE id = %s',
            vals
        )
        if cur.rowcount == 0:
            return jsonify({'error': '資料不存在'}), 404

        conn.commit()
        return jsonify({'ok': True})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        put_conn(conn)


@app.route('/api/tables/<table_name>/data/<int:row_id>', methods=['DELETE'])
@validate_table
def api_delete_data(table_name, row_id):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(f'DELETE FROM "{table_name}" WHERE id = %s', (row_id,))
        if cur.rowcount == 0:
            return jsonify({'error': '資料不存在'}), 404
        conn.commit()
        return jsonify({'ok': True})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        put_conn(conn)


# ---------- 頁面路由 ----------

@app.route('/')
def page_index():
    return render_template('index.html')


@app.route('/tables/<table_name>/designer')
@validate_table
def page_designer(table_name):
    return render_template('designer.html', table_name=table_name)


@app.route('/tables/<table_name>/data')
@validate_table
def page_data(table_name):
    return render_template('data.html', table_name=table_name)


# ---------- 錯誤處理 ----------

@app.errorhandler(400)
def bad_request(e):
    return jsonify({'error': str(e.description)}), 400


@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': str(e.description)}), 404


# ---------- 啟動 ----------

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5555, debug=True)
