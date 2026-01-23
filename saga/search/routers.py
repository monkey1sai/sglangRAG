"""
Prompt Router for SAGA Generator.

Decides which prompt strategy to use based on the task context (keywords, data type).
Implements the "Code Review Router" pattern: routing tasks to the most appropriate
reasoning model (e.g. Math/Logic vs. General/Creative).
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import List, Optional
from dataclasses import dataclass

from saga.search.generators import AnalysisReport

logger = logging.getLogger(__name__)

class PromptStrategy(ABC):
    """Abstract base class for prompt generation strategies."""
    
    @abstractmethod
    def build_prompt(self, population: List[str], feedback: AnalysisReport, num: int) -> str:
        """Build the prompt for the specific strategy."""
        pass
    
    @abstractmethod
    def parse_candidates(self, raw_output: str, expected: int) -> List[str]:
        """Parse the LLM output into candidates."""
        pass


class GeneralStrategy(PromptStrategy):
    """Original SAGA prompt strategy with full analysis context."""
    
    def build_prompt(self, population: List[str], feedback: AnalysisReport, num: int) -> str:
        top_candidates = population[:3] if len(population) >= 3 else population
        
        return f"""你是一個科學發現助手。基於以下分析反饋，請生成 {num} 個改進的候選方案。

## 當前最佳候選
{chr(10).join(f'- {c}' for c in top_candidates)}

## 分析反饋
- 瓶頸目標: {feedback.bottleneck}
- 改善趨勢: {feedback.improvement_trend:.2%}
- 建議: {', '.join(feedback.suggested_constraints) if feedback.suggested_constraints else '無'}

## 要求
請生成 {num} 個新候選，每行一個，專注於改善瓶頸目標。
格式：
CANDIDATE: <候選內容>
"""

    def parse_candidates(self, raw_output: str, expected: int) -> List[str]:
        candidates = []
        for line in raw_output.split("\n"):
            if line.strip().startswith("CANDIDATE:"):
                content = line.split("CANDIDATE:", 1)[1].strip()
                if content:
                    candidates.append(content)
        return candidates[:expected]


class MathStrategy(PromptStrategy):
    """Codex-style strategy for Math/Symbolic Regression tasks.
    
    Focuses on raw data patterns and formula simplicity. 
    Removes bureaucratic meta-data.
    """
    
    def build_prompt(self, population: List[str], feedback: AnalysisReport, num: int) -> str:
        top = population[0] if population else ""
        
        # Robust data detection
        is_data = False
        dataset_str = "[(0,0), (1,1)] # Default"
        current_formula = top
        
        # If 'top' looks like a list of points (contains typical data structure)
        if top and top.count("(") > 1 and top.count(",") > 2:
             dataset_str = top
             current_formula = "y = 0.0 * x  # Initial placeholder"
             is_data = True
        elif not top:
             current_formula = "y = 0.0 * x"

        # Construct Feedback Message (The "Communication" part)
        feedback_msg = "No feedback yet."
        if feedback:
            feedback_msg = f"""
- Current Score Impact: {feedback.improvement_trend:.2%} improvement
- Bottleneck: {feedback.bottleneck} (This metric needs work!)
- Reviewer Suggestion: {', '.join(feedback.suggested_constraints)}
"""

        prompt = f"""You are a Mathematical Reasoning Agent participating in an evolutionary code review loop.

# PROJECT CONTEXT
We are trying to find a python formula `y = f(x)` that fits the following dataset:
{dataset_str}

# CURRENT STATUS
**Current Best Formula**: `{current_formula}`
**Reviewer Feedback**:
{feedback_msg}

# YOUR MISSION
Communicate with the Reviewer by proposing {num} BETTER formulas.
1. **Analyze the Feedback**: If the previous formula failed (e.g. error too high), hypothesize why (e.g. "needs quadratic term", "coefficient too small").
2. **Iterate**: Propose variations. 
   - If current is `x`, try `x**2`. 
   - If current is `x**2`, try `x**2 + x`.
3. **Format**: Output valid Python expressions only.

# PROPOSAL FORMAT
FORMULA: <expression>

# EXAMPLES
dataset: [(1,1), (2,4), (3,9)] -> FORMULA: x**2
dataset: [(1,3), (2,5), (3,7)] -> FORMULA: 2*x + 1

# YOUR TURN (Propose {num} formulas):
"""
        return prompt

    def parse_candidates(self, raw_output: str, expected: int) -> List[str]:
        import re
        candidates = []
        # Strict regex: allow numbers, x, operators, parens, equals, spaces, and math functions
        # Reject anything with Chinese, or alphabets other than valid math tokens
        allowed_pattern = re.compile(r"^[0-9a-zA-Z\.\+\-\*\/\(\)\,\=\s\_]+$")
        
        for line in raw_output.split("\n"):
            clean = line.strip()
            content = ""
            
            if clean.startswith("FORMULA:"):
                content = clean.split("FORMULA:", 1)[1].strip()
            # Allow "Communication" style output where LLM might say "Try adding x: ..."
            elif ":" in clean and "x" in clean:
                 parts = clean.split(":")
                 potential = parts[-1].strip()
                 if any(op in potential for op in ["+", "-", "*", "/", "**"]):
                     content = potential
            
            if content:
                # 1. Sanity Check: Length and Garbage
                if content.count(",") > 3 or content.count("(") > 4 or len(content) > 100:
                    continue
                
                # 2. Strict Character Check (Anti-Hallucination Firewall)
                if not allowed_pattern.match(content):
                    logger.warning(f"[MathStrategy] Filtered invalid content: {content}")
                    continue
                
                # 3. Block common non-math words just in case regex allows letters
                if any(word in content.lower() for word in ["improve", "adjust", "formula", "candidate", "改進", "調整", "optimized"]):
                    continue
                    
                candidates.append(content)
        
        logger.info(f"[MathStrategy] Parsed {len(candidates)} valid formulas from LLM response.")
        return candidates[:expected]


class PromptRouter:
    """Routes tasks to the appropriate prompt strategy."""
    
    def __init__(self):
        self._strategies = {
            "general": GeneralStrategy(),
            "math": MathStrategy()
        }
    
    def get_strategy(self, keywords: List[str]) -> PromptStrategy:
        """Select strategy based on keywords."""
        math_keywords = ["formula", "equation", "regression", "symbolic", "math", "擬合", "公式", "回歸", "多項式", "x²"]
        
        if any(k in keywords for k in math_keywords):
            logger.info("[PromptRouter] Selected Strategy: MATH (Codex Mode)")
            return self._strategies["math"]
        
        logger.info("[PromptRouter] Selected Strategy: GENERAL")
        return self._strategies["general"]
