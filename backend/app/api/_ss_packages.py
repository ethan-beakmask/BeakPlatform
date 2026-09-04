"""
System Settings - 套件版本查詢子模組

端點：
- GET    /api/system-settings/package-versions        查詢套件版本
"""
import json
import os
import re
import subprocess
import time
import importlib.metadata
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from packaging.version import Version, InvalidVersion
from flask import jsonify, request

from app.services.holiday_calendar_service import TW_GOV_CALENDAR_URL, TW_GOV_CURATOR_URL, TW_GOV_DATASET_URL
from ..security.decorators import system_admin_required


DATA_SOURCES = [{
    'key': 'tw_gov_calendar',
    'name': '中華民國政府行政機關辦公日曆表',
    'provider': '政府資料開放平台',
    'provider_url': TW_GOV_DATASET_URL,
    'license': '政府資料開放授權條款－第 1 版（相容 CC BY 4.0）',
    'curator': 'ruyut/TaiwanCalendar',
    'curator_url': TW_GOV_CURATOR_URL,
    'endpoint': TW_GOV_CALENDAR_URL,
}]


# 記憶體快取
_package_versions_cache = {
    'data': None,
    'cached_at': None,
    'ttl': 1800  # 30 分鐘
}

# Vendor 套件 metadata（顯示名稱 + npm 套件名）
# 清單由掃描 vendor/ 目錄自動產生，此處僅提供 npm 名稱對照
VENDOR_META = {
    'bootstrap': {'display': 'Bootstrap', 'npm': 'bootstrap'},
    'alpine': {'display': 'Alpine.js', 'npm': 'alpinejs'},
    'cytoscape': {'display': 'Cytoscape.js', 'npm': 'cytoscape'},
    'formio': {'display': 'Formio', 'npm': '@formio/js'},
    'fontawesome': {'display': 'Font Awesome', 'npm': '@fortawesome/fontawesome-free'},
    'ace': {'display': 'Ace Editor', 'npm': 'ace-builds'},
    'gridstack': {'display': 'GridStack', 'npm': 'gridstack'},
    'wunderbaum': {'display': 'Wunderbaum', 'npm': 'wunderbaum'},
    'mermaid': {'display': 'Mermaid', 'npm': 'mermaid'},
}

# 掃描時略過的目錄/檔案（非套件項目）
VENDOR_SCAN_SKIP = {'fonts', 'jstree-theme'}

# 版本覆寫來源（優先於從檔案內容偵測）
# 存在的理由：minified dist 內的版本字串會落後或根本不是套件自己的版本。
#   - GridStack 13.0.2 的 dist 內仍寫 GDRev="13.0.1"（上游打包時漏更新）
#   - 內容偵測會抓到內嵌依賴的版本（mermaid 曾被抓成 3.0.9）
# 兩者都會讓套件版本頁顯示假的「可更新」或錯誤版本，且不會有任何錯誤訊息。
VENDOR_VERSION_FILE = 'VERSION'          # 目錄型套件：vendor/<pkg>/VERSION
VENDOR_VERSION_MANIFEST = 'versions.json'  # 單檔型套件：vendor/versions.json 的 {key: 版本}

# 版本號格式（覆寫值不合格式一律忽略，退回檔案偵測）
_VERSION_PATTERN = re.compile(r'\d+\.\d+\.\d+')

# versions.json 的快取（依 mtime 失效）
_version_manifest_cache = {'mtime': None, 'data': {}}


def register(bp):
    """將套件版本路由掛載到 Blueprint"""

    @bp.route('/package-versions', methods=['GET'])
    @system_admin_required
    def get_package_versions():
        """
        查詢 Python 後端套件 + 前端 vendor 套件的版本資訊

        Query params:
            refresh: 'true' 強制重新查詢（忽略快取）
        """
        force_refresh = request.args.get('refresh', '').lower() == 'true'
        now = time.time()

        # 檢查快取
        cache = _package_versions_cache
        if (not force_refresh
                and cache['data'] is not None
                and cache['cached_at'] is not None
                and (now - cache['cached_at']) < cache['ttl']):
            result = cache['data'].copy()
            result['cached'] = True
            result['cached_at'] = datetime.fromtimestamp(cache['cached_at']).isoformat()
            return jsonify({'success': True, 'data': result})

        # 執行查詢
        data = _check_package_versions()

        # 更新快取
        cache['data'] = data
        cache['cached_at'] = now

        data_response = data.copy()
        data_response['cached'] = False
        data_response['cached_at'] = datetime.fromtimestamp(now).isoformat()

        return jsonify({'success': True, 'data': data_response})


# =============================================================================
# Helper Functions
# =============================================================================

def _parse_requirements():
    """解析 requirements.txt"""
    req_path = os.path.join(os.path.dirname(__file__), '..', '..', 'requirements.txt')
    req_path = os.path.normpath(req_path)
    packages = []

    if not os.path.exists(req_path):
        return packages

    with open(req_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            # 解析 name==version 或 name>=version 等
            match = re.match(r'^([a-zA-Z0-9_-]+)\s*([>=<~!]+)\s*([\d.]+)', line)
            if match:
                packages.append({
                    'name': match.group(1),
                    'required_version': match.group(3),
                    'operator': match.group(2),
                })
    return packages


def _get_installed_version(package_name):
    """取得已安裝版本"""
    try:
        return importlib.metadata.version(package_name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _fetch_pypi_latest(package_name):
    """從 PyPI 取得最新版本"""
    import requests as req_lib
    try:
        resp = req_lib.get(
            f'https://pypi.org/pypi/{package_name}/json',
            timeout=3
        )
        if resp.status_code == 200:
            return resp.json().get('info', {}).get('version')
    except Exception:
        pass
    return None


def _fetch_npm_latest(package_name):
    """從 npm registry 取得最新穩定版本"""
    import requests as req_lib
    try:
        resp = req_lib.get(
            f'https://registry.npmjs.org/{package_name}',
            timeout=5
        )
        if resp.status_code == 200:
            data = resp.json()
            # 優先取 dist-tags.latest
            latest = data.get('dist-tags', {}).get('latest', '')
            # 若 latest 是穩定版，直接回傳
            if latest and _is_stable_version(latest):
                return latest
            # 否則從所有版本中找最新穩定版
            versions = list(data.get('versions', {}).keys())
            stable = [v for v in versions if _is_stable_version(v)]
            if stable:
                stable.sort(key=lambda v: _parse_version_tuple(v))
                return stable[-1]
            # 全都是預發行版本，回傳 latest tag 原值
            return latest or None
    except Exception:
        pass
    return None


def _is_stable_version(version_str):
    """判斷是否為穩定版本（不含 rc/alpha/beta/dev）"""
    return not re.search(r'(rc|alpha|beta|dev|canary|next|pre)', version_str, re.IGNORECASE)


def _parse_version_tuple(version_str):
    """將版本字串解析為可排序的 tuple"""
    m = re.match(r'(\d+)\.(\d+)\.(\d+)', version_str)
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return (0, 0, 0)


def _normalize_npm_version(version_str):
    """將 npm semver 預發行版本轉換為 PEP 440 格式"""
    if not version_str:
        return version_str
    # 提取主版本號部分 (x.y.z)
    m = re.match(r'(\d+\.\d+\.\d+)', version_str)
    return m.group(1) if m else version_str


def _compare_versions(installed, latest):
    """比較版本，回傳狀態"""
    if not installed or not latest:
        return 'check_failed'
    try:
        v_installed = Version(installed)
        v_latest = Version(latest)
    except InvalidVersion:
        # npm semver 格式與 PEP 440 不相容時，嘗試只取主版本號比較
        try:
            v_installed = Version(_normalize_npm_version(installed))
            v_latest = Version(_normalize_npm_version(latest))
        except InvalidVersion:
            return 'check_failed'

    if v_installed >= v_latest:
        return 'up_to_date'
    if v_installed.major < v_latest.major:
        return 'major_update'
    return 'minor_update'


def _get_vendor_key(name):
    """從檔名或目錄名提取套件識別 key"""
    return name.split('.')[0].lower()


def _find_main_file_in_dir(dir_path, dir_name):
    """在 vendor 子目錄中找主要 JS 或 CSS 檔用於版本偵測"""
    js_files = []
    css_files = []
    for root, _, files in os.walk(dir_path):
        for f in files:
            full = os.path.join(root, f)
            if f.endswith('.js'):
                js_files.append(full)
            elif f.endswith('.css'):
                css_files.append(full)

    if not js_files and not css_files:
        return None

    # JS 優先，找跟目錄名相關的
    dn = dir_name.lower().replace('-', '')
    for f in js_files:
        bn = os.path.basename(f).lower().replace('-', '')
        if dn in bn:
            return f
    if js_files:
        return js_files[0]

    # CSS，找 all.min.css 或跟目錄名相關的
    for f in css_files:
        bn = os.path.basename(f).lower()
        if 'all' in bn or dn in bn:
            return f
    return css_files[0] if css_files else None


def _normalize_override(value):
    """驗證覆寫值為 X.Y.Z 格式，不合格式回 None（退回檔案偵測）"""
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value if _VERSION_PATTERN.fullmatch(value) else None


def _load_version_manifest(vendor_dir):
    """讀 vendor/versions.json（不存在或壞掉一律回空 dict），依 mtime 快取"""
    path = os.path.join(vendor_dir, VENDOR_VERSION_MANIFEST)
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        _version_manifest_cache['mtime'] = None
        _version_manifest_cache['data'] = {}
        return {}

    if _version_manifest_cache['mtime'] != mtime:
        data = {}
        try:
            with open(path, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                data = loaded
        except Exception:
            data = {}
        _version_manifest_cache['mtime'] = mtime
        _version_manifest_cache['data'] = data

    return _version_manifest_cache['data']


def _read_version_file(dir_path):
    """
    讀套件目錄下的 VERSION 檔

    只取第一行的第一段，所以 `13.0.2  # 2026-08-14 下載` 這種帶註記的寫法可用；
    但開頭仍必須是純版本號，不做模糊比對（抓錯版本比抓不到更糟）。
    """
    path = os.path.join(dir_path, VENDOR_VERSION_FILE)
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            parts = f.readline().split()
    except OSError:
        return None
    return _normalize_override(parts[0]) if parts else None


def _resolve_vendor_version(key, main_file, entry_path, manifest):
    """
    決定 vendor 套件的安裝版本

    優先序：套件目錄的 VERSION 檔 > versions.json 的對應 key > 從檔案內容偵測。
    回傳 (版本號或 None, 是否來自覆寫)
    """
    if os.path.isdir(entry_path):
        override = _read_version_file(entry_path)
        if override:
            return override, True

    override = _normalize_override(manifest.get(key))
    if override:
        return override, True

    return _detect_version_from_file(main_file), False


def _detect_version_from_file(file_path):
    """從檔案內容自動偵測版本號"""
    try:
        with open(file_path, 'r', errors='ignore') as f:
            header = f.read(3000)

        # Header patterns（前 3000 字元，依優先順序）
        header_patterns = [
            r'@version\s+v?([\d]+\.[\d]+\.[\d]+)',
            r'(?:Version|VERSION)[\s:]+v?([\d]+\.[\d]+\.[\d]+)',
            # 套件名 + 任意非數字字元 + 版本（處理 "Font Awesome Free 7.2.0" 等）
            r'(?:Bootstrap|Font Awesome|Formio|Cytoscape|GridStack|'
            r'Wunderbaum|Ace)[^\d]*([\d]+\.[\d]+\.[\d]+)',
            r'[/*#!]\s*v([\d]+\.[\d]+\.[\d]+)',
        ]
        for pattern in header_patterns:
            match = re.search(pattern, header, re.IGNORECASE)
            if match:
                return match.group(1)

        # Header 找不到，掃描全檔找 inline version
        with open(file_path, 'r', errors='ignore') as f:
            content = f.read()
        full_patterns = [
            # 已知大型套件的命名版本（避免抓到內嵌依賴的版本）
            r'Formio\.version\s*=\s*["\'](\d+\.\d+\.\d+)["\']',
            # 屬性賦值: .version="X.Y.Z" 或 .GDRev="X.Y.Z"
            r'\.(?:version|GDRev)\s*=\s*["\'](\d+\.\d+\.\d+)["\']',
            # 通用: version:"X.Y.Z"（物件字面值，最後手段）
            r'version["\s:=]*["\'](\d+\.\d+\.\d+)["\']',
        ]
        for pattern in full_patterns:
            match = re.search(pattern, content)
            if match:
                return match.group(1)
    except Exception:
        pass
    return None


def _scan_vendor_packages():
    """掃描 vendor/ 目錄，自動偵測所有前端套件"""
    static_dir = os.path.join(os.path.dirname(__file__), '..', 'static')
    static_dir = os.path.normpath(static_dir)
    vendor_dir = os.path.join(static_dir, 'vendor')

    if not os.path.isdir(vendor_dir):
        return []

    packages = {}  # key -> package info
    manifest = _load_version_manifest(vendor_dir)

    for entry in sorted(os.listdir(vendor_dir)):
        entry_path = os.path.join(vendor_dir, entry)

        # 跳過隱藏檔案、JSON 資料檔（含 versions.json）、已知非套件項目
        if (entry.startswith('.')
                or entry.endswith('.json')
                or entry in VENDOR_SCAN_SKIP):
            continue

        key = _get_vendor_key(entry)

        # 同 key 已處理（CSS + JS 同名時，JS 優先偵測版本）
        if key in packages:
            if entry.endswith('.js') and not packages[key]['source'].endswith('.js'):
                # 已被覆寫的版本不讓 JS 檔的偵測值蓋掉
                if not packages[key]['_version_overridden']:
                    installed = _detect_version_from_file(entry_path)
                    if installed:
                        packages[key]['installed_version'] = installed
                packages[key]['source'] = f'vendor/{entry}'
            continue

        # 判斷主要檔案
        if os.path.isdir(entry_path):
            main_file = _find_main_file_in_dir(entry_path, entry)
            if not main_file:
                continue
            rel = os.path.relpath(main_file, static_dir)
            source = rel.replace(os.sep, '/')
        else:
            main_file = entry_path
            source = f'vendor/{entry}'

        # 決定版本（覆寫優先於檔案偵測）
        installed, overridden = _resolve_vendor_version(
            key, main_file, entry_path, manifest
        )

        # 取得 metadata
        meta = VENDOR_META.get(key, {})
        display_name = meta.get('display', key.replace('-', ' ').title())
        npm_name = meta.get('npm')
        is_custom = entry.startswith('beak-')

        packages[key] = {
            'name': display_name,
            'installed_version': installed or '未偵測',
            'latest_version': None,
            'status': ('custom' if is_custom
                       else ('check_failed' if not installed else 'checking')),
            'source': source,
            '_npm_name': npm_name,
            '_is_custom': is_custom,
            '_version_overridden': overridden,
        }

    return list(packages.values())


# === 系統服務版本檢查 ===

def _get_redis_installed_version():
    """從 redis-server --version 取得安裝版本"""
    try:
        out = subprocess.run(
            ['redis-server', '--version'],
            capture_output=True, text=True, timeout=5
        )
        # "Redis server v=7.0.15 sha=..."
        m = re.search(r'v=(\d+\.\d+\.\d+)', out.stdout)
        return m.group(1) if m else None
    except Exception:
        return None


def _get_postgres_installed_version():
    """從 psql --version 取得安裝版本"""
    try:
        out = subprocess.run(
            ['psql', '--version'],
            capture_output=True, text=True, timeout=5
        )
        # "psql (PostgreSQL) 16.13 ..."
        m = re.search(r'(\d+\.\d+)', out.stdout)
        return m.group(1) if m else None
    except Exception:
        return None


def _fetch_redis_latest():
    """從 GitHub releases 取得 Redis 最新穩定版"""
    try:
        import urllib.request
        import json as _json
        url = 'https://api.github.com/repos/redis/redis/releases?per_page=10'
        req = urllib.request.Request(url, headers={'User-Agent': 'BeakPlatform'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            releases = _json.loads(resp.read())
        for rel in releases:
            if rel.get('prerelease'):
                continue
            ver = rel['tag_name'].lstrip('v')
            if re.match(r'^\d+\.\d+\.\d+$', ver):
                return ver
    except Exception:
        pass
    return None


def _fetch_postgres_latest():
    """從 GitHub tags 取得 PostgreSQL 最新穩定版（REL_X_Y 格式）"""
    try:
        import urllib.request
        import json as _json
        url = 'https://api.github.com/repos/postgres/postgres/tags?per_page=30'
        req = urllib.request.Request(url, headers={'User-Agent': 'BeakPlatform'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            tags = _json.loads(resp.read())
        best = None
        for tag in tags:
            m = re.match(r'^REL_(\d+)_(\d+)$', tag['name'])
            if m:
                major, minor = int(m.group(1)), int(m.group(2))
                if best is None or (major, minor) > best:
                    best = (major, minor)
        if best:
            return f'{best[0]}.{best[1]}'
    except Exception:
        pass
    return None


def _check_system_services():
    """檢查系統服務版本"""
    services = [
        ('Redis', _get_redis_installed_version, _fetch_redis_latest),
        ('PostgreSQL', _get_postgres_installed_version, _fetch_postgres_latest),
    ]

    results = []
    for name, get_installed, fetch_latest in services:
        installed = get_installed()
        entry = {
            'name': name,
            'installed_version': installed or '未安裝',
            'latest_version': None,
            'status': 'check_failed' if not installed else 'checking',
        }
        results.append(entry)

    # 並行查詢線上版本
    with ThreadPoolExecutor(max_workers=3) as executor:
        future_map = {}
        for i, svc in enumerate(results):
            if svc['installed_version'] != '未安裝':
                future = executor.submit(services[i][2])
                future_map[future] = i

        for future in as_completed(future_map):
            idx = future_map[future]
            try:
                latest = future.result()
                results[idx]['latest_version'] = latest or '無法檢查'
                if latest:
                    results[idx]['status'] = _compare_versions(
                        results[idx]['installed_version'], latest
                    )
                else:
                    results[idx]['status'] = 'check_failed'
            except Exception:
                results[idx]['latest_version'] = '無法檢查'
                results[idx]['status'] = 'check_failed'

    return results


def _check_package_versions():
    """執行完整套件版本檢查"""
    start_time = time.time()

    # === Python 套件 ===
    requirements = _parse_requirements()
    python_packages = []

    # 先取得已安裝版本
    for pkg in requirements:
        installed = _get_installed_version(pkg['name'])
        python_packages.append({
            'name': pkg['name'],
            'required_version': pkg['required_version'],
            'installed_version': installed or '未安裝',
            'latest_version': None,
            'status': 'check_failed' if not installed else 'checking',
        })

    # 並行查詢 PyPI 最新版本
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_map = {}
        for i, pkg in enumerate(python_packages):
            if pkg['installed_version'] != '未安裝':
                future = executor.submit(_fetch_pypi_latest, pkg['name'])
                future_map[future] = i

        for future in as_completed(future_map):
            idx = future_map[future]
            try:
                latest = future.result()
                python_packages[idx]['latest_version'] = latest or '無法檢查'
                if latest:
                    python_packages[idx]['status'] = _compare_versions(
                        python_packages[idx]['installed_version'], latest
                    )
                else:
                    python_packages[idx]['status'] = 'check_failed'
            except Exception:
                python_packages[idx]['latest_version'] = '無法檢查'
                python_packages[idx]['status'] = 'check_failed'

    # === 前端 vendor 套件（自動掃描 vendor/ 目錄）===
    frontend_packages = _scan_vendor_packages()

    # 並行查詢 npm 最新版本（跳過自製套件和未偵測版本的）
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_map = {}
        for i, pkg in enumerate(frontend_packages):
            npm_name = pkg.get('_npm_name')
            if pkg.get('_is_custom') or not npm_name:
                continue
            if pkg['installed_version'] == '未偵測':
                continue
            future = executor.submit(_fetch_npm_latest, npm_name)
            future_map[future] = i

        for future in as_completed(future_map):
            idx = future_map[future]
            try:
                latest = future.result()
                frontend_packages[idx]['latest_version'] = latest or '無法檢查'
                if latest:
                    frontend_packages[idx]['status'] = _compare_versions(
                        frontend_packages[idx]['installed_version'], latest
                    )
                else:
                    frontend_packages[idx]['status'] = 'check_failed'
            except Exception:
                frontend_packages[idx]['latest_version'] = '無法檢查'
                frontend_packages[idx]['status'] = 'check_failed'

    # 清理內部欄位
    for pkg in frontend_packages:
        pkg.pop('_npm_name', None)
        pkg.pop('_is_custom', None)
        pkg.pop('_version_overridden', None)

    # === 系統服務 ===
    service_packages = _check_system_services()

    duration_ms = int((time.time() - start_time) * 1000)

    return {
        'python_packages': python_packages,
        'frontend_packages': frontend_packages,
        'service_packages': service_packages,
        'data_sources': DATA_SOURCES,
        'check_duration_ms': duration_ms,
    }
