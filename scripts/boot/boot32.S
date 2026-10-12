/*
 * boot32.S -- 32-bit PVH entry stub for a bare-metal Quanta kernel (--bare).
 *
 * WHY THIS EXISTS
 * QEMU's -kernel multiboot loader refuses ELF64 ("Cannot load x86-64 image,
 * give a 32bit one"), so a 64-bit Quanta kernel cannot use a multiboot header.
 * It uses the PVH path instead: QEMU loads the ELF64 normally, scans PT_NOTE
 * for the Xen note XEN_ELFNOTE_PHYS32_ENTRY (type 18), and enters that 32-bit
 * PHYSICAL address in 32-bit protected mode with paging off. This stub builds
 * the identity page tables, enables long mode, and jumps to the 64-bit entry
 * the compiler emits immediately after it.
 *
 * This is the ONLY non-Quanta code in the image: ~170 bytes of 32-bit
 * bootstrap that Quanta's 64-bit backend cannot express. Every kernel
 * capability under test (GDT/IDT gates, trap handlers, in/out, lgdt/lidt,
 * iretq) is emitted by Quanta itself. The bytes are generated into
 * compiler/<ver>/src/x86/boot32_bytes.quanta by scripts/boot/gen_boot32.py;
 * regenerate with:
 *
 *     python3 scripts/boot/gen_boot32.py <compiler-version-dir>
 *
 * The generated file records the assembler listing as comments, and
 * scripts/boot/verify_boot32.sh disassembles the emitted prefix back out of a
 * built ELF and compares it against this source.
 *
 * LAYOUT (fixed by the compiler, asserted at emit time):
 *   BASE = 0x400000, ht = 64 + 56*5 = 0x158 (5 program headers in --bare mode)
 *   prefix    = [note 20 bytes][this stub section]
 *   note.desc = STUB_BASE  = BASE + ht + 20
 *   entry64   = ENTRY_BASE = STUB_BASE + sizeof(.boot32)
 * STUB_BASE and ENTRY_BASE are supplied as --defsym by the generator; the
 * generator resolves ENTRY_BASE in two passes from the section size.
 */

    .set PT_BASE, 0x200000        /* page tables: RAM above the kernel image */

    .section .note.Xen,"a",@note
    .balign 4
    .long 4                       /* namesz */
    .long 4                       /* descsz */
    .long 18                      /* XEN_ELFNOTE_PHYS32_ENTRY */
    .asciz "Xen"                  /* name, NUL-padded to namesz */
    .balign 4
    .long STUB_BASE               /* 32-bit physical entry QEMU jumps to */

    .section .boot32,"ax",@progbits
    .code32
    .globl boot32
boot32:
    cli
    movl    $gdt_desc, %eax
    lgdt    (%eax)

    movl    $PT_BASE, %edi        /* zero PML4 + PDPT (8 KiB; 12 keeps margin) */
    xorl    %eax, %eax
    movl    $3072, %ecx
    rep stosl

    movl    $(PT_BASE + 0x1000 + 3), %eax   /* PML4[0] -> PDPT | present|rw */
    movl    %eax, PT_BASE

    /* PDPT: four 1 GiB pages, i.e. an identity map of the low 4 GiB.
     *
     * Not one 2 MiB PD page of 1 GiB: the compiler links a program's globals
     * at the fixed BSS base GDATA = 0x42200000 (~1.03 GiB, "ET_EXEC, absolute
     * addressing"), which is OUTSIDE a 1 GiB map. Measured: with a 1 GiB map
     * the first global store in a Quanta bare-metal program took a #PF
     * (CR2 = 0x42200168, e=0002) and the guest triple-faulted. The guest
     * therefore also needs >= 1.06 GiB of RAM for the segment to exist —
     * documented in docs/plans/kernel-capability.md Phase D.
     */
    movl    $0x00000083, PT_BASE + 0x1000   /* [0] 0..1 GiB, PS|P|RW */
    movl    $0, PT_BASE + 0x1004
    movl    $0x40000083, PT_BASE + 0x1008   /* [1] 1..2 GiB */
    movl    $0, PT_BASE + 0x100c
    movl    $0x80000083, PT_BASE + 0x1010   /* [2] 2..3 GiB */
    movl    $0, PT_BASE + 0x1014
    movl    $0xc0000083, PT_BASE + 0x1018   /* [3] 3..4 GiB */
    movl    $0, PT_BASE + 0x101c

    movl    %cr4, %eax
    orl     $0x20, %eax           /* CR4.PAE */
    movl    %eax, %cr4

    movl    $PT_BASE, %eax
    movl    %eax, %cr3

    movl    $0xC0000080, %ecx     /* IA32_EFER */
    rdmsr
    orl     $0x100, %eax          /* EFER.LME */
    wrmsr

    movl    %cr0, %eax
    orl     $0x80000001, %eax     /* CR0.PG | CR0.PE */
    movl    %eax, %cr0

    ljmp    $0x08, $ENTRY_BASE    /* 64-bit code selector -> Quanta entry */

    .balign 8
gdt:
    .quad   0x0000000000000000    /* 0x00 null */
    .quad   0x00af9a000000ffff    /* 0x08 64-bit code */
    .quad   0x00cf92000000ffff    /* 0x10 data */
gdt_end:
gdt_desc:
    .word   gdt_end - gdt - 1     /* limit = 23 */
    .long   gdt                   /* base */
    .word   0
    .balign 16
