# Integrated-WAF 已移到獨立的 repo

防禦節點自 BeakPlatform v2.0.0 起移到 **[ethan-beakmask/Integrated-WAF](https://github.com/ethan-beakmask/Integrated-WAF)**，
安裝說明見該 repo 的 [docs/install.md](https://github.com/ethan-beakmask/Integrated-WAF/blob/main/docs/install.md)。

```bash
curl -fsSL https://raw.githubusercontent.com/ethan-beakmask/Integrated-WAF/v2.0.0/install.sh -o ~/integrated-waf-install.sh
sudo bash ~/integrated-waf-install.sh --pair '<開通字串>' --backend http://<被保護網站IP>:<埠> --yes
```

這個目錄只剩這份說明與一支只印出新位置的 `install.sh`，給仍在使用舊下載網址的人。
BeakPlatform v1.0.0 時期的完整內容可在本 repo 的 `v1.0.0` tag 找到。
