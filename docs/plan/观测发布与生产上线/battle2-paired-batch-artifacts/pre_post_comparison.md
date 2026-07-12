| 指标 | PRE | POST | Δ相对 |
|---|---|---|---|
| TTFT tutorbot.llm.stream p50 (ms) | 1378.0 | 1293.0 | -6.2% |
| TTFT tutorbot.llm.stream p95 (ms) | 2216.0 | 3518.0 | +58.8% |
| TTFT llm.stream p50 (ms) | 5399.0 | 5453.0 | +1.0% |
| TTFT llm.stream p95 (ms) | 10219.0 | 9459.0 | -7.4% |
| TTFVT mean content.delta (ms, prom) | 5301.7 | 4601.6 | -13.2% |
| TTFVT count (prom delta) | 41 | 41 | +0.0% |
| Generations/trace avg | 2.39 | 2.10 | -12.1% |
| Generations/trace p95 | 4 | 3 | -25.0% |
| Token input | 622870 | 443341 | -28.8% |
| Token output | 35847 | 30907 | -13.8% |
| Cost ($) | 0.6811 | 0.4923 | -27.7% |
| Trace duration main p50 (ms) | 23159.0 | 15409.0 | -33.5% |
| Trace duration main p95 (ms) | 34750.0 | 27114.0 | -22.0% |
| Summary-maintainer gen calls | 0 | 0 | n/a |
| Summary-maintainer tokens | 0 | 0 | n/a |
| Client wall main p50 (ms) | 9578.2 | 8903.4 | -7.0% |
| Client wall main p95 (ms) | 17201.0 | 15477.7 | -10.0% |
| Sentinel wall p50 (ms) | 6391.4 | 4398.7 | -31.2% |
| Sentinel TTFT p50 (ms, langfuse) | 1539.0 | 1816.0 | +18.0% |
| Sentinel TTFT p95 (ms, langfuse) | 3931.0 | 4925.0 | +25.3% |
| Main TTFT p50 (ms, langfuse) | 4524.0 | 3301.0 | -27.0% |
| Main TTFT p95 (ms, langfuse) | 9845.0 | 9459.0 | -3.9% |

## 分桶 TTFVT (content.delta, prom delta)
| 桶 | PRE | POST |
|---|---|---|
| ≤500ms | 0 | 0 |
| ≤1000ms | 2 | 3 |
| ≤2000ms | 6 | 8 |
| ≤4000ms | 22 | 27 |
| ≤8000ms | 34 | 35 |
| ≤16000ms | 38 | 39 |
| ≤32000ms | 41 | 41 |
| ≤64000ms | 41 | 41 |
| ≤+Infms | 41 | 41 |

## 可证伪判定
- TTFVT 均值变化: 5302 -> 4602 ms (-13.2%) => 恶化>10%? **否,未触发**
- 哨兵 TTFT p50 漂移: 1539 -> 1816 ms (+18.0%) => >30%? **否,无漂移混淆**
- 哨兵客户端墙钟 p50 漂移: 6391 -> 4399 ms (-31.2%) => >30%? **是**
