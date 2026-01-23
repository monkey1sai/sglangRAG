# SAGA 實現細節和程式碼指南

本文檔提供 SAGA 各個模塊的實現細節、程式碼範例和常見的改進策略。

---

## 第一部分：AdvancedAnalyzer 實現細節

### 1.1 核心方法

```python
class AdvancedAnalyzer:
    def run(self, state: Dict[str, Any] | Any) -> Dict[str, Any]:
        """
        分析當前優化狀態

        計算流程：
        1. 提取 candidates, scores, weights, iteration
        2. 計算每個目標維度的統計信息
        3. 計算目標達成率
        4. 計算 Pareto 最優候選數
        5. 計算改進趨勢
        6. 識別瓶頸
        7. 生成約束建議
        """
```

### 1.2 評分分佈計算

```python
def _calculate_score_distribution(self, scores: List[List[float]]) -> Dict[str, Dict]:
    """
    計算每個目標維度的統計

    輸入: scores 是 n_candidates × n_objectives 矩陣

    輸出:
    {
        "objective_1": {"min": 0.2, "max": 0.9, "avg": 0.6, "std": 0.15},
        "objective_2": {...},
        ...
    }
    """
    if not scores:
        return {}

    n_objectives = len(scores[0])
    distribution = {}

    for obj_idx in range(n_objectives):
        scores_by_obj = [s[obj_idx] for s in scores]
        distribution[f"objective_{obj_idx}"] = {
            "min": min(scores_by_obj),
            "max": max(scores_by_obj),
            "avg": sum(scores_by_obj) / len(scores_by_obj),
            "std": statistics.stdev(scores_by_obj) if len(scores_by_obj) > 1 else 0
        }

    return distribution
```

### 1.3 目標達成率計算

```python
def _calculate_goal_achievement(self, scores: List[List[float]],
                                weights: List[float]) -> Dict[str, float]:
    """
    計算加權多目標達成率

    邏輯：
    - 每個目標維度: avg_score / target_threshold
    - 加權達成率: sum(weights[i] * achievement[i])
    """
    if not scores or not weights:
        return {}

    n_objectives = len(scores[0])
    achievement = {}

    for obj_idx in range(n_objectives):
        scores_by_obj = [s[obj_idx] for s in scores]
        avg_score = sum(scores_by_obj) / len(scores_by_obj)
        threshold = self.goal_thresholds.get(f"goal_{obj_idx}", 0.7)
        achievement[f"goal_{obj_idx}"] = min(avg_score / threshold, 1.0)

    return achievement
```

### 1.4 Pareto 最優性檢查

```python
def _count_pareto_optimal(self, scores: List[List[float]]) -> int:
    """
    計算 Pareto 前沿中的候選數

    定義: 候選 A 主導候選 B，若所有維度上 A 都 >= B，至少一個 > B

    Pareto 最優候選 = 沒有其他候選主導它的候選
    """
    if not scores:
        return 0

    def is_dominated(idx_a, idx_b):
        a, b = scores[idx_a], scores[idx_b]
        dominated = all(a[i] >= b[i] for i in range(len(a)))
        strictly_better = any(a[i] > b[i] for i in range(len(a)))
        return dominated and strictly_better

    pareto_count = 0
    for i in range(len(scores)):
        is_pareto = not any(is_dominated(j, i) for j in range(len(scores)) if i != j)
        if is_pareto:
            pareto_count += 1

    return pareto_count
```

### 1.5 改進趨勢計算

```python
def _calculate_improvement_trend(self, scores: List[List[float]]) -> float:
    """
    計算本輪相對前輪的改進趨勢

    邏輯:
    - 如果 scores 是第一輪: 返回 0.5 (中性)
    - 否則: (當前最佳 - 前輪最佳) / 前輪最佳

    返回值：
    - 負數 = 退步
    - 0 = 沒變
    - 正數 = 改進
    """
    if not scores or len(self._previous_report) == 0:
        return 0.5  # 中性

    current_best = max(sum(s) for s in scores) / len(scores[0])
    previous_best = # 從 _previous_report 取得

    if previous_best == 0:
        return 0.5

    trend = (current_best - previous_best) / abs(previous_best)
    return trend
```

### 1.6 瓶頸識別

```python
def _identify_bottleneck(self, score_distribution: Dict,
                        goal_achievement: Dict) -> str:
    """
    識別最薄弱的目標

    瓶頸 = 達成率最低的目標
    """
    if not goal_achievement:
        return "unknown"

    bottleneck_goal = min(goal_achievement, key=goal_achievement.get)
    return bottleneck_goal
```

### 1.7 約束建議

```python
def _suggest_constraints(self, score_distribution: Dict,
                        improvement_trend: float,
                        bottleneck: str) -> List[str]:
    """
    根據分析提出新約束建議

    策略：
    1. 如果某維度方差很大 → 提議限制該維度的值域
    2. 如果趨勢為負 → 提議增加多樣性約束
    3. 針對瓶頸目標 → 提議強制增加該目標的最小值
    """
    suggestions = []

    # 策略 1: 高方差 → 限制值域
    for obj, stats in score_distribution.items():
        if stats["std"] > 0.3:  # 高方差閾值
            suggestions.append(f"限制{obj}的值域在 [{stats['avg']-0.2}, {stats['avg']+0.2}]")

    # 策略 2: 負趨勢 → 多樣性
    if improvement_trend < 0:
        suggestions.append("增加候選多樣性約束，探索不同的候選空間")

    # 策略 3: 瓶頸
    suggestions.append(f"增加{bottleneck}的最小值要求")

    return suggestions
```

---

## 第二部分：AdvancedPlanner 實現細節

### 2.1 策略確定

```python
def _determine_strategy(self, analysis: Dict, iteration: int) -> str:
    """
    根據迭代輪數和分析結果確定優化策略

    返回: "exploration" | "exploitation" | "balance"
    """
    # 早期迭代: 探索
    if iteration < 3:
        return "exploration"

    # 檢查收斂跡象
    improvement_trend = analysis.get("improvement_trend", 0.5)

    # 改進趨勢為正: 開發
    if improvement_trend > 0.1:
        return "exploitation"

    # 改進趨勢為負: 平衡
    if improvement_trend < -0.1:
        return "balance"

    # 預設: 平衡
    return "balance"
```

### 2.2 權重調整

```python
def _adjust_weights(self, current_weights: List[float],
                   analysis: Dict,
                   strategy: str) -> tuple[List[float], Dict[str, float]]:
    """
    根據分析結果動態調整目標權重

    返回: (新權重, 調整量字典)
    """
    goal_achievement = analysis.get("goal_achievement", {})
    new_weights = list(current_weights)
    adjustments = {}

    # 根據策略調整調整率
    if strategy == "exploration":
        adjustment_rate = 0.05  # 小幅調整，保持多樣性
    elif strategy == "exploitation":
        adjustment_rate = 0.15  # 大幅調整，聚焦改進
    else:  # balance
        adjustment_rate = 0.1

    # 調整權重
    for i, (goal, achievement) in enumerate(goal_achievement.items()):
        threshold = 0.7  # 或从 state.goal_thresholds 取得

        if achievement < threshold:
            # 未達成目標: 增加權重
            delta = adjustment_rate * (threshold - achievement)
            new_weights[i] = min(new_weights[i] + delta, 0.8)
            adjustments[goal] = delta
        else:
            # 已達成目標: 降低權重
            delta = -adjustment_rate * (achievement - threshold)
            new_weights[i] = max(new_weights[i] + delta, 0.1)
            adjustments[goal] = delta

    # 歸一化權重
    total = sum(new_weights)
    new_weights = [w / total for w in new_weights]

    return new_weights, adjustments
```

### 2.3 約束生成

```python
def _generate_constraints(self, analysis: Dict,
                         current_constraints: List[str],
                         strategy: str) -> List[str]:
    """
    根據分析和策略生成新約束
    """
    new_constraints = []

    bottleneck = analysis.get("bottleneck", "")
    suggested = analysis.get("suggested_constraints", [])

    # 根據 Analyzer 的建議添加
    for sugg in suggested:
        if sugg not in current_constraints:
            new_constraints.append(sugg)

    # 根據策略添加額外約束
    if strategy == "exploitation":
        # 開發策略: 加強已有約束
        new_constraints.append(f"嚴格遵循{bottleneck}的最小閾值")
    elif strategy == "exploration":
        # 探索策略: 鬆散約束，促進多樣性
        new_constraints.append("允許更多的候選多樣性")

    return new_constraints
```

### 2.4 焦點目標識別

```python
def _identify_focus(self, analysis: Dict) -> List[str]:
    """
    根據分析結果識別本輪的焦點目標
    """
    goal_achievement = analysis.get("goal_achievement", {})

    # 焦點 = 達成率最低的 2 個目標
    focus = sorted(goal_achievement, key=goal_achievement.get)[:2]

    return focus
```

---

## 第三部分：AdvancedImplementer 實現細節

### 3.1 評分函數生成

```python
class AdvancedImplementer:
    async def run(self, state: Dict) -> Dict:
        """
        根據規劃生成評分函數代碼

        返回 scoring_code (Python 字符串)
        """
        plan = state.get("plan", {})
        constraints = state.get("constraints", [])

        # 生成評分函數框架
        scoring_code = self._generate_base_score_function(plan)

        # 應用約束
        scoring_code = self._apply_constraints(scoring_code, constraints)

        return {
            "scoring_code": scoring_code,
            "version": "v1.0",
            "summary": "Score function with applied constraints"
        }

    def _generate_base_score_function(self, plan: Dict) -> str:
        """
        生成基礎評分函數

        模板:
        def score(candidate: str, context: dict) -> list:
            obj1_score = ...
            obj2_score = ...
            obj3_score = ...
            return [obj1_score, obj2_score, obj3_score]
        """
        code = '''def score(candidate: str, context: dict) -> list:
    """
    評分函數: 為候選方案賦予多維度評分
    """
    try:
        # 目標 1: 複雜度 (越簡單越好，返回 1 - complexity)
        complexity = len(candidate) / 100
        obj1_score = max(0, 1 - complexity)

        # 目標 2: 多樣性 (與歷史候選不同的程度)
        previous_scores = context.get("previous_scores", [])
        similarity = len(set(candidate) & set(previous_scores)) / max(len(candidate), 1)
        obj2_score = max(0, 1 - similarity)

        # 目標 3: 目標達成 (應用約束檢查)
        constraint_satisfied = True
        for constraint in context.get("constraints", []):
            # 檢查 candidate 是否滿足 constraint
            pass
        obj3_score = 1.0 if constraint_satisfied else 0.0

        return [obj1_score, obj2_score, obj3_score]

    except Exception as e:
        return [0.5, 0.5, 0.5]  # 錯誤時返回中性評分
'''
        return code

    def _apply_constraints(self, code: str, constraints: List[str]) -> str:
        """
        將約束條件集成到評分函數
        """
        if not constraints:
            return code

        # 在評分函數中添加約束檢查邏輯
        constraint_checks = "\n    ".join([
            f"# 約束: {c}" for c in constraints
        ])

        # 插入到代碼中
        modified_code = code.replace(
            "# 檢查 candidate 是否滿足 constraint",
            constraint_checks
        )

        return modified_code
```

---

## 第四部分：AdvancedOptimizer 實現細節

### 4.1 優化主循環

```python
class AdvancedOptimizer:
    def optimize(self, candidates: List[str],
                scoring_code: str,
                weights: List[float]) -> List[Tuple[str, List[float]]]:
        """
        內部迴圈: 使用評分函數和生成器優化候選

        步驟:
        1. 執行評分函數得到當前評分
        2. 使用 Beam Search 選擇前 k 個
        3. 使用 Generator 生成新候選
        4. 重複 n 次
        """
        current_candidates = candidates

        for inner_iter in range(self.inner_iterations):
            # Step 1: 評分
            scores = self._execute_scoring(current_candidates, scoring_code)

            # Step 2: 選擇
            top_k = self.selector.select(
                candidates=current_candidates,
                scores=scores,
                weights=weights,
                top_k=self.beam_width
            )

            if inner_iter == self.inner_iterations - 1:
                # 最後一次迭代，返回結果
                return top_k

            # Step 3: 生成新候選
            # 創建反饋
            feedback = AnalysisReport(
                score_distribution={},
                goal_achievement={},
                pareto_count=len(top_k),
                improvement_trend=0.5,
                bottleneck="unknown",
                suggested_constraints=[],
                iteration=0
            )

            new_candidates = self.generator.generate(
                population=[c for c, _ in top_k],
                feedback=feedback,
                num_candidates=len(candidates)
            )

            current_candidates = new_candidates

        return top_k

    def _execute_scoring(self, candidates: List[str],
                        scoring_code: str) -> List[List[float]]:
        """
        執行評分函數

        通過 exec() 動態執行 Python 代碼
        """
        scores = []

        # 編譯評分函數
        local_vars = {}
        exec(scoring_code, {}, local_vars)
        score_func = local_vars.get("score")

        if not score_func:
            raise ValueError("Invalid scoring code")

        # 對每個候選評分
        context = {"keywords": self.context, "previous_scores": candidates}

        for candidate in candidates:
            try:
                score = score_func(candidate, context)
                scores.append(score)
            except Exception as e:
                # 評分失敗，返回中性評分
                scores.append([0.5, 0.5, 0.5])

        return scores
```

### 4.2 Beam Search 選擇

```python
def beam_search(candidates: List[str],
               scorer: Callable[[str], List[float]],
               beam_width: int,
               weights: List[float] = None) -> List[Tuple[str, List[float]]]:
    """
    Beam Search: 選擇前 k 個最佳候選
    """
    scored = []

    for c in candidates:
        score_vec = scorer(c)

        # 計算加權評分
        if weights:
            weighted = sum(w * s for w, s in zip(weights, score_vec))
        else:
            weighted = sum(score_vec) / len(score_vec)

        scored.append((c, score_vec, weighted))

    # 按加權評分排序
    scored.sort(key=lambda x: x[2], reverse=True)

    # 返回前 k 個 (不包含加權分數)
    return [(c, s) for c, s, _ in scored[:beam_width]]
```

---

## 第五部分：候選生成器實現細節

### 5.1 LLMGenerator 詳細實現

```python
class LLMGenerator(CandidateGenerator):
    def generate(self, population: List[str],
                feedback: AnalysisReport,
                num_candidates: int = 5) -> List[str]:
        """
        使用 LLM 生成新候選
        """
        # 獲取適當的提示策略
        strategy = self.router.get_strategy(self.keywords)

        # 構建提示
        prompt = strategy.build_prompt(population, feedback, num_candidates)

        # 調用 LLM
        response = self.client.call(prompt, temperature=0.8)

        # 解析回應
        raw_content = response["choices"][0]["message"]["content"]
        candidates = strategy.parse_candidates(raw_content, num_candidates)

        return candidates
```

### 5.2 提示構建 (符號回歸範例)

```python
class SymbolicRegressionStrategy:
    def build_prompt(self, population: List[str],
                    feedback: AnalysisReport,
                    num_candidates: int) -> str:
        """
        為符號回歸任務構建提示
        """
        best = population[0] if population else "x"
        bottleneck = feedback.bottleneck
        trend = "改進" if feedback.improvement_trend > 0 else "停滯"

        prompt = f"""
你是一個符號回歸專家。任務是為給定的數據集找到最佳擬合公式。

當前最佳候選: {best}
優化瓶頸: {bottleneck}
改進趨勢: {trend}
當前候選池:
{chr(10).join(population)}

請生成 {num_candidates} 個新的公式候選，改進當前解。
考慮以下策略:
1. 嘗試添加新的項 (如 x^2, x^3 等)
2. 嘗試組合現有項
3. 嘗試不同的係數

輸出格式: 每行一個公式，不要有其他說明文字。
"""
        return prompt

    def parse_candidates(self, content: str,
                        num_candidates: int) -> List[str]:
        """
        從 LLM 回應中解析公式
        """
        lines = content.strip().split('\n')
        candidates = []

        for line in lines:
            line = line.strip()
            if line and not line.startswith('#'):
                # 驗證是有效的 Python 表達式
                try:
                    compile(line, '<string>', 'eval')
                    candidates.append(line)
                except:
                    continue

        return candidates[:num_candidates]
```

### 5.3 EvoGenerator 實現

```python
class EvoGenerator(CandidateGenerator):
    def generate(self, population: List[str],
                feedback: AnalysisReport,
                num_candidates: int = 5) -> List[str]:
        """
        使用遺傳算法生成候選
        """
        new_candidates = []

        for _ in range(num_candidates):
            if random.random() < self.crossover_rate and len(population) >= 2:
                # 交叉
                parent1, parent2 = random.sample(population, 2)
                child = self._crossover(parent1, parent2)
            else:
                # 選擇父代
                child = random.choice(population)

            # 變異
            if random.random() < self.mutation_rate:
                child = self._mutate(child)

            new_candidates.append(child)

        return new_candidates

    def _crossover(self, parent1: str, parent2: str) -> str:
        """
        單點交叉
        """
        mid1 = len(parent1) // 2
        mid2 = len(parent2) // 2
        child = parent1[:mid1] + parent2[mid2:]
        return child

    def _mutate(self, candidate: str) -> str:
        """
        隨機變異
        """
        if not candidate:
            return candidate

        pos = random.randint(0, len(candidate) - 1)
        mutations = ["+1", "-1", "*2", "/2", "**2"]
        mutation = random.choice(mutations)

        new_candidate = candidate[:pos] + mutation + candidate[pos:]
        return new_candidate
```

---

## 第六部分：ModeController 實現細節

### 6.1 操作模式切換

```python
class ModeController:
    def __init__(self, default_mode: OperationMode = OperationMode.SEMI_PILOT):
        self._mode = default_mode
        self._review_stages = MODE_REVIEW_STAGES[default_mode].copy()

    def requires_human_review(self, stage: str) -> bool:
        """
        檢查特定階段是否需要人類審查
        """
        return stage.lower() in self._review_stages

    def switch_mode(self, new_mode: OperationMode) -> None:
        """
        動態切換操作模式
        """
        old_mode = self._mode
        self._mode = new_mode
        self._review_stages = MODE_REVIEW_STAGES[new_mode].copy()
        logger.info(f"Mode switched: {old_mode.value} → {new_mode.value}")
```

### 6.2 模式定義

```python
MODE_REVIEW_STAGES = {
    OperationMode.CO_PILOT: {
        "analyze",      # 分析報告需審查
        "plan",         # 規劃結果需審查
        "implement",    # 評分函數需審查
        "optimize"      # 優化結果需審查
    },
    OperationMode.SEMI_PILOT: {
        "analyze"       # 只有分析報告需審查
    },
    OperationMode.AUTOPILOT: set()  # 無需審查
}
```

---

## 第七部分：TerminationChecker 實現細節

### 7.1 終止條件檢查

```python
class TerminationChecker:
    def should_stop(self, state: LoopState) -> bool:
        """
        檢查是否應終止外迴圈
        """
        # 條件 1: 最大迭代數
        if state.iteration >= self.max_iters:
            self._termination_reason = f"Reached max iterations ({state.iteration})"
            return True

        # 條件 2: 收斂
        if self._is_converged(state.score_history):
            self._termination_reason = "Score converged"
            return True

        # 條件 3: 目標達成
        if self._all_goals_achieved(state):
            self._termination_reason = "All goals achieved"
            return True

        # 條件 4: Pareto 穩定
        if self._pareto_stable(state.pareto_history):
            self._termination_reason = "Pareto front stable"
            return True

        return False

    def _is_converged(self, score_history: List[float]) -> bool:
        """
        檢查評分是否收斂

        邏輯: 最後 patience 次迭代的評分變化都 < eps
        """
        if len(score_history) < self.convergence_patience + 1:
            return False

        recent = score_history[-self.convergence_patience:]
        baseline = score_history[-(self.convergence_patience + 1)]

        return all(abs(s - baseline) < self.convergence_eps for s in recent)

    def _all_goals_achieved(self, state: LoopState) -> bool:
        """
        檢查是否所有目標都已達成
        """
        if not state.analysis_reports:
            return False

        latest_report = state.analysis_reports[-1]
        goal_achievement = latest_report.goal_achievement

        for goal, threshold in self.goal_thresholds.items():
            if goal_achievement.get(goal, 0) < threshold:
                return False

        return True

    def _pareto_stable(self, pareto_history: List[int]) -> bool:
        """
        檢查 Pareto 前沿是否穩定
        """
        if len(pareto_history) < self.pareto_patience + 1:
            return False

        recent = pareto_history[-self.pareto_patience:]
        baseline = pareto_history[-(self.pareto_patience + 1)]

        return all(p == baseline for p in recent)
```

---

## 第八部分：常見改進和優化

### 8.1 加快評分函數執行

**問題:** 複雜的評分函數可能很慢

**解決方案:**
```python
# 使用緩存
from functools import lru_cache

@lru_cache(maxsize=1000)
def expensive_calculation(candidate: str) -> float:
    # 昂貴計算
    pass

# 並行評分
from concurrent.futures import ThreadPoolExecutor

def parallel_score(candidates: List[str], score_func):
    with ThreadPoolExecutor(max_workers=4) as executor:
        scores = list(executor.map(score_func, candidates))
    return scores
```

### 8.2 改進 LLM 提示質量

**策略:**
1. 使用 Few-shot 示例
2. 明確指定輸出格式
3. 提供約束條件
4. 包含評估指標

**範例:**
```python
def build_advanced_prompt(population, feedback):
    examples = """
示例 1: 輸入 f(x) = x，建議 f(x) = x + 1
示例 2: 輸入 f(x) = x^2，建議 f(x) = x^2 + x
"""

    prompt = f"""
任務：生成符號公式

{examples}

當前候選:
{chr(10).join(population)}

瓶頸: {feedback.bottleneck}

請生成 5 個改進的公式，按以下格式:
公式1
公式2
...
"""
    return prompt
```

### 8.3 添加約束驗證

```python
class ConstraintValidator:
    @staticmethod
    def validate_formula(formula: str, constraints: List[str]) -> bool:
        """
        驗證公式是否滿足所有約束
        """
        for constraint in constraints:
            if "長度" in constraint:
                max_len = extract_number(constraint)
                if len(formula) > max_len:
                    return False
            elif "操作數" in constraint:
                if count_operators(formula) > extract_number(constraint):
                    return False

        return True
```

### 8.4 動態權重調整

```python
def adaptive_weight_adjustment(weights, history, iteration):
    """
    根據歷史性能自適應調整權重
    """
    # 計算每個目標的改進空間
    improvement_potential = []
    for i, hist in enumerate(history):
        current = hist[-1]
        threshold = 0.7
        potential = threshold - current
        improvement_potential.append(potential)

    # 調整權重以最大化改進空間
    adjusted = [w * p for w, p in zip(weights, improvement_potential)]

    # 歸一化
    return [a / sum(adjusted) for a in adjusted]
```

---

## 第九部分：調試和日誌

### 9.1 詳細日誌記錄

```python
import logging

logger = logging.getLogger(__name__)

# 設置日誌級別
logging.basicConfig(
    level=logging.DEBUG,
    format='[%(asctime)s] %(name)s - %(levelname)s - %(message)s'
)

# 在各模塊記錄詳細信息
logger.debug(f"[Analyzer] Score distribution: {score_distribution}")
logger.debug(f"[Planner] Adjusted weights: {new_weights}")
logger.info(f"[Optimizer] Generated {len(new_candidates)} candidates")
```

### 9.2 性能分析

```python
import time

def measure_performance(func):
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed = (time.perf_counter() - start) * 1000  # ms
        logger.info(f"{func.__name__} took {elapsed:.2f}ms")
        return result
    return wrapper

@measure_performance
def expensive_operation():
    # ...
    pass
```

---

## 總結

SAGA 的實現基於以下關鍵原則：

1. **模塊化** - 各模塊獨立但協調
2. **可擴展性** - 易於添加新的生成器、約束等
3. **靈活控制** - 支援從全自動到完全手動的各種模式
4. **數據驅動** - 基於分析反饋動態調整策略
5. **性能關注** - 並行評分、緩存、動態超時

---

**版本:** 1.0
**日期:** 2025-01-23
