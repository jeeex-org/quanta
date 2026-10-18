# scripts/bench.sh — Quanta 0.0.247 vs gcc -O2 — 2026-10-18T12:41:01+08:00
# runs/side: 3 (best of, alternating) · load: 10.21, 9.68, 10.39

| case | Quanta | gcc -O2 | ratio | notes |
|---|---|---|---|---|
| benchmark_arith | 156 ms | 13 ms | 12.00x | best-of-15 (<30ms row) |
| benchmark_big_array | 6 ms | 6 ms | 1.00x | best-of-15 (<30ms row) |
| benchmark_closure_call | 15 ms | 8 ms | 1.88x | best-of-15 (<30ms row) |
| benchmark_closure_capture | 16 ms | 8 ms | 2.00x | best-of-15 (<30ms row) |
| benchmark_div_const | 82 ms | 9 ms | 9.11x | best-of-15 (<30ms row) |
| benchmark_enum | 6 ms | 6 ms | 1.00x | best-of-15 (<30ms row) |
| benchmark_fib | 6 ms | 6 ms | 1.00x | best-of-15 (<30ms row) |
| benchmark_fib_recursive | 21 ms | 8 ms | 2.62x | best-of-15 (<30ms row) |
| benchmark_file_io | 6 ms | 7 ms | 0.86x | best-of-15 (<30ms row) |
| benchmark_fileio | 73 ms | 21 ms | 3.48x | best-of-15 (<30ms row) |
| benchmark_float | 95 ms | 17 ms | 5.59x | best-of-15 (<30ms row) |
| benchmark_float_ops | 6 ms | 7 ms | 0.86x | best-of-15 (<30ms row) |
| benchmark_fnptr_indirect | 20 ms | 8 ms | 2.50x | best-of-15 (<30ms row) |
| benchmark_generic_call | 16 ms | 7 ms | 2.29x | best-of-15 (<30ms row) |
| benchmark_heavy_div | 55 ms | 7 ms | 7.86x | best-of-15 (<30ms row) |
| benchmark_heavy_div2 | 497 ms | 23 ms | 21.61x | best-of-15 (<30ms row) |
| benchmark_heavy_float | 69 ms | 12 ms | 5.75x | best-of-15 (<30ms row) |
| benchmark_heavy_float2 | 370 ms | 41 ms | 9.02x |  |
| benchmark_heavy_int | 286 ms | 18 ms | 15.89x | best-of-15 (<30ms row) |
| benchmark_heavy_int2 | 1264 ms | 53 ms | 23.85x |  |
| benchmark_heavy_mem | 18 ms | 9 ms | 2.00x | best-of-15 (<30ms row) |
| benchmark_heavy_recursion | 9 ms | 6 ms | 1.50x | best-of-15 (<30ms row) |
| benchmark_higher_order | 16 ms | 7 ms | 2.29x | best-of-15 (<30ms row) |
| benchmark_int_ops | 6 ms | 6 ms | 1.00x | best-of-15 (<30ms row) |
| benchmark_loop_sum | 10 ms | 6 ms | 1.67x | best-of-15 (<30ms row) |
| benchmark_match | 5 ms | 5 ms | 1.00x | best-of-15 (<30ms row) |
| benchmark_mem | 19 ms | 10 ms | 1.90x | best-of-15 (<30ms row) |
| benchmark_mem_ops | 8 ms | 8 ms | 1.00x | best-of-15 (<30ms row) |
| benchmark_mutual_recursion | 439 ms | 73 ms | 6.01x |  |
| benchmark_nested_calls | 6 ms | 7 ms | 0.86x | best-of-15 (<30ms row) |
| benchmark_params8 | 21 ms | 8 ms | 2.62x | best-of-15 (<30ms row) |
| benchmark_q4k | 7 ms | 8 ms | 0.88x | best-of-15 (<30ms row) |
| benchmark_q4k_heavy | 18 ms | 8 ms | 2.25x | best-of-15 (<30ms row) |
| benchmark_q4k_matmul | 6 ms | 6 ms | 1.00x | best-of-15 (<30ms row) |
| benchmark_recursion | 8 ms | 6 ms | 1.33x | best-of-15 (<30ms row) |
| benchmark_regpressure | 69 ms | 12 ms | 5.75x | best-of-15 (<30ms row) |
| benchmark_string | 6 ms | 7 ms | 0.86x | best-of-15 (<30ms row) |
| benchmark_struct | 6 ms | 6 ms | 1.00x | best-of-15 (<30ms row) |
# load after: 9.42, 9.51, 10.29
# gates that must stay green with any codegen change: functional suite + SELFHOST 7/7
# OK: every row compiled and every C twin kept its loop.
