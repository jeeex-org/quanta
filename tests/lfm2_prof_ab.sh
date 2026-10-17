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
#   7 ignore_eos  8 fused_q4k  9 fused_q6k  10 prof  11 prof_work  12 (change)
# Fields 10+ are NEW and optional: a 9-field conf still works (both default 0),
# so the peer A/B driver tests/run_q6k_fused_ab.sh is unaffected.
#
# prof=1 turns on the phase table. prof_work=1 ALSO turns on the worker-side
# marks, which serialise the pool (clock() is mmap+clock_gettime+munmap here, so
# 20 workers x 2 marks per matvec contend on mmap_lock): use it only for the
# short `conc` run that answers the pool-concurrency question.
#
# Stages:
#   exact     bit-exactness gate (tests/lfm2_fused_logits_test.quanta). RUN FIRST.
#   baseline  clean rate, timer OFF, canonical lengths.
#   prof      phase table, timer ON (prof_work OFF). NOT a rate measurement.
#   conc      SHORT run with prof_work=1 -- pool concurrency only, times void.
#   ab        baseline vs the change under test (conf field 12), timer OFF.
#
# Usage: bash tests/lfm2_prof_ab.sh exact|baseline|prof|conc|ab
set -u
cd "$(dirname "$0")/.." || exit 2
REPO="$PWD"
# COMPILER IS PINNED, NOT DERIVED FROM VERSION. A second unit is adding f16/f32
# float types in a new compiler/0.0.247 tree and will eventually bump VERSION;
# deriving QC from that file would swap the compiler underneath a running
# measurement without a word. Pin it, print it in every run, and report it.
# Override with QC=... only deliberately.
QC="${QC:-$PWD/compiler/0.0.246/bin/x86/qc}"
CONF=tests/lfm2_decode_bench.conf
# PRIVATE scratch: the peer runner also uses $TMPDIR/lfm2_decode_bench.bin,
# so a concurrent peer would clobber this binary MID-RUN. Own directory.
SCRATCH="${PROF_SCRATCH:-/home/tali/.hermes/cache/scratch/lfm2prof}"
mkdir -p "$SCRATCH" || exit 2
# log dir kept separate from the peer's /tmp names for the same reason
LOGD="$SCRATCH/logs"
mkdir -p "$LOGD" || exit 2
BENCH="$SCRATCH/lfm2_decode_bench.bin"
EXBIN="$SCRATCH/lfm2_fused_logits.bin"
CONF_CANON="20 128 512 1024 1 1 1 0 0"
LENS="${LENS:-128 1024 128}"
CONC_LENS="${CONC_LENS:-32 32 32}"

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
    echo "qc      : $QC"
    echo "qc_md5  : $(md5sum "$QC" 2>/dev/null | cut -d' ' -f1)"
}

stage_exact () {
    echo "=== STAGE exact: bit-exactness gate (all 128000 logits) ==="
    ( ulimit -c 0 -v 8000000; "$QC" -O tests/lfm2_fused_logits_test.quanta "$EXBIN" ) \
        || { echo "COMPILE FAIL rc=$?"; exit 2; }
    echo "run_start: $(date '+%F %T')"
    ( ulimit -c 0 -v 32000000; timeout 5400 nice -n 0 "$EXBIN" </dev/null ) > $LOGD/prof_stage_exact.log 2>&1
    local rc=$?
    echo "run_end  : $(date '+%F %T')  rc=$rc"
    grep -E 'prompt_ids|argmax:|used=|logits_n|CONTROL|Q4K |Q6K |BOTH |pass0_argmax0|first 24|PASS|FAIL|DONE' $LOGD/prof_stage_exact.log
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
    echo "conf    : $(cat $CONF)"
    echo "          fields: workers len1 len2 len3 mmap cache_norms ignore_eos fused_q4k fused_q6k [prof] [prof_work] [fused_chain]"
    echo "load_pre: $(cat /proc/loadavg)"
    echo "start   : $(date '+%F %T')"
    ( ulimit -c 0 -v 32000000; timeout 7200 nice -n 0 "$BENCH" </dev/null ) > "$log" 2>&1
    local rc=$?
    echo "end     : $(date '+%F %T')  rc=$rc"
    echo "load_post: $(cat /proc/loadavg)"
    grep -E '^conf:|^prof |load_ms=|fused_q4k_active|fused_q6k_active|^---run|gen_tokens|first_argmax_id|prefill_ms|tok_per_s_x1000|ms_per_token_x100|tok_ms_min|rss_kb_start|vmpeak_kb_start|^---generated ids|DONE|PASS|FAIL' "$log"
    echo
}

stage_baseline () { bench_build; run_arm "BASELINE rate, timer OFF (canonical-ish)" "20 $LENS 1 1 1 1 1 0 0" $LOGD/prof_stage_baseline.log; }
stage_prof     () { bench_build; run_arm "PROF phase table, timer ON, prof_work ON" "20 $LENS 1 1 1 1 1 1 1" $LOGD/prof_stage_prof.log; }
stage_prof_nw  () { bench_build; run_arm "PROF phase table, timer ON, prof_work OFF" "20 $LENS 1 1 1 1 1 1 0" $LOGD/prof_stage_prof_nw.log; }
stage_conc     () { bench_build; run_arm "CONC pool concurrency, prof_work=1 (SHORT; times void)" "20 $CONC_LENS 1 1 1 1 1 1 1" $LOGD/prof_stage_conc.log; }

stage_ab () {
    echo "=== STAGE ab: baseline (change OFF) vs change ON, timer OFF both arms ==="
    bench_build
    run_arm "A chain=0 (baseline)" "20 $LENS 1 1 1 1 1 0 0 0" $LOGD/prof_ab_A.log
    run_arm "B chain=1 (the change under test)" "20 $LENS 1 1 1 1 1 0 0 1" $LOGD/prof_ab_B.log
}

peer_gate
env_report
case "${1:-}" in
    exact)    stage_exact ;;
    baseline) stage_baseline ;;
    prof)     stage_prof ;;
    conc)     stage_conc ;;
    ab)       stage_ab ;;
    *) echo "usage: $0 exact|baseline|prof|conc|ab"; exit 2 ;;
esac

printf '%s\n' "$CONF_CANON" > "$CONF"
echo "restored conf: $(cat $CONF)"
echo "=== driver done: $(date '+%F %T') load=$(cat /proc/loadavg) ==="
