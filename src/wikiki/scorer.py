from .rules import Flag


class TensionScorer:
    def calculate(self, flags: list[Flag]) -> float:
        return min(sum(f.weight for f in flags) * 100, 100.0)

    def to_status(self, score: float) -> str:
        if score < 25:
            return "calm"
        if score < 50:
            return "elevated"
        if score < 75:
            return "tense"
        return "critical"
