# 公告擬稿：子系統開發模組（NoCode Builder）尚未完工（2026-09-13）

> 本檔只是擬稿，供 Ethan 貼到 `/security/alert-broadcasts/` 建立公告使用。
> 本次任務不代為建立公告，也不代為決定生效時間與受眾範圍。

## 背景

「子系統開發模組」選單已於 2026-09-13 解除隱藏（見 `dev-notes/NOCODE_MENU_HIDE.md`）。
Ethan 定案：現在解除隱藏；鐵人賽（至 2026-10）期間不修改 `modules/nocode_builder/`
程式碼；以公告告知使用者「尚未完工、考慮移出本專案、請勿使用」。
已知資安缺口見 BBN 待辦 **PF-271** 與 `dev-notes/NOCODE_UNHIDE_SECURITY_AUDIT_20260913.md`。

## 建議公告內容（zh-TW）

**標題**：子系統開發模組（NoCode Builder）尚未完工，請勿使用

**內文**：

子系統開發模組（NoCode Builder）目前仍在開發中，功能尚未完成。平台團隊正在評估
是否將本模組移出本專案。

在此之前，請勿在正式環境使用本模組，也請勿透過本模組存放任何真實資料。

本公告有效期至 2026-10-31。

## 建議公告內容（en）

**Title**: NoCode Builder module is incomplete — do not use

**Body**:

The NoCode Builder (subsystem development) module is still under active
development and is not feature-complete. The platform team is evaluating
whether to remove this module from the project.

Until further notice, please do not use this module in production, and do
not store any real data through it.

This notice is valid until 2026-10-31.

## 解除後可考慮在幾個入口加彈出提醒（只列不實作）

以下入口可考慮加上一次性彈出提醒（例如頁面載入時的 modal 或橫幅），
提醒內容同上方公告，僅供 Ethan 後續評估是否要做、由誰做：

- `/nocode-builder/`
- `/nocode-builder/sub-systems`
- `/nocode-builder/lookup`
- `/nocode-builder/workspace/<sc>`
- `/nocode-builder/ir-designer/<sc>`

（本次任務依硬性限制不得修改 `modules/nocode_builder/` 底下任何檔案，
故僅列出入口清單，不實作彈出提醒。）
