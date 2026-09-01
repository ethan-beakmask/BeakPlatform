#!/usr/bin/env python3
"""
100 - PF-102：清除 2026-05 policy 未調整期產生的 suricata STREAM 內部雜訊事件與案件

背景：見 BeakBroodNest atom 5186（PF-102，2026-08-15）。2026-05-09~13 期間 policy
尚未調整，.20 的 Suricata 對反代鏈路流量（含部分外部來源，如 GCP 相關 IP
35.190.46.17，占 2648 筆）大量觸發 STREAM 系列解析警告
（rule_id 2210020/2210029/2210045/2210044 共 6808 筆，另有 400 筆非 STREAM
的一般 network_activity/web_activity 混在同一批 suricata 事件內），
造成平台 od_intake_events 累積 7208 筆 suricata 事件，遠高於同期 ClickHouse
（secstack.events）僅 170 筆的對照數字。2026-05-13 曾因此發生事故：3 小時湧入
4063 筆，executor 對每事件開進程，RAM 9.4GB / load 70 整台雪崩。

用戶 2026-08-15 定案（見 atom 5186「刪除範圍已定案」段，推翻前文「若整月清掉」
的備案）：

    只刪 source_system='suricata' 且 received_at < '2026-06-01' 的 intake 事件
    與其級聯案件（約 7208 筆）。同期 coraza 536 筆真實 WAF 攻擊、vector 2 筆
    一律保留，不動。

級聯範圍（執行前已用 SQL 交叉查證，del_cases 與保留事件無交集、無跨污染，
也沒有子流程 parent/root 外部引用這些案件）：

    od_intake_events (source_system=suricata, received_at<2026-06-01)
      -> fw_workflow_instances               (經 case_secure_code，1:1，7203 筆)
          -> fw_form_instances                (經 workflow_instance_secure_code /
                                                form_instance_secure_code 雙向，7203 筆)
          -> fw_node_execution_queue           (經 workflow_instance_secure_code)
          -> fw_node_execution_logs            (經 workflow_instance_id，須先 join id)
          -> fw_workflow_variables             (實測 0 筆，仍檢查以防未來資料變化)
          -> fw_approval_records               (實測 0 筆，仍檢查)
      -> od_defense_decisions                  (經 case_secure_code，實測 0 筆——
                                                 這批雜訊事件沒有觸發過任何防禦決策，
                                                 不涉及 block/unblock 問題)

**注意與工單原文的落差**（執行時發現，工單描述有誤，寫入本檔頭供後續 session 參考）：
  1. 工單提到的 `fw_workflow_node_instances`、`fw_workflow_tasks` 兩個表在本庫
     不存在，實際的節點軌跡/佇列是 `fw_node_execution_queue` +
     `fw_node_execution_logs`，簽核記錄表是 `fw_approval_records`。
  2. 工單提到的 `alert_broadcasts` 表不存在。AlertBroadcastHandler
     （modules/form_workflow/services/node_handlers/alert_broadcast_handler.py）
     實際把緊急廣播寫進 `lookup_items`（category_code='broadcast'），以
     broadcast_code 為鍵覆蓋最新一則、不是逐案記錄，與本次案件級聯無關，
     本腳本不處理（CLAUDE.md 已有這條備忘）。
  3. 工單「這批雜訊是什麼」只列了 3 個 STREAM rule_id，實際待刪範圍內還有
     rule_id=2210020（2798 筆，佔最大宗，也是 STREAM 系列，只是工單漏列）
     與約 400 筆非 STREAM 的一般 network_activity/web_activity 事件混雜其中。
     由於用戶定案的刪除條件是「source_system='suricata' 且
     received_at<2026-06-01」（不是逐 rule_id 篩選），這個落差不影響刪除範圍，
     但代表這批資料不是「純 STREAM 雜訊」，額外附帶了少量其他規則的低置信度事件。
  4. 工單「actor_ip 分布」寫 192.168.0.20（4429 筆）/192.168.0.16/127.0.0.1，
     實測 192.168.0.20 為 4288 筆、192.168.0.16 為 90 筆、無 127.0.0.1，
     且有 2648 筆來自外部 IP 35.190.46.17（非反代鏈路內部流量）。
     這批資料的性質是「STREAM 引擎雜訊」沒有疑義（rule_id 佐證），
     但「全部是內部反代流量」的描述不準確，其中一部分來源是外部 IP。

刪除方式：硬刪除。本機是測試資料庫（CLAUDE.md：可忽略舊資料、不用修正），
軟刪除（is_deleted=true）無法真正釋放這批資料，不符合本次清理的目的
（這批資料本身就曾造成一次 executor 過載事故）；執行前一律先 pg_dump
相關表全量備份到 /opt/tmp/backup/。

使用方式：
    cd /opt/BeakPlatform-dev
    set -a && source .env && set +a
    python scripts/migrations/100_cleanup_pf102_suricata_stream_noise.py            # dry-run（預設）
    python scripts/migrations/100_cleanup_pf102_suricata_stream_noise.py --dry-run  # 同上，明寫
    python scripts/migrations/100_cleanup_pf102_suricata_stream_noise.py --apply    # 實際刪除（含自動備份）
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime

_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_dir = os.path.join(_script_dir, '..', '..')
sys.path.insert(0, os.path.join(_project_dir, 'backend'))

from sqlalchemy import text  # noqa: E402

CUTOFF = '2026-06-01'
SOURCE_SYSTEM = 'suricata'
BACKUP_DIR_ROOT = '/opt/tmp/backup'

# 依級聯關係，子表在前、父表在後（實際刪除依此順序執行；DB 本身沒有 FK 約束，
# 但保持這個順序方便閱讀與未來若補上 FK 也不會出錯）
BACKUP_TABLES = [
    'od_intake_events',
    'fw_workflow_instances',
    'fw_form_instances',
    'fw_node_execution_queue',
    'fw_node_execution_logs',
    'fw_workflow_variables',
    'fw_approval_records',
    'od_defense_decisions',
]

FORM_INSTANCE_MATCH = """
    fi.workflow_instance_secure_code = ANY(:codes)
    OR fi.secure_code IN (
        SELECT wi.form_instance_secure_code FROM fw_workflow_instances wi
        WHERE wi.secure_code = ANY(:codes) AND wi.form_instance_secure_code IS NOT NULL
    )
"""


def _get_del_case_codes(conn) -> list[str]:
    rows = conn.execute(
        text(
            """
            SELECT DISTINCT case_secure_code FROM od_intake_events
            WHERE received_at < :cutoff AND source_system = :src
              AND case_secure_code IS NOT NULL
            """
        ),
        {'cutoff': CUTOFF, 'src': SOURCE_SYSTEM},
    ).fetchall()
    return [r[0] for r in rows]


def _count_all(conn, codes: list[str]) -> dict[str, int]:
    counts = {}
    counts['od_intake_events'] = conn.execute(
        text(
            "SELECT count(*) FROM od_intake_events "
            "WHERE received_at < :cutoff AND source_system = :src"
        ),
        {'cutoff': CUTOFF, 'src': SOURCE_SYSTEM},
    ).scalar()
    counts['fw_workflow_instances'] = conn.execute(
        text("SELECT count(*) FROM fw_workflow_instances WHERE secure_code = ANY(:codes)"),
        {'codes': codes},
    ).scalar()
    counts['fw_form_instances'] = conn.execute(
        text(f"SELECT count(*) FROM fw_form_instances fi WHERE {FORM_INSTANCE_MATCH}"),
        {'codes': codes},
    ).scalar()
    counts['fw_node_execution_queue'] = conn.execute(
        text(
            "SELECT count(*) FROM fw_node_execution_queue "
            "WHERE workflow_instance_secure_code = ANY(:codes)"
        ),
        {'codes': codes},
    ).scalar()
    counts['fw_node_execution_logs'] = conn.execute(
        text(
            """
            SELECT count(*) FROM fw_node_execution_logs l
            JOIN fw_workflow_instances wi ON l.workflow_instance_id = wi.id
            WHERE wi.secure_code = ANY(:codes)
            """
        ),
        {'codes': codes},
    ).scalar()
    counts['fw_workflow_variables'] = conn.execute(
        text(
            "SELECT count(*) FROM fw_workflow_variables "
            "WHERE workflow_instance_secure_code = ANY(:codes) OR root_instance_code = ANY(:codes)"
        ),
        {'codes': codes},
    ).scalar()
    counts['fw_approval_records'] = conn.execute(
        text(
            "SELECT count(*) FROM fw_approval_records "
            "WHERE workflow_instance_secure_code = ANY(:codes)"
        ),
        {'codes': codes},
    ).scalar()
    counts['od_defense_decisions'] = conn.execute(
        text("SELECT count(*) FROM od_defense_decisions WHERE case_secure_code = ANY(:codes)"),
        {'codes': codes},
    ).scalar()
    return counts


def _check_block_without_unblock_in_scope(conn, codes: list[str]) -> list:
    """本次刪除範圍內，action='block' 且找不到後續 unblock 的決策清單。
    （額外用途：即使刪除範圍外，也順手列出全表現況供人工確認，見 main() 呼叫處）
    """
    rows = conn.execute(
        text(
            """
            SELECT b.secure_code, b.org_secure_code, b.target_type, b.target_value,
                   b.status, b.decided_at, b.expires_at
            FROM od_defense_decisions b
            WHERE b.case_secure_code = ANY(:codes) AND b.action = 'block'
              AND NOT EXISTS (
                SELECT 1 FROM od_defense_decisions u
                WHERE u.action = 'unblock'
                  AND u.target_type = b.target_type
                  AND u.target_value = b.target_value
                  AND u.org_secure_code = b.org_secure_code
                  AND u.decided_at >= b.decided_at
              )
            ORDER BY b.decided_at
            """
        ),
        {'codes': codes},
    ).fetchall()
    return rows


def _check_block_without_unblock_global(conn) -> list:
    """全表（不限本次刪除範圍）的 block 未 unblock 清單，供交付報告參考。"""
    rows = conn.execute(
        text(
            """
            SELECT b.secure_code, b.org_secure_code, b.target_type, b.target_value,
                   b.status, b.decided_at, b.expires_at, b.case_secure_code
            FROM od_defense_decisions b
            WHERE b.action = 'block'
              AND NOT EXISTS (
                SELECT 1 FROM od_defense_decisions u
                WHERE u.action = 'unblock'
                  AND u.target_type = b.target_type
                  AND u.target_value = b.target_value
                  AND u.org_secure_code = b.org_secure_code
                  AND u.decided_at >= b.decided_at
              )
            ORDER BY b.decided_at
            """
        )
    ).fetchall()
    return rows


def _orphan_check_post(conn, codes: list[str]) -> dict[str, int]:
    """刪除後應全數為 0；非 0 代表級聯漏刪。"""
    return _count_all(conn, codes)


def _run_backup() -> str:
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    backup_dir = os.path.join(BACKUP_DIR_ROOT, f'pf102-{ts}')
    os.makedirs(backup_dir, exist_ok=True)

    db_url = os.environ.get('DATABASE_URL', '')
    if not db_url:
        raise RuntimeError('DATABASE_URL 未設定，請先 set -a && source .env && set +a')

    dump_file = os.path.join(backup_dir, 'pf102_backup.sql')
    cmd = ['pg_dump', db_url, '-Fp', '-f', dump_file]
    for t in BACKUP_TABLES:
        cmd.extend(['-t', t])
    print(f'[BACKUP] 執行: pg_dump ({len(BACKUP_TABLES)} 張表) -> {dump_file}')
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f'pg_dump 失敗: {result.stderr}')
    size = os.path.getsize(dump_file)
    print(f'[BACKUP] 完成，檔案大小 {size} bytes')
    return dump_file


def _run_deletes(conn, codes: list[str]) -> dict[str, int]:
    deleted = {}

    r = conn.execute(
        text(
            """
            DELETE FROM fw_node_execution_logs l
            USING fw_workflow_instances wi
            WHERE l.workflow_instance_id = wi.id AND wi.secure_code = ANY(:codes)
            """
        ),
        {'codes': codes},
    )
    deleted['fw_node_execution_logs'] = r.rowcount

    r = conn.execute(
        text(
            "DELETE FROM fw_node_execution_queue WHERE workflow_instance_secure_code = ANY(:codes)"
        ),
        {'codes': codes},
    )
    deleted['fw_node_execution_queue'] = r.rowcount

    r = conn.execute(
        text(
            "DELETE FROM fw_workflow_variables "
            "WHERE workflow_instance_secure_code = ANY(:codes) OR root_instance_code = ANY(:codes)"
        ),
        {'codes': codes},
    )
    deleted['fw_workflow_variables'] = r.rowcount

    r = conn.execute(
        text("DELETE FROM fw_approval_records WHERE workflow_instance_secure_code = ANY(:codes)"),
        {'codes': codes},
    )
    deleted['fw_approval_records'] = r.rowcount

    r = conn.execute(
        text("DELETE FROM od_defense_decisions WHERE case_secure_code = ANY(:codes)"),
        {'codes': codes},
    )
    deleted['od_defense_decisions'] = r.rowcount

    # 必須在刪 fw_workflow_instances 之前執行（子查詢引用它）
    r = conn.execute(
        text(f"DELETE FROM fw_form_instances fi WHERE {FORM_INSTANCE_MATCH}"),
        {'codes': codes},
    )
    deleted['fw_form_instances'] = r.rowcount

    r = conn.execute(
        text("DELETE FROM fw_workflow_instances WHERE secure_code = ANY(:codes)"),
        {'codes': codes},
    )
    deleted['fw_workflow_instances'] = r.rowcount

    r = conn.execute(
        text(
            "DELETE FROM od_intake_events "
            "WHERE received_at < :cutoff AND source_system = :src"
        ),
        {'cutoff': CUTOFF, 'src': SOURCE_SYSTEM},
    )
    deleted['od_intake_events'] = r.rowcount

    return deleted


def run(apply_changes: bool) -> int:
    from app import create_app, db

    app = create_app()
    with app.app_context():
        conn = db.session

        codes = _get_del_case_codes(conn)
        print(f'[SCOPE] 待刪案件（fw_workflow_instances）數量: {len(codes)}')

        counts = _count_all(conn, codes)
        print('[DRY-RUN COUNT] 各表預計刪除筆數：')
        for k, v in counts.items():
            print(f'  {k}: {v}')

        block_rows = _check_block_without_unblock_in_scope(conn, codes)
        print(f'[CHECK] 本次刪除範圍內 od_defense_decisions action=block 且未 unblock: {len(block_rows)} 筆')
        for row in block_rows:
            print(f'  secure_code={row.secure_code} target={row.target_type}:{row.target_value} status={row.status}')

        global_block_rows = _check_block_without_unblock_global(conn)
        print(f'[CHECK] 全表（不限本次範圍）od_defense_decisions action=block 且未 unblock: {len(global_block_rows)} 筆（僅供參考，本腳本不處理）')

        if not apply_changes:
            print('[MODE] dry-run，未寫入任何變更（連線交易將 rollback）')
            conn.rollback()
            return 0

        # --apply：先備份，再刪除
        backup_path = _run_backup()

        deleted = _run_deletes(conn, codes)
        print('[APPLY] 各表實際刪除筆數：')
        for k, v in deleted.items():
            print(f'  {k}: {v}')

        conn.commit()
        print('[APPLY] 交易已 commit')

        orphan_counts = _orphan_check_post(conn, codes)
        print('[VERIFY] 刪除後孤兒檢查（應全數為 0）：')
        all_zero = True
        for k, v in orphan_counts.items():
            print(f'  {k}: {v}')
            if v:
                all_zero = False
        if all_zero:
            print('[VERIFY] 通過：無殘留孤兒')
        else:
            print('[VERIFY] 警告：仍有殘留，請人工檢查上列非 0 項目')

        print(f'[SUMMARY] backup={backup_path}')
        print(
            '[SUMMARY] deleted='
            + ', '.join(f'{k}={v}' for k, v in deleted.items())
        )
        return 0 if all_zero else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description='PF-102: 清除 2026-05 suricata STREAM 內部雜訊事件與案件',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            '範例：\n'
            '  先看會刪什麼（不寫入，預設行為）：\n'
            '    ./100_cleanup_pf102_suricata_stream_noise.py\n'
            '    ./100_cleanup_pf102_suricata_stream_noise.py --dry-run\n'
            '  實際硬刪並自動備份：\n'
            '    ./100_cleanup_pf102_suricata_stream_noise.py --apply\n'
        ),
    )
    parser.add_argument('--dry-run', action='store_true', help='只列出會刪除的筆數，不寫入（預設）')
    parser.add_argument('--apply', action='store_true', help='實際執行刪除（會先自動備份）')
    args = parser.parse_args()

    if args.dry_run and args.apply:
        parser.error('--dry-run 與 --apply 只能擇一')

    return run(apply_changes=args.apply)


if __name__ == '__main__':
    sys.exit(main())
