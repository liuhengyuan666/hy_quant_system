from __future__ import annotations

try:
    import backtrader as bt
except Exception:
    bt = None


if bt is not None:

    class MovingAverageCrossStrategy(bt.Strategy):
        params = (("fast", 20), ("slow", 60))

        def __init__(self):
            self.fast_ma = bt.indicators.SimpleMovingAverage(self.data.close, period=self.p.fast)
            self.slow_ma = bt.indicators.SimpleMovingAverage(self.data.close, period=self.p.slow)
            self.cross = bt.indicators.CrossOver(self.fast_ma, self.slow_ma)

        def next(self):
            if not self.position and self.cross > 0:
                self.buy()
            elif self.position and self.cross < 0:
                self.close()

else:

    class MovingAverageCrossStrategy:
        pass
