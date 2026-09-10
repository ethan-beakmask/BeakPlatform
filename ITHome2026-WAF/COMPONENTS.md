# ITHome2026-WAF 內容物、單獨安裝方式與授權聲明
# ITHome2026-WAF: Contents, Standalone Installation, and Licensing Notice

## 聲明 / Notice

**本安裝包只是「快速安裝與整合」。裡面每一個元件的著作權都屬於各自的原作者與專案，
本安裝包不主張任何元件的所有權，也不改變它們的授權條款。**
唯一由本專案自行撰寫的程式是 `od-bridge/`（事件轉送與決策落地的小型橋接程式）與
`install.sh` / `cf_tunnel.py` / `nftables.sh` 這幾支整合腳本，以 Apache License 2.0 釋出。
使用任何元件前請自行閱讀並遵守該元件的授權。

**This package is a quick-install and integration bundle only. All copyright in each component
remains with its original authors and projects. This package claims no ownership over any
component and does not alter their licenses.** The only code written by this project is
`od-bridge/` (a small bridge that forwards events and applies decisions) and the integration
scripts `install.sh` / `cf_tunnel.py` / `nftables.sh`, released under the Apache License 2.0.
Please read and comply with each component's license before use.

## 元件清單 / Components

| 元件 Component | 用途 Role | 版本 Version (pinned) | 授權 License | 上游 Upstream |
|---|---|---|---|---|
| OWASP ModSecurity CRS (nginx) | WAF：nginx + libmodsecurity v3 + OWASP Core Rule Set | image `owasp/modsecurity-crs:nginx`（浮動 tag，安裝時取最新 / floating tag） | Apache 2.0 | https://github.com/coreruleset/modsecurity-crs-docker |
| Suricata | 網路入侵偵測 Network IDS（被動監聽網卡 / passive sniffing） | `jasonish/suricata:7.0` | GPLv2（以獨立程序執行，未連結進本專案程式 / runs as a separate process, not linked） | https://suricata.io |
| Emerging Threats Open ruleset | Suricata 規則集 / rule set，安裝時下載 | 每日更新 / daily | BSD（ET Open） | https://rules.emergingthreats.net |
| CrowdSec | 行為偵測與封鎖（LAPI）/ behavioural detection & blocking | `crowdsecurity/crowdsec:v1.6.4` | MIT | https://github.com/crowdsecurity/crowdsec |
| Vector | 日誌收集與正規化（轉 OCSF）/ log shipping & normalisation | `timberio/vector:0.41.1-alpine` | MPL 2.0 | https://vector.dev |
| ClickHouse | 事件儲存與查詢 / event storage | `clickhouse/clickhouse-server:24.8` | Apache 2.0 | https://clickhouse.com |
| cloudflared | Cloudflare Tunnel 連接器 / tunnel connector | `cloudflare/cloudflared:2026.8.3` | Apache 2.0 | https://github.com/cloudflare/cloudflared |
| nginx | 歡迎頁靜態網頁伺服器 / static page for the welcome hostname | `nginx:1.27-alpine` | BSD-2-Clause | https://nginx.org |
| Grafana（選用 optional） | 儀表板 / dashboards | `grafana/grafana:11.3.0` + `grafana-clickhouse-datasource` | AGPLv3（Grafana）/ Apache 2.0（datasource plugin） | https://grafana.com |
| EveBox（選用 optional） | Suricata 告警瀏覽 / alert viewer | `jasonish/evebox:0.18.2` | MIT | https://evebox.org |
| Portainer CE（選用 optional） | 容器管理介面 / container UI | `portainer/portainer-ce:2.21.4` | zlib | https://www.portainer.io |
| Docker Engine + Compose plugin | 容器執行環境 / runtime（apt `docker.io`、`docker-compose-v2`） | Ubuntu 套件庫版本 / distro packages | Apache 2.0 | https://www.docker.com |
| nftables | 主機防火牆與封鎖集合 / host firewall & block sets | Ubuntu 套件庫 / distro package | GPLv2 | https://netfilter.org |
| ethtool | 關閉監聽網卡的 GRO/LRO/TSO/GSO 卸載，避免 Suricata 收到截斷封包 / NIC offload control for clean capture | Ubuntu 套件庫 / distro package | GPLv2 | https://www.kernel.org/pub/software/network/ethtool/ |
| od-bridge（本專案 this project） | 事件簽章轉送到 BeakPlatform、輪詢決策落地到 nftables / CrowdSec / EDL | 隨本 repo / this repo | Apache 2.0 | 本目錄 `od-bridge/` |

Grafana 為 AGPLv3：本安裝包僅以容器方式執行未修改的官方映像檔，未散布修改版本。
Grafana is AGPLv3: this package only runs the unmodified official image as a container; no modified build is distributed.

## 各元件單獨安裝 / Installing each component on its own

以下指令與本安裝包無關，是各元件的通用裝法，方便只想用其中一部分的人。
The commands below are generic ways to run each component by itself, independent of this package.

```bash
# OWASP ModSecurity CRS (WAF in front of http://backend:8000)
docker run -d --name waf -p 8080:8080 -e BACKEND=http://backend:8000 -e PARANOIA=1 owasp/modsecurity-crs:nginx

# Suricata (sniff interface eth0, write /var/log/suricata/eve.json)
docker run -d --name suricata --net=host --cap-add=NET_ADMIN --cap-add=NET_RAW --cap-add=SYS_NICE \
  -v suricata-logs:/var/log/suricata jasonish/suricata:7.0 -i eth0
docker exec suricata suricata-update            # download ET Open rules

# CrowdSec (LAPI on 127.0.0.1:8081)
docker run -d --name crowdsec -p 127.0.0.1:8081:8080 -v crowdsec-config:/etc/crowdsec \
  -v crowdsec-data:/var/lib/crowdsec/data crowdsecurity/crowdsec:v1.6.4

# Vector (config at ./vector.yaml)
docker run -d --name vector -v $PWD/vector.yaml:/etc/vector/vector.yaml:ro timberio/vector:0.41.1-alpine

# ClickHouse
docker run -d --name clickhouse -p 8123:8123 -p 9000:9000 -e CLICKHOUSE_PASSWORD=changeme \
  -v clickhouse-data:/var/lib/clickhouse clickhouse/clickhouse-server:24.8

# cloudflared (token from Cloudflare Zero Trust → Tunnels)
docker run -d --name cloudflared cloudflare/cloudflared:2026.8.3 tunnel --no-autoupdate run --token <TOKEN>

# nginx static page
docker run -d --name welcome -p 8081:80 -v $PWD/html:/usr/share/nginx/html:ro nginx:1.27-alpine

# Grafana / EveBox / Portainer
docker run -d --name grafana -p 3000:3000 grafana/grafana:11.3.0
docker run -d --name evebox -p 5636:5636 -v suricata-logs:/var/log/suricata:ro jasonish/evebox:0.18.2 \
  server --no-auth --datastore=sqlite --data-directory=/data --input=/var/log/suricata/eve.json --host=0.0.0.0
docker run -d --name portainer -p 9443:9443 -v /var/run/docker.sock:/var/run/docker.sock portainer/portainer-ce:2.21.4

# Host packages (Ubuntu)
sudo apt-get install -y docker.io docker-compose-v2 nftables
```

## 本安裝包做的整合 / What this package adds on top

- 一份 `docker-compose.yml` 把上述元件接成一條鏈：WAF 與 Suricata 的告警 → Vector 轉成 OCSF →
  ClickHouse（全量）與 od-bridge（過濾、封頂後送 BeakPlatform）；od-bridge 再把平台的封鎖決策
  落地到 nftables、CrowdSec 與 EDL 檔
- `install.sh` 一鍵安裝、`.env` 集中所有參數、`nftables.sh` 產生主機防火牆、
  `cf_tunnel.py` 用 Cloudflare API 建 tunnel 與 DNS
- 設定檔內的註解說明每個選擇的理由，方便拆開來單獨使用或替換

One `docker-compose.yml` wires the components into a pipeline (WAF/Suricata alerts → Vector →
ClickHouse and od-bridge → BeakPlatform; decisions back to nftables/CrowdSec/EDL), plus the
installer, a single `.env`, the firewall generator, and the Cloudflare helper. Comments in each
config explain the reasoning so any part can be replaced or used alone.
