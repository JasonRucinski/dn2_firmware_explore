// trim.asm -- Waverider's level trim: one gain factor per voice, for the oscillators, the sub
// and the noise (docs/waverider-trim.md).
//
// Our own code, assembled with selache's `selas` (GPL-3.0, used as a tool and never linked
// in), run offline in digikit's SHARC executor and checked bit for bit against
// dnfw.waverider.live.render_two (scripts/sharc_waverider_m5.py); it has never run on a DSP.
//
// Entered by `JUMP` from machine9_live.asm's wr_t5v_lev_on, in place of its jump to the
// modulator, once per voice and oscillator, and left by `JUMP` to the modulator (wr_mod,
// sw 0x16f700). It reads this voice's TRIM word (WaveTone's FINE, sound parameter 49: frame
// byte offset 168 + 2 x 49 = 266 in the voice's 146-byte slot at 0x25c48c + 146t), takes its
// coarse byte >> 1 as an index 0..63 into the 64 float32 factors at 0x2e0300
// (dnfw.waverider.live.trim_table), and stores the one it finds at 0x2de6c8. The gains the
// loop, sub.asm and noise.asm form (LEV, SUB, NOIS as a float, times a constant) take that
// word where they took f32(1/25600): the factor is f32(10^(dB/20) / 25600), so LEV 100 with
// the knob at its centre (the record's stock default) comes out at -11 dB, the level of a
// default WaveTone.
//
// In: R9 = t (the voice), R4 = POS, R14 = LEV, DM 0x2de6c4 = the oscillator (all kept for wr_mod).
// Out: DM 0x2de6c8 = the factor. Clobbers R0-R2, R10-R12, I0 (the modulator's own set).
// Only forms the firmware itself uses, and every add has R8-R15 first (reader_m5.asm).
//
// PLACEMENT IS FIXED at PM sw 0x170100 (DM 0x2e0200), in the gap after sync.asm; the table
// follows at 0x2e0300 and ends where SYNC's note table starts, 0x2e0400.

.SECTION/PM seg_pmco;

.GLOBAL wr_trim.;
wr_trim.:
      // the voice's frame, 0x25c48c + 146t, plus 266: its TRIM word
      R10 = LSHIFT R9 BY 7;
      R11 = LSHIFT R9 BY 4;
      R10 = R10 + R11;
      R11 = LSHIFT R9 BY 1;
      R10 = R10 + R11;
      R12 = 0x25c596;                   // 0x25c48c + 266
      R10 = R12 + R10;
      R1 = -4;
      R1 = R10 AND R1;
      I0 = R1;
      R0 = DM(0, I0);                   // the pair of 16-bit words that holds it
      R2 = 2;
      R2 = R10 AND R2;                  // 0: the low half, 2: the high
      R2 = LSHIFT R2 BY 3;              // 0 or 16
      R1 = R1 - R1;
      R1 = R1 - R2;
      R0 = LSHIFT R0 BY R1;             // the word down to bit 0
      R12 = 0xffff;
      R0 = R0 AND R12;
      R0 = LSHIFT R0 BY -9;             // coarse >> 1: 0..63
      R1 = 63;
      R0 = MIN(R0, R1);
      R0 = LSHIFT R0 BY 2;              // a float32 each
      R12 = 0x2e0300;
      R0 = R12 + R0;
      I0 = R0;
      R0 = DM(0, I0);                   // the factor
      DM(0x2de6c8) = R0;
      JUMP 0x16f700;                    // -> wr_mod.
