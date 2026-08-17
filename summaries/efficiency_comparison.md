

## Improvement 3b — Inference efficiency (quantization comparison)

| Quantization | Accuracy (n=20 subset) | Avg latency/query |
|---|---|---|
| Q4 (default) | 11/20 = 55.0% | 2.42s |
| Q8 | 11/20 = 55.0% | 3.77s |

**Finding:** identical accuracy, but Q4 is ~36% faster per query. The default quantization choice
made back in Phase 0 (for VRAM headroom on the T4) costs nothing in accuracy while being
meaningfully faster -- a clean, positive efficiency result. fp16 was excluded from this comparison
(would need ~14-15GB, leaving almost no VRAM headroom on a 15.6GB T4 and risking the same
instability fought throughout this project).
