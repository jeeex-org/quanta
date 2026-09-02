# Quanta 0.0.132 — json stdlib (AI/data interchange), DONE

## Summary
Added `lib/std/json.quanta`, imported via `import std/json`. Provides JSON parse +
stringify with a tagged heap-node representation.

## Design
- JSON value = heap node (3 i64 words via mem_alloc): [0]=kind, [1]=payload, [2]=reserved.
  kind: 0=null,1=bool,2=number,3=string,4=array,5=object
- Arrays: std/vec of i64 node-handles. Objects: std/map (string key -> i64 node-handle).
- Parse state via globals _js_src/_js_pos/_js_len (single-threaded).
- Public API: json_parse(s)->node, json_stringify(j)->string,
  json_kind/json_bool/json_num/json_str/json_arr/json_obj.

## Verification (real)
- Fixpoint: gen2==gen3 = 8e1bb23fc7e626ee4b8513dc690197c1 (self-host clean).
- std_json_test.quanta rc=0 (24 assertions): object/array/nested-object parse,
  kind + value accessors, stringify round-trip re-parse, scalars true/false/null,
  escape handling (\n -> byte 10).
- Gate: functional 163/163, stdlib 8/8, multi-TU 3/3, all 11 layers GREEN.

## Next core
0.0.133 — secure (TLS 1.3 + hybrid X25519/ML-KEM PQC)
