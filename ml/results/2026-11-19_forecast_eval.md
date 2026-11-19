# HPI forecast backtest 2026-11-19

30 CREA benchmark series (region x type), data through 2026-09.
Rolling origin from 2015-01; ridge refitted at every origin on past examples only (alpha 1.0, not tuned).

| Horizon | Forecasts | Naive MAPE | Seasonal naive MAPE | Ridge MAPE |
|---|---|---|---|---|
| 3 months | 4,140 | 4.21% | 5.00% | 4.28% |
| 6 months | 4,050 | 6.83% | 7.79% | 7.08% |

Origins from 2022-01 (the peak and the fall after it):

| Horizon | Naive MAPE | Seasonal naive MAPE | Ridge MAPE |
|---|---|---|---|
| 3 months | 4.00% | 6.30% | 5.08% |
| 6 months | 6.01% | 9.88% | 8.78% |
