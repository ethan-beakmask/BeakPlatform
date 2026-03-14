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
    "docs/archive"
    "docs/knowledge"
    "tools"
    "devtools"
    ".forgejo"
    "scripts/migrations"
    "scripts/systemd"
)

# 個別檔案
EXCLUDE_FILES=(
    "CLAUDE.md"
    "temp_WEB_Builder全程序.txt"
    "workflow_node開發進度表.csv"
    "beakplatform.service"
    "restart_flask.sh"
    "docs/CICD_SETUP.md"
    "docs/emailrelay-setup.md"
    "docs/enterprise-defaults-checklist.md"
    "docs/GLOSSARY.md"
    "docs/LOOKUP_TABLE_GUIDE.md"
    "docs/PLATFORM_MODULARIZATION_PLAN.md"
    "docs/rbac-requirements-questionnaire.md"
    "docs/SECURITY_AUDIT_20260302.md"
    "docs/SQL_SYNC.md"
    "docs/VARIABLE_SYSTEM_SPEC.md"
    "docs/WEB_BUILDER_PROVISION_PLAN.md"
    "docs/WEB_BUILDER_SPEC.md"
    "docs/WEB_BUILDER_STUDIO_SPEC.md"
    "scripts/push_github.sh"
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
    echo "  直接推送..."
    git push "$REMOTE" "$BRANCH"
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
