#!/bin/bash
# =============================================================================
# push_github.sh - 過濾推送到 GitHub
# =============================================================================
# 將 main 分支推送到 GitHub，但排除內部文件和開發工具。
# 使用臨時分支移除排除檔案後 force push。
#
# 用法: ./scripts/push_github.sh
# =============================================================================
set -e

REMOTE="github"
BRANCH="main"
TEMP_BRANCH="_github_filtered"

# === 排除清單 ===
# 完整目錄
EXCLUDE_DIRS=(
    # 內部開發筆記（handoff、規格、踩坑紀錄、manifest）。
    # 對外的使用者文件在 docs/，不在這裡，會照常推上 GitHub。
    # 兩個目錄的分界規則見 CLAUDE.md「文件目錄：docs/ 與 dev-notes/」。
    "dev-notes"
    "tools"
    "devtools"
    ".forgejo"
    "scripts/systemd"
    "backend/app/templates/pages/dev"
    # E2E 測試依賴 /dev/quick-login 免密碼登入（backend/app/web/dev.py 本身已在
    # 排除清單、正式部署不存在）。推上公開 repo 只會得到一組必然跑不起來的測試，
    # 而且等於公開描述開發後門的用法。
    "tests/e2e"
)

# 個別檔案
EXCLUDE_FILES=(
    "CLAUDE.md"
    "temp_WEB_Builder全程序.txt"
    "workflow_node開發進度表.csv"
    "beakplatform.service"
    "restart_dev.sh"
    # scripts - 內部工具與初始化
    "scripts/push_github.sh"
    "scripts/init_database.sh"
    "scripts/seed_data.py"
    "scripts/seed_test_companies.py"
    "scripts/analyze_project.py"
    "scripts/install_emailrelay.sh"
    "scripts/backfill_sync.py"
    "scripts/sync_worker.py"
    "scripts/beakplatform-sync-worker.service"
    "scripts/migrate_variable_syntax.py"
    "scripts/upgrade_approval_tables.py"
    "scripts/rotate_credentials.py"
    "scripts/sql_form_setup.sql"
    "scripts/readme.txt"
    "scripts/security_scan.sh"
    "scripts/spec_check.py"
    "scripts/dev_update.sh"
    "scripts/add_column_comments.sql"
    "scripts/init_db.sql"
    "scripts/workflow_bundle.py"
    # scripts/verify_install.sh 已隨 install.sh 開放給用戶
    # backend - 開發工具
    "backend/app/web/dev.py"
    "backend/app/static/js/quick-login.js"
    # 根目錄 - 開發工具
    "reset_password.py"
    "app-info.sh"
)

echo "=== 過濾推送到 GitHub ==="

# 確保在 main 分支且工作區乾淨
current=$(git branch --show-current)
if [ "$current" != "$BRANCH" ]; then
    echo "錯誤: 請在 $BRANCH 分支執行"
    exit 1
fi

if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "錯誤: 工作區有未提交的變更，請先 commit"
    exit 1
fi

# 刪除舊的臨時分支（如有）
git branch -D "$TEMP_BRANCH" 2>/dev/null || true

# 從 main 建立臨時分支
git checkout -b "$TEMP_BRANCH" "$BRANCH" --quiet

excluded=0

# 移除排除的目錄
for item in "${EXCLUDE_DIRS[@]}"; do
    if git ls-files "$item" | grep -q .; then
        git rm -r --cached "$item" --quiet 2>/dev/null
        echo "  排除目錄: $item/"
        excluded=$((excluded + 1))
    fi
done

# 移除排除的檔案
for item in "${EXCLUDE_FILES[@]}"; do
    if git ls-files --error-unmatch "$item" &>/dev/null; then
        git rm --cached "$item" --quiet 2>/dev/null
        echo "  排除檔案: $item"
        excluded=$((excluded + 1))
    fi
done

if [ "$excluded" -eq 0 ]; then
    echo "  無需排除的檔案"
    git checkout "$BRANCH" --quiet
    git branch -D "$TEMP_BRANCH" 2>/dev/null || true
    # GitHub repo 的 history 與 origin 永遠不一致（過去過濾推送會產生不同 commit hash），
    # 即使本次無檔案要排除，正常 push 也會被 fast-forward 拒絕。
    # 一律 force push，維持「local main 是 source of truth、GitHub 是過濾鏡像」的語意。
    echo "  Force push 推送 (GitHub 為過濾鏡像)..."
    git push "$REMOTE" "$BRANCH" --force
else
    # 提交移除
    git commit -m "chore: exclude internal files from public repository" --quiet

    # Force push 到 GitHub
    git push "$REMOTE" "$TEMP_BRANCH:$BRANCH" --force
fi

# 回到 main，清理
# --force: git rm --cached 留下的檔案會變成 untracked，需強制切回
git checkout "$BRANCH" --force --quiet
git branch -D "$TEMP_BRANCH" 2>/dev/null || true

echo "=== GitHub 推送完成 (排除 ${excluded} 項) ==="
