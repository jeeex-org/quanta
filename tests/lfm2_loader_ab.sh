#!/usr/bin/env bash
# Paired pre/post A/B for the loader-redundancy unit. Both binaries are from the
# SAME source tree except lib/std/lfm2_forward.quanta + lib/std/gguf_mm.quanta:
#   /tmp/bench_pre.bin   = HEAD (git show HEAD:lib/std/...)
#   /tmp/bench_post.bin  = HEAD + (1) fc_cache_norms also caches attn_q_norm /
#                               attn_k_norm per layer
#                               (2) the y=0 pre-fill removed, replaced by the
#                                   pool worker error channel in pl_submit
# Arms alternate pre,post,post,pre so ambient drift is a paired confound.
set -u
cd /opt/tali/quanta || exit 2
CONF=tests/lfm2_decode_bench.conf
LOGD=/home/tali/.hermes/cache/scratch/lfm2prof/logs
printf '20 128 128 128 1 1 1 1 1 0 0 1 1 1 1\n' > "$CONF"
echo "conf: $(cat $CONF)"
echo "qc: $PWD/compiler/0.0.248/bin/x86/qc md5 $(md5sum compiler/0.0.248/bin/x86/qc | cut -d" " -f1)"
for arm in pre post post pre; do
  log="$LOGD/mine_ab_${arm}.log"
  echo "=== arm=$arm start $(date '+%F %T') load=$(cut -d' ' -f1 /proc/loadavg) ==="
  ( ulimit -c 0 -v 32000000; timeout 3600 nice -n 0 /tmp/bench_$arm.bin </dev/null ) > "$log" 2>&1
  echo "rc=$? end $(date '+%F %T') load=$(cut -d' ' -f1 /proc/loadavg)"
  grep -E "^conf:|fused_.*_active|fused_.*_used|tok_per_s_x1000|gen_tokens|first_argmax_id|ms_per_token|vmpeak_kb_start|^rss@128|anon_kb_start" "$log" | head -40
  echo
done
printf '20 128 512 1024 1 1 1 0 0\n' > "$CONF"
echo "restored conf: $(cat $CONF)"
echo DONE
