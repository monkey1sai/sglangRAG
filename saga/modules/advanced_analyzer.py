"""
Advanced Analyzer module for SAGA data-driven decision feedback.

Generates comprehensive analysis reports with:
- Score distribution statistics
- Goal achievement rates
- Pareto front analysis
- Improvement trends
- Bottleneck identification
- Suggested constraints
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional
import statistics

from saga.search.generators import AnalysisReport

logger = logging.getLogger(__name__)


@dataclass
class ReportRow:
    """Single row in the analysis report table."""
    metric: str
    value: str
    status: str  # "good", "warning", "critical"
    trend: str   # "↑", "↓", "→"


class AdvancedAnalyzer:
    """Advanced analyzer with comprehensive data-driven feedback.
    
    Analyzes current optimization state and generates detailed reports
    to guide the Planner's objective weight adjustments.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize analyzer with optional configuration.
        
        Args:
            config: Configuration dict with thresholds and settings
        """
        self.config = config or {}
        self.goal_thresholds = self.config.get("goal_thresholds", {})
        self.bottleneck_threshold = self.config.get("bottleneck_threshold", 0.5)
        self._previous_report: Optional[AnalysisReport] = None
        
        logger.info(f"[AdvancedAnalyzer] Initialized with config: {self.config}")
    
    def run(self, state: Dict[str, Any] | Any) -> Dict[str, Any]:
        """Analyze current state and generate report data.
        
        Args:
            state: Current loop state (dict or LoopState object)
            
        Returns:
            Dictionary with all analysis metrics
        """
        logger.info("[AdvancedAnalyzer] Starting analysis...")
        
        # Helper to safely retrieve attributes from dict or object
        def get_val(obj, key, alt_key=None, default=None):
            val = default
            if isinstance(obj, dict):
                val = obj.get(key, obj.get(alt_key) if alt_key else default)
            else:
                val = getattr(obj, key, getattr(obj, alt_key, default) if alt_key else default)
            return val

        candidates = get_val(state, "candidates", default=[])
        # Try 'current_scores' (LoopState) then 'scores' (legacy dict)
        scores = get_val(state, "current_scores", "scores", [])
        weights = get_val(state, "weights", default=[])
        iteration = get_val(state, "iteration", default=0)
        
        # Calculate score distribution per dimension
        score_distribution = self._calculate_score_distribution(scores)
        
        # Calculate goal achievement rates
        goal_achievement = self._calculate_goal_achievement(scores, weights)
        
        # Find Pareto optimal candidates
        pareto_count = self._count_pareto_optimal(scores)
        
        # Calculate improvement trend
        improvement_trend = self._calculate_improvement_trend(scores)
        
        # Identify bottleneck objective
        bottleneck = self._identify_bottleneck(score_distribution, goal_achievement)
        
        # Suggest new constraints based on analysis
        suggested_constraints = self._suggest_constraints(
            score_distribution, goal_achievement, bottleneck
        )
        
        result = {
            "score_distribution": score_distribution,
            "goal_achievement": goal_achievement,
            "pareto_count": pareto_count,
            "improvement_trend": improvement_trend,
            "bottleneck": bottleneck,
            "suggested_constraints": suggested_constraints,
            "iteration": iteration,
            "candidate_count": len(candidates),
            "report_table": self._generate_report_table(
                score_distribution, goal_achievement, pareto_count, 
                improvement_trend, bottleneck
            )
        }
        
        logger.info(
            f"[AdvancedAnalyzer] Analysis complete: "
            f"pareto={pareto_count}, bottleneck={bottleneck}, trend={improvement_trend:.2%}"
        )
        
        return result
    
    def _calculate_score_distribution(
        self, scores: List[List[float]]
    ) -> Dict[str, Dict[str, float]]:
        """Calculate statistics for each score dimension."""
        if not scores or not scores[0]:
            return {}
        
        num_dims = len(scores[0])
        distribution = {}
        
        for dim in range(num_dims):
            dim_scores = [s[dim] for s in scores if len(s) > dim]
            if dim_scores:
                distribution[f"dim_{dim}"] = {
                    "min": min(dim_scores),
                    "max": max(dim_scores),
                    "avg": statistics.mean(dim_scores),
                    "std": statistics.stdev(dim_scores) if len(dim_scores) > 1 else 0
                }
        
        return distribution
    
    def _calculate_goal_achievement(
        self, scores: List[List[float]], weights: List[float]
    ) -> Dict[str, float]:
        """Calculate achievement rate for each goal."""
        if not scores:
            return {}
        
        achievement = {}
        thresholds = self.goal_thresholds or {}
        
        for i, weight in enumerate(weights):
            goal_name = f"goal_{i}"
            
            # Helper to get threshold
            threshold = 0.7
            if isinstance(thresholds, dict):
                threshold = thresholds.get(goal_name, 0.7)
            elif isinstance(thresholds, list):
                if i < len(thresholds):
                    threshold = thresholds[i]
            
            dim_scores = [s[i] for s in scores if len(s) > i]
            if dim_scores:
                achieved_count = sum(1 for s in dim_scores if s >= threshold)
                achievement[goal_name] = achieved_count / len(dim_scores)
        
        return achievement
    
    def _count_pareto_optimal(self, scores: List[List[float]]) -> int:
        """Count candidates on the Pareto front."""
        if not scores:
            return 0
        
        pareto_count = 0
        for i, s1 in enumerate(scores):
            is_dominated = False
            for j, s2 in enumerate(scores):
                if i != j and self._dominates(s2, s1):
                    is_dominated = True
                    break
            if not is_dominated:
                pareto_count += 1
        
        return pareto_count
    
    def _dominates(self, s1: List[float], s2: List[float]) -> bool:
        """Check if s1 Pareto-dominates s2 (all >= and at least one >)."""
        better_in_at_least_one = False
        for v1, v2 in zip(s1, s2):
            if v1 < v2:
                return False
            if v1 > v2:
                better_in_at_least_one = True
        return better_in_at_least_one
    
    def _calculate_improvement_trend(self, scores: List[List[float]]) -> float:
        """Calculate improvement trend compared to previous analysis."""
        if not scores:
            return 0.0
        
        current_avg = statistics.mean([sum(s) / len(s) for s in scores if s])
        
        if self._previous_report and self._previous_report.raw_data:
            prev_scores = self._previous_report.raw_data.get("scores", [])
            if prev_scores:
                prev_avg = statistics.mean([sum(s) / len(s) for s in prev_scores if s])
                return (current_avg - prev_avg) / max(prev_avg, 0.001)
        
        return 0.0
    
    def _identify_bottleneck(
        self, 
        score_distribution: Dict[str, Dict[str, float]],
        goal_achievement: Dict[str, float]
    ) -> str:
        """Identify the most difficult objective to achieve."""
        if not goal_achievement:
            return "unknown"
        
        # Find goal with lowest achievement rate
        min_achievement = 1.0
        bottleneck = "unknown"
        
        for goal, rate in goal_achievement.items():
            if rate < min_achievement:
                min_achievement = rate
                bottleneck = goal
        
        return bottleneck
    
    def _suggest_constraints(
        self,
        score_distribution: Dict[str, Dict[str, float]],
        goal_achievement: Dict[str, float],
        bottleneck: str
    ) -> List[str]:
        """Suggest new constraints based on analysis."""
        suggestions = []
        
        # Suggest constraint for bottleneck
        if bottleneck != "unknown":
            achievement = goal_achievement.get(bottleneck, 0)
            if achievement < self.bottleneck_threshold:
                suggestions.append(f"Increase weight for {bottleneck} (current achievement: {achievement:.1%})")
        
        # Suggest constraint for high variance dimensions
        for dim, stats in score_distribution.items():
            if stats.get("std", 0) > 0.3:
                suggestions.append(f"High variance in {dim} (std={stats['std']:.3f}), consider adding regularization")
        
        # Suggest constraint if Pareto front too small
        # (This would need pareto_count passed in, simplified for now)
        
        return suggestions
    
    def _generate_report_table(
        self,
        score_distribution: Dict[str, Dict[str, float]],
        goal_achievement: Dict[str, float],
        pareto_count: int,
        improvement_trend: float,
        bottleneck: str
    ) -> List[Dict[str, str]]:
        """Generate structured report table for UI display."""
        rows = []
        
        # Overall metrics
        rows.append(asdict(ReportRow(
            metric="Pareto 前沿數量",
            value=str(pareto_count),
            status="good" if pareto_count >= 3 else "warning",
            trend="→"
        )))
        
        rows.append(asdict(ReportRow(
            metric="改善趨勢",
            value=f"{improvement_trend:+.1%}",
            status="good" if improvement_trend > 0 else ("critical" if improvement_trend < -0.05 else "warning"),
            trend="↑" if improvement_trend > 0 else ("↓" if improvement_trend < 0 else "→")
        )))
        
        rows.append(asdict(ReportRow(
            metric="瓶頸目標",
            value=bottleneck,
            status="warning" if bottleneck != "unknown" else "good",
            trend="→"
        )))
        
        # Goal achievements
        for goal, rate in goal_achievement.items():
            rows.append(asdict(ReportRow(
                metric=f"{goal} 達成率",
                value=f"{rate:.1%}",
                status="good" if rate >= 0.8 else ("warning" if rate >= 0.5 else "critical"),
                trend="→"
            )))
        
        # Score distributions
        for dim, stats in score_distribution.items():
            rows.append(asdict(ReportRow(
                metric=f"{dim} 平均",
                value=f"{stats['avg']:.3f}",
                status="good" if stats['avg'] >= 0.7 else "warning",
                trend="→"
            )))
        
        return rows
    
    def save_previous_report(self, report: AnalysisReport) -> None:
        """Save report for trend comparison in next iteration."""
        self._previous_report = report
