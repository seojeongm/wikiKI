from .rules import Flag


class TensionScorer:
    def calculate(self, flags: list[Flag]) -> float:
        return min(sum(f.weight for f in flags) * 100, 100.0)
