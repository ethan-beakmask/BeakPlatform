"""
路由守門宣告表一致性測試（PERM-05）。

一致性檢查刻意用 subprocess 跑 `scripts/route_guard_inventory.py --check`，
而不是在本進程建 app。原因是 `app.module_loader.module_loader` 是進程層級單例
（`_loaded` 旗標），第二個以後建立的 app **不會再註冊模組 blueprint**：
單獨跑本檔時 url_map 有 859 條，與其他測試一起跑時只剩 449 條，
表裡的模組 endpoint 會被誤判成「已不存在」。重設 `_loaded` 也救不回來
（實測只還原到 732 條，部分模組載入會失敗）。

進程隔離同時解決另一個問題：產表的工具用 `create_app('development')`，
本檔若自行用 `create_app('testing')` 比對，兩者的 url_map 一旦分歧就會紅得莫名其妙。
現在兩邊都走同一支工具、同一個 config。
"""
from pathlib import Path
import subprocess
import sys

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
TABLE_PATH = REPO_ROOT / 'backend' / 'app' / 'security' / 'route_guard_table.yaml'
TOOL_PATH = REPO_ROOT / 'scripts' / 'route_guard_inventory.py'

VALID_REVIEW = {'unreviewed', 'confirmed', 'intentional_open'}
VALID_AUDIENCE = {'SYSTEM_ADMIN', 'ORG_ADMIN', 'EMPLOYEE', 'EXTERNAL',
                  'ANONYMOUS', 'NON_HUMAN'}
AUTO_FIELDS = ('rules', 'methods', 'source', 'guards', 'guard_args',
               'has_internal_check', 'internal_identity_check')


@pytest.fixture(scope='module')
def table():
    with TABLE_PATH.open(encoding='utf-8') as fh:
        return yaml.safe_load(fh)


def test_table_schema_valid(table):
    """表本身的結構與人工欄位值域（不需要 app，同進程即可跑）。"""
    assert 'routes' in table, '宣告表缺少 routes 區段'
    problems = []
    for endpoint, entry in table['routes'].items():
        for field in AUTO_FIELDS:
            if field not in entry:
                problems.append(f'  - {endpoint}: 缺少自動欄位 {field}')
        review = entry.get('review')
        if review not in VALID_REVIEW:
            problems.append(
                f'  - {endpoint}: review={review!r} 不是合法值 {sorted(VALID_REVIEW)}')
        if review == 'intentional_open' and not (entry.get('note') or '').strip():
            problems.append(
                f'  - {endpoint}: review=intentional_open 時 note 必須寫明理由')
        audience = entry.get('max_audience')
        if audience is not None:
            if not isinstance(audience, list):
                problems.append(f'  - {endpoint}: max_audience 必須是 null 或清單')
            else:
                bad = sorted(set(audience) - VALID_AUDIENCE)
                if bad:
                    problems.append(
                        f'  - {endpoint}: max_audience 含非法值 {bad}，'
                        f'合法值為 {sorted(VALID_AUDIENCE)}')

    assert not problems, (
        '路由守門宣告表格式有問題：\n' + '\n'.join(problems)
        + '\n欄位規格見 dev-notes/ROUTE_GUARD_TABLE_SPEC.md。'
    )


def test_route_guard_table_matches_code():
    """表與程式碼一致（缺登記 / 殘留條目 / 守門被改動，三者任一都會紅）。"""
    result = subprocess.run(
        [sys.executable, str(TOOL_PATH), '--check'],
        cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=300,
    )
    assert result.returncode == 0, (
        '路由守門宣告表與程式碼不一致：\n'
        + (result.stdout or '') + (result.stderr or '')
        + '\n新增或改動路由後必須執行 '
        '`venv/bin/python scripts/route_guard_inventory.py --update`，'
        '並為新條目填寫 max_audience 與 review。'
    )
