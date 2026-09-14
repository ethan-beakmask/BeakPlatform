"""
BeakPlatform Server Manage - Redis Monitor
主機管理 - Redis 監看頁面

系統管理員專用，提供 Redis 伺服器狀態監看：
- 伺服器資訊 (INFO)
- 即時指標 (memory, clients, ops/sec)
- Key 瀏覽 (SCAN + TYPE/TTL/GET)
- 慢查詢紀錄 (SLOWLOG)
"""
import logging
import os

import redis
from flask import Blueprint, render_template, jsonify, request
from flask_babel import gettext as _

from ..security.decorators import system_admin_required

logger = logging.getLogger(__name__)

server_manage_bp = Blueprint('server_manage', __name__)

REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')


def _get_redis():
    """取得 Redis 連線（短命連線，用完即關）"""
    return redis.from_url(REDIS_URL, decode_responses=True, socket_timeout=5)


# ──────────────────── Web Page ────────────────────

@server_manage_bp.route('/redis-monitor')
@system_admin_required
def redis_monitor():
    """Redis 監看頁面"""
    return render_template('pages/server_manage/redis_monitor.html')


# ──────────────────── API Endpoints ────────────────────

@server_manage_bp.route('/api/redis/info')
@system_admin_required
def api_redis_info():
    """
    取得 Redis INFO（全部區段）
    回傳結構化 JSON，前端直接渲染
    """
    try:
        r = _get_redis()
        info = r.info('all')
        r.close()

        # 整理關鍵指標
        summary = {
            'version': info.get('redis_version', '-'),
            'mode': info.get('redis_mode', '-'),
            'os': info.get('os', '-'),
            'uptime_seconds': info.get('uptime_in_seconds', 0),
            'uptime_days': info.get('uptime_in_days', 0),
            'tcp_port': info.get('tcp_port', '-'),
            'pid': info.get('process_id', '-'),
            # Memory
            'used_memory': info.get('used_memory', 0),
            'used_memory_human': info.get('used_memory_human', '-'),
            'used_memory_peak_human': info.get('used_memory_peak_human', '-'),
            'used_memory_rss_human': info.get('used_memory_rss_human', '-'),
            'maxmemory_human': info.get('maxmemory_human', '-'),
            'mem_fragmentation_ratio': info.get('mem_fragmentation_ratio', '-'),
            # Clients
            'connected_clients': info.get('connected_clients', 0),
            'blocked_clients': info.get('blocked_clients', 0),
            'maxclients': info.get('maxclients', 0),
            # Stats
            'total_connections_received': info.get('total_connections_received', 0),
            'total_commands_processed': info.get('total_commands_processed', 0),
            'instantaneous_ops_per_sec': info.get('instantaneous_ops_per_sec', 0),
            'keyspace_hits': info.get('keyspace_hits', 0),
            'keyspace_misses': info.get('keyspace_misses', 0),
            # Persistence
            'rdb_last_save_time': info.get('rdb_last_save_time', 0),
            'rdb_last_bgsave_status': info.get('rdb_last_bgsave_status', '-'),
            'aof_enabled': info.get('aof_enabled', 0),
            # Keyspace
            'databases': {},
        }

        # Hit rate
        hits = summary['keyspace_hits']
        misses = summary['keyspace_misses']
        total = hits + misses
        summary['hit_rate'] = round(hits / total * 100, 2) if total > 0 else 0

        # Keyspace (db0, db1, ...)
        for key, val in info.items():
            if key.startswith('db') and isinstance(val, dict):
                summary['databases'][key] = val

        return jsonify({'ok': True, 'data': summary})

    except redis.ConnectionError as e:
        logger.error('Redis 連線失敗: %s', e)
        return jsonify({'ok': False, 'error': _('Redis 連線失敗')}), 503
    except Exception as e:
        logger.error('Redis INFO 錯誤: %s', e)
        return jsonify({'ok': False, 'error': str(e)}), 500


@server_manage_bp.route('/api/redis/keys')
@system_admin_required
def api_redis_keys():
    """
    SCAN 瀏覽 Key（分頁）
    參數:
      - cursor: SCAN cursor (預設 0)
      - pattern: 匹配模式 (預設 *)
      - count: 每次 SCAN 建議筆數 (預設 50)
      - db: 資料庫編號 (預設 0)
    """
    cursor = int(request.args.get('cursor', 0))
    pattern = request.args.get('pattern', '*')
    count = min(int(request.args.get('count', 50)), 200)
    db_num = int(request.args.get('db', 0))

    # 防止 pattern injection
    if len(pattern) > 100:
        return jsonify({'ok': False, 'error': _('pattern 過長')}), 400

    try:
        r = _get_redis()
        r.select(db_num)

        next_cursor, keys = r.scan(cursor=cursor, match=pattern, count=count)

        # 取每個 key 的 type 和 TTL
        results = []
        pipe = r.pipeline()
        for k in keys:
            pipe.type(k)
            pipe.ttl(k)
            pipe.memory_usage(k)
        pipe_results = pipe.execute()

        for i, k in enumerate(keys):
            idx = i * 3
            results.append({
                'key': k,
                'type': pipe_results[idx],
                'ttl': pipe_results[idx + 1],
                'memory': pipe_results[idx + 2],
            })

        r.close()

        return jsonify({
            'ok': True,
            'cursor': next_cursor,
            'keys': results,
            'has_more': next_cursor != 0,
        })

    except redis.ConnectionError as e:
        return jsonify({'ok': False, 'error': _('Redis 連線失敗')}), 503
    except Exception as e:
        logger.error('Redis SCAN 錯誤: %s', e)
        return jsonify({'ok': False, 'error': str(e)}), 500


@server_manage_bp.route('/api/redis/key/<path:key_name>')
@system_admin_required
def api_redis_key_detail(key_name):
    """
    取得單一 Key 的值
    參數:
      - db: 資料庫編號 (預設 0)
    """
    db_num = int(request.args.get('db', 0))

    try:
        r = _get_redis()
        r.select(db_num)

        key_type = r.type(key_name)
        ttl = r.ttl(key_name)
        mem = r.memory_usage(key_name)

        if key_type == 'none':
            r.close()
            return jsonify({'ok': False, 'error': _('Key 不存在')}), 404

        # 依型別取值（限制回傳大小）
        value = None
        truncated = False
        max_items = 100

        if key_type == 'string':
            val = r.get(key_name)
            if val and len(val) > 10000:
                value = val[:10000]
                truncated = True
            else:
                value = val

        elif key_type == 'list':
            length = r.llen(key_name)
            value = r.lrange(key_name, 0, max_items - 1)
            truncated = length > max_items

        elif key_type == 'set':
            members = list(r.sscan_iter(key_name, count=max_items))
            value = members[:max_items]
            truncated = len(members) > max_items

        elif key_type == 'zset':
            value = r.zrange(key_name, 0, max_items - 1, withscores=True)
            truncated = r.zcard(key_name) > max_items

        elif key_type == 'hash':
            all_fields = list(r.hscan_iter(key_name, count=max_items))
            value = dict(all_fields[:max_items])
            truncated = len(all_fields) > max_items

        elif key_type == 'stream':
            value = '(stream - 不支援預覽)'

        r.close()

        return jsonify({
            'ok': True,
            'key': key_name,
            'type': key_type,
            'ttl': ttl,
            'memory': mem,
            'value': value,
            'truncated': truncated,
        })

    except Exception as e:
        logger.error('Redis key detail 錯誤: %s', e)
        return jsonify({'ok': False, 'error': str(e)}), 500


@server_manage_bp.route('/api/redis/slowlog')
@system_admin_required
def api_redis_slowlog():
    """
    取得 SLOWLOG（最近 50 筆）
    """
    try:
        r = _get_redis()
        entries = r.slowlog_get(50)
        r.close()

        results = []
        for entry in entries:
            # SLOWLOG 的 command 不受 decode_responses 影響，一律是 bytes
            command = entry.get('command', '')
            if isinstance(command, bytes):
                command = command.decode('utf-8', errors='replace')
            results.append({
                'id': entry.get('id'),
                'timestamp': entry.get('start_time'),
                'duration_us': entry.get('duration'),
                'command': command,
            })

        return jsonify({'ok': True, 'entries': results})

    except redis.ConnectionError as e:
        return jsonify({'ok': False, 'error': _('Redis 連線失敗')}), 503
    except Exception as e:
        logger.error('Redis SLOWLOG 錯誤: %s', e)
        return jsonify({'ok': False, 'error': str(e)}), 500


@server_manage_bp.route('/api/redis/dbsize')
@system_admin_required
def api_redis_dbsize():
    """各 DB 的 key 數量（用於快速刷新）"""
    try:
        r = _get_redis()
        info = r.info('keyspace')
        r.close()
        return jsonify({'ok': True, 'keyspace': info})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500
