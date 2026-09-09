# `.20` 的 sshd 設定片段（權威副本）

本目錄的檔案對應 `.20:/etc/ssh/sshd_config.d/` 底下**由本專案管理**的片段。
`.20` 上的檔案是執行中的設定，本目錄是它的權威副本——**改動時兩邊都要改**。

不在本目錄的檔案（例如 cloud-init 產生的 `50-cloud-init.conf`）不歸本專案管，
不要複製進來，也不要在 `.20` 上刪掉它。

**兩邊不一致時以 `.20` 為準**（那是實際生效的），先 diff 再決定怎麼收斂：

```bash
cd /opt/BeakPlatform-dev
diff <(ssh -i ~/.ssh/company-wsl ethan@192.168.0.20 \
        'sudo cat /etc/ssh/sshd_config.d/00-pf107-hardening.conf') \
     sec-vm-bootstrap/ssh/00-pf107-hardening.conf
ssh -i ~/.ssh/company-wsl ethan@192.168.0.20 'sudo ls -la /etc/ssh/sshd_config.d/'
```

底下所有 `ssh -i ~/.ssh/company-wsl` 都是**在 `.16` 上以 `ethan` 執行**
（那把私鑰在 `/home/ethan/.ssh/`）。`ethan` 在 `.20` 上有 `NOPASSWD:ALL`，
所以文件裡的 `sudo` 都不會問密碼——**問密碼就表示你不是用這條路進去的**。

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

## 22 埠連不上時的檢查順序

照這個順序走，不要跳。前三步在 `.16` 或任何白名單機器上做，後面要進得去才做。

```bash
# 1. 症狀分類：逾時 vs Permission denied（決定往下走哪一邊）
ssh -v -o ConnectTimeout=8 ethan@192.168.0.20 true

# 2. 逾時 → 查 nftables。counter 是累計值，測試前後各讀一次看有沒有增加
ssh sec-vm 'sudo nft list chain inet secstack ssh_guard_input | grep counter'

# 3. 逾時且 drop 有跳 → 你的來源不在白名單，看 log 確認它看到的來源 IP
ssh sec-vm "sudo journalctl -k --since '-1 day' | grep SSHGUARD_DROP | tail"

# 4. 進得去之後，確認 sshd 本身活著、且真的在聽 22
ssh sec-vm 'systemctl is-active ssh; sudo ss -ltnp "sport = :22"'

# 5. Permission denied → 看 .20 認的公鑰有哪些，比對自己手上的私鑰指紋
ssh sec-vm 'ssh-keygen -lf ~/.ssh/authorized_keys'
ssh-keygen -lf ~/.ssh/<你的私鑰>
```

**在白名單內卻仍連不上**（`ssh_guard_input` 的 drop counter 沒動）就不要再查防火牆，
直接跳到第 4、5 步。

## SSHGUARD_DROP log 的實際長相與抽取方式

```
Aug 15 18:21:29 sec-vm kernel: SSHGUARD_DROP IN=ens18 OUT= MAC=bc:24:11:72:7c:44:bc:24:11:d6:94:80:08:00 \
  SRC=192.168.0.199 DST=192.168.0.20 LEN=60 ... PROTO=TCP SPT=47987 DPT=22 ... SYN URGP=0
```

```bash
# 依來源 IP 統計敲門次數
ssh sec-vm "sudo journalctl -k --since '-7 days' | grep SSHGUARD_DROP \
  | grep -oE 'SRC=[0-9.]+' | sort | uniq -c | sort -rn"
```

三件事會讓這份統計失真，判讀前要知道：

- **規則有 `limit rate 20/minute`**，被高頻掃描時 log 是抽樣的，
  **次數以 `nft` 的 drop counter 為準，log 只用來看「是誰」**
- **只有被 drop 的才進 log**。白名單來源（`.10`/`.16`/`.100`）敲 22 不會留下
  `SSHGUARD_DROP`，要查那些得看 `journalctl -u ssh`
- journal 在 `.20` 是**持久化的**（`/var/log/journal` 存在，Storage=auto），
  重開機後查得到；目前最舊記錄回溯到 2026-07-15

## `ens18` 是寫死在規則裡的，換網卡要一起改

```bash
ssh sec-vm "ip -o -4 route show to default | awk '{print \$5}'"   # 應回 ens18
```

`ssh_guard_input` 與其他三條 guard chain 都以 `iifname != "ens18" accept` 開頭。
網卡名變了而規則沒跟著改，**結果是所有規則失效（全部走 accept），不是連不上**——
壞掉的方向是「更寬鬆」，不會有任何症狀，只能靠這條檢查發現。

`claude` 這個 OS 帳號沒有 `~/.ssh/authorized_keys`，本設定生效後它完全失去
遠端入口（僅剩主控台）。**這是預期結果，不是待修的問題。**

## 從 Windows 連過來的兩個坑（2026-08-16 當場踩到）

**一、`ssh ethan@192.168.0.20` 會 `Permission denied (publickey)`，`ssh sec-vm` 卻可以。**

不是設定壞了。`~/.ssh/config` 的 `Host sec-vm` 只匹配 `sec-vm` 這個字面，
打 IP 不匹配 → 不套用 `IdentityFile` → ssh 拿預設的 `id_rsa`／`id_ed25519`
去試，那兩把不在 `.20` 的 `authorized_keys` 裡。兩個解法：

```
Host sec-vm 192.168.0.20          # 讓 IP 也匹配同一組設定
```
```cmd
ssh -i %USERPROFILE%\.ssh\sec-vm_ed25519 ethan@192.168.0.20
```

**二、Windows CMD 不吃單引號**，遠端命令要用雙引號包，內層改用單引號：

```cmd
:: 錯（CMD 把單引號當字面，管線在本機展開，grep 被當成本機命令）
ssh sec-vm 'sudo journalctl -k --since "-1 day" | grep SSHGUARD_DROP'

:: 對
ssh sec-vm "sudo journalctl -k --since '-1 day' | grep SSHGUARD_DROP"
```

PowerShell 兩種引號都吃，但 `|` 仍會被本機先解讀，一樣要整串包起來。
