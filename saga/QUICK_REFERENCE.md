# SAGA 快速參考卡

## 核心概念 30 秒速記

**SAGA** = 多輪迭代優化系統

每次迭代：`分析 → 規劃 → 實現 → 優化`

用戶 → SagaRunner → OuterLoop (多次迭代) → 最佳解

---

## 關鍵數據結構

### LoopState
當前優化狀態快照
```
iteration, text, keywords, constraints, candidates,
current_scores, best_candidate, best_score,
score_history, weights, goal_thresholds
```

### AnalysisReport
分析結果
```
score_distribution, goal_achievement, pareto_count,
improvement_trend, bottleneck, suggested_constraints
```

### IterationResult
每次迭代產出
```
iteration, analysis_report, new_constraints,
best_candidate, best_score, elapsed_ms
```

---

## 四層架構快速表

| 層級 | 模塊 | 輸入 | 輸出 | 人審 |
|------|------|------|------|------|
| 1 | AdvancedAnalyzer | LoopState | AnalysisReport | Co/Semi |
| 2 | AdvancedPlanner | Analysis | weights, constraints | Co |
| 3 | AdvancedImplementer | Plan | scoring_code | Co |
| 4 | AdvancedOptimizer | candidates, scores, weights | top-k candidates | - |

---

## 操作模式對照表

| 模式 | Analyze | Plan | Implement | Optimize | 用途 |
|------|---------|------|-----------|----------|------|
| **Co-pilot** | ✓ | ✓ | ✓ | ✓ | 高風險、探索 |
| **Semi-pilot** | ✓ | - | - | - | 一般任務 |
| **Autopilot** | - | - | - | - | 大規模搜索 |

---

## 主要方法簽名速查

### SagaRunner
```python
runner = SagaRunner(cfg)
async for event in runner.run(text, keywords, mode, config_overrides):
    # IterationResult | HumanReviewRequest | FinalReport | LogEvent
```

### OuterLoop
```python
loop = OuterLoop(...)
async for event in loop.run(initial_state, run_id):
    # ...
```

### AdvancedAnalyzer
```python
report = analyzer.run(state)
# 返回 {score_distribution, goal_achievement, ...}
```

### AdvancedPlanner
```python
plan = planner.run({analysis, constraints, iteration})
# 返回 {weights, new_constraints, strategy}
```

### AdvancedImplementer
```python
impl = implementer.run({plan, constraints})
# 返回 {scoring_code, version, summary}
```

### AdvancedOptimizer
```python
optimized = optimizer.optimize(candidates, scoring_code, weights)
# 返回 [(candidate, score), ...]
```

### LLMGenerator
```python
new_cands = generator.generate(population, feedback, num_candidates)
# 返回 [cand1, cand2, ...]
```

### EvoGenerator
```python
new_cands = generator.generate(population, feedback, num_candidates)
# 使用交叉/變異
```

### TerminationChecker
```python
if terminator.should_stop(state):
    reason = terminator.get_termination_reason(state)
```

### ModeController
```python
if mode_controller.requires_human_review(stage):
    # 發送 HumanReviewRequest
```

---

## 配置常用參數

### 運行時參數 (config_overrides)
```python
{
    "max_iters": 10,                      # 最大迭代
    "convergence_eps": 0.001,             # 收斂精度
    "convergence_patience": 3,            # 收斂判決迭代數
    "goal_thresholds": [0.7, 0.7, 0.7],  # 目標閾值
    "weights": [0.33, 0.34, 0.33]        # 初始權重
}
```

### 環境變數 (.env)
```bash
SAGA_RUN_DIR=runs
SAGA_MAX_ITERS=10
SAGA_BEAM_WIDTH=3
SAGA_USE_LLM_MODULES=true
SGLANG_API_KEY=sk-...
SGLANG_BASE_URL=http://localhost:8082
```

---

## 終止條件檢查清單

```python
should_stop() 返回 True 當:
1. iteration >= max_iters
2. score_history 最後 patience 次變化 < eps
3. 所有目標達成率 >= 閾值
4. pareto_history 最後 patience 次相同
```

---

## 事件流對照

### 完整事件序列

```
LogEvent("info", "Run started")
  ↓
LogEvent("info", "Iteration 1...")
LogEvent("info", "Step 1: Analyzing...")
LogEvent("success", "Analysis complete")
[HumanReviewRequest] ← Semi-pilot 暫停
LogEvent("success", "Analysis approved")
LogEvent("info", "Step 2: Planning...")
...
IterationResult(iteration=1, best_score=0.65)
  ↓
[重複迭代]
  ↓
FinalReport(best_candidate="...", best_score=0.95)
```

---

## 評分函數模板

### 基礎評分函數簽名

```python
def score(candidate: str, context: dict) -> list:
    """
    評分多個目標

    Args:
        candidate: 要評分的候選 (通常是公式/代碼)
        context: {
            "keywords": [...],
            "previous_scores": [...],
            "constraints": [...]
        }

    Returns:
        [obj1_score, obj2_score, ...] 在 [0, 1] 範圍
    """
    try:
        obj1_score = ...  # 計算第一個目標
        obj2_score = ...  # 計算第二個目標
        ...
        return [obj1_score, obj2_score, ...]
    except:
        return [0.5, 0.5, ...]  # 錯誤時返回中性評分
```

---

## 常見錯誤和修復

| 問題 | 原因 | 解決方案 |
|------|------|--------|
| 評分不變 | 收斂或評分函數錯誤 | 增加 max_iters，檢查 scoring_code |
| 候選很差 | 提示詞不夠好 | 改進 LLMGenerator 提示 |
| 很慢 | 評分函數複雜或 LLM 慢 | 並行評分，使用 EvoGenerator |
| 人審一直等待 | 忘記發送批准 | 检查 WebSocket 連接 |

---

## 權重調整快速公式

```python
# 提高未達成目標的權重
if achievement[i] < threshold:
    weights[i] += adjustment_rate * (threshold - achievement[i])

# 降低已達成目標的權重
else:
    weights[i] -= adjustment_rate * (achievement[i] - threshold)

# 歸一化
weights = weights / sum(weights)
```

---

## Beam Search 演算法

```python
1. 計算所有候選的加權評分
   weighted_score = Σ(weights[i] * scores[i])

2. 排序 (降序)

3. 返回前 k 個

時間複雜度: O(n log n)
```

---

## 遺傳算法步驟

```python
for each generation:
    1. 隨機選擇 2 個父代
    2. 單點交叉 (50% 概率)
       child = parent1[:mid] + parent2[mid:]
    3. 隨機變異 (10% 概率)
       mutation = 隨機替換或插入
    4. 返回子代
```

---

## 環境變數快速複製

```bash
# 複製到 .env
SAGA_RUN_DIR=runs
SAGA_BEAM_WIDTH=3
SAGA_MAX_ITERS=10
SAGA_USE_LLM_MODULES=true
SAGA_TIMEOUT_S=10.0

SGLANG_API_KEY=sk-xxx
SGLANG_BASE_URL=http://localhost:8082

GROQ_API_KEY=gsk-xxx (可選)
GROQ_MODEL=openai/gpt-oss-120b (可選)
```

---

## 調試技巧

### 啟用詳細日誌
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### 性能測量
```python
import time
start = time.perf_counter()
# ... 代碼 ...
elapsed = (time.perf_counter() - start) * 1000  # ms
print(f"Elapsed: {elapsed:.2f}ms")
```

### 驗證狀態
```python
state = LoopState(...)
print(f"Candidates: {len(state.candidates)}")
print(f"Best score: {state.best_score}")
print(f"Constraints: {state.constraints}")
```

---

## 常見使用場景

### 場景 1: 符號回歸
```python
runner.run(
    text="擬合這些數據點",
    keywords=["方程", "多項式", "擬合"],
    mode="semi-pilot",
    config_overrides={"max_iters": 5, "weights": [0.4, 0.3, 0.3]}
)
```

### 場景 2: 代碼搜索
```python
runner.run(
    text="找一個快速排序實現",
    keywords=["排序", "算法", "代碼"],
    mode="autopilot",
    config_overrides={"max_iters": 20}
)
```

### 場景 3: 高風險任務
```python
runner.run(
    text="...",
    keywords=[...],
    mode="co-pilot",  # 每步審查
    config_overrides={"max_iters": 3}
)
```

---

## 輸出文件位置

```
runs/
├── {run_id}/
│   ├── trace.db          # SQLite 追蹤數據庫
│   ├── graph.json        # 計算圖
│   └── workflow.mmd      # Mermaid 流程圖
```

---

## 快速 API 查詢

### 獲取配置狀態
```python
mode_controller.get_status()
terminator.get_status()
```

### 模式切換
```python
mode_controller.switch_mode(OperationMode.AUTOPILOT)
```

### 添加/移除審查階段
```python
mode_controller.add_review_stage("plan")
mode_controller.remove_review_stage("implement")
```

---

## 性能優化檢查清單

- [ ] 使用 EvoGenerator 而不是 LLMGenerator 加快速度
- [ ] 並行執行評分函數
- [ ] 減少 max_iters 對於快速迭代
- [ ] 緩存複雜計算結果
- [ ] 使用較小的 beam_width
- [ ] 增加 convergence_eps 放鬆收斂判決

---

## 前端集成快速開始

### WebSocket 連接
```javascript
const ws = new WebSocket('ws://localhost:9200/ws/run');

ws.send(JSON.stringify({
    text: "...",
    keywords: [...],
    mode: "semi-pilot",
    config_overrides: { max_iters: 10 }
}));

ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    // 處理 msg.type: "iteration_result", "human_review_request", "final_report"
};
```

### 批准人工審查
```javascript
ws.send(JSON.stringify({ type: "approve" }));
```

---

## 擴展點

### 添加新的生成器
```python
class MyGenerator(CandidateGenerator):
    def generate(self, population, feedback, num_candidates):
        # 自定義邏輯
        return new_candidates

    def get_name(self):
        return "MyGenerator"
```

### 添加新的選擇器
```python
class MySelector(Selector):
    def select(self, candidates, scores, weights, top_k):
        # 自定義邏輯
        return top_k_candidates
```

### 添加新的終止條件
```python
def _custom_termination(self, state):
    if some_custom_condition(state):
        self._termination_reason = "Custom reason"
        return True
    return False
```

---

## 版本歷史

| 版本 | 日期 | 主要變化 |
|------|------|---------|
| 1.0 | 2025-01-23 | 初始版本 |

---

**最後更新:** 2025-01-23
**快速參考版本:** 1.0
