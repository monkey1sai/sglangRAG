"""
符號回歸整合測試 - 驗證 SAGA 多輪目標演化

隱藏公式: y = x² + 3x - 2
目標: 讓 SAGA 透過多輪迭代「發現」這個公式

評分維度:
1. 擬合精度 (50%) - MSE 越小分數越高
2. 公式簡潔性 (30%) - 字符數越少分數越高  
3. 泛化能力 (20%) - 測試點預測準確度
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

# 添加專案根目錄到 Python 路徑
sys.path.insert(0, str(Path(__file__).parent.parent))

from saga.config import SagaConfig
from saga.outer_loop import OuterLoop, LoopState, IterationResult, FinalReport, HumanReviewRequest
from saga.mode_controller import ModeController, OperationMode
from saga.termination import TerminationChecker, TerminationConfig
from saga.modules.advanced_analyzer import AdvancedAnalyzer
from saga.modules.advanced_planner import AdvancedPlanner
from saga.modules.advanced_implementer import AdvancedImplementer
from saga.modules.advanced_optimizer import AdvancedOptimizer
from saga.search.generators import LLMGenerator, EvoGenerator
from saga.adapters.sglang_adapter import SGLangAdapter

# 設定 logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# =============================================================================
# 測試數據
# =============================================================================

# 隱藏公式: y = x² + 3x - 2
TRUE_FORMULA = "x**2 + 3*x - 2"

DATA_POINTS = [
    (-3, -2),   # (-3)² + 3*(-3) - 2 = 9 - 9 - 2 = -2
    (-2, -4),   # (-2)² + 3*(-2) - 2 = 4 - 6 - 2 = -4
    (-1, -4),   # (-1)² + 3*(-1) - 2 = 1 - 3 - 2 = -4
    (0, -2),    # 0² + 3*0 - 2 = -2
    (1, 2),     # 1² + 3*1 - 2 = 1 + 3 - 2 = 2
    (2, 8),     # 2² + 3*2 - 2 = 4 + 6 - 2 = 8
    (3, 16),    # 3² + 3*3 - 2 = 9 + 9 - 2 = 16
    (4, 26),    # 4² + 3*4 - 2 = 16 + 12 - 2 = 26
]

# 泛化測試點
TEST_X = 5
TEST_Y = 38  # 5² + 3*5 - 2 = 25 + 15 - 2 = 38

# 初始候選猜測 (刻意選擇較差的公式)
INITIAL_CANDIDATES = [
    "2*x",           # 線性，擬合差
    "x + 1",         # 線性，擬合差
    "3*x - 1",       # 線性，擬合較差
    "x*x",           # 缺少線性項和常數項
    "x*x + x",       # 缺少係數調整
]


# =============================================================================
# 評分函數
# =============================================================================

def safe_eval_formula(formula: str, x: float) -> float:
    """安全執行公式計算"""
    try:
        # 移除可能的空白和危險字符
        clean_formula = formula.strip()
        # 只允許基本數學運算
        allowed = {"x": x, "__builtins__": {}}
        return float(eval(clean_formula, allowed))
    except Exception:
        return float('inf')


def calculate_mse(formula: str, data_points: list) -> float:
    """計算均方誤差"""
    if not data_points:
        return float('inf')
    
    errors = []
    for x, y_true in data_points:
        y_pred = safe_eval_formula(formula, x)
        if y_pred == float('inf'):
            return float('inf')
        errors.append((y_pred - y_true) ** 2)
    
    return sum(errors) / len(errors)


def score_formula(formula: str, context: dict = None) -> list:
    """評分函數：擬合精度、簡潔性、泛化能力
    
    Args:
        formula: 候選公式字串
        context: 包含 data_points, test_x, test_y 的上下文
        
    Returns:
        [fit_score, simplicity_score, generalization_score]
    """
    context = context or {}
    data_points = context.get("data_points", DATA_POINTS)
    test_x = context.get("test_x", TEST_X)
    test_y = context.get("test_y", TEST_Y)
    
    # 1. 擬合精度 (權重 0.5)
    mse = calculate_mse(formula, data_points)
    if mse == float('inf'):
        fit_score = 0.0
    else:
        # 使用 sigmoid 函數將 MSE 映射到 [0, 1]
        # MSE=0 → score=1, MSE=100 → score≈0
        fit_score = max(0, 1 - mse / 100)
    
    # 2. 簡潔性 (權重 0.3)
    formula_len = len(formula.strip())
    # 假設最優公式長度約 15 字符 (x**2 + 3*x - 2)
    simplicity_score = max(0, 1 - formula_len / 50)
    
    # 3. 泛化能力 (權重 0.2)
    y_pred_test = safe_eval_formula(formula, test_x)
    if y_pred_test == float('inf'):
        generalization_score = 0.0
    else:
        gen_error = abs(y_pred_test - test_y)
        generalization_score = max(0, 1 - gen_error / 50)
    
    return [fit_score, simplicity_score, generalization_score]


# =============================================================================
# 生成評分程式碼 (動態生成給 sandbox 執行)
# =============================================================================

SCORING_CODE = '''
def score(text: str, context: dict) -> list:
    """評分函數：擬合精度、簡潔性、泛化能力"""
    import math
    
    formula = text.strip()
    data_points = context.get("data_points", [])
    test_x = context.get("test_x", 5)
    test_y = context.get("test_y", 38)
    
    def safe_eval(f, x):
        try:
            return float(eval(f, {"x": x, "math": math, "__builtins__": {}}))
        except:
            return float('inf')
    
    # 1. 擬合精度
    mse = 0
    for x, y_true in data_points:
        y_pred = safe_eval(formula, x)
        if y_pred == float('inf'):
            mse = 100
            break
        mse += (y_pred - y_true) ** 2
    mse /= max(len(data_points), 1)
    fit_score = max(0, 1 - mse / 100)
    
    # 2. 簡潔性
    simplicity_score = max(0, 1 - len(formula) / 50)
    
    # 3. 泛化能力
    y_pred_test = safe_eval(formula, test_x)
    if y_pred_test == float('inf'):
        gen_score = 0.0
    else:
        gen_score = max(0, 1 - abs(y_pred_test - test_y) / 50)
    
    return [fit_score, simplicity_score, gen_score]
'''


# =============================================================================
# 主測試流程
# =============================================================================

async def run_symbolic_regression_test():
    """執行符號回歸整合測試"""
    
    print("=" * 60)
    print("  符號回歸整合測試 - SAGA 多輪目標演化驗證")
    print("=" * 60)
    print()
    print(f"🎯 隱藏公式: {TRUE_FORMULA}")
    print(f"📊 測試數據: {len(DATA_POINTS)} 個點")
    print(f"🔬 泛化測試: x={TEST_X} → y={TEST_Y}")
    print()
    
    # 配置
    config = SagaConfig(
        use_sglang=True,
        use_llm_modules=True,
        beam_width=5,
    )
    
    # 初始化模組
    mode = ModeController(OperationMode.AUTOPILOT)  # 全自動執行
    
    terminator = TerminationChecker(TerminationConfig(
        max_iters=5,
        convergence_eps=0.01,
        convergence_patience=2,
        goal_thresholds={
            "goal_0": 0.95,  # 擬合精度閾值
            "goal_1": 0.5,   # 簡潔性閾值
            "goal_2": 0.9,   # 泛化能力閾值
        }
    ))
    
    analyzer = AdvancedAnalyzer(config={
        "goal_thresholds": {
            "goal_0": 0.95,
            "goal_1": 0.5,
            "goal_2": 0.9,
        },
        "bottleneck_threshold": 0.5
    })
    
    planner = AdvancedPlanner()
    implementer = AdvancedImplementer()
    
    # 初始化 SGLang 適配器
    sglang_url = config.sglang_url or "http://localhost:8082/v1/chat/completions"
    sglang_api_key = config.sglang_api_key or ""
    
    print(f"🔗 SGLang URL: {sglang_url}")
    
    try:
        sglang_client = SGLangAdapter(base_url=sglang_url, api_key=sglang_api_key)
        # 使用 LLM 驅動的生成器
        generator = LLMGenerator(client=sglang_client)
        print("✅ 使用 LLM 驅動的候選生成器")
    except Exception as e:
        logger.warning(f"無法初始化 LLMGenerator: {e}，改用 EvoGenerator")
        generator = EvoGenerator(mutation_rate=0.3, crossover_rate=0.5)
        print("⚠️ 使用進化算法生成器 (Fallback)")
    
    optimizer = AdvancedOptimizer(
        generator=generator,
        config={
            "inner_iterations": 3,
            "batch_size": 8,
            "timeout": 10.0  # LLM 需要較長的超時時間
        }
    )
    
    # 初始狀態
    initial_state = LoopState(
        text=f"找出擬合以下數據點的數學公式: {DATA_POINTS}",
        keywords=["x²", "多項式", "擬合", "二次"],
        constraints=[
            "公式必須是 x 的函數",
            "使用 Python 語法 (例如 x**2 而非 x^2)",
        ],
        candidates=INITIAL_CANDIDATES.copy(),
        weights=[0.5, 0.3, 0.2],  # 擬合、簡潔、泛化
        goal_thresholds={
            "goal_0": 0.95,
            "goal_1": 0.5,
            "goal_2": 0.9,
        }
    )
    
    # 執行外層迴圈
    loop = OuterLoop(
        config=config,
        analyzer=analyzer,
        planner=planner,
        implementer=implementer,
        optimizer=optimizer,
        terminator=terminator,
        mode_controller=mode
    )
    
    print("-" * 60)
    print("開始多輪迭代...")
    print("-" * 60)
    print()
    
    iteration_results = []
    final_report = None
    all_reports = []  # 記錄所有輪次的詳細報告
    
    import json
    from datetime import datetime
    
    async for result in loop.run(initial_state, run_id="symbolic_regression_test"):
        if isinstance(result, IterationResult):
            iteration_results.append(result)
            
            # 計算詳細評分
            scores = score_formula(result.best_candidate, {
                "data_points": DATA_POINTS,
                "test_x": TEST_X,
                "test_y": TEST_Y
            })
            
            # 建立詳細報告
            round_report = {
                "iteration": result.iteration,
                "timestamp": datetime.now().isoformat(),
                "best_candidate": result.best_candidate,
                "best_score": result.best_score,
                "scores": {
                    "fit_accuracy": scores[0],
                    "simplicity": scores[1],
                    "generalization": scores[2]
                },
                "analysis": {
                    "bottleneck": result.analysis_report.bottleneck,
                    "pareto_count": result.analysis_report.pareto_count,
                    "improvement_trend": result.analysis_report.improvement_trend,
                    "suggested_constraints": result.analysis_report.suggested_constraints
                },
                "new_constraints": result.new_constraints,
                "elapsed_ms": result.elapsed_ms
            }
            all_reports.append(round_report)
            
            # 輸出詳細報告
            print("=" * 60)
            print(f"📍 Iteration {result.iteration} 詳細報告")
            print("=" * 60)
            print(f"⏱️  時間戳: {round_report['timestamp']}")
            print(f"⏱️  耗時: {result.elapsed_ms} ms")
            print()
            print(f"🏆 最佳候選: {result.best_candidate}")
            print(f"📊 加權總分: {result.best_score:.4f}")
            print()
            print("📈 詳細評分:")
            print(f"   擬合精度: {scores[0]:.4f} (權重 50%)")
            print(f"   公式簡潔: {scores[1]:.4f} (權重 30%)")
            print(f"   泛化能力: {scores[2]:.4f} (權重 20%)")
            print()
            print("🔍 分析結果:")
            print(f"   瓶頸目標: {result.analysis_report.bottleneck}")
            print(f"   Pareto 數量: {result.analysis_report.pareto_count}")
            print(f"   改善趨勢: {result.analysis_report.improvement_trend:+.2%}")
            
            if result.analysis_report.suggested_constraints:
                print(f"   建議約束: {result.analysis_report.suggested_constraints}")
            
            if result.new_constraints:
                print()
                print("🆕 新增約束:")
                for c in result.new_constraints:
                    print(f"   • {c}")
            
            print()
            print("-" * 60)
            print()
            
        elif isinstance(result, HumanReviewRequest):
            print(f"⏸️  需要人工審核: {result.message}")
            # 在 Autopilot 模式下不應該出現
            
        elif isinstance(result, FinalReport):
            final_report = result
    
    # 輸出最終結果
    print("=" * 60)
    print("  測試結果")
    print("=" * 60)
    print()
    
    if final_report:
        print(f"✅ 終止原因: {final_report.termination_reason}")
        print(f"📊 總迭代數: {final_report.total_iterations}")
        print(f"🏆 最終最佳候選: {final_report.best_candidate}")
        print(f"📈 最終分數: {final_report.best_score:.4f}")
        print(f"⏱️ 總耗時: {final_report.elapsed_ms} ms")
        print()
        
        # 驗證最終公式
        print("📐 公式驗證:")
        final_formula = final_report.best_candidate
        for x, y_true in DATA_POINTS:
            y_pred = safe_eval_formula(final_formula, x)
            status = "✓" if abs(y_pred - y_true) < 0.01 else "✗"
            print(f"   x={x:2d}: 預測={y_pred:6.2f}, 真實={y_true:6.2f} {status}")
        
        # 泛化測試
        y_pred_test = safe_eval_formula(final_formula, TEST_X)
        gen_status = "✓" if abs(y_pred_test - TEST_Y) < 1 else "✗"
        print()
        print(f"🔬 泛化測試: x={TEST_X} → 預測={y_pred_test:.2f}, 真實={TEST_Y} {gen_status}")
        
        # 與真實公式比較
        print()
        print(f"🎯 真實公式: {TRUE_FORMULA}")
        print(f"🤖 發現公式: {final_formula}")
        
        # 判斷成功與否
        final_scores = score_formula(final_formula, {
            "data_points": DATA_POINTS,
            "test_x": TEST_X,
            "test_y": TEST_Y
        })
        
        print()
        if final_scores[0] >= 0.95 and final_scores[2] >= 0.9:
            print("🎉 測試成功！SAGA 成功發現了公式！")
        else:
            print("⚠️ 測試部分成功，公式接近但不完全匹配")
            print(f"   擬合精度: {final_scores[0]:.3f} (需要 ≥ 0.95)")
            print(f"   泛化能力: {final_scores[2]:.3f} (需要 ≥ 0.90)")
    else:
        print("❌ 測試失敗：未獲得最終報告")
    
    return final_report


# =============================================================================
# 簡化版測試 (不依賴完整 OuterLoop)
# =============================================================================

def run_simple_test():
    """簡化版測試 - 直接測試評分函數和演化邏輯"""
    
    print("=" * 60)
    print("  簡化版符號回歸測試")
    print("=" * 60)
    print()
    
    # 測試評分函數
    print("📊 評分函數測試:")
    test_formulas = [
        "2*x",                # 線性
        "x**2",               # 缺少線性項
        "x**2 + 3*x",         # 缺少常數項
        "x**2 + 3*x - 2",     # 正確答案
        "x**2 + 3*x - 1.5",   # 接近正確
    ]
    
    context = {
        "data_points": DATA_POINTS,
        "test_x": TEST_X,
        "test_y": TEST_Y
    }
    
    best_formula = None
    best_total_score = 0
    weights = [0.5, 0.3, 0.2]
    
    for formula in test_formulas:
        scores = score_formula(formula, context)
        total = sum(w * s for w, s in zip(weights, scores))
        mse = calculate_mse(formula, DATA_POINTS)
        
        print(f"  {formula:20s} | MSE={mse:8.2f} | 擬合={scores[0]:.3f} | 簡潔={scores[1]:.3f} | 泛化={scores[2]:.3f} | 總分={total:.3f}")
        
        if total > best_total_score:
            best_total_score = total
            best_formula = formula
    
    print()
    print(f"🏆 最佳公式: {best_formula}")
    print(f"   總分: {best_total_score:.3f}")
    
    # 驗證
    print()
    print("📐 驗證最佳公式:")
    for x, y_true in DATA_POINTS[:4]:
        y_pred = safe_eval_formula(best_formula, x)
        print(f"   x={x:2d}: 預測={y_pred:6.2f}, 真實={y_true:6.2f}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="符號回歸整合測試")
    parser.add_argument("--simple", action="store_true", help="執行簡化版測試")
    args = parser.parse_args()
    
    if args.simple:
        run_simple_test()
    else:
        # 執行完整異步測試
        asyncio.run(run_symbolic_regression_test())
