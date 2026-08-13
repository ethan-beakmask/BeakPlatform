# codex spec 片段庫

## 這是什麼

派工給 `codex exec` 時**直接貼進 prompt** 的規範片段。

存在的理由：codex 不會讀 CLAUDE.md，也不會判斷哪些規範適用於當前任務。
實測（2026-07-28~29，BeakPlatform 一日五次派工）：
**prompt 中明列的規範 codex 全數遵守；未明列的一律漏掉。**

過去這些內容散在 CLAUDE.md 裡，形式是「給 Claude 讀的散文」，
派工時得憑記憶重寫一遍——重寫就會漏。改成可直接 `cat` 的片段後，
一份內容一個來源，改一次兩邊同步。

## 怎麼用

```bash
# 寫 spec 時把需要的片段接在任務描述後面
cat > /tmp/spec.txt <<'TASK'
（任務描述、檔案清單、驗收條件）
TASK
cat dev-notes/codex_spec/frontend.md dev-notes/codex_spec/i18n.md >> /tmp/spec.txt
cat dev-notes/codex_spec/_footer.md >> /tmp/spec.txt

sudo -u ethan timeout 900 codex exec --sandbox danger-full-access \
  --skip-git-repo-check -C /opt/BeakPlatform-dev -o /tmp/codex_result.txt - < /tmp/spec.txt 2>&1
```

## 片段清單

| 檔案 | 何時貼 |
|---|---|
| `frontend.md` | 任務碰到模板 / JS / CSS |
| `i18n.md` | 任務新增任何 user-facing 字串 |
| `security.md` | 任務碰到 API / DB / 權限 / 租戶資料 / 新增公開端點 |
| `portal.md` | 任務碰到 NoCode 子系統 portal 或 Page IR |
| `_footer.md` | **每次都貼**（自我驗證指令 + 瀏覽器驗收要求 + 反規避提示） |

## 維護規則

- 片段內容有變更時，**同步更新 CLAUDE.md 的對應指針**（反之亦然）
- 新的踩坑先問：這是「codex 猜不到的專案特有事實」還是「通用工程常識」？
  前者進片段庫，後者不必寫（codex 本來就會）
- 片段只放「怎麼做才對」與「做錯會怎樣」，不放背景故事
