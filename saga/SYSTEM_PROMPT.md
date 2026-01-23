# SAGA 系統提示文檔
## 為 AI 助手理解 SAGA 架構和邏輯

---

## 第一部分：SAGA 系統總覽

### 1.1 核心概念

**SAGA** (Self-Evolving Scientific Discovery System) 是一個**多輪迭代優化系統**，專門設計用於：
- 複雜問題求解與優化
- 多目標科學發現
- 符號回歸、方程擬合等科學計算任務
- 動態約束和目標權重演化

**核心理念：** 通過多輪迭代，系統不斷分析當前狀態、調整優化策略、生成新候選方案，最終收斂到最優解。

---

### 1.2 系統架構概覽

```
用戶請求 (input text, keywords, mode, parameters)
    ↓
SagaRunner (主入口，初始化所有組件)
    ↓
OuterLoop (多輪迭代控制器)
    ├─ 迭代 1, 2, ..., n 直到終止條件
    │   ├─ AdvancedAnalyzer (分析當前狀態)
    │   ├─ AdvancedPlanner (規劃優化策略)
    │   ├─ AdvancedImplementer (實現評分函數)
    │   ├─ AdvancedOptimizer (內部迴圈優化)
    │   └─ TerminationChecker (檢查是否終止)
    ├─ ModeController (控制人類審查時機)
    └─ TraceDB (記錄迭代過程)
    ↓
FinalReport (最終報告)
```

---

## 第二部分：核心數據結構

### 2.1 LoopState (循環狀態)

維護跨迭代的狀態信息：

```python
@dataclass
class LoopState:
    iteration: int = 0                    # 當前迭代次數
    text: str = ""                        # 問題描述文本
    keywords: List[str] = []              # 關鍵字列表
    constraints: List[str] = []           # 當前約束集
    candidates: List[str] = []            # 候選方案列表
    current_scores: List[List[float]] =[] # 多維評分 (n_candidates × n_objectives)
    best_candidate: str = ""              # 最佳候選
    best_score: float = 0.0               # 加權最佳評分
    score_history: List[float] = []       # 歷史評分序列 (用於收斂檢查)
    pareto_history: List[int] = []        # Pareto前沿候選數歷史
    weights: List[float] = [0.33, 0.34, 0.33]  # 目標權重
    goal_thresholds: List[float] = [0.7, 0.7, 0.7]  # 目標閾值
    analysis_reports: List[AnalysisReport] = []  # 歷史分析報告
```

**關鍵點：**
- `current_scores`: 多維度評分，每個候選有 n 個分量 (如效率、準確度、複雜度)
- `weights`: 加權多目標優化的權重 (應歸一化)
- `score_history`: 追蹤最佳評分的變化，用於收斂檢查

### 2.2 AnalysisReport (分析報告)

由 AdvancedAnalyzer 生成，包含系統狀態的深度分析：

```python
@dataclass
class AnalysisReport:
    score_distribution: Dict[str, Dict[str, float]]  # 各維度分數統計 (min, max, avg, std)
    goal_achievement: Dict[str, float]               # 各目標達成率
    pareto_count: int                                # Pareto最優候選數
    improvement_trend: float                         # 改進趨勢 (負=回退, 正=改進)
    bottleneck: str                                  # 最差的目標
    suggested_constraints: List[str]                 # 建議的約束
    iteration: int                                   # 迭代編號
```

### 2.3 IterationResult (迭代結果)

每次迭代的完整結果快照：

```python
@dataclass
class IterationResult:
    iteration: int                    # 迭代編號
    analysis_report: AnalysisReport   # 該迭代的分析報告
    new_constraints: List[str]        # 本迭代新增約束
    best_candidate: str               # 本迭代最佳候選
    best_score: float                 # 本迭代最佳評分
    elapsed_ms: int                   # 執行時間(毫秒)
```

---

## 第三部分：四層迭代架構

### 3.1 迭代流程 (Outer Loop)

每次迭代依次執行 4 個模塊，加上人類審查檢查點：

#### **第 1 步：AdvancedAnalyzer (分析)**

**目的：** 分析當前狀態的性能瓶頸和機會

**輸入：**
- `LoopState`: 候選、評分、權重、約束
- `current_scores`: n_candidates × n_objectives 的評分矩陣

**分析內容：**
1. **評分分佈統計** - 每個目標維度的 min/max/avg/std
2. **目標達成率** - 各目標達成加權目標的比例
3. **Pareto 最優性** - 計算 Pareto 前沿候選數
4. **改進趨勢** - 比較本輪與前輪分數的差異
5. **瓶頸識別** - 找出最薄弱的目標
6. **約束建議** - 基於分析提出新約束

**輸出：** `AnalysisReport` 物件

**人類審查** (Co-pilot/Semi-pilot 模式)：
- Co-pilot: 需要人類審查並批准分析報告
- Semi-pilot: 需要人類審查分析報告
- Autopilot: 跳過審查

#### **第 2 步：AdvancedPlanner (規劃)**

**目的：** 根據分析結果調整優化策略

**輸入：**
- `AnalysisReport`: 上一步的分析結果
- 當前約束、權重、迭代數

**計劃內容：**
1. **確定策略** - Exploration (探索)/Exploitation (開發)/Balance (平衡)
   - 初期迭代：傾向探索
   - 後期迭代：傾向開發
   - 停滯時：平衡
2. **調整權重** - 增加瓶頸目標的權重，降低已達成目標的權重
3. **生成約束** - 基於分析提出新約束，限制搜索空間
4. **識別焦點** - 確定本輪優化的重點目標

**權重調整算法：**
```
if goal_achievement[g] < threshold:
    weights[g] += adjustment_rate * (threshold - achievement[g])
else:
    weights[g] -= adjustment_rate * (achievement[g] - threshold)

# 歸一化權重
weights = weights / sum(weights)
```

**輸出：** 新的 `weights`、`new_constraints`、`strategy`

**人類審查** (Co-pilot 模式)：
- 審查新的約束和權重調整

#### **第 3 步：AdvancedImplementer (實現)**

**目的：** 根據規劃生成評分函數代碼

**輸入：**
- `OptimizationPlan`: 規劃結果 (權重、約束、策略)
- 關鍵詞和背景信息

**實現內容：**
1. **生成評分函數** - 用 Python 代碼編寫 `score(text, context)` 函數
2. **應用約束** - 將新約束編碼入評分函數
3. **版本管理** - 追蹤評分函數的版本

**評分函數簽名：**
```python
def score(candidate: str, context: Dict[str, Any]) -> List[float]:
    """
    Args:
        candidate: 要評分的候選方案 (通常是公式/程式碼)
        context: 包含 keywords, previous_scores, constraints 等上下文

    Returns:
        List[float]: 多維評分 [obj1_score, obj2_score, ...]
    """
    # 根據 candidate 計算多個客觀函數值
    # 返回歸一化到 [0, 1] 的評分向量
    pass
```

**輸出：** `scoring_code` (Python 代碼字符串)

#### **第 4 步：AdvancedOptimizer (優化) - 內部迴圈**

**目的：** 運行內部迴圈優化，生成新候選方案

**算法架構 (內部迴圈)：**

1. **初始化：**
   - 當前候選集合
   - 評分函數 (由 Implementer 生成)
   - 目標權重

2. **候選生成：**
   - 使用 `LLMGenerator` 或 `EvoGenerator` 生成新候選
   - LLMGenerator: 利用 LLM (SGLang/Groq) 根據分析反饋智能生成
   - EvoGenerator: 基於遺傳算法的進化 (交叉、變異)

3. **評分：**
   - 對所有候選執行評分函數
   - 生成 `current_scores` 矩陣

4. **Beam Search 選擇：**
   - 使用加權 Beam Search 選出前 k 個最佳候選
   - 加權函數: `weighted_score = sum(weights[i] * scores[i])`

5. **迭代：** 重複 2-4 步，直至內部終止條件

**輸出：** 優化後的候選集合和評分

---

### 3.2 終止條件 (TerminationChecker)

外迴圈在以下任何條件滿足時終止：

1. **最大迭代數**
   - `iteration >= max_iters`

2. **評分收斂**
   - 最後 `convergence_patience` 次迭代的評分變化 < `convergence_eps`

3. **所有目標達成**
   - 所有目標的達成率 >= 各自的閾值

4. **Pareto 前沿穩定**
   - 最後 `pareto_patience` 次迭代的 Pareto 候選數不變

**終止配置：**
```python
@dataclass
class TerminationConfig:
    max_iters: int = 10                    # 最大迭代次數
    convergence_eps: float = 0.001         # 收斂判決: 評分變化閾值
    convergence_patience: int = 3          # 收斂判決: 連續迭代次數
    goal_thresholds: Dict[str, float] = {} # 目標達成閾值
    pareto_patience: int = 3               # Pareto 穩定判決: 連續迭代次數
```

---

## 第四部分：操作模式控制

### 4.1 三種操作模式

由 `ModeController` 管理，控制在迭代過程中何時暫停進行人類審查：

| 模式 | 審查點 | 適用場景 |
|------|--------|---------|
| **Co-pilot** | 每一步 (分析、規劃、實現、優化) | 高風險、探索性任務，需深度參與 |
| **Semi-pilot** (預設) | 分析報告 | 一般任務，人類指導策略，自動優化 |
| **Autopilot** | 無 (完全自主) | 大規模搜索，需快速運行 |

### 4.2 人類審查請求

當需要審查時，系統發送 `HumanReviewRequest`：

```python
@dataclass
class HumanReviewRequest:
    review_type: HumanReviewType  # ANALYZE, PLAN, IMPLEMENT, APPROVE_CONSTRAINTS
    data: Dict[str, Any]          # 審查數據 (報告、計劃等)
    message: str                  # 提示信息 (如 "請審核第 2 輪分析報告")
    iteration: int                # 迭代編號
```

前端應：
1. 收到 `HumanReviewRequest`，展示相關信息
2. 等待用戶批准或修改
3. 發送 `{type: "approve"}` 或 `{type: "reject", reason: "..."}` 回應
4. 系統繼續執行下一步

---

## 第五部分：候選生成策略

### 5.1 LLMGenerator (LLM 驅動生成)

**工作原理：**
1. 根據 `keywords` 路由到適當的提示策略
2. 構建包含上下文的提示 (當前最佳候選、瓶頸、改進趨勢)
3. 調用 LLM (SGLang 或 Groq) 生成新候選
4. 解析 LLM 輸出，提取候選列表

**優點：** 智能、上下文感知、通常質量高

**缺點：** 依賴 LLM 可用性、可能較慢

### 5.2 EvoGenerator (進化算法)

**工作原理：**
1. 交叉 (Crossover): 隨機選擇兩個父代候選，在中點交叉
2. 變異 (Mutation): 隨機替換候選中的字符或插入新字符
3. 選擇: 保留最高評分的候選

**優點：** 快速、無外部依賴、多樣性高

**缺點：** 可能不夠智能，生成的候選可能不太有意義

### 5.3 提示策略路由 (PromptRouter)

根據 `keywords` 自動選擇適當的提示策略：

- **數學/方程**：優化符號表達式 (x²、多項式等)
- **代碼**：生成程式碼片段或算法
- **通用**：通用的改進建議

---

## 第六部分：主要類和接口

### 6.1 SagaRunner (主入口)

```python
class SagaRunner:
    def __init__(self, cfg: SagaConfig)

    async def run(
        self,
        text: str,                              # 問題文本
        keywords: list[str],                    # 關鍵詞
        mode: str = "semi-pilot",               # 操作模式
        run_id: Optional[str] = None,           # 運行 ID
        config_overrides: Optional[dict] = None # 科學家參數覆蓋
    ) -> AsyncIterator[IterationResult | HumanReviewRequest | FinalReport]
```

**config_overrides 參數說明：**
```python
{
    "max_iters": 10,              # 最大迭代次數
    "convergence_eps": 0.001,     # 收斂精度
    "convergence_patience": 3,    # 收斂判決迭代數
    "goal_thresholds": [0.7, 0.7, 0.7],  # 目標達成閾值
    "weights": [0.33, 0.34, 0.33],       # 初始權重
}
```

### 6.2 OuterLoop (多輪迴圈控制)

```python
class OuterLoop:
    async def run(
        self,
        initial_state: LoopState,
        run_id: str
    ) -> AsyncIterator[IterationResult | HumanReviewRequest | FinalReport | LogEvent]
```

**產出的事件類型：**
- `LogEvent`: 系統日誌事件 (info, warning, error, success)
- `IterationResult`: 單次迭代結果
- `HumanReviewRequest`: 等待人類審查
- `FinalReport`: 最終報告

### 6.3 ModeController (操作模式控制)

```python
class ModeController:
    def requires_human_review(self, stage: str) -> bool
    def switch_mode(self, new_mode: OperationMode) -> None
    def get_status(self) -> dict
```

### 6.4 TerminationChecker (終止檢查)

```python
class TerminationChecker:
    def should_stop(self, state: LoopState) -> bool
    def get_termination_reason(self, state: LoopState) -> str
    def get_status(self) -> dict
```

---

## 第七部分：配置和環境變數

### 7.1 SagaConfig (運行時配置)

```python
@dataclass
class SagaConfig:
    run_dir: str = "runs"                    # 運行輸出目錄
    beam_width: int = 3                      # Beam 寬度 (保留前 k 個候選)
    max_iters: int = 2                       # 預設最大迭代次數

    sglang_url: str = "http://localhost:8082/v1/chat/completions"
    sglang_api_key: str = ""                 # SGLang API 金鑰
    timeout_s: float = 10.0                  # 超時時間(秒)

    use_llm_modules: bool = True             # 是否使用 LLM 模塊
    use_groq: bool = False                   # 是否使用 Groq
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
```

### 7.2 環境變數

來自 `.env` 文件：
```bash
SAGA_RUN_DIR=runs
SAGA_BEAM_WIDTH=3
SAGA_MAX_ITERS=10
SAGA_USE_LLM_MODULES=true
SGLANG_API_KEY=sk-...
SGLANG_BASE_URL=http://localhost:8082
```

---

## 第八部分：典型執行流程

### 8.1 完整執行示例

```
初始化
└─ SagaRunner 初始化
   ├─ AdvancedAnalyzer
   ├─ AdvancedPlanner
   ├─ AdvancedImplementer
   ├─ AdvancedOptimizer (含 Generator)
   └─ TraceDB

執行 run() 開始迴圈
└─ OuterLoop 運行
   │
   ├─ 迭代 1
   │  ├─ AdvancedAnalyzer.run() → AnalysisReport
   │  ├─ [Semi-pilot: 人類審查分析] ← 暫停等待批准
   │  ├─ AdvancedPlanner.run() → 新權重、新約束
   │  ├─ AdvancedImplementer.run() → 評分函數代碼
   │  ├─ AdvancedOptimizer.optimize()
   │  │  ├─ Generator.generate() → 新候選
   │  │  ├─ 評分函數執行 → current_scores
   │  │  └─ Beam Search 選擇前 k 個
   │  ├─ 更新 LoopState
   │  └─ 收斂檢查 → 繼續
   │
   ├─ 迭代 2
   │  └─ (同上)
   │
   ├─ ...
   │
   └─ 迭代 n
      └─ (同上)
      │
      └─ 終止檢查 → 停止

生成 FinalReport
└─ 包含:
   ├─ 最佳候選
   ├─ 最佳評分
   ├─ 評分演化歷史
   ├─ 所有分析報告
   ├─ 終止原因
   └─ 總執行時間
```

---

## 第九部分：與外部服務的集成

### 9.1 SGLang 適配器 (SGLangAdapter)

```python
class SGLangAdapter:
    def call(self, prompt: str, temperature: float = 0.7) -> Dict
        """
        調用遠程 SGLang 服務
        返回 OpenAI 格式的回應
        """
```

**使用場景：**
- LLMGenerator 調用 SGLang 生成候選
- LLM 模塊調用評分模型

### 9.2 Groq 適配器 (GroqAdapter)

備選的 LLM 後端，用於更快的推理。

---

## 第十部分：輸出和追蹤

### 10.1 TraceDB (SQLite 追蹤數據庫)

每個運行都會在 `runs/{run_id}/` 下創建：
- `trace.db`: SQLite 數據庫，記錄每次迭代的節點和邊
- `graph.json`: 計算圖 JSON 格式
- `workflow.mmd`: Mermaid 流程圖

### 10.2 最終輸出 (FinalReport)

```python
@dataclass
class FinalReport:
    run_id: str                    # 運行 ID
    total_iterations: int          # 實際迭代次數
    termination_reason: str        # 終止原因
    best_candidate: str            # 最佳方案
    best_score: float              # 最佳評分
    score_evolution: List[float]   # 評分進化曆史
    all_reports: List[AnalysisReport]  # 所有分析報告
    elapsed_ms: int                # 總執行時間(毫秒)
```

---

## 第十一部分：常見使用模式

### 11.1 Python 程式碼使用

```python
from saga.config import SagaConfig
from saga.runner import SagaRunner

async def main():
    cfg = SagaConfig()
    runner = SagaRunner(cfg)

    # 定義問題
    text = "找一個多項式擬合這些數據點..."
    keywords = ["多項式", "擬合", "方程"]

    # 運行
    async for event in runner.run(
        text=text,
        keywords=keywords,
        mode="semi-pilot",
        config_overrides={
            "max_iters": 5,
            "weights": [0.4, 0.3, 0.3],
            "goal_thresholds": [0.8, 0.8, 0.8]
        }
    ):
        if isinstance(event, IterationResult):
            print(f"Iter {event.iteration}: best_score={event.best_score:.4f}")
        elif isinstance(event, HumanReviewRequest):
            print(f"Waiting for human review: {event.message}")
            # 前端應發送 approve 消息
        elif isinstance(event, FinalReport):
            print(f"Final result: {event.best_candidate}")
```

### 11.2 WebSocket 服務使用 (Web 前端)

Web UI 通過 WebSocket 連接 `saga_server` 的 `/ws/run` 端點：

```javascript
const ws = new WebSocket('ws://localhost:9200/ws/run');

ws.send(JSON.stringify({
    text: "找方程...",
    keywords: ["多項式"],
    mode: "semi-pilot",
    config_overrides: {
        max_iters: 10,
        weights: [0.33, 0.33, 0.34]
    }
}));

ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);

    if (msg.type === 'iteration_result') {
        // 更新進度圖表
    } else if (msg.type === 'human_review_request') {
        // 展示審查介面
        // 用戶批准後：
        ws.send(JSON.stringify({ type: 'approve' }));
    } else if (msg.type === 'final_report') {
        // 展示最終結果
    }
};
```

---

## 第十二部分：調試和擴展指南

### 12.1 添加新的評分維度

1. 修改 AdvancedImplementer 生成的評分函數，返回 n 維向量
2. 更新 LoopState.weights 以包含新維度的權重
3. 更新 LoopState.goal_thresholds 以設置新維度的目標

### 12.2 自定義候選生成策略

1. 創建新的 `CandidateGenerator` 子類
2. 實現 `generate()` 方法
3. 在 SagaRunner 中註冊新生成器

### 12.3 添加新的終止條件

1. 在 TerminationChecker 中添加新的 `_check_*()` 方法
2. 在 `should_stop()` 中調用新方法
3. 更新 TerminationConfig 以支持新參數

---

## 第十三部分：常見問題和最佳實踐

### 13.1 Q: 為什麼分數收斂了但沒有達到目標?
**A:** 這表示系統達到了局部最優。嘗試：
- 增加 `max_iters`
- 調整 `weights` 以給目標更高權重
- 增加 `convergence_eps` (放鬆收斂判決)

### 13.2 Q: 如何強制探索而不是開發?
**A:** 使用 Co-pilot 模式定期審查，或在 config_overrides 中增加 `max_iters`

### 13.3 Q: 為什麼 LLMGenerator 生成的候選有時很奇怪?
**A:** LLM 生成具有隨機性。嘗試：
- 降低 LLM 溫度參數
- 改進提示詞
- 使用 EvoGenerator 作為降級方案

### 13.4 最佳實踐
- 為符號回歸任務使用 Semi-pilot 或 Autopilot
- 為高風險任務使用 Co-pilot
- 監控 `score_evolution` 曲線，如果平坦則增加約束
- 定期檢查 `bottleneck` 報告，針對性調整權重

---

## 第十四部分：架構圖

### 14.1 數據流圖

```
LoopState
    ↓
AdvancedAnalyzer → AnalysisReport
    ↓
AdvancedPlanner → OptimizationPlan
    ↓
AdvancedImplementer → scoring_code (Python)
    ↓
AdvancedOptimizer (內部迴圈)
    ├─ Generator (LLMGenerator | EvoGenerator) → new candidates
    ├─ Executor (scoring_code) → current_scores
    └─ Selector (Beam Search) → top-k candidates
    ↓
LoopState (更新) → 下一迭代
```

### 14.2 類依賴圖

```
SagaRunner
    ├─ SagaConfig
    ├─ AdvancedAnalyzer
    ├─ AdvancedPlanner
    ├─ AdvancedImplementer
    ├─ AdvancedOptimizer
    │   ├─ CandidateGenerator (LLMGenerator | EvoGenerator)
    │   │   ├─ SGLangAdapter | GroqAdapter
    │   │   └─ PromptRouter
    │   └─ Selector (ParetoSelector | BeamSelector)
    ├─ ModeController
    │   └─ OperationMode (enum)
    ├─ TerminationChecker
    │   └─ TerminationConfig
    └─ TraceDB
```

---

## 第十五部分：關鍵類和方法速查表

| 類名 | 主要方法 | 返回類型 | 用途 |
|------|--------|--------|------|
| `SagaRunner` | `run()` | AsyncIterator | 主入口，啟動整個系統 |
| `OuterLoop` | `run()` | AsyncIterator | 多輪迭代控制器 |
| `AdvancedAnalyzer` | `run()` | Dict | 分析當前狀態 |
| `AdvancedPlanner` | `run()` | Dict | 規劃優化策略 |
| `AdvancedImplementer` | `run()` | Dict | 生成評分函數 |
| `AdvancedOptimizer` | `optimize()` | List[Tuple] | 內部迴圈優化 |
| `LLMGenerator` | `generate()` | List[str] | LLM 驅動的候選生成 |
| `EvoGenerator` | `generate()` | List[str] | 進化算法生成候選 |
| `ModeController` | `requires_human_review()` | bool | 檢查是否需人審查 |
| `TerminationChecker` | `should_stop()` | bool | 檢查是否應終止 |
| `TraceDB` | `write_node()` | None | 記錄迭代信息 |

---

## 總結

**SAGA 是一個複雜但靈活的系統，核心思想是：**

```
迭代 = 分析 → 規劃 → 實現 → 優化 → 評估
     ↓
  收斂或達成目標? → 是 → 終止
     ↑
  否 → 回到迭代
```

通過動態調整權重、約束和生成策略，SAGA 能夠高效地探索解空間，並在多個目標之間取得平衡。結合人類的智慧（通過審查模式），SAGA 可以應對複雜的科學發現任務。

---

**此文檔版本：** 1.0 (2025-01-23)
**文檔維護者：** SAGA 開發團隊
**最後更新：** 2025-01-23

---
