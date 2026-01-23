"""
BeakPlatform DevTools - 獨立開發工具服務
Port: 7001
限制: 僅內網 IP 可存取

此服務獨立於主應用，不會觸發安全掃描
"""
from functools import wraps
from datetime import datetime
from flask import Flask, render_template, request, abort, jsonify
from sqlalchemy import create_engine, text, inspect
import os

app = Flask(__name__)

# 資料庫連線
DATABASE_URL = os.environ.get(
    'DATABASE_URL',
    'postgresql://beakplatform:postgres123@localhost:5432/beakplatform_dev'
)
engine = create_engine(DATABASE_URL)


def internal_network_only(f):
    """限制只有內網 IP 可以存取"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        client_ip = request.remote_addr

        allowed_prefixes = (
            '192.168.',
            '10.',
            '172.16.', '172.17.', '172.18.', '172.19.',
            '172.20.', '172.21.', '172.22.', '172.23.',
            '172.24.', '172.25.', '172.26.', '172.27.',
            '172.28.', '172.29.', '172.30.', '172.31.',
            '127.0.0.1',
            '::1',
        )

        if not client_ip or not client_ip.startswith(allowed_prefixes):
            abort(403)

        return f(*args, **kwargs)
    return decorated_function


@app.route('/')
@internal_network_only
def index():
    """DevTools 首頁"""
    tools = [
        {'name': 'Quick Login', 'url': 'http://192.168.0.16:7000/dev/quick-login', 'desc': '多帳號快速切換', 'external': True, 'icon': 'bolt'},
        {'name': 'DB Viewer', 'url': '/db-viewer', 'desc': '資料表檢視器', 'icon': 'database'},
    ]
    return render_template('index.html', tools=tools)


@app.route('/db-viewer')
@internal_network_only
def db_viewer():
    """資料表檢視器"""
    inspector = inspect(engine)
    table_names = inspector.get_table_names()

    tables_data = []

    with engine.connect() as conn:
        for table_name in table_names:
            try:
                # 取得總筆數
                count_result = conn.execute(
                    text(f'SELECT COUNT(*) FROM "{table_name}"')
                ).scalar()

                # 取得資料表註解
                table_comment_result = conn.execute(text(
                    f"SELECT obj_description('{table_name}'::regclass, 'pg_class')"
                )).scalar()

                # 取得欄位資訊
                columns = inspector.get_columns(table_name)
                column_names = [col['name'] for col in columns]

                # 取得欄位註解
                comment_result = conn.execute(text("""
                    SELECT column_name, col_description(
                        (quote_ident(table_schema) || '.' || quote_ident(table_name))::regclass,
                        ordinal_position
                    ) as comment
                    FROM information_schema.columns
                    WHERE table_name = :table_name
                    ORDER BY ordinal_position
                """), {'table_name': table_name})
                column_comments = {row.column_name: row.comment for row in comment_result}

                columns_info = [
                    {'name': col['name'], 'type': str(col['type']), 'comment': column_comments.get(col['name'])}
                    for col in columns
                ]

                # 排序欄位
                order_column = None
                if 'created_at' in column_names:
                    order_column = 'created_at'
                elif 'id' in column_names:
                    order_column = 'id'

                # 取得最新 25 筆
                if order_column:
                    query = text(f'SELECT * FROM "{table_name}" ORDER BY "{order_column}" DESC LIMIT 25')
                else:
                    query = text(f'SELECT * FROM "{table_name}" LIMIT 25')

                rows_result = conn.execute(query)
                rows = [dict(row._mapping) for row in rows_result]

                tables_data.append({
                    'name': table_name,
                    'comment': table_comment_result,
                    'count': count_result,
                    'columns': column_names,
                    'columns_info': columns_info,
                    'rows': rows,
                    'order_by': order_column
                })
            except Exception as e:
                tables_data.append({
                    'name': table_name,
                    'count': 0,
                    'columns': [],
                    'columns_info': [],
                    'rows': [],
                    'error': str(e)
                })

    tables_data.sort(key=lambda x: x['count'], reverse=True)

    return render_template('db_viewer.html', tables=tables_data, now=datetime.now())


@app.route('/health')
def health():
    """健康檢查"""
    return jsonify({'status': 'ok', 'service': 'beakplatform-devtools'})


@app.route('/api/organizations')
@internal_network_only
def get_organizations():
    """取得所有企業列表（從 organizations 表）"""
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT secure_code, name
            FROM organizations
            WHERE is_deleted = false
            ORDER BY secure_code
        """))
        orgs = [{'code': row[0], 'name': row[1]} for row in result]

    return jsonify({
        'success': True,
        'data': orgs
    })


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=7001, debug=True)
