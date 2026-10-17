#!/usr/bin/env bash
# Measurement driver for the folded Q6_K route: Q4_K-only vs Q4_K+Q6_K.
# Sequential and exclusive -- the box is a shared, load-sensitive resource.
# Conf fields: workers len1 len2 len3 use_mmap cache_norms ignore_eos fused_q4k fused_q6k
set -u
cd /opt/tali/quanta || exit 2
BIN=/tmp/lfm2_decode_bench.bin
CONF=tests/lfm2_decode_bench.conf

if [ ! -x "$BIN" ]; then echo "no bench bin"; exit 2; fi

# discipline: refuse to start while a peer model process is alive
PEERS=$(pgrep -af 'lfm2_decode_bench\.bin|lfm2_gen_driver|lfm2_generate\.bin|wire\.py' | grep -v pgrep | grep -v 'defunct' || true)
if [ -n "$PEERS" ]; then echo "REFUSING: model-heavy peer alive:"; echo "$PEERS"; exit 4; fi

echo "=== setup ==="
echo "date    : $(date '+%F %T %Z')"
echo "governor: $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null || echo '?')"
echo "cores   : $(nproc)"
echo "load    : $(cat /proc/loadavg)"
echo "top_cpu : $(ps -eo pcpu,comm --sort=-pcpu | sed -n '2p')"
echo "user    : $(id -un)  box: $(hostname)"

run_conf () {
    local tag="$1"; local line="$2"; local log="$3"
    printf '%s\n' "$line" > "$CONF"
    echo "=== $tag ==="
    echo "conf    : $(cat $CONF)"
    echo "load_pre: $(cat /proc/loadavg)"
    echo "start   : $(date '+%F %T')"
    ( ulimit -c 0 -v 32000000; timeout 7200 nice -n 0 "$BIN" </dev/null ) > "$log" 2>&1
    local rc=$?
    echo "end     : $(date '+%F %T')  rc=$rc"
    echo "load_post: $(cat /proc/loadavg)"
    grep -E 'conf:|lens=|fused_q4k=|fused_q6k=|load_ms=|fused_q4k_active|fused_q6k_active|prompt_ids|^---run|gen_tokens|first_argmax_id|prefill_ms|tok_per_s|ms_per_token|tok_ms_min|rss_kb_start|anon_kb_start|vmpeak_kb_start|^---generated ids|DONE|PASS|FAIL' "$log"
    echo
}

run_conf "A: Q4_K fused only (fused_q4k=1 fused_q6k=0)" "20 128 512 1024 1 1 1 1 0" /tmp/bench_A_q4konly.log
run_conf "B: Q4_K + Q6_K fused (fused_q4k=1 fused_q6k=1)" "20 128 512 1024 1 1 1 1 1" /tmp/bench_B_both.log

# restore the canonical conf (both fused flags OFF = the shipped default)
printf '20 128 512 1024 1 1 1 0 0\n' > "$CONF"
echo "restored conf: $(cat $CONF)"
echo "=== driver done: $(date '+%F %T') load=$(cat /proc/loadavg) ==="
