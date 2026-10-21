// pulse.asm -- Bloom milestone B3b: PULSE on FREQ. Once a block, before the stock unpack
// reads the received frame, add the Innerbloom pulse to every Bloom track's FREQ word.
//
// Our own code, assembled with selache's `selas` (GPL-3.0, used as a tool and never
// linked in) and the post-fixes in scripts/sharc_waverider_m3.py. The contract is
// dnfw.bloom.live.pulse_block, bit for bit in float32 (scripts/sharc_bloom_b3b.py).
//
// The per-frame handler calls the per-block routine sw 0x1c2712 from sw 0x1c9fbc, after
// loading its first argument at sw 0x1c9fb9: `r4 = 0x268438`. The build replaces that
// one 48-bit load with `JUMP 0x16f400` (the site Waverider's entry_mark.asm uses; the
// two mods exclude each other). This code runs, performs the load it displaced, and
// jumps back to the call. B1b (docs/bloom-machine.md) showed the stock filter follows a
// FREQ word rewritten here exactly as it follows the ColdFire's own, one block late.
//
// The received page is the unpack's third argument, R12, which the handler has loaded
// by sw 0x1c9fb9 (`r12 = ...` at 0x1c9fb5; 0x2c0478 + (DM[0x268a38] << 8) in the runner's
// calls). For every track t whose machine (frame +148 + 2t, low nibble) is 7, with the
// note-trig mask at frame +34:
//
//   if word != last: base = word         (a value from the ColdFire, not our own)
//   if trig t:       step = STEP0, phase = 0, n = 0
//   if step == 0:    word = base         (never triggered)
//   else:            m = 1 - |phase - 0.5| * 4
//                    word = clamp(base + trunc(m * 8192), 0, 0x7f00)
//                    phase += step, wrapped; n < 12000: n += 1, step = STEP1 at
//                    12000, else step * RATIO
//   last = word, written back into FREQ (frame +0x12e + 146t)
//
// The forms are B3a's (bloom_loop.asm): no hardware DO loop, taps by `In = Rn` then
// `DM(k, In)`, no M0-M3 in an access, no float result in F0, adds with R8-R15 first.
// R4, R8 and R12 are the call's arguments and R2 is pushed by the call: everything
// used is saved and restored, and R4 is then loaded as the displaced instruction does.
//
// PLACEMENT IS FIXED: this code loads at PM sw 0x16f400 (L1 block 1, byte 0x2de800).
//
// DM (byte addresses, zeros at boot):
//   0x2dec00  16 tracks x 32 bytes: step (f32), phase (f32), n, base, last
//   0x2dee00  save area: R0-R15, I1, I2
//   0x2dee60  tracks left, 16 - t
//   0x2dee64  the received page
//   0x2dee68  the note-trig mask

.SECTION/PM seg_pmco;

.GLOBAL bp_pulse.;
bp_pulse.:
      DM(0x2dee00) = R0;
      DM(0x2dee04) = R1;
      DM(0x2dee08) = R2;
      DM(0x2dee0c) = R3;
      DM(0x2dee10) = R4;
      DM(0x2dee14) = R5;
      DM(0x2dee18) = R6;
      DM(0x2dee1c) = R7;
      DM(0x2dee20) = R8;
      DM(0x2dee24) = R9;
      DM(0x2dee28) = R10;
      DM(0x2dee2c) = R11;
      DM(0x2dee30) = R12;
      DM(0x2dee34) = R13;
      DM(0x2dee38) = R14;
      DM(0x2dee3c) = R15;
      DM(0x2dee40) = I1;
      DM(0x2dee44) = I2;

      R13 = PASS R12;                   // the page the unpack will read: its third argument
      DM(0x2dee64) = R13;
      R12 = 32;
      R2 = R13 + R12;
      I1 = R2;
      R14 = DM(0, I1);
      R7 = -16;
      R14 = LSHIFT R14 BY R7;           // +34, the high half: the note-trig mask
      DM(0x2dee68) = R14;
      R0 = 16;
      DM(0x2dee60) = R0;                // tracks left, 16 - t

.GLOBAL bp_track.;
bp_track.:
      R0 = DM(0x2dee60);
      R1 = 16;
      R9 = R1 - R0;                     // t

      // the machine: the half-word at page + 148 + 2t
      R10 = LSHIFT R9 BY 1;
      R11 = 148;
      R10 = R10 + R11;
      R13 = DM(0x2dee64);
      R2 = R13 + R10;
      R1 = 2;
      R1 = R2 AND R1;                   // 2: the high half of its word
      R4 = -4;
      R2 = R2 AND R4;
      I1 = R2;
      R5 = DM(0, I1);
      R1 = PASS R1;
      IF EQ JUMP bp_mlow.;
      R7 = -16;
      R5 = LSHIFT R5 BY R7;
.GLOBAL bp_mlow.;
bp_mlow.:
      R6 = 15;
      R5 = R5 AND R6;
      R6 = 7;
      COMP(R5, R6);
      IF NE JUMP bp_next.;

      // the track's state, 0x2dec00 + 32t
      R2 = LSHIFT R9 BY 5;
      R12 = 0x2dec00;
      R2 = R12 + R2;
      I2 = R2;

      // FREQ: the half-word at page + 0x12e + 146t; I1 and R15 (2: high) kept for the write
      R10 = LSHIFT R9 BY 7;
      R11 = LSHIFT R9 BY 4;
      R10 = R10 + R11;
      R11 = LSHIFT R9 BY 1;
      R10 = R10 + R11;                  // 146t
      R11 = 0x12e;
      R10 = R10 + R11;
      R13 = DM(0x2dee64);
      R2 = R13 + R10;
      R15 = 2;
      R15 = R2 AND R15;
      R4 = -4;
      R2 = R2 AND R4;
      I1 = R2;
      R6 = DM(0, I1);
      R15 = PASS R15;
      IF EQ JUMP bp_flow.;
      R7 = -16;
      R6 = LSHIFT R6 BY R7;
.GLOBAL bp_flow.;
bp_flow.:
      R7 = 0xffff;
      R6 = R6 AND R7;                   // the page's FREQ word

      R8 = DM(4, I2);                   // last
      COMP(R6, R8);
      IF EQ JUMP bp_based.;
      DM(3, I2) = R6;                   // base = the page's word
.GLOBAL bp_based.;
bp_based.:
      R0 = DM(0x2dee68);
      R7 = -R9;
      R1 = LSHIFT R0 BY R7;
      R2 = 1;
      R1 = R1 AND R2;                   // trig bit t
      IF EQ JUMP bp_notrig.;
      R0 = 0x3c03126f;                  // STEP0: 12 Hz a block
      DM(0, I2) = R0;
      R0 = 0;
      DM(1, I2) = R0;                   // phase 0
      DM(2, I2) = R0;                   // n 0
.GLOBAL bp_notrig.;
bp_notrig.:
      R10 = DM(3, I2);                  // base: the word, if no pulse
      R14 = DM(0, I2);                  // step
      R14 = PASS R14;
      IF EQ JUMP bp_write.;             // never triggered

      R1 = DM(1, I2);                   // phase
      R11 = 0x3f000000;                 // 0.5
      F2 = F1 - F11;
      F2 = ABS F2;
      R12 = 0x40800000;                 // 4.0
      F2 = F2 * F12;
      R13 = 0x3f800000;                 // 1.0
      F2 = F13 - F2;                    // m, -1 .. +1
      R12 = 0x46000000;                 // 8192.0: the depth
      F2 = F2 * F12;
      R2 = TRUNC F2;
      R10 = R10 + R2;                   // base + offset
      R12 = 0;
      R10 = MAX(R10, R12);
      R12 = 0x7f00;
      R10 = MIN(R10, R12);              // 0 .. FREQ_MAX

      F1 = F14 + F1;                    // phase + step
      COMP(F1, F13);
      IF LT JUMP bp_pwrap.;
      F1 = F1 - F13;
.GLOBAL bp_pwrap.;
bp_pwrap.:
      DM(1, I2) = R1;

      R2 = DM(2, I2);                   // n
      R3 = 12000;                       // the glide's blocks: 8 s
      COMP(R2, R3);
      IF GE JUMP bp_write.;
      R12 = 1;
      R2 = R12 + R2;
      DM(2, I2) = R2;
      COMP(R2, R3);
      IF EQ JUMP bp_last.;
      R12 = 0x3f7ff26e;                 // RATIO: (1/12)^(1/12000)
      F14 = F14 * F12;
      DM(0, I2) = R14;
      JUMP bp_write.;
.GLOBAL bp_last.;
bp_last.:
      R14 = 0x3a2ec33e;                 // STEP1: 1 Hz a block
      DM(0, I2) = R14;

.GLOBAL bp_write.;
bp_write.:
      DM(4, I2) = R10;                  // last
      R5 = DM(0, I1);                   // FREQ's word, again
      R15 = PASS R15;
      IF EQ JUMP bp_wlow.;
      R12 = 0xffff;
      R5 = R5 AND R12;
      R11 = LSHIFT R10 BY 16;
      R5 = R11 OR R5;
      JUMP bp_wput.;
.GLOBAL bp_wlow.;
bp_wlow.:
      R12 = 0xffff0000;
      R5 = R5 AND R12;
      R5 = R10 OR R5;
.GLOBAL bp_wput.;
bp_wput.:
      DM(0, I1) = R5;

.GLOBAL bp_next.;
bp_next.:
      R0 = DM(0x2dee60);
      R1 = 1;
      R0 = R0 - R1;
      DM(0x2dee60) = R0;
      IF NE JUMP bp_track.;

      R0 = DM(0x2dee00);
      R1 = DM(0x2dee04);
      R2 = DM(0x2dee08);
      R3 = DM(0x2dee0c);
      R4 = DM(0x2dee10);
      R5 = DM(0x2dee14);
      R6 = DM(0x2dee18);
      R7 = DM(0x2dee1c);
      R8 = DM(0x2dee20);
      R9 = DM(0x2dee24);
      R10 = DM(0x2dee28);
      R11 = DM(0x2dee2c);
      R12 = DM(0x2dee30);
      R13 = DM(0x2dee34);
      R14 = DM(0x2dee38);
      R15 = DM(0x2dee3c);
      I1 = DM(0x2dee40);
      I2 = DM(0x2dee44);

      R4 = 0x268438;                    // the displaced load
      JUMP 0x1c9fbc;                    // back to the call
.bp_pulse..end:
      .type bp_pulse.,STT_FUNC;
