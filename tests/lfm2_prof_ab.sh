#!/usr/bin/env bash
# tests/lfm2_prof_ab.sh -- driver for the per-stage profile and the A/B it feeds.
#
# WHY A DRIVER, not a hand-typed command line: the bench conf is POSITIONAL and a
# peer already mis-counted its fields here and silently measured the wrong arm.
# So every run below PRINTS the conf line it actually wrote, immediately before
# running, and the conf is restored to the canonical 9-field shipped default at
# the end (the shape tests/run_q6k_fused_ab.sh also restores).
#
# Conf fields (tests/lfm2_decode_bench.quanta):
#   1 workers  2 len1  3 len2  4 len3  5 use_mmap  6 cache_norms
#   7 ignore_eos  8 fused_q4k  9 fused_q6k  10 prof
# Field 10 is NEW and optional: a 9-field conf still works (prof defaults 0), so
# the peer A/B driver is unaffected.
#
# Stages:
#   exact  bit-exactness gate (tests/lfm2_fused_logits_test.quanta). ALWAYS RUN
#          FIRST -- correctness before any timing.
#   prof   decode bench with the opt-in per-stage timer ON (conf field 10 = 1).
#          The timer build is THIS build of the bench; a rate measured with
#          prof=1 contains the clock() marks and is NOT a speed measurement.
#   ab     two arms in one script, no prof: A = both fused (baseline),
#          B = both fused + the change under test (conf field 11).
#
# Usage: bash tests/lfm2_prof_ab.sh exact|prof|ab
set -u
cd "$(dirname "$0")/.." || exit 2
REPO="$PWD"
QC="$REPO/compiler/$(cat "$REPO/VERSION")/bin/x86/qc"
CONF=tests/lfm2_decode_bench.conf
SCRATCH="${TMPDIR:-/tmp}"
BENCH="$SCRATCH/lfm2_decode_bench.bin"
EXBIN="$SCRATCH/lfm2_fused_logits.bin"
CONF_CANON="20 128 512 1024 1 1 1 0 0"
LENS="${PROF_LENS:-128 1024 128}"

peer_gate () {
    local peers
    peers=$(pgrep -af 'lfm2_decode_bench\.bin|lfm2_gen_driver|lfm2_generate\.bin|wire\.py|lfm2_fused_logits\.bin' | grep -v pgrep | grep -v 'defunct' || true)
    if [ -n "$peers" ]; then
        echo "REFUSING: model-heavy peer alive (measurement discipline):"
        echo "$peers"
        exit 4
    fi
}

env_report () {
    echo "date    : $(date '+%F %T %Z')"
    echo "governor: $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null || echo '?')"
    echo "cores   : $(nproc)"
    echo "load    : $(cat /proc/loadavg)"
    echo "top_cpu : $(ps -eo pcpu,comm --sort=-pcpu | sed -n '2p')"
    echo "user    : $(id -un)  box: $(hostname)"
    echo "head    : $(git rev-parse --short HEAD)  dirty=$(git status --short | wc -l)"
}

stage_exact () {
    echo "=== STAGE exact: bit-exactness gate (all 128000 logits) ==="
    ( ulimit -c 0 -v 8000000; "$QC" -O tests/lfm2_fused_logits_test.quanta "$EXBIN" ) \
        || { echo "COMPILE FAIL rc=$?"; exit 2; }
    echo "run_start: $(date '+%F %T')"
    ( ulimit -c 0 -v 32000000; timeout 5400 nice -n 0 "$EXBIN" </dev/null ) > /tmp/prof_stage_exact.log 2>&1
    local rc=$?
    echo "run_end  : $(date '+%F %T')  rc=$rc"
    grep -E 'prompt_ids|argmax:|used=|logits_n|CONTROL|Q4K |Q6K |BOTH |pass0_argmax0|first 24|PASS|FAIL|DONE' /tmp/prof_stage_exact.log
    if [ "$rc" != 0 ]; then
        echo "BIT-EXACTNESS GATE FAILED (rc=$rc) -- stop here, do not time anything"
        exit "$rc"
    fi
}

bench_build () {
    ( ulimit -c 0 -v 8000000; "$QC" -O tests/lfm2_decode_bench.quanta "$BENCH" ) \
        || { echo "COMPILE FAIL rc=$?"; exit 2; }
}

run_arm () {
    local tag="$1"; local line="$2"; local log="$3"
    printf '%s\n' "$line" > "$CONF"
    echo "=== $tag ==="
    echo "conf    : $(cat $CONF)   (fields: workers len1 len2 len3 mmap cache_norms ignore_eos fused_q4k fused_q6k [prof] [change])"
    echo "load_pre: $(cat /proc/loadavg)"
    echo "start   : $(date '+%F %T')"
    ( ulimit -c 0 -v 32000000; timeout 7200 nice -n 0 "$BENCH" </dev/null ) > "$log" 2>&1
    local rc=$?
    echo "end     : $(date '+%F %T')  rc=$rc"
    echo "load_post: $(cat /proc/loadavg)"
    grep -E '^conf:|^prof |load_ms=|fused_q4k_active|fused_q6k_active|^---run|gen_tokens|first_argmax_id|prefill_ms|tok_per_s_x1000|ms_per_token_x100|tok_ms_min|rss_kb_start|vmpeak_kb_start|^---generated ids|DONE|PASS|FAIL' "$log"
    echo
}

stage_prof () {
    echo "=== STAGE prof: per-stage timer build, conf field 10 = 1 ==="
    echo "NOTE: this build contains the timer and the conf turns it ON, so the"
    echo "      tok/s printed below is NOT a speed measurement -- it is inflated by"
    echo "      the clock() marks. fc_prof_cal_ns is printed with each table."
    bench_build
    run_arm "PROF (both fused, prof=1)" "20 $LENS 1 1 1 1 1 1" /tmp/prof_stage_prof.log
}

stage_ab () {
    local line_a="20 $LENS 1 1 1 1 1 0"
    local line_b="20 $LENS 1 1 1 1 1 1"
    echo "=== STAGE ab: baseline (no change) vs change, timer OFF both arms ==="
    bench_build
    run_arm "A baseline (both fused, change OFF)" "$line_a" /tmp/prof_ab_A.log
    run_arm "B change ON" "$line_b" /tmp/prof_ab_B.log
}

peer_gate
env_report
case "${1:-}" in
    exact) stage_exact ;;
    prof)  stage_prof ;;
    ab)    stage_ab ;;
    *) echo "usage: $0 exact|prof|ab"; exit 2 ;;
esac

# restore the canonical conf whatever happened
printf '%s\n' "$CONF_CANON" > "$CONF"
echo "restored conf: $(cat $CONF)"
echo "=== driver done: $(date '+%F %T') load=$(cat /proc/loadavg) ==="
