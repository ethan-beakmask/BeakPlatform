#!/usr/bin/env python3
"""
BeakPlatform 專案分析工具
整合多種分析功能：路由分析、目錄結構、資料庫匯出、未使用檔案分析

用法：
    python scripts/analyze_project.py routes      # API 路由分析
    python scripts/analyze_project.py structure   # 目錄結構分析
    python scripts/analyze_project.py database    # 資料庫結構匯出
    python scripts/analyze_project.py unused      # 未使用檔案分析
    python scripts/analyze_project.py all         # 執行所有分析
"""

import os
import sys
import re
import argparse
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Set, Tuple, Optional

# 確保可以 import 專案模組
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

try:
    import openpyxl
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False
    print("⚠️  openpyxl 未安裝，Excel 匯出功能將不可用")
    print("   安裝: pip install openpyxl")

try:
    import psycopg2
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False


# ============================================================================
# 共用樣式
# ============================================================================

class ExcelStyles:
    """Excel 樣式定義"""

    @staticmethod
    def get_header_style():
        return {
            'font': Font(bold=True, size=11, color='FFFFFF'),
            'fill': PatternFill(start_color='4472C4', end_color='4472C4', fill_type='solid'),
            'alignment': Alignment(horizontal='center', vertical='center'),
        }

    @staticmethod
    def get_border():
        return Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )


# ============================================================================
# 1. 路由分析器
# ============================================================================

class RouteAnalyzer:
    """Flask 路由分析器"""

    # BeakPlatform 安全裝飾器
    SECURITY_DECORATORS = {
        'public_route': '公開路由',
        'login_required': '需要登入',
        'admin_required': '需要企業管理員',
        'system_admin_required': '需要系統管理員',
        'csrf.exempt': 'CSRF 豁免',
    }

    def __init__(self, root_path: Path):
        self.root_path = root_path
        self.routes = []
        self.blueprint_prefixes = {}
        self.endpoints = {}  # endpoint -> path 映射

    def scan_blueprint_prefixes(self):
        """掃描 Blueprint URL 前綴"""
        print("🔍 掃描 Blueprint URL 前綴...")

        # 1. 先掃描 Blueprint 定義時的 url_prefix
        bp_definition_prefixes = {}
        for py_file in (self.root_path / 'backend' / 'app').rglob('*.py'):
            if '__pycache__' in str(py_file):
                continue
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()

                # 匹配: xxx = Blueprint(..., url_prefix='/xxx')
                # 支援單行和多行定義
                pattern = r'(\w+)\s*=\s*Blueprint\([^)]*url_prefix=[\'"]([^\'"]+)[\'"][^)]*\)'
                for match in re.finditer(pattern, content, re.DOTALL):
                    bp_var = match.group(1)
                    url_prefix = match.group(2)
                    bp_definition_prefixes[bp_var] = url_prefix
            except Exception:
                continue

        # 2. 掃描 register_blueprint 呼叫 (包括 api/__init__.py 和 web/__init__.py)
        register_files = [
            self.root_path / 'backend' / 'app' / 'api' / '__init__.py',
            self.root_path / 'backend' / 'app' / 'web' / '__init__.py',
        ]

        for init_file in register_files:
            if not init_file.exists():
                continue
            with open(init_file, 'r', encoding='utf-8') as f:
                content = f.read()

            # 匹配: app.register_blueprint(xxx_bp, url_prefix='/xxx')
            pattern = r'app\.register_blueprint\((\w+)(?:,\s*url_prefix=[\'"]([^\'"]+)[\'"])?\)'
            for match in re.finditer(pattern, content):
                bp_var = match.group(1)
                url_prefix = match.group(2)  # 可能是 None

                if url_prefix:
                    # register_blueprint 時指定的 url_prefix 優先
                    self.blueprint_prefixes[bp_var] = url_prefix
                    print(f"   ├─ {bp_var:25s} -> {url_prefix}")
                elif bp_var in bp_definition_prefixes:
                    # 使用定義時的 url_prefix
                    self.blueprint_prefixes[bp_var] = bp_definition_prefixes[bp_var]
                    print(f"   ├─ {bp_var:25s} -> {bp_definition_prefixes[bp_var]} (定義時)")
                else:
                    # 沒有 url_prefix (如 main_bp)
                    self.blueprint_prefixes[bp_var] = ''
                    print(f"   ├─ {bp_var:25s} -> / (無前綴)")

        print(f"   ✅ 找到 {len(self.blueprint_prefixes)} 個 Blueprint")

        # 3. 建立 Blueprint 變數名 -> Blueprint 名稱的映射
        self.bp_var_to_name = {}
        for py_file in (self.root_path / 'backend' / 'app').rglob('*.py'):
            if '__pycache__' in str(py_file):
                continue
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()

                # 匹配: xxx_bp = Blueprint('name', ...)
                pattern = r'(\w+)\s*=\s*Blueprint\([\'"]([^\'"]+)[\'"]'
                for match in re.finditer(pattern, content):
                    bp_var = match.group(1)
                    bp_name = match.group(2)
                    self.bp_var_to_name[bp_var] = bp_name
            except Exception:
                continue

    def scan_routes(self):
        """掃描所有 Flask 路由"""
        print("🔍 掃描 Flask 路由...")

        for py_file in (self.root_path / 'backend').rglob('*.py'):
            if '__pycache__' in str(py_file) or 'venv' in str(py_file):
                continue
            try:
                self._scan_file(py_file)
            except Exception as e:
                print(f"   ⚠️ 無法解析 {py_file}: {e}")

        print(f"   ✅ 找到 {len(self.routes)} 個路由")
        return self.routes

    def _scan_file(self, file_path: Path):
        """掃描單一 Python 檔案"""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 找出 docstring 範圍 (triple-quoted strings)
        # 用於忽略 docstring 中的範例程式碼
        docstring_ranges = []
        for pattern in [r'"""', r"'''"]:
            positions = [m.start() for m in re.finditer(pattern, content)]
            for i in range(0, len(positions) - 1, 2):
                if i + 1 < len(positions):
                    docstring_ranges.append((positions[i], positions[i + 1]))

        def is_in_docstring(pos: int) -> bool:
            """檢查位置是否在 docstring 內"""
            for start, end in docstring_ranges:
                if start < pos < end:
                    return True
            return False

        # 找出路由裝飾器
        # 匹配: @xxx.route('/path', methods=['GET', 'POST'])
        route_pattern = r'@(\w+)\.route\([\'"]([^\'"]*)[\'"](?:,\s*methods=\[([^\]]+)\])?\)'

        for match in re.finditer(route_pattern, content):
            # 跳過 docstring 中的範例程式碼
            if is_in_docstring(match.start()):
                continue
            bp_name = match.group(1)
            route_path = match.group(2)
            methods_str = match.group(3)

            # 解析 HTTP 方法
            if methods_str:
                methods = [m.strip().strip('\'"') for m in methods_str.split(',')]
            else:
                methods = ['GET']

            # 找函數名稱和安全裝飾器
            func_name, decorators = self._find_function_info(content, match.end())

            # 計算行號
            line_number = content[:match.start()].count('\n') + 1

            # 取得完整路徑
            full_path = self._get_full_path(bp_name, route_path)

            # 建立 endpoint (blueprint_name.function_name)
            bp_real_name = self.bp_var_to_name.get(bp_name, bp_name)
            endpoint = f"{bp_real_name}.{func_name}"

            route_info = {
                'path': full_path,
                'original_path': route_path,
                'methods': methods,
                'function': func_name,
                'blueprint': bp_name,
                'endpoint': endpoint,
                'file': str(file_path.relative_to(self.root_path)),
                'line': line_number,
                'decorators': decorators,
                'security_level': self._get_security_level(decorators),
            }
            self.routes.append(route_info)
            # 建立 endpoint -> path 映射
            self.endpoints[endpoint] = full_path

    def _get_full_path(self, bp_name: str, route_path: str) -> str:
        """取得完整路徑"""
        if bp_name in self.blueprint_prefixes:
            prefix = self.blueprint_prefixes[bp_name]
            if not route_path:
                # 空路由，直接返回前綴
                return prefix or '/'
            if route_path.startswith('/'):
                return prefix + route_path
            return prefix + '/' + route_path
        return route_path or '/'

    def _find_function_info(self, content: str, start_pos: int) -> Tuple[str, List[str]]:
        """找出函數名稱和裝飾器"""
        remaining = content[start_pos:]

        # 收集裝飾器
        decorators = []
        for decorator in self.SECURITY_DECORATORS.keys():
            if f'@{decorator}' in remaining[:500]:
                decorators.append(decorator)

        # 找函數名稱
        func_match = re.search(r'def\s+(\w+)\s*\(', remaining)
        func_name = func_match.group(1) if func_match else 'unknown'

        return func_name, decorators

    def _get_security_level(self, decorators: List[str]) -> str:
        """判斷安全等級"""
        if 'system_admin_required' in decorators:
            return '系統管理員'
        elif 'admin_required' in decorators:
            return '企業管理員'
        elif 'login_required' in decorators:
            return '需要登入'
        elif 'public_route' in decorators:
            return '公開'
        return '未標記'

    def export_to_excel(self, output_file: str):
        """匯出到 Excel"""
        if not HAS_OPENPYXL:
            print("❌ openpyxl 未安裝，無法匯出 Excel")
            return

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Flask 路由總覽"

        headers = ['完整路徑', 'HTTP方法', '函數名稱', 'Blueprint', '安全等級', '裝飾器', '檔案', '行號']
        styles = ExcelStyles.get_header_style()
        border = ExcelStyles.get_border()

        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=header)
            cell.font = styles['font']
            cell.fill = styles['fill']
            cell.alignment = styles['alignment']
            cell.border = border

        for idx, route in enumerate(self.routes, 2):
            ws.cell(row=idx, column=1, value=route['path']).border = border
            ws.cell(row=idx, column=2, value=', '.join(route['methods'])).border = border
            ws.cell(row=idx, column=3, value=route['function']).border = border
            ws.cell(row=idx, column=4, value=route['blueprint']).border = border
            ws.cell(row=idx, column=5, value=route['security_level']).border = border
            ws.cell(row=idx, column=6, value=', '.join(route['decorators'])).border = border
            ws.cell(row=idx, column=7, value=route['file']).border = border
            ws.cell(row=idx, column=8, value=route['line']).border = border

            # 根據安全等級上色
            if route['security_level'] == '系統管理員':
                for col in range(1, 9):
                    ws.cell(row=idx, column=col).fill = PatternFill(
                        start_color='FFCDD2', end_color='FFCDD2', fill_type='solid'
                    )
            elif route['security_level'] == '未標記':
                # Issue #12: 未標記路由使用紅色警告
                for col in range(1, 9):
                    ws.cell(row=idx, column=col).fill = PatternFill(
                        start_color='FF6B6B', end_color='FF6B6B', fill_type='solid'
                    )
                    ws.cell(row=idx, column=col).font = Font(color='FFFFFF', bold=True)

        # 設定欄寬
        ws.column_dimensions['A'].width = 40
        ws.column_dimensions['B'].width = 15
        ws.column_dimensions['C'].width = 25
        ws.column_dimensions['D'].width = 20
        ws.column_dimensions['E'].width = 15
        ws.column_dimensions['F'].width = 25
        ws.column_dimensions['G'].width = 45
        ws.column_dimensions['H'].width = 8

        ws.freeze_panes = 'A2'
        wb.save(output_file)
        print(f"   ✅ Excel 已生成: {output_file}")



# ============================================================================
# 2. 目錄結構分析器
# ============================================================================

class DirectoryAnalyzer:
    """目錄結構分析器"""

    IGNORE_DIRS = {
        '__pycache__', '.git', '.idea', '.vscode', 'node_modules',
        '.pytest_cache', 'venv', 'env', '.env', 'dist', 'build',
        'instance', 'htmlcov', '.coverage', '.mypy_cache'
    }

    IGNORE_FILES = {'.DS_Store', 'Thumbs.db', '.gitkeep', '*.pyc'}

    # BeakPlatform 專案目錄用途
    BEAKMASK_PURPOSES = {
        'backend/app/security': '安全核心模組 (認證/授權/RBAC)',
        'backend/app/api': 'API 路由 (Blueprint)',
        'backend/app/web': 'Web 頁面路由',
        'backend/app/models': '資料庫模型 (SQLAlchemy)',
        'backend/app/services': '業務邏輯服務層',
        'backend/app/templates': 'Jinja2 模板',
        'backend/tests': '測試檔案',
        'scripts': '輔助腳本',
        'docs': '專案文件',
        'docs/knowledge': '知識庫 (經驗累積)',
        '.semgrep': '安全掃描規則',
    }

    def __init__(self, root_path: Path):
        self.root_path = root_path
        self.results = []

    def analyze(self):
        """執行目錄結構分析"""
        print("🔍 開始分析目錄結構...")

        for root, dirs, files in os.walk(self.root_path):
            root_path = Path(root)

            # 過濾忽略的目錄
            dirs[:] = [d for d in dirs if d not in self.IGNORE_DIRS and not d.startswith('.')]

            try:
                relative_path = root_path.relative_to(self.root_path)
                if str(relative_path) == '.':
                    display_path = './'
                    level = 0
                else:
                    display_path = './' + str(relative_path).replace('\\', '/')
                    level = len(relative_path.parts)
            except ValueError:
                continue

            # 過濾檔案
            filtered_files = [f for f in files if not f.startswith('.') and not f.endswith('.pyc')]

            # 猜測目錄用途
            purpose = self._guess_purpose(str(relative_path), filtered_files)

            # 按副檔名分組
            files_by_ext = defaultdict(list)
            for f in filtered_files[:20]:  # 每個目錄最多 20 個檔案
                ext = Path(f).suffix.lower() or '(無副檔名)'
                if len(files_by_ext[ext]) < 10:
                    files_by_ext[ext].append(f)

            file_list = '\n'.join(
                f"{ext}: {', '.join(names)}"
                for ext, names in sorted(files_by_ext.items())
            ) or '(空目錄)'

            self.results.append({
                'path': display_path,
                'level': level,
                'purpose': purpose,
                'file_list': file_list,
                'total_files': len(filtered_files),
                'subdirs': len(dirs),
            })

        self.results.sort(key=lambda x: x['path'])
        print(f"   ✅ 分析完成，共 {len(self.results)} 個目錄")

    def _guess_purpose(self, relative_path: str, files: List[str]) -> str:
        """猜測目錄用途"""
        # 先檢查 BeakPlatform 專用目錄
        for path, purpose in self.BEAKMASK_PURPOSES.items():
            if relative_path == path or relative_path.startswith(path + '/'):
                return purpose

        # 通用判斷
        dir_name = Path(relative_path).name.lower()

        purposes = {
            'api': 'API 路由',
            'web': 'Web 頁面路由',
            'models': '資料庫模型',
            'services': '業務邏輯服務',
            'templates': 'Jinja2 模板',
            'static': '靜態資源',
            'tests': '測試檔案',
            'docs': '專案文件',
            'scripts': '輔助腳本',
            'migrations': '資料庫遷移',
            'components': '頁面元件',
            'pages': '頁面檔案',
            'layouts': '版型檔案',
        }

        for keyword, purpose in purposes.items():
            if keyword in dir_name:
                return purpose

        # 根據檔案類型判斷
        extensions = {Path(f).suffix.lower() for f in files}

        if '.py' in extensions:
            return 'Python 程式模組'
        if '.html' in extensions:
            return 'HTML 模板檔案'
        if '.js' in extensions:
            return 'JavaScript 模組'
        if '.css' in extensions:
            return '樣式表檔案'

        return '通用目錄'

    def export_to_excel(self, output_file: str):
        """匯出到 Excel"""
        if not HAS_OPENPYXL:
            print("❌ openpyxl 未安裝，無法匯出 Excel")
            return

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "目錄結構分析"

        headers = ['目錄路徑', '層級', '目錄用途', '檔案清單', '檔案數', '子目錄數']
        styles = ExcelStyles.get_header_style()
        border = ExcelStyles.get_border()

        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=header)
            cell.font = styles['font']
            cell.fill = styles['fill']
            cell.alignment = styles['alignment']
            cell.border = border

        for idx, result in enumerate(self.results, 2):
            ws.cell(row=idx, column=1, value=result['path']).border = border
            ws.cell(row=idx, column=2, value=result['level']).border = border
            ws.cell(row=idx, column=3, value=result['purpose']).border = border
            ws.cell(row=idx, column=4, value=result['file_list']).border = border
            ws.cell(row=idx, column=5, value=result['total_files']).border = border
            ws.cell(row=idx, column=6, value=result['subdirs']).border = border

            # 根據層級設定背景色
            if result['level'] == 0:
                for col in range(1, 7):
                    ws.cell(row=idx, column=col).fill = PatternFill(
                        start_color='E7E6E6', end_color='E7E6E6', fill_type='solid'
                    )

        # 設定欄寬
        ws.column_dimensions['A'].width = 45
        ws.column_dimensions['B'].width = 8
        ws.column_dimensions['C'].width = 35
        ws.column_dimensions['D'].width = 60
        ws.column_dimensions['E'].width = 10
        ws.column_dimensions['F'].width = 10

        ws.freeze_panes = 'A2'
        wb.save(output_file)
        print(f"   ✅ Excel 已生成: {output_file}")


# ============================================================================
# 3. 資料庫分析器
# ============================================================================

class DatabaseAnalyzer:
    """資料庫結構分析器"""

    def __init__(self, root_path: Path):
        self.root_path = root_path
        self.db_config = self._load_db_config()
        self.tables_info = []

    def _load_db_config(self) -> dict:
        """載入資料庫設定"""
        env_file = self.root_path / '.env'
        config = {
            'host': 'localhost',
            'port': '5432',
            'database': 'beakplatform_dev',
            'user': 'beakplatform',
            'password': 'postgres123',
        }

        if env_file.exists():
            with open(env_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if '=' in line and not line.startswith('#'):
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")

                        # 優先使用 DATABASE_URL
                        if key == 'DATABASE_URL' and value:
                            # postgresql://user:pass@host:port/dbname
                            import re
                            match = re.match(
                                r'postgresql://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)',
                                value
                            )
                            if match:
                                config['user'] = match.group(1)
                                config['password'] = match.group(2)
                                config['host'] = match.group(3)
                                config['port'] = match.group(4)
                                config['database'] = match.group(5)
                                break  # DATABASE_URL 優先，不再讀取其他設定

        return config

    def analyze(self):
        """分析資料庫結構"""
        if not HAS_PSYCOPG2:
            print("❌ psycopg2 未安裝，無法分析資料庫")
            print("   安裝: pip install psycopg2-binary")
            return

        print(f"🔍 連接資料庫: {self.db_config['database']}...")

        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()

            # 取得所有資料表
            cursor.execute("""
                SELECT table_name,
                       obj_description(('"' || table_schema || '"."' || table_name || '"')::regclass, 'pg_class') as table_comment
                FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_type = 'BASE TABLE'
                ORDER BY table_name;
            """)
            tables = cursor.fetchall()

            print(f"   ✅ 找到 {len(tables)} 個資料表")

            for table_name, table_comment in tables:
                # 取得資料筆數
                cursor.execute(f'SELECT COUNT(*) FROM "{table_name}"')
                count = cursor.fetchone()[0]

                # 取得欄位資訊
                cursor.execute("""
                    SELECT column_name, data_type, is_nullable,
                           col_description(('"public"."' || %s || '"')::regclass::oid, ordinal_position) as comment
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = %s
                    ORDER BY ordinal_position;
                """, (table_name, table_name))
                columns = cursor.fetchall()

                self.tables_info.append({
                    'name': table_name,
                    'comment': table_comment or '',
                    'count': count,
                    'columns': [
                        {
                            'name': col[0],
                            'type': col[1],
                            'nullable': col[2],
                            'comment': col[3] or '',
                        }
                        for col in columns
                    ],
                })
                print(f"   ├─ {table_name}: {count:,} 筆, {len(columns)} 欄位")

            cursor.close()
            conn.close()

        except Exception as e:
            print(f"   ❌ 資料庫連接失敗: {e}")

    def export_to_excel(self, output_file: str):
        """匯出到 Excel"""
        if not HAS_OPENPYXL or not self.tables_info:
            return

        wb = openpyxl.Workbook()
        styles = ExcelStyles.get_header_style()
        border = ExcelStyles.get_border()

        # 目錄頁
        ws = wb.active
        ws.title = "目錄"

        headers = ['序號', '資料表名稱', '說明', '資料筆數', '欄位數']
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=header)
            cell.font = styles['font']
            cell.fill = styles['fill']
            cell.border = border

        for idx, table in enumerate(self.tables_info, 2):
            ws.cell(row=idx, column=1, value=idx-1).border = border
            ws.cell(row=idx, column=2, value=table['name']).border = border
            ws.cell(row=idx, column=3, value=table['comment']).border = border
            ws.cell(row=idx, column=4, value=table['count']).border = border
            ws.cell(row=idx, column=5, value=len(table['columns'])).border = border

        ws.column_dimensions['A'].width = 8
        ws.column_dimensions['B'].width = 30
        ws.column_dimensions['C'].width = 40
        ws.column_dimensions['D'].width = 12
        ws.column_dimensions['E'].width = 10

        # 各資料表頁籤
        for table in self.tables_info:
            sheet_name = table['name'][:31]
            ws = wb.create_sheet(title=sheet_name)

            # 表頭
            ws['A1'] = f"資料表: {table['name']}"
            ws['A1'].font = Font(bold=True, size=14)
            ws['A2'] = f"說明: {table['comment']}"
            ws['A3'] = f"資料筆數: {table['count']:,}"

            # 欄位資訊
            col_headers = ['欄位名稱', '資料型態', '可空', '說明']
            for col, header in enumerate(col_headers, 1):
                cell = ws.cell(row=5, column=col, value=header)
                cell.font = styles['font']
                cell.fill = styles['fill']
                cell.border = border

            for idx, col_info in enumerate(table['columns'], 6):
                ws.cell(row=idx, column=1, value=col_info['name']).border = border
                ws.cell(row=idx, column=2, value=col_info['type']).border = border
                ws.cell(row=idx, column=3, value=col_info['nullable']).border = border
                ws.cell(row=idx, column=4, value=col_info['comment']).border = border

            ws.column_dimensions['A'].width = 25
            ws.column_dimensions['B'].width = 20
            ws.column_dimensions['C'].width = 10
            ws.column_dimensions['D'].width = 40

        wb.save(output_file)
        print(f"   ✅ Excel 已生成: {output_file}")


# ============================================================================
# 4. 前端分析器
# ============================================================================

class FrontendAnalyzer:
    """前端 API 呼叫分析器"""

    def __init__(self, root_path: Path):
        self.root_path = root_path
        self.api_calls = []

    def scan(self):
        """掃描前端 API 呼叫"""
        print("🔍 掃描前端 API 呼叫...")

        # 掃描 HTML 模板
        templates_dir = self.root_path / 'backend' / 'app' / 'templates'
        if templates_dir.exists():
            for html_file in templates_dir.rglob('*.html'):
                self._scan_file(html_file, 'html')

        # 掃描 JS 檔案
        for js_file in self.root_path.rglob('*.js'):
            if 'node_modules' in str(js_file) or 'venv' in str(js_file):
                continue
            self._scan_file(js_file, 'js')

        print(f"   ✅ 找到 {len(self.api_calls)} 個 API 呼叫")
        return self.api_calls

    def _scan_file(self, file_path: Path, file_type: str):
        """掃描單一檔案"""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except Exception:
            return

        relative_path = str(file_path.relative_to(self.root_path))

        # 1. 解析 JavaScript 變數定義 (const/let/var XXX = '/api/...')
        js_vars = {}
        for match in re.finditer(r'(?:const|let|var)\s+(\w+)\s*=\s*[\'"]([^\'"]+)[\'"]', content):
            var_name = match.group(1)
            var_value = match.group(2)
            if var_value.startswith('/'):
                js_vars[var_name] = var_value

        # 2. fetch 呼叫 (靜態字串)
        for match in re.finditer(r'fetch\s*\(\s*[\'"]([^\'"]+)[\'"]', content):
            api_path = match.group(1)
            if api_path.startswith('/'):
                self.api_calls.append({
                    'api': api_path.split('?')[0],
                    'file': relative_path,
                    'file_type': file_type,
                    'method': 'fetch',
                    'line': content[:match.start()].count('\n') + 1,
                })

        # 3. fetch 動態路徑 (模板字串 `...`)
        for match in re.finditer(r'fetch\s*\(\s*`([^`]+)`', content):
            api_path = match.group(1)

            # 替換已知的 JavaScript 變數
            for var_name, var_value in js_vars.items():
                api_path = api_path.replace(f'${{{var_name}}}', var_value)

            # 將剩餘的 ${xxx} 替換為 <param> 以便比對
            normalized = re.sub(r'\$\{[^}]+\}', '<param>', api_path)

            if normalized.startswith('/'):
                self.api_calls.append({
                    'api': normalized.split('?')[0],
                    'file': relative_path,
                    'file_type': file_type,
                    'method': 'fetch',
                    'line': content[:match.start()].count('\n') + 1,
                })

        # 4. axios 呼叫
        for match in re.finditer(r'axios\.(get|post|put|delete|patch)\s*\(\s*[\'"`]([^\'"` ]+)[\'"`]', content):
            http_method = match.group(1).upper()
            api_path = match.group(2)
            if api_path.startswith('/'):
                self.api_calls.append({
                    'api': api_path.split('?')[0],
                    'file': relative_path,
                    'file_type': file_type,
                    'method': f'axios.{http_method}',
                    'line': content[:match.start()].count('\n') + 1,
                })

        # url_for 呼叫 (Jinja2)
        for match in re.finditer(r"url_for\s*\(\s*['\"]([^'\"]+)['\"]", content):
            endpoint = match.group(1)
            self.api_calls.append({
                'api': f"url_for({endpoint})",
                'file': relative_path,
                'file_type': file_type,
                'method': 'url_for',
                'line': content[:match.start()].count('\n') + 1,
            })


# ============================================================================
# 主程式
# ============================================================================

def run_routes_analysis(root_path: Path, output_dir: Path):
    """執行路由分析"""
    print("\n" + "=" * 60)
    print("📊 路由分析")
    print("=" * 60)

    analyzer = RouteAnalyzer(root_path)
    analyzer.scan_blueprint_prefixes()
    analyzer.scan_routes()

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    if HAS_OPENPYXL:
        excel_file = output_dir / f'BeakPlatform_路由分析_{timestamp}.xlsx'
        analyzer.export_to_excel(str(excel_file))

    # 統計
    print(f"\n📈 路由統計:")
    by_security = defaultdict(int)
    for route in analyzer.routes:
        by_security[route['security_level']] += 1

    for level, count in sorted(by_security.items()):
        print(f"   {level}: {count}")


def run_structure_analysis(root_path: Path, output_dir: Path):
    """執行目錄結構分析"""
    print("\n" + "=" * 60)
    print("📊 目錄結構分析")
    print("=" * 60)

    analyzer = DirectoryAnalyzer(root_path)
    analyzer.analyze()

    if HAS_OPENPYXL:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        excel_file = output_dir / f'BeakPlatform_目錄結構_{timestamp}.xlsx'
        analyzer.export_to_excel(str(excel_file))


def run_database_analysis(root_path: Path, output_dir: Path):
    """執行資料庫分析"""
    print("\n" + "=" * 60)
    print("📊 資料庫結構分析")
    print("=" * 60)

    analyzer = DatabaseAnalyzer(root_path)
    analyzer.analyze()

    if HAS_OPENPYXL and analyzer.tables_info:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        excel_file = output_dir / f'BeakPlatform_資料庫結構_{timestamp}.xlsx'
        analyzer.export_to_excel(str(excel_file))


def run_unused_analysis(root_path: Path, output_dir: Path):
    """執行未使用檔案分析"""
    print("\n" + "=" * 60)
    print("📊 未使用檔案分析")
    print("=" * 60)

    # 先執行路由和前端分析
    route_analyzer = RouteAnalyzer(root_path)
    route_analyzer.scan_blueprint_prefixes()
    route_analyzer.scan_routes()

    frontend_analyzer = FrontendAnalyzer(root_path)
    frontend_analyzer.scan()

    # 建立索引
    api_routes_by_path = {r['path']: r for r in route_analyzer.routes}
    api_routes_by_endpoint = route_analyzer.endpoints  # endpoint -> path

    # 分離 url_for 呼叫和一般 API 呼叫
    url_for_calls = [c for c in frontend_analyzer.api_calls if c['method'] == 'url_for']
    fetch_calls = [c for c in frontend_analyzer.api_calls if c['method'] != 'url_for']

    # 統計已使用的路由
    used_routes = set()

    # 1. 處理 url_for 呼叫 (endpoint 格式)
    for call in url_for_calls:
        # url_for(auth.login) -> 取出 auth.login
        endpoint = call['api'].replace('url_for(', '').replace(')', '')
        if endpoint in api_routes_by_endpoint:
            used_routes.add(api_routes_by_endpoint[endpoint])

    # 2. 處理一般 fetch/axios 呼叫 (路徑格式)
    for call in fetch_calls:
        api_path = call['api']

        # 直接匹配
        if api_path in api_routes_by_path:
            used_routes.add(api_path)
            continue

        # 模糊匹配 (處理 <param> 和路由參數)
        # 將所有參數正規化為 <*> 後比對
        api_normalized = re.sub(r'<[^>]+>', '<*>', api_path)
        for route_path in api_routes_by_path:
            route_normalized = re.sub(r'<[^>]+>', '<*>', route_path)
            if route_normalized == api_normalized:
                used_routes.add(route_path)
                break

    # 找出未被呼叫的路由
    unused_routes = [r for r in route_analyzer.routes if r['path'] not in used_routes]

    # 找出無法對應的 API 呼叫
    unmatched_calls = []
    for call in frontend_analyzer.api_calls:
        if call['method'] == 'url_for':
            endpoint = call['api'].replace('url_for(', '').replace(')', '')
            if endpoint not in api_routes_by_endpoint:
                unmatched_calls.append(call)
        else:
            api_path = call['api']
            matched = api_path in api_routes_by_path
            if not matched:
                # 模糊匹配 - 將所有參數正規化為 <*> 後比對
                api_normalized = re.sub(r'<[^>]+>', '<*>', api_path)
                for route_path in api_routes_by_path:
                    route_normalized = re.sub(r'<[^>]+>', '<*>', route_path)
                    if route_normalized == api_normalized:
                        matched = True
                        break
            if not matched:
                unmatched_calls.append(call)

    print(f"\n📈 分析結果:")
    print(f"   已使用路由: {len(used_routes)}/{len(route_analyzer.routes)}")
    print(f"   未使用路由: {len(unused_routes)}/{len(route_analyzer.routes)}")
    print(f"   無法對應的 API 呼叫: {len(unmatched_calls)}/{len(frontend_analyzer.api_calls)}")

    if unused_routes:
        print(f"\n⚠️  未被呼叫的路由 ({len(unused_routes)} 個):")
        for route in unused_routes:
            print(f"   ├─ {route['path']} ({route['endpoint']})")

    if unmatched_calls:
        print(f"\n⚠️  無法對應的 API 呼叫 (前 10 個):")
        for call in unmatched_calls[:10]:
            print(f"   ├─ {call['api']} (from {call['file']}:{call['line']})")

    # Issue #11: 匯出到 Excel
    if HAS_OPENPYXL:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        excel_file = output_dir / f'BeakPlatform_未使用分析_{timestamp}.xlsx'
        export_unused_to_excel(
            excel_file,
            unused_routes,
            unmatched_calls,
            route_analyzer.routes,
            frontend_analyzer.api_calls,
            used_routes
        )


def export_unused_to_excel(output_file: Path, unused_routes: list, unmatched_calls: list,
                           all_routes: list, all_calls: list, used_routes: set):
    """匯出未使用分析結果到 Excel (Issue #11)"""
    wb = openpyxl.Workbook()
    styles = ExcelStyles.get_header_style()
    border = ExcelStyles.get_border()

    # ========== 摘要頁 ==========
    ws = wb.active
    ws.title = "摘要"

    ws['A1'] = "BeakPlatform 未使用分析報告"
    ws['A1'].font = Font(bold=True, size=16)
    ws['A3'] = f"分析時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

    summary_data = [
        ('總路由數', len(all_routes)),
        ('已使用路由', len(used_routes)),
        ('未使用路由', len(unused_routes)),
        ('未使用比例', f"{len(unused_routes)/len(all_routes)*100:.1f}%" if all_routes else "N/A"),
        ('', ''),
        ('總 API 呼叫數', len(all_calls)),
        ('無法對應的呼叫', len(unmatched_calls)),
    ]

    for idx, (label, value) in enumerate(summary_data, 5):
        ws.cell(row=idx, column=1, value=label).font = Font(bold=True)
        ws.cell(row=idx, column=2, value=value)

    ws.column_dimensions['A'].width = 20
    ws.column_dimensions['B'].width = 15

    # ========== 未使用路由頁 ==========
    ws_unused = wb.create_sheet("未使用路由")

    headers = ['路徑', 'HTTP 方法', '函數名稱', 'Blueprint', '安全等級', '檔案', '行號']
    for col, header in enumerate(headers, 1):
        cell = ws_unused.cell(row=1, column=col, value=header)
        cell.font = styles['font']
        cell.fill = styles['fill']
        cell.border = border

    for idx, route in enumerate(unused_routes, 2):
        ws_unused.cell(row=idx, column=1, value=route['path']).border = border
        ws_unused.cell(row=idx, column=2, value=', '.join(route['methods'])).border = border
        ws_unused.cell(row=idx, column=3, value=route['function']).border = border
        ws_unused.cell(row=idx, column=4, value=route['blueprint']).border = border
        ws_unused.cell(row=idx, column=5, value=route['security_level']).border = border
        ws_unused.cell(row=idx, column=6, value=route['file']).border = border
        ws_unused.cell(row=idx, column=7, value=route['line']).border = border

        # 未標記路由紅色警告
        if route['security_level'] == '未標記':
            for col in range(1, 8):
                ws_unused.cell(row=idx, column=col).fill = PatternFill(
                    start_color='FF6B6B', end_color='FF6B6B', fill_type='solid'
                )
                ws_unused.cell(row=idx, column=col).font = Font(color='FFFFFF')

    ws_unused.column_dimensions['A'].width = 40
    ws_unused.column_dimensions['B'].width = 12
    ws_unused.column_dimensions['C'].width = 25
    ws_unused.column_dimensions['D'].width = 18
    ws_unused.column_dimensions['E'].width = 12
    ws_unused.column_dimensions['F'].width = 45
    ws_unused.column_dimensions['G'].width = 8
    ws_unused.freeze_panes = 'A2'

    # ========== 無法對應的 API 呼叫頁 ==========
    ws_unmatched = wb.create_sheet("無法對應的呼叫")

    headers = ['API 路徑', '呼叫方式', '檔案', '行號']
    for col, header in enumerate(headers, 1):
        cell = ws_unmatched.cell(row=1, column=col, value=header)
        cell.font = styles['font']
        cell.fill = styles['fill']
        cell.border = border

    for idx, call in enumerate(unmatched_calls, 2):
        ws_unmatched.cell(row=idx, column=1, value=call['api']).border = border
        ws_unmatched.cell(row=idx, column=2, value=call['method']).border = border
        ws_unmatched.cell(row=idx, column=3, value=call['file']).border = border
        ws_unmatched.cell(row=idx, column=4, value=call['line']).border = border

    ws_unmatched.column_dimensions['A'].width = 50
    ws_unmatched.column_dimensions['B'].width = 15
    ws_unmatched.column_dimensions['C'].width = 50
    ws_unmatched.column_dimensions['D'].width = 8
    ws_unmatched.freeze_panes = 'A2'

    wb.save(output_file)
    print(f"   ✅ Excel 已生成: {output_file}")


def run_duplicates_analysis(root_path: Path, output_dir: Path):
    """執行重複路由檢測 (Issue #13)"""
    print("\n" + "=" * 60)
    print("📊 重複路由檢測")
    print("=" * 60)

    analyzer = RouteAnalyzer(root_path)
    analyzer.scan_blueprint_prefixes()
    analyzer.scan_routes()

    # 按路徑分組
    routes_by_path = defaultdict(list)
    for route in analyzer.routes:
        # 使用正規化路徑（忽略參數名稱差異）
        normalized_path = re.sub(r'<[^>]+>', '<param>', route['path'])
        routes_by_path[normalized_path].append(route)

    # 找出同路徑多方法的路由
    multi_method_routes = {
        path: routes for path, routes in routes_by_path.items()
        if len(routes) > 1
    }

    # 找出真正的重複（同路徑同方法）
    true_duplicates = []
    for path, routes in routes_by_path.items():
        methods_seen = {}
        for route in routes:
            for method in route['methods']:
                key = (path, method)
                if key in methods_seen:
                    true_duplicates.append({
                        'path': route['path'],
                        'method': method,
                        'route1': methods_seen[key],
                        'route2': route,
                    })
                else:
                    methods_seen[key] = route

    print(f"\n📈 分析結果:")
    print(f"   同路徑多方法的路由組: {len(multi_method_routes)}")
    print(f"   真正重複的路由 (同路徑同方法): {len(true_duplicates)}")

    if multi_method_routes:
        print(f"\n📋 同路徑多方法的路由:")
        for path, routes in sorted(multi_method_routes.items()):
            print(f"\n   {path}")
            for route in routes:
                methods = ', '.join(route['methods'])
                print(f"      ├─ [{methods}] -> {route['function']} ({route['file']}:{route['line']})")

    if true_duplicates:
        print(f"\n⚠️  真正重複的路由 (需要檢查):")
        for dup in true_duplicates:
            print(f"   ├─ {dup['path']} [{dup['method']}]")
            print(f"      Route 1: {dup['route1']['function']} ({dup['route1']['file']}:{dup['route1']['line']})")
            print(f"      Route 2: {dup['route2']['function']} ({dup['route2']['file']}:{dup['route2']['line']})")

    # 匯出到 Excel
    if HAS_OPENPYXL:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        excel_file = output_dir / f'BeakPlatform_重複路由_{timestamp}.xlsx'
        export_duplicates_to_excel(excel_file, multi_method_routes, true_duplicates)


def export_duplicates_to_excel(output_file: Path, multi_method_routes: dict, true_duplicates: list):
    """匯出重複路由到 Excel"""
    wb = openpyxl.Workbook()
    styles = ExcelStyles.get_header_style()
    border = ExcelStyles.get_border()

    # ========== 同路徑多方法頁 ==========
    ws = wb.active
    ws.title = "同路徑多方法"

    headers = ['路徑', 'HTTP 方法', '函數名稱', '檔案', '行號']
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = styles['font']
        cell.fill = styles['fill']
        cell.border = border

    row = 2
    for path, routes in sorted(multi_method_routes.items()):
        for route in routes:
            ws.cell(row=row, column=1, value=route['path']).border = border
            ws.cell(row=row, column=2, value=', '.join(route['methods'])).border = border
            ws.cell(row=row, column=3, value=route['function']).border = border
            ws.cell(row=row, column=4, value=route['file']).border = border
            ws.cell(row=row, column=5, value=route['line']).border = border
            row += 1
        # 加空行分隔不同路徑
        row += 1

    ws.column_dimensions['A'].width = 45
    ws.column_dimensions['B'].width = 15
    ws.column_dimensions['C'].width = 25
    ws.column_dimensions['D'].width = 45
    ws.column_dimensions['E'].width = 8
    ws.freeze_panes = 'A2'

    # ========== 真正重複頁 ==========
    if true_duplicates:
        ws_dup = wb.create_sheet("真正重複")

        headers = ['路徑', '方法', '函數1', '檔案1', '行號1', '函數2', '檔案2', '行號2']
        for col, header in enumerate(headers, 1):
            cell = ws_dup.cell(row=1, column=col, value=header)
            cell.font = styles['font']
            cell.fill = styles['fill']
            cell.border = border

        for idx, dup in enumerate(true_duplicates, 2):
            ws_dup.cell(row=idx, column=1, value=dup['path']).border = border
            ws_dup.cell(row=idx, column=2, value=dup['method']).border = border
            ws_dup.cell(row=idx, column=3, value=dup['route1']['function']).border = border
            ws_dup.cell(row=idx, column=4, value=dup['route1']['file']).border = border
            ws_dup.cell(row=idx, column=5, value=dup['route1']['line']).border = border
            ws_dup.cell(row=idx, column=6, value=dup['route2']['function']).border = border
            ws_dup.cell(row=idx, column=7, value=dup['route2']['file']).border = border
            ws_dup.cell(row=idx, column=8, value=dup['route2']['line']).border = border

            # 紅色警告
            for col in range(1, 9):
                ws_dup.cell(row=idx, column=col).fill = PatternFill(
                    start_color='FF6B6B', end_color='FF6B6B', fill_type='solid'
                )
                ws_dup.cell(row=idx, column=col).font = Font(color='FFFFFF')

        ws_dup.freeze_panes = 'A2'

    wb.save(output_file)
    print(f"   ✅ Excel 已生成: {output_file}")


def run_deadcode_analysis(root_path: Path, output_dir: Path):
    """執行死代碼檢測 (Issue #14)"""
    print("\n" + "=" * 60)
    print("📊 死代碼檢測")
    print("=" * 60)

    backend_path = root_path / 'backend'
    if not backend_path.exists():
        print("   ❌ 找不到 backend 目錄")
        return

    # 收集所有 Python 模組
    all_modules = set()
    module_files = {}  # module_name -> file_path

    for py_file in backend_path.rglob('*.py'):
        if '__pycache__' in str(py_file):
            continue

        # 跳過測試檔案
        if 'tests' in str(py_file) or 'test_' in py_file.name:
            continue

        relative_path = py_file.relative_to(backend_path)
        # 轉換為模組名稱 (app/models/user.py -> app.models.user)
        if py_file.name == '__init__.py':
            module_name = str(relative_path.parent).replace('/', '.').replace('\\', '.')
        else:
            module_name = str(relative_path.with_suffix('')).replace('/', '.').replace('\\', '.')

        if module_name and module_name != '.':
            all_modules.add(module_name)
            module_files[module_name] = str(relative_path)

    print(f"   找到 {len(all_modules)} 個 Python 模組")

    # 收集所有 import 語句
    imported_modules = set()

    for py_file in backend_path.rglob('*.py'):
        if '__pycache__' in str(py_file):
            continue

        try:
            with open(py_file, 'r', encoding='utf-8') as f:
                content = f.read()

            # 匹配 import xxx 和 from xxx import yyy
            for match in re.finditer(r'^import\s+([\w.]+)', content, re.MULTILINE):
                imported_modules.add(match.group(1))

            for match in re.finditer(r'^from\s+([\w.]+)\s+import', content, re.MULTILINE):
                module = match.group(1)
                imported_modules.add(module)
                # 也加入父模組
                parts = module.split('.')
                for i in range(1, len(parts)):
                    imported_modules.add('.'.join(parts[:i]))

        except Exception:
            continue

    # 找出未被引用的模組
    # 排除入口點和 __init__.py
    entry_points = {'run', 'app', 'wsgi', 'manage'}

    orphan_modules = []
    for module in all_modules:
        module_base = module.split('.')[-1]

        # 排除入口點
        if module_base in entry_points:
            continue

        # 排除 __init__ (會被自動載入)
        if module_base == '__init__':
            continue

        # 檢查是否被引用
        is_imported = False
        for imported in imported_modules:
            if imported == module or imported.startswith(module + '.') or module.startswith(imported + '.'):
                is_imported = True
                break

        if not is_imported:
            orphan_modules.append({
                'module': module,
                'file': module_files.get(module, ''),
            })

    print(f"   已引用模組: {len(imported_modules)}")
    print(f"   未被引用的模組: {len(orphan_modules)}")

    if orphan_modules:
        print(f"\n⚠️  可能的死代碼 (未被 import 的模組):")
        for orphan in orphan_modules[:20]:
            print(f"   ├─ {orphan['module']} ({orphan['file']})")
        if len(orphan_modules) > 20:
            print(f"   └─ ... 還有 {len(orphan_modules) - 20} 個")

    # 匯出到 Excel
    if HAS_OPENPYXL and orphan_modules:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        excel_file = output_dir / f'BeakPlatform_死代碼_{timestamp}.xlsx'
        export_deadcode_to_excel(excel_file, orphan_modules, all_modules, imported_modules)


def export_deadcode_to_excel(output_file: Path, orphan_modules: list, all_modules: set, imported_modules: set):
    """匯出死代碼分析到 Excel"""
    wb = openpyxl.Workbook()
    styles = ExcelStyles.get_header_style()
    border = ExcelStyles.get_border()

    # ========== 摘要頁 ==========
    ws = wb.active
    ws.title = "摘要"

    ws['A1'] = "BeakPlatform 死代碼分析報告"
    ws['A1'].font = Font(bold=True, size=16)
    ws['A3'] = f"分析時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

    summary_data = [
        ('總模組數', len(all_modules)),
        ('已引用模組', len(imported_modules)),
        ('未被引用模組', len(orphan_modules)),
    ]

    for idx, (label, value) in enumerate(summary_data, 5):
        ws.cell(row=idx, column=1, value=label).font = Font(bold=True)
        ws.cell(row=idx, column=2, value=value)

    ws.column_dimensions['A'].width = 20
    ws.column_dimensions['B'].width = 15

    # ========== 未引用模組頁 ==========
    ws_orphan = wb.create_sheet("未引用模組")

    headers = ['模組名稱', '檔案路徑']
    for col, header in enumerate(headers, 1):
        cell = ws_orphan.cell(row=1, column=col, value=header)
        cell.font = styles['font']
        cell.fill = styles['fill']
        cell.border = border

    for idx, orphan in enumerate(orphan_modules, 2):
        ws_orphan.cell(row=idx, column=1, value=orphan['module']).border = border
        ws_orphan.cell(row=idx, column=2, value=orphan['file']).border = border

        # 黃色警告
        for col in range(1, 3):
            ws_orphan.cell(row=idx, column=col).fill = PatternFill(
                start_color='FFF3CD', end_color='FFF3CD', fill_type='solid'
            )

    ws_orphan.column_dimensions['A'].width = 40
    ws_orphan.column_dimensions['B'].width = 50
    ws_orphan.freeze_panes = 'A2'

    wb.save(output_file)
    print(f"   ✅ Excel 已生成: {output_file}")


def main():
    """主程式"""
    parser = argparse.ArgumentParser(
        description='BeakPlatform 專案分析工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
    python scripts/analyze_project.py routes      # API 路由分析
    python scripts/analyze_project.py structure   # 目錄結構分析
    python scripts/analyze_project.py database    # 資料庫結構匯出
    python scripts/analyze_project.py unused      # 未使用檔案分析 (Issue #11)
    python scripts/analyze_project.py duplicates  # 重複路由檢測 (Issue #13)
    python scripts/analyze_project.py deadcode    # 死代碼檢測 (Issue #14)
    python scripts/analyze_project.py all         # 執行所有分析
        """
    )

    parser.add_argument(
        'command',
        choices=['routes', 'structure', 'database', 'unused', 'duplicates', 'deadcode', 'all'],
        help='分析類型'
    )

    parser.add_argument(
        '-o', '--output',
        default='.',
        help='輸出目錄 (預設: 當前目錄)'
    )

    args = parser.parse_args()

    root_path = PROJECT_ROOT
    output_dir = Path(args.output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("  BeakPlatform 專案分析工具")
    print("=" * 60)
    print(f"專案路徑: {root_path}")
    print(f"輸出目錄: {output_dir}")

    if args.command == 'routes' or args.command == 'all':
        run_routes_analysis(root_path, output_dir)

    if args.command == 'structure' or args.command == 'all':
        run_structure_analysis(root_path, output_dir)

    if args.command == 'database' or args.command == 'all':
        run_database_analysis(root_path, output_dir)

    if args.command == 'unused' or args.command == 'all':
        run_unused_analysis(root_path, output_dir)

    if args.command == 'duplicates' or args.command == 'all':
        run_duplicates_analysis(root_path, output_dir)

    if args.command == 'deadcode' or args.command == 'all':
        run_deadcode_analysis(root_path, output_dir)

    print("\n" + "=" * 60)
    print("🎉 分析完成！")
    print("=" * 60)


if __name__ == '__main__':
    main()
