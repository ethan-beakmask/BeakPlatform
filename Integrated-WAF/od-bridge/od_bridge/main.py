import asyncio
import logging
import sys

from .config import load_config
from .enforcers import edl
from .executor import run_executor_loop
from .ingest import run_ingest_server


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )


async def _amain() -> None:
    _setup_logging()
    cfg = load_config()
    log = logging.getLogger("main")
    tasks = [asyncio.create_task(run_ingest_server(cfg), name="ingest")]
    if cfg.executor_enabled:
        tasks.append(asyncio.create_task(run_executor_loop(cfg), name="executor"))
        log.info("executor enabled, polling every %ss for points=%s",
                 cfg.poll_interval, ",".join(cfg.my_enforcement_points))
    else:
        log.warning("executor DISABLED (no SA credentials in env)")

    if "edl" in cfg.my_enforcement_points:
        # Render once at boot so the firewall never fetches a stale or missing
        # file after a restart, then keep pruning expired entries on a timer.
        edl.reconcile(cfg)
        tasks.append(asyncio.create_task(edl.run_prune_loop(cfg), name="edl-prune"))
        log.info("edl enforcer enabled, dir=%s prune every %ss",
                 cfg.edl_dir, cfg.edl_prune_interval)

    await asyncio.gather(*tasks, return_exceptions=False)


if __name__ == "__main__":
    asyncio.run(_amain())
