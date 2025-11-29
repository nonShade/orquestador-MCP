# orchestrator/fuse.py
import logging
from typing import List, Dict, Any, Optional, Tuple
from orchestrator.schemas import DecisionType, Identity, Candidate

logger = logging.getLogger(__name__)


class FusionEngine:
    """
    Identity fusion engine that combines PP2 results using threshold and margin logic
    """

    def __init__(self, threshold: float = 0.75, margin: float = 0.2):
        """
        Initialize fusion engine with threshold (τ) and margin (δ) parameters

        Args:
            threshold: Minimum score required for positive identification
            margin: Maximum difference allowed between top scores for "identified" decision
        """
        self.threshold = threshold
        self.margin = margin

    def fuse_results(self, pp2_results: List[Dict[str, Any]]) -> Tuple[DecisionType, Optional[Identity], List[Candidate]]:
        """
        Fuse PP2 results into a single identity decision

        Args:
            pp2_results: List of PP2 service responses

        Returns:
            Tuple of (decision, identity, candidates)
        """
        if not pp2_results:
            logger.warning("No PP2 results to fuse")
            return DecisionType.UNKNOWN, None, []

        valid_responses = []
        for result in pp2_results:
            if "error" not in result and "is_me" in result:
                valid_responses.append(result)

        if not valid_responses:
            logger.warning("No valid PP2 responses to fuse")
            return DecisionType.UNKNOWN, None, []

        candidates = []
        for response in valid_responses:
            candidate = Candidate(
                name=response.get("name", response.get("service", "Unknown")),
                score=response.get("score", 0.0)
            )
            candidates.append(candidate)

        candidates.sort(key=lambda x: x.score, reverse=True)

        logger.info(f"Fusion engine processing {len(candidates)} candidates")
        logger.debug(f"Top candidates: {
                     [(c.name, c.score) for c in candidates[:3]]}")

        decision, identity = self._apply_fusion_rules(candidates)

        logger.info(f"Fusion decision: {decision.value}")
        if identity:
            logger.info(f"Identified as: {
                        identity.name} (score: {identity.score})")

        return decision, identity, candidates

    def _apply_fusion_rules(self, candidates: List[Candidate]) -> Tuple[DecisionType, Optional[Identity]]:
        """
        Apply fusion rules based on threshold (τ) and margin (δ)

        Rules:
        1. UNKNOWN: No candidate meets threshold OR all scores are very low
        2. IDENTIFIED: Top candidate meets threshold AND has clear margin over second
        3. AMBIGUOUS: Multiple candidates meet threshold OR margin too small
        """
        if not candidates:
            return DecisionType.UNKNOWN, None

        top_candidate = candidates[0]
        second_candidate = candidates[1] if len(candidates) > 1 else None

        if top_candidate.score < self.threshold:
            logger.debug(f"Top score {top_candidate.score} below threshold {
                         self.threshold}")
            return DecisionType.UNKNOWN, None

        if second_candidate is None or second_candidate.score < self.threshold:
            identity = Identity(name=top_candidate.name,
                                score=top_candidate.score)
            return DecisionType.IDENTIFIED, identity

        score_difference = top_candidate.score - second_candidate.score

        if score_difference >= self.margin:
            identity = Identity(name=top_candidate.name,
                                score=top_candidate.score)
            return DecisionType.IDENTIFIED, identity
        else:
            logger.debug(f"Ambiguous: top scores too close ({
                         score_difference} < {self.margin})")
            return DecisionType.AMBIGUOUS, None

    def get_summary_stats(self, candidates: List[Candidate]) -> Dict[str, Any]:
        """
        Get summary statistics for the fusion process
        """
        if not candidates:
            return {
                "total_candidates": 0,
                "above_threshold": 0,
                "max_score": 0.0,
                "avg_score": 0.0,
                "score_spread": 0.0
            }

        scores = [c.score for c in candidates]
        above_threshold_count = sum(
            1 for score in scores if score >= self.threshold)

        return {
            "total_candidates": len(candidates),
            "above_threshold": above_threshold_count,
            "max_score": max(scores),
            "avg_score": sum(scores) / len(scores),
            "score_spread": max(scores) - min(scores) if len(scores) > 1 else 0.0,
            "threshold_used": self.threshold,
            "margin_used": self.margin
        }


def load_fusion_config(threshold: Optional[float] = None, margin: Optional[float] = None) -> FusionEngine:
    """
    Load fusion engine with configuration from environment or defaults
    """
    import os

    tau = threshold if threshold is not None else float(
        os.getenv("THRESHOLD", "0.75"))
    delta = margin if margin is not None else float(os.getenv("MARGIN", "0.2"))

    logger.info(f"Fusion engine configured with τ={tau}, δ={delta}")
    return FusionEngine(threshold=tau, margin=delta)
