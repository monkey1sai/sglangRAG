# SAGA Web Interface 重新設計計畫

**Created**: 2026-01-23
**Author**: Antigravity Agent

---

## 目標

解決現有 SAGA UI 的問題，並支援符號回歸範例 (`demo_symbolic_regression.py`) 全自動執行。

---

## 問題分析

| 問題 | 現況 | 目標 |
|------|------|------|
| 文字顯示 | 長文需拖曳拉 bar | 自動展開/收合 |
| 空白利用 | 面板間空白多 | 全屏三欄佈局 |
| Agent 日誌 | 僅有 system_log | 分別顯示 Analyzer/Planner/Implementer |
| 控制功能 | 僅有「取消」 | 新增「暫停」「停止」並導出結果 |
| 預設模板 | 無 | 符號回歸範例可一鍵載入 |

---

## 修改範圍

### [MODIFY] saga_server/app.py

新增 WebSocket 事件：
- `agent_log`: 攜帶 `agent_type` (analyzer/planner/implementer)
- `pause` / `resume` 命令處理
- `stop` 命令處理並返回當前結果

### [MODIFY] web_client/src/App.jsx

1. **佈局重構**：三欄式 Grid (左控制/中主面板/右日誌)
2. **新增控制按鈕**：暫停、恢復、停止
3. **Agent 日誌 Tab**：System / Analyzer / Planner / Implementer
4. **符號回歸模板**：一鍵載入預設參數

### [MODIFY] web_client/src/style.css

- 三欄佈局 CSS
- Tab 切換樣式
- 暫停狀態按鈕樣式

### [NEW] web_client/src/components/AgentLogPanel.jsx

Agent 專屬日誌面板組件

### [NEW] web_client/src/templates/symbolic_regression.json

符號回歸預設參數模板

---

## 實作優先順序

1. ⭐ **後端暫停/停止 API** (必須)
2. ⭐ **前端控制按鈕** (必須)
3. **符號回歸模板載入** (重要)
4. **Agent 日誌分類顯示** (重要)
5. **佈局優化** (增強)

---

## 驗證計畫

### 1. 符號回歸測試
```bash
# UI 設定後按「開始執行」
# 驗證 LLM 能推論出 y = x² + 3x - 2
```

### 2. 暫停/停止功能
```
1. 啟動全自動模式
2. 運行中按「暫停」→ 確認迭代暫停
3. 按「恢復」→ 確認繼續
4. 按「停止」→ 確認導出當前最佳結果
```

### 3. 日誌顯示
```
確認各 Agent 的輸出分別顯示在對應 Tab
```
