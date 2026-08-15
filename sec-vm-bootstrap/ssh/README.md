# `.20` 的 sshd 設定片段（權威副本）

本目錄的檔案對應 `.20:/etc/ssh/sshd_config.d/` 底下**由本專案管理**的片段。
`.20` 上的檔案是執行中的設定，本目錄是它的權威副本——**改動時兩邊都要改**。

不在本目錄的檔案（例如 cloud-init 產生的 `50-cloud-init.conf`）不歸本專案管，
不要複製進來，也不要在 `.20` 上刪掉它。

## 檔名的數字前綴不是排版習慣

`sshd_config` 的語意是 **first obtained value wins**，而主檔頂部的
`Include /etc/ssh/sshd_config.d/*.conf` 按**字典序**讀取。

`.20` 的 `50-cloud-init.conf` 寫死 `PasswordAuthentication yes`，
所以覆寫它的檔案必須排在它前面（`00-`）。用 `99-` 之類的名字會被先設定的值
蓋過去，而且 **`sshd -t` 會通過、也不會有任何警告**——症狀是「設定寫了沒生效」。

驗證的唯一方式是看展開後的有效值，不是看檔案內容：

```bash
sudo sshd -T | grep -iE '^(passwordauthentication|pubkeyauthentication|kbdinteractiveauthentication)'
```

## 部署

```bash
# 從 .16 推上去
scp -i ~/.ssh/company-wsl sec-vm-bootstrap/ssh/00-pf107-hardening.conf ethan@192.168.0.20:/tmp/
ssh -i ~/.ssh/company-wsl ethan@192.168.0.20 '
  sudo cp -a /etc/ssh/sshd_config.d /root/sshd_config.d.bak.$(date +%Y%m%d-%H%M%S)
  sudo mv /tmp/00-pf107-hardening.conf /etc/ssh/sshd_config.d/
  sudo chown root:root /etc/ssh/sshd_config.d/00-pf107-hardening.conf
  sudo sshd -t && sudo systemctl reload ssh
'
```

**改 sshd 設定前先掛自動還原**（PF-107 用的手法）：設定寫錯到 sshd 起不來時，
金鑰也進不去，那時只剩 PVE console。

```bash
sudo systemd-run --on-active=120 --unit=sshd-rollback \
  /bin/bash -c "rm -f /etc/ssh/sshd_config.d/00-pf107-hardening.conf; systemctl reload ssh"
# ... 改設定、驗證 ...
sudo systemctl stop sshd-rollback.timer     # 驗證通過後撤銷
```

## 現行狀態（2026-08-16 起）

`.20` 的 sshd **只收公鑰**。目前接受三把金鑰，清單見 `.20` 的
`CREDENTIALS.md` §1.1（該檔不進版控）。22 埠另有 nftables 來源白名單
（`.10` / `.16` / `.100`），規則在 `../nftables-bootstrap.sh`。

兩層的症狀不同，排查時先分辨：

| 症狀 | 是哪一層 |
|---|---|
| 連線逾時 | nftables 擋的（來源不在白名單） |
| `Permission denied (publickey)` | sshd 擋的（沒有可用金鑰） |

`claude` 這個 OS 帳號沒有 `~/.ssh/authorized_keys`，本設定生效後它完全失去
遠端入口（僅剩主控台）。**這是預期結果，不是待修的問題。**
