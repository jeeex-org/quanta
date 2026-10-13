# Quanta Status Dashboard (AUTO-GENERATED)

Generated at **2026-10-13T21:35:11Z** (epoch 1791927311) by `scripts/regen_status.sh`.
Freshness is enforced by the gate's verify-status stage
(`test_suites/scripts/verify_status.quanta`, threshold 30 days) --
run `bash scripts/regen_status.sh` to refresh.

## SI / roadmap delivery

| metric | value |
|---|---|
| gap_specs specs | 9011 |
| distinct domains | 97 |
| distinct categories | 2159 |
| distinct modules named | 5499 |
| modules delivered in lib/std | 22 |
| delivery ratio | 0.4% |
| lib/std real modules | 165 |
| test_suites/codes tests | 619 |
| planned/ module stubs | 9237 |
| planned/ generated tests | 16861 |
| planned/INDEX.tsv rows | 26098 |

## SI pipeline modules

| module | file | lines | present |
|---|---|---|---|
| std/spec_parser | lib/std/spec_parser.quanta | 187 | yes |
| std/spec_to_ir | lib/std/spec_to_ir.quanta | 193 | yes |
| std/pattern_library | lib/std/pattern_library.quanta | 105 | yes |
| std/code_synthesizer | lib/std/code_synthesizer.quanta | 298 | yes |
| std/test_generator | lib/std/test_generator.quanta | 262 | yes |
| std/si_main | lib/std/si_main.quanta | 109 | yes |

## Genuinely missing stdlib targets

- `std/net/http` -- MISSING
- `std/jsonrpc` -- MISSING
- `std/lsp` -- MISSING
- `std/html_parser` -- MISSING
- `std/graphics` -- MISSING

## Delivery by domain (top 15 by spec count)

| domain | specs | delivered | % |
|---|---|---|---|
| programming_language | 596 | 20 | 3.4% |
| countries | 360 | 0 | 0.0% |
| investment | 244 | 1 | 0.4% |
| airlines | 169 | 6 | 3.6% |
| advertising | 168 | 12 | 7.1% |
| insurance_industry | 162 | 3 | 1.9% |
| chemicals_industry | 159 | 0 | 0.0% |
| accounting | 149 | 3 | 2.0% |
| logistics | 149 | 11 | 7.4% |
| manufacturing | 146 | 0 | 0.0% |
| defense | 139 | 2 | 1.4% |
| entertainment | 134 | 0 | 0.0% |
| tobacco | 134 | 0 | 0.0% |
| construction | 130 | 0 | 0.0% |
| real_estate | 129 | 0 | 0.0% |
