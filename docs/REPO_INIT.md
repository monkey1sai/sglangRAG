# Repo 初始化（可公開 / 可維護 / 支援 Git LFS）

本 repo **不提交**模型、音檔、金鑰與本機依賴（例如 Piper 可執行檔）。請用 `.env.example` 作為唯一範本。

## 1. 第一次初始化（新 repo）

```bash
git init

# Git LFS（追蹤大型二進位）
git lfs install
git lfs track "*.onnx"
git lfs track "*.pt"
git lfs track "*.bin"
# 若未來需要把音檔放 LFS，再啟用
# git lfs track "*.wav"

git add .gitattributes .gitignore
git add .
git commit -m "chore: initialize repository structure"
```

> `.gitattributes` 已包含 LFS 規則；`git lfs track ...` 主要用於在新 repo 時產生/更新設定並讓團隊一致。

## 2. 已存在 repo 加入 LFS（既有專案）

```bash
git lfs install
git add .gitattributes
git commit -m "chore: enable git lfs for large assets"
```

> 若你已經把大檔案 commit 進 Git history，請先討論 migration（`git lfs migrate`），避免 history 變更影響協作。
