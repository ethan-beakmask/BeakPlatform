import base64
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    intake_url: str
    intake_key_id: str
    intake_secret: bytes

    sa_login_url: str
    decisions_url: str
    sa_id: str
    sa_secret: str

    applied_by: str
    my_enforcement_points: tuple
    poll_interval: float
    ingest_listen_host: str
    ingest_listen_port: int
    ingest_token: str

    crowdsec_lapi_url: str

    edl_dir: str
    edl_prune_interval: float
    edl_header: bool

    @property
    def executor_enabled(self) -> bool:
        return bool(self.sa_id and self.sa_secret)


def _split_listen(value: str) -> tuple:
    host, _, port = value.rpartition(":")
    return host or "0.0.0.0", int(port)


def load_config() -> Config:
    secret_b64 = os.environ["INTAKE_SECRET_B64"]
    host, port = _split_listen(os.environ.get("INGEST_LISTEN", "0.0.0.0:8500"))
    return Config(
        intake_url=os.environ["INTAKE_URL"],
        intake_key_id=os.environ["INTAKE_KEY_ID"],
        intake_secret=base64.urlsafe_b64decode(secret_b64),
        sa_login_url=os.environ["SA_LOGIN_URL"],
        decisions_url=os.environ["DECISIONS_URL"],
        sa_id=os.environ.get("SA_ID", ""),
        sa_secret=os.environ.get("SA_SECRET", ""),
        applied_by=os.environ.get("APPLIED_BY", "od-bridge"),
        my_enforcement_points=tuple(
            x.strip() for x in os.environ.get("MY_ENFORCEMENT_POINTS", "").split(",") if x.strip()
        ),
        poll_interval=float(os.environ.get("POLL_INTERVAL", "5")),
        ingest_listen_host=host,
        ingest_listen_port=port,
        ingest_token=os.environ.get("BRIDGE_INGEST_TOKEN", "").strip(),
        crowdsec_lapi_url=os.environ.get("CROWDSEC_LAPI_URL", "http://crowdsec:8080"),
        edl_dir=os.environ.get("EDL_DIR", "/state/edl"),
        edl_prune_interval=float(os.environ.get("EDL_PRUNE_INTERVAL", "60")),
        # Off by default: PAN-OS only documents `[address][space][comment]`,
        # so a standalone `#` line is not a format a firewall must accept.
        edl_header=os.environ.get("EDL_HEADER", "0").strip().lower() in ("1", "true", "yes", "on"),
    )
