// bloom_loop.asm -- Bloom milestone B3a: the type-7 render loop. A PolyBLEP saw per
// Bloom track, into its track buffer, before the per-track chain.
//
// Our own code, assembled with selache's `selas` (GPL-3.0, used as a tool and never
// linked in) and the post-fixes in scripts/sharc_waverider_m3.py. The contract is
// dnfw.bloom.live, bit for bit in float32 (scripts/sharc_bloom_b3a.py).
//
// Entered by the JUMP the build writes at sw 0x1c9448 (after the Swarmer render loop in
// sw 0x1c8ef1, before the per-track chain), once per block. It scans the 16 track
// records and, for every track whose machine type is 7:
//
//   pitch  the engine's note cell, 0x254b14 + 4t (float semitones), validated in the
//          integer domain first (an exponent of 0xff or a set sign bit gives +0.0),
//          plus TUN1 (WaveTone's param 25, the frame copy 0x25c48c, offset 218 + 146t:
//          frame word / 256 - 64), below 0 -> 0, then MIN 127. As Waverider M6 does.
//   step   k = TRUNC note, fr = note - k; dt and inv from the tables DT[k], INV[k]
//          (dnfw.bloom.live.dt_table / inv_table), each interpolated as
//          T[k] + fr * (T[k+1] - T[k]).
//   saw    per sample: y = 2p - 1; the BLEP below dt or above 1 - dt; out = y * 0.5;
//          p += dt, wrapped. The phase is kept per track at PHASES + 4t.
//
// The forms are the ones Waverider's shipped loops use (docs/waverider-dsp-silence.md,
// reader_m5.asm's notes): no hardware DO loop (a count in a register, `IF NE JUMP`
// back); memory taps by `In = Rn` then `DM(0, In)` or a post-modify with M6; no M0-M3
// in an access; no conditional compute; adds with R8-R15 first. No float result goes to
// F0 (anomaly 20000072: F0, then a single-operand compute, stalls).
//
// PLACEMENT IS FIXED: this code loads at PM sw 0x16eb00 (L1 block 1, byte 0x2dd600),
// inside Waverider's region (the two mods exclude each other). The jumps inside are to
// labels (PC-relative, sharc_waverider_m3.fix_rel_jump); the way back is absolute.
//
// DM (byte addresses):
//   0x2dde00  save area: R0-R15, I0-I5, I12, M0-M4 (28 words)
//   0x2dde80  tracks left, 16 - t
//   0x2ddf00  PHASES: 16 floats, one per track, zeros at boot
//   0x2de000  DT: 129 floats
//   0x2de400  INV: 129 floats

.SECTION/PM seg_pmco;

.GLOBAL bl_loop.;
bl_loop.:
      DM(0x2dde00) = R0;
      DM(0x2dde04) = R1;
      DM(0x2dde08) = R2;
      DM(0x2dde0c) = R3;
      DM(0x2dde10) = R4;
      DM(0x2dde14) = R5;
      DM(0x2dde18) = R6;
      DM(0x2dde1c) = R7;
      DM(0x2dde20) = R8;
      DM(0x2dde24) = R9;
      DM(0x2dde28) = R10;
      DM(0x2dde2c) = R11;
      DM(0x2dde30) = R12;
      DM(0x2dde34) = R13;
      DM(0x2dde38) = R14;
      DM(0x2dde3c) = R15;
      DM(0x2dde40) = I0;
      DM(0x2dde44) = I1;
      DM(0x2dde48) = I2;
      DM(0x2dde4c) = I3;
      DM(0x2dde50) = I4;
      DM(0x2dde54) = I5;
      DM(0x2dde58) = I12;
      DM(0x2dde5c) = M0;
      DM(0x2dde60) = M1;
      DM(0x2dde64) = M2;
      DM(0x2dde68) = M3;
      DM(0x2dde6c) = M4;

      I3 = 0x25566c;                    // &track[0].machine (0x2554b8 + 0x1b4)
      I5 = 0x254a60;                    // &track_buffer[0]
      R0 = 16;
      DM(0x2dde80) = R0;                // tracks left, 16 - t

.GLOBAL bl_track.;
bl_track.:
      M4 = 0x8d;                        // record stride in words (0x234 bytes)
      R2 = DM(I3, M4);                  // this track's machine type; I3 -> next record
      R3 = DM(I5, M6);                  // this track's buffer; I5 -> next
      R4 = 7;
      COMP(R2, R4);
      IF NE JUMP bl_next.;

      R0 = DM(0x2dde80);
      R1 = 16;
      R9 = R1 - R0;                     // t (R9 holds t only until F9 = dt, below)
      R2 = LSHIFT R9 BY 2;
      R12 = 0x2ddf00;                   // &PHASES[0]
      R2 = R12 + R2;
      I2 = R2;                          // &PHASES[t], kept for the load and the store

      // TUN1 (param 25): the half-word at 0x25c48c + 218 + 146t, little-endian
      R10 = LSHIFT R9 BY 7;
      R11 = LSHIFT R9 BY 4;
      R10 = R10 + R11;
      R11 = LSHIFT R9 BY 1;
      R10 = R10 + R11;                  // 146t
      R12 = 0x25c566;                   // 0x25c48c + 218
      R2 = R12 + R10;                   // &TUN1, 2-byte aligned
      R1 = 2;
      R1 = R2 AND R1;                   // 2: the high half of its word
      R4 = -4;
      R2 = R2 AND R4;
      I1 = R2;
      R13 = DM(0, I1);
      R7 = -16;
      R1 = PASS R1;
      IF EQ JUMP bl_tun_low.;
      R13 = LSHIFT R13 BY R7;           // the high half
.GLOBAL bl_tun_low.;
bl_tun_low.:
      R6 = 0xffff;
      R13 = R13 AND R6;                 // TUN1, the sound's value

      // the note cell, validated before any float operation
      R2 = LSHIFT R9 BY 2;
      R12 = 0x254b14;
      R2 = R12 + R2;
      I1 = R2;
      R8 = DM(0, I1);                   // note, float semitones
      R2 = LSHIFT R8 BY -23;
      R12 = 0xff;
      R2 = R2 AND R12;                  // the exponent field
      COMP(R2, R12);
      IF EQ JUMP bl_note0.;
      R8 = PASS R8;
      IF LT JUMP bl_note0.;
      JUMP bl_note_ok.;
.GLOBAL bl_note0.;
bl_note0.:
      R8 = R8 - R8;                     // +0.0
.GLOBAL bl_note_ok.;
bl_note_ok.:
      R12 = -8;
      F13 = FLOAT R13 BY R12;           // frame word / 256
      R12 = 0x42800000;                 // 64.0
      F13 = F13 - F12;
      F8 = F8 + F13;                    // note + TUN1
      R8 = PASS R8;
      IF LT JUMP bl_note_low.;
      JUMP bl_note_tuned.;
.GLOBAL bl_note_low.;
bl_note_low.:
      R8 = R8 - R8;                     // below note 0 -> +0.0
.GLOBAL bl_note_tuned.;
bl_note_tuned.:
      R12 = 0x42fe0000;                 // 127.0
      F8 = MIN(F8, F12);                // 0 <= note <= 127
      R1 = TRUNC F8;                    // k, 0..127
      R12 = R12 - R12;
      F2 = FLOAT R1 BY R12;
      F8 = F8 - F2;                     // fr, 0 <= fr < 1
      R1 = LSHIFT R1 BY 2;              // 4k

      R12 = 0x2de000;                   // &DT[0]
      R2 = R12 + R1;
      I1 = R2;
      R4 = DM(0, I1);                   // DT[k]
      R5 = DM(1, I1);                   // DT[k + 1]
      F5 = F5 - F4;
      F5 = F8 * F5;
      F9 = F4 + F5;                     // dt

      R12 = 0x2de400;                   // &INV[0]
      R2 = R12 + R1;
      I1 = R2;
      R4 = DM(0, I1);                   // INV[k]
      R5 = DM(1, I1);                   // INV[k + 1]
      F5 = F5 - F4;
      F5 = F8 * F5;
      F10 = F4 + F5;                    // inv

      // the phase, and the constants of the sample loop (I2 is &PHASES[t], set above)
      R8 = DM(0, I2);                   // p
      R11 = 0x3f800000;                 // 1.0
      R12 = 0x3f000000;                 // 0.5, the gain
      F13 = F11 - F9;                   // 1 - dt
      I0 = R3;                          // out: the track buffer
      R6 = DM(0x2dde24);                // the dispatch's R9: the block size

.GLOBAL bl_sample.;
bl_sample.:
      F1 = F8 + F8;
      F1 = F1 - F11;                    // y = 2p - 1
      COMP(F8, F9);
      IF LT JUMP bl_blep_low.;
      COMP(F8, F13);
      IF GT JUMP bl_blep_high.;
      JUMP bl_out.;
.GLOBAL bl_blep_low.;
bl_blep_low.:
      F2 = F8 * F10;                    // u = p * inv
      F3 = F2 + F2;
      F4 = F2 * F2;
      F3 = F3 - F4;
      F3 = F3 - F11;                    // u + u - u*u - 1
      F1 = F1 - F3;
      JUMP bl_out.;
.GLOBAL bl_blep_high.;
bl_blep_high.:
      F2 = F8 - F11;
      F2 = F2 * F10;                    // u = (p - 1) * inv
      F4 = F2 * F2;
      F3 = F4 + F2;
      F3 = F3 + F2;
      F3 = F3 + F11;                    // u*u + u + u + 1
      F1 = F1 - F3;
.GLOBAL bl_out.;
bl_out.:
      F1 = F1 * F12;                    // y * gain
      DM(I0, M6) = F1;
      F8 = F8 + F9;                     // p + dt
      COMP(F8, F11);
      IF LT JUMP bl_wrapped.;
      F8 = F8 - F11;
.GLOBAL bl_wrapped.;
bl_wrapped.:
      R1 = 1;
      R6 = R6 - R1;
      IF NE JUMP bl_sample.;
      DM(0, I2) = R8;                   // the phase, for the next block

.GLOBAL bl_next.;
bl_next.:
      R0 = DM(0x2dde80);
      R1 = 1;
      R0 = R0 - R1;
      DM(0x2dde80) = R0;
      IF NE JUMP bl_track.;

      R0 = DM(0x2dde00);
      R1 = DM(0x2dde04);
      R2 = DM(0x2dde08);
      R3 = DM(0x2dde0c);
      R4 = DM(0x2dde10);
      R5 = DM(0x2dde14);
      R6 = DM(0x2dde18);
      R7 = DM(0x2dde1c);
      R8 = DM(0x2dde20);
      R9 = DM(0x2dde24);
      R10 = DM(0x2dde28);
      R11 = DM(0x2dde2c);
      R12 = DM(0x2dde30);
      R13 = DM(0x2dde34);
      R14 = DM(0x2dde38);
      R15 = DM(0x2dde3c);
      I0 = DM(0x2dde40);
      I1 = DM(0x2dde44);
      I2 = DM(0x2dde48);
      I3 = DM(0x2dde4c);
      I4 = DM(0x2dde50);
      I5 = DM(0x2dde54);
      I12 = DM(0x2dde58);
      M0 = DM(0x2dde5c);
      M1 = DM(0x2dde60);
      M2 = DM(0x2dde64);
      M3 = DM(0x2dde68);
      M4 = DM(0x2dde6c);

      // the two instructions the entry JUMP replaced (0x1c9448, 0x1c944a)
      I5 = DM(-24, I6);
      R10 = DM(-34, I6);
      JUMP 0x1c944c;
.bl_loop..end:
      .type bl_loop.,STT_FUNC;
