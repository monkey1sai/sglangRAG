# TPS 調整策略（SGLang Tool Use 基準）

本文件整理「以提升 TPS 為主」的調整策略，適用於 `sglang-server/benchmark_50_tools_tps.py` 這類工具呼叫壓測腳本。

## 影響 TPS 的關鍵因素
- **tool schema 長度**：tools 定義越長，prompt 越大，TPS 越低。
- **tools 數量**：工具越多，模型選擇成本越高，TPS 越低。
- **輸出長度**：回答或 tool_call 參數越長，TPS 越低。
- **模式與策略**：`tool_choice`、`max_tokens`、stream 模式會直接影響 TPS。

## 最高優先的 TPS 提升策略
1. **降低 tools 數量**：建議 8–12 個工具為一組壓測集。
2. **精簡 tool schema**：移除不必要欄位（例如 `settings` 詳細參數）。
3. **限制輸出長度**：降低 `max_tokens`（例如 32–80）。
4. **避免自由回答**：全部請求都以工具操作為主，減少自然語言輸出。
5. **強制 tool 呼叫**：`tool_choice = "required"` 可避免回覆文字拉低 TPS。
6. **動態裁剪工具**：依請求關鍵字只傳對應工具，縮短 prompt。

## 目前基準腳本設定（摘要）
檔案：`sglang-server/benchmark_50_tools_tps.py`
- `TOOL_COUNT = 12`
- `tool_choice = "required"`
- `max_tokens = 80`
- tool schema 已精簡（無 `settings` 內部參數）
- 只產生工具導向請求（無一般問答）
- 依請求關鍵字動態裁剪 tools

## 測試方式
```powershell
.venv\Scripts\python.exe sglang-server\benchmark_50_tools_tps.py --concurrency 1 --total 5 --no-stream
```

## 取捨與建議
- **TPS 優先**：降低 tools 數量 + 簡化 schema + 強制 tool。
- **準確度優先**：保留更多工具與完整參數，但 TPS 會下降。
- 建議區分 **TPS profile** 與 **Accuracy profile**，分別測量。
