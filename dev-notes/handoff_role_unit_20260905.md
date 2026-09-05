# 交接：PF-247 角色@單位簽核設計 → 新 session 執行（2026-09-05 12:40）

> 給執行 PF-247 的新 session。撰寫設計的 session（PF-226／PF-71 那個）保留中，Ethan 會把你的結果拿回去給它審。
> **你的任務是照 `dev-notes/ROLE_UNIT_APPROVAL_DESIGN.md` 逐期派 codex 並驗收，不是重新設計。**
> 文件裡任何一條看不懂或覺得有矛盾，停下來問 Ethan，不要自行詮釋後開工。

> **進度（2026-09-05 13:40）**：第 1 期已完成並通過執行 session 驗收（記錄在設計文件第十一節），等原 session 複審後派第 2 期。
> 第 2 期 spec 要把第 1 期實作的實際介面餵給 codex：`task_authorizer._spec_from()` 讀的 key（`assignee_unit_secure_code` / `assignee_role_type` / `absence_fallback`）、
> `unit_resolver.resolve_user_unit()` 的簽名，以及 `/opt/tmp/verify/pf247/phase1_seed.sql` 裡合成列的 `result.data` 形狀（就是 handler 該寫出的樣子）。

## 一、先讀（順序）

1. `CLAUDE.md`（每個 session 必讀；特別是 PERM-03、TENANT-02、「流程 graph 的引擎行為」表、「跑測試」段）
2. `dev-notes/ROLE_UNIT_APPROVAL_DESIGN.md` 全文——**第八節六個決策點必須已由 Ethan 回答**，答案在 BBN #5400（PF-247）追記裡；沒有答案就不要派第 1 期
3. `dev-notes/codex_spec/README.md`、`_footer.md`、`security.md`；第 3 期另讀 `frontend.md`、`i18n.md`
4. `~/.claude/knowledge_base/standards/coding_standards/codex_first_policy.md`（派工參數、timeout、stdin 餵 prompt）
5. 上一輪的 spec 範本：`/opt/tmp/codex/20260905-pf226-no-assignee-spec.txt`（結構、規範貼法、測試要求寫法照這個）

## 二、每期固定流程

1. `note_task_status(ref='PF-247', status='in_progress')`（第 1 期開工時一次即可）
2. 讀設計文件該期那一列，讀該期要改的每個檔案的**現況**（codex 對專案無記憶，spec 要餵足：函式名、行號、既有欄位）
3. 寫 spec 到 `/opt/tmp/codex/<日期>-pf247-phase<N>-spec.txt`，內容含：目標與驗收條件、檔案清單與現況、設計文件該節**逐字貼入**（不要只給路徑）、規範片段、測試案例（每條斷言主體要不同）、`_footer.md` 全文
4. 派工：`nohup setsid bash -c 'sudo -u ethan timeout 1800 codex exec --sandbox danger-full-access --skip-git-repo-check -C /opt/BeakPlatform-dev -o /opt/tmp/codex/<日期>-pf247-phase<N>-result.txt - < <spec> > <stdout.log> 2> <stderr.log>; echo "exit=$?" >> <stderr.log>' &`，再用 Monitor 盯 `^exit=`
5. 驗收（主 Claude 專屬，不可外包）：先反向檢查（死碼、舊函式名殘留、拆字串、manifest）→ 讀 diff → 跑該期測試＋全量（全量用 `nohup setsid` 跑 `bash scripts/run_tests.sh -q`，約 22 分鐘，基準 2026-09-05：1035 passed／1 failed＝PF-34／2 skipped）→ `sudo systemctl restart beakplatform-dev-executor beakplatform-dev` 並等 `/auth/login` 回 200 → 依設計文件第七節驗收矩陣**實測**該期涵蓋的情境，憑證 `tee` 進 `/opt/tmp/verify/<日期>-role-unit-phase<N>.log`
6. 過了才 commit（訊息格式照 git log 最近幾筆），`note_update(atom_id=5400, append_content=...)` 追記該期結果與憑證路徑，然後**停下來回報 Ethan**，等他拿去給原 session 審、回覆後才派下一期
7. 退回上限 2 次，之後改自己依規範實作

## 三、這個 session 踩過、你也會撞的

- **Claude Code harness 會以「記憶體不足」中止背景 Bash／Monitor**：長工作一律 `nohup setsid ... &` 脫離 session，再用 Monitor 以 `until grep -q "^exit=" log; do sleep 20; done` 監看；Monitor 逾時要重掛
- **codex 撞 OpenAI capacity 時 exit 1、沒有 `-o` 結果檔，但工作區變更是完整的**：看 `git status` 與 stderr 尾判斷，不要重派
- **平台層 web／api 要用模組 model 一律在函式內 import**，模組層級 import 會讓 flask 起不來而 pytest 測不出來（CLAUDE.md 特定代理段）
- **mkdocs 對中文標題產生的 anchor 是 `_9` 這種流水號**，手冊跨頁連結不要帶 `#中文` anchor（PF-226 的 codex 就寫壞一個）；每次改手冊後跑 `NO_MKDOCS_2_WARNING=1 ./venv-docs/bin/mkdocs build --strict` 看有沒有 anchor 的 INFO 行
- **設計器儲存流程會 bump revision，但發行要另打 `POST /api/mappings/<mapping sc>/publish`**（CSRF token 從 `/dashboard` meta 取），發行後 published sc 會換、舊的變 Suspended；GHTRAVEL 目前 published sc 是 `NfrmHdR6pVWLo2L2eCttCA`（mapping `MTz1S7Kc_uFCCMcP4ibhrC`，流程模板 `q1lfu30j8rQW4xwT7AlbUp`）。實測完記得把示範流程還原成預設並重新發行，CLAUDE.md 範例企業段的 sc 要跟著改
- 測身分判定的可執行小工具：`/tmp/claude-1000/.../scratchpad/pf226_check.sh` 會消失，寫法在 `/opt/tmp/verify/20260905-pf226.log` 開頭可重建（quick-login → `GET /api/form-center/pending-tasks` → `GET /api/form-center/pending-tasks/<佇列 sc>` 看 200／403）；直接呼叫 `task_authorizer.resolve_acting_identity()` 的 python 範本也在同一份 log
- 用 SQL 造角色指派：`user_role_assignments` 的 `secure_code`、`assigned_at`、**`created_at`、`updated_at`** 四個都是 NOT NULL 且 DB 無預設（ORM 才有；2026-09-05 第 1 期驗收第一輪 12 個 FAIL 全是這個），`assigned_by` 填可辨識標記（如 `PF247-P1-TEST`），事後 `DELETE ... WHERE assigned_by='<標記>'`；**這次要造的是帶 `unit_secure_code` 的指派**
- beluga 行銷部門的現成材料：ethanyu＝副主管、aaaa＝代理人(一)、ssss＝代理人(二)、user＝成員；主管職缺（沒有 DEPT_MANAGER 指派），正好是驗收矩陣 #2 的樣本，#3 要自己指派一位主管
- OD 案件不進表單中心待簽清單，用詳情端點判定（CLAUDE.md 有）

## 四、PF-226 留下的現況（別當成待修）

GHTRAVEL 三張 2026-09-04 的測試單（PROC-20260904-0001～0003）仍停在 WAITING、`assignees=[]`——那是修前的樣本，刻意留著當對照，不要去補簽或清掉。
2026-09-05 的 PROC-20260905-0001（REJECTED）與 0002（COMPLETED）是修後憑證。
