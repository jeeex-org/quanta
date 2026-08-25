# Quanta — Language Design

Quanta is a programming language you can pick up quickly. You write what you want
in short, plain code, and Quanta catches mistakes before they break anything. It
reads your program as structure it can check from the first line, and it speaks
the language of many fields — a scientist writes `laplace(potential)`, a musician
writes notes, a cryptographer writes ciphers — in the words each already uses.

The goal: a complete language where you rarely think about memory or safety
because Quanta handles it; where every field has its own natural notation; and
where your program is something the compiler checks as you write, so mistakes are
caught early instead of at runtime.

---

## 1. What Quanta Is

- **Safe to change.** Quanta reads your program as structure, not plain text, so
  a small edit can't quietly break it. It checks your work as you go.
- **Short and regular.** Programs are small and read top to bottom. There is no
  setup file to learn — one command and you are running.
- **Builds itself.** The Quanta compiler is written in Quanta. The same language
  that builds your app builds the tools around it.
- **One program, many places.** Write it once; Quanta packs the same program to
  run on your laptop, in a web page, or on a small device.
- **Speaks many fields.** Science, music, finance, and cryptography each get their
  own natural way of writing, in words their experts already use.
- **Looks after memory.** Quanta handles memory and safety for you; if you truly
  need raw access, that is an explicit, separate choice — not the normal path.

---

## 2. What Quanta Does

- **Gets out of your way at the start.** Your first hour is spent saying what you
  want, not wiring up tools.
- **Carries the hard parts.** Types, memory, and build targets are figured out by
  Quanta, not written down by you.
- **Lets experts write naturally.** A scientist writes `laplace(potential)`
  instead of `matrix_multiply(...)`.
- **Explains its errors.** When something is wrong, Quanta says what, why, and
  how to fix it.
- **Catches mistakes as you type.** It checks after every change, so you know
  immediately.
- **Stays manageable at scale.** Small programs and large ones are written the
  same way.
- **Keeps sensitive code honest.** In the cryptography and blockchain dialects,
  the unsafe forms — timing leaks, replay, bad randomness — simply will not
  compile.
- **Keeps its own docs true.** Every example in the documentation is run as a
  test; a broken example fails the build.

---

## 3. Why It Works

One idea holds it together: **Quanta treats your program as something it can
check, from the very first line.** Because the structure is knowable, writing
stays simple, mistakes are caught early, and the same code runs everywhere. The
things that make other languages heavy — setup, packaging, fragile text,
guessing whether code is right — are handled at the foundation, not left to you.

Quanta is the language that results.
