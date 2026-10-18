// fp16_conv_oracle.c -- the DECISIVE ORACLE for the f16/f32 language types.
//
// TEST SCAFFOLDING ONLY. Not part of lib/, never called by the compiler or by
// the native inference path (Quanta does not link C). It exists so that every
// conversion the new f16/f32 types implement is pinned, bit for bit, against
// the real upstream library instead of against a transcription of it.
//
// It links the INSTALLED libggml-base and calls the two real exported symbols
//   ggml_fp16_to_fp32(ggml_fp16_t) -> float      (f16 -> f32, widening)
//   ggml_fp32_to_fp16(float)       -> ggml_fp16_t (f32 -> f16, RNE narrowing)
// which is the same library the Q6_K dequant row was proven bit-exact against.
// The f64 -> f32 narrowing has no ggml entry point, so mode `d2f` uses the host
// compiler's own `(float)d` conversion, which is IEEE round-to-nearest-even.
//
// Build + run through test_suites/scripts/gen_fp16_fixtures.py, which compiles
// this file, writes the fixtures under tests/fixtures/, and prints their md5s.
//
// Usage: fp16_conv_oracle {h2f|f2h|d2f|probe} [in] [out]

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include "ggml.h"

int main(int argc, char ** argv) {
    if (argc < 2) { fprintf(stderr, "usage: %s h2f|f2h|d2f|probe ...\n", argv[0]); return 2; }

    if (strcmp(argv[1], "h2f") == 0) {
        // 65536 u32 LE: the f32 bit pattern ggml_fp16_to_fp32 gives for each f16 pattern.
        if (argc < 3) { fprintf(stderr, "usage: h2f <out.bin>\n"); return 2; }
        FILE * f = fopen(argv[2], "wb");
        if (!f) { perror("fopen"); return 1; }
        for (int i = 0; i < 65536; i++) {
            ggml_fp16_t h; memcpy(&h, &i, 2);
            float v = ggml_fp16_to_fp32(h);
            uint32_t bits; memcpy(&bits, &v, 4);
            fwrite(&bits, 4, 1, f);
        }
        fclose(f); return 0;
    }

    if (strcmp(argv[1], "f2h") == 0) {
        // stdin-style: read u32 LE f32 cases, write u16 LE f16 results.
        if (argc < 4) { fprintf(stderr, "usage: f2h <cases.bin> <out.bin>\n"); return 2; }
        FILE * in = fopen(argv[2], "rb");  if (!in) { perror("fopen in"); return 1; }
        FILE * out = fopen(argv[3], "wb"); if (!out) { perror("fopen out"); return 1; }
        uint32_t b;
        while (fread(&b, 4, 1, in) == 1) {
            float v; memcpy(&v, &b, 4);
            ggml_fp16_t h = ggml_fp32_to_fp16(v);
            uint16_t hb; memcpy(&hb, &h, 2);
            fwrite(&hb, 2, 1, out);
        }
        fclose(in); fclose(out); return 0;
    }

    if (strcmp(argv[1], "d2f") == 0) {
        // read u64 LE f64 cases, write u32 LE f32 results ((float) cast, RNE).
        if (argc < 4) { fprintf(stderr, "usage: d2f <cases.bin> <out.bin>\n"); return 2; }
        FILE * in = fopen(argv[2], "rb");  if (!in) { perror("fopen in"); return 1; }
        FILE * out = fopen(argv[3], "wb"); if (!out) { perror("fopen out"); return 1; }
        uint64_t b;
        while (fread(&b, 8, 1, in) == 1) {
            double d; memcpy(&d, &b, 8);
            float v = (float) d;
            uint32_t bits; memcpy(&bits, &v, 4);
            fwrite(&bits, 4, 1, out);
        }
        fclose(in); fclose(out); return 0;
    }

    if (strcmp(argv[1], "probe") == 0) {
        static const uint16_t pats[] = {
            0x0000, 0x8000, 0x0001, 0x8001, 0x03FF, 0x0400, 0x3555, 0x3C00,
            0xBC00, 0x7BFF, 0x7C00, 0xFC00, 0x7C01, 0x7E00, 0xFE00, 0xFFFF,
            0x0401, 0x83FF, 0x3800, 0xB800, 0x3BFF, 0xBBFF, 0x0002, 0x7CFF,
        };
        printf("f16 pattern -> f32 bits (ggml_fp16_to_fp32)\n");
        for (unsigned k = 0; k < sizeof(pats)/sizeof(pats[0]); k++) {
            uint16_t p = pats[k];
            ggml_fp16_t h; memcpy(&h, &p, 2);
            float v = ggml_fp16_to_fp32(h);
            uint32_t bits; memcpy(&bits, &v, 4);
            printf("  0x%04X -> 0x%08X\n", p, bits);
        }
        static const uint32_t fpats[] = {
            0x00000000, 0x80000000, 0x00000001, 0x00001000, 0x00002000,
            0x3F800000, 0x3F800FFF, 0x3F801000, 0x3F801001, 0x40000000,
            0x3F802000, 0x3E000000, 0x477FE000, 0x477FFFFF, 0x47800000,
            0x7F7FFFFF, 0x7F800000, 0x7F800001, 0x7FC00000, 0xFF800000,
            0x33000000, 0x33000001, 0x33800000, 0x38800000, 0x387FFFFF,
            0x38800001, 0x477FFFFE, 0x7FFFFFFF, 0xFFFFFFFF, 0xC77FE000,
        };
        printf("\nf32 bits -> f16 (ggml_fp32_to_fp16)\n");
        for (unsigned k = 0; k < sizeof(fpats)/sizeof(fpats[0]); k++) {
            float v; memcpy(&v, &fpats[k], 4);
            ggml_fp16_t h = ggml_fp32_to_fp16(v);
            uint16_t hb; memcpy(&hb, &h, 2);
            printf("  0x%08X -> 0x%04X\n", fpats[k], hb);
        }
        return 0;
    }

    fprintf(stderr, "unknown mode %s\n", argv[1]);
    return 2;
}
