// accel.asm -- do the DSP's filter accelerators, FIR0 and IIR0, compute what digikit's models say?
//
// Our own code, assembled with selache's `selas` (GPL-3.0, used as a tool and never
// linked in). A diagnostic, never a mod: the build is scripts/build_accelprobe.py, the
// jobs and their TCBs are dnfw.waverider.accelprobe's, and tools/dn2accel.py reads the
// result and compares it, bit for bit, with digikit's FIR0 and IIR0 models.
//
// The idle loop's back edge jumps here; this goes on to idle_load.asm (wr_idle), which jumps
// back to the loop's top. So it only runs when the DSP has nothing else to do.
//
// The first call runs every job of the RUNS table, in order. For each: CTL1 = 0, a read of
// DMASTAT (the read clears WDONE and ACDONE on the chip), CHNPTR, then CTL1 (EN | DMAEN and
// the job's bits) starts it. DMASTAT is polled until ACDONE, at most LIMIT reads; then
// CTL1 = 0. RESULTS gets the EMUCLK cycles from the start to ACDONE, the DMASTAT read that
// showed it, and the reads it took (LIMIT: it never finished).
//
// Every call after that publishes one more half of the words PUBTAB names (the jobs' outputs,
// their write-back words and RESULTS), every 64th call, to reply word 2 of both reply pages:
// TAG << 16 | HALF, halves swapped as reply word 0, so the ColdFire reads a big-endian u32.
// TAG = k + 1 for the half k (word k >> 1, the high half when k is odd), so 0 is never sent.
// Reply word 2 is block_count.asm's, absent from this build (idle_load.asm keeps 1, 3, 4).
//
// It uses R0-R7, I0-I2, saved to its own area and restored before wr_idle; ASTAT is free
// (the idle loop recomputes what it tests).
//
// PLACEMENT IS FIXED: this code loads at PM sw 0x16f800 (L1 block 1, byte 0x2df000).
//
// DM (byte addresses, the build's state block at 0x2df800):
//   0x2df800..0x2df828  save: R0-R7, I0, I1, I2
//   0x2df840  PHASE (0: the jobs are to run)   0x2df844  TICK   0x2df848  PUBI (the next half)
//   0x2df84c  NRUNS   0x2df850  NHALVES (2 x the words in PUBTAB)
//   0x2df854  the RUNS entry next, 0x2df858  the RESULTS entry next
//   0x2df880  RUNS: 16 bytes a job (the accelerator's MMR base, CHNPTR, CTL1, 0)
//   0x2df900  RESULTS: 16 bytes a job (cycles, the DMASTAT read, reads, 0)
//   0x2dfa00  PUBTAB: a DM byte address a word
//   0x2c49d8 / 0x2c59d8  reply word 2

.SECTION/PM seg_pmco;

.GLOBAL wr_acc.;
wr_acc.:
      DM(0x2df800) = R0;
      DM(0x2df804) = R1;
      DM(0x2df808) = R2;
      DM(0x2df80c) = R3;
      DM(0x2df810) = R4;
      DM(0x2df814) = R5;
      DM(0x2df818) = R6;
      DM(0x2df81c) = R7;
      DM(0x2df820) = I0;
      DM(0x2df824) = I1;
      DM(0x2df828) = I2;

      R0 = DM(0x2df840);                // PHASE
      R0 = PASS R0;
      IF NE JUMP 0x16f898;              // -> wr_acc_pub.
      R7 = DM(0x2df84c);                // NRUNS

.GLOBAL wr_acc_run.;
wr_acc_run.:
      R7 = PASS R7;
      IF EQ JUMP 0x16f890;              // -> wr_acc_ran.
      R0 = DM(0x2df854);
      I1 = R0;                          // this job's RUNS entry
      R2 = 16;
      R0 = R0 + R2;
      DM(0x2df854) = R0;
      R0 = DM(0x2df858);
      I2 = R0;                          // its RESULTS entry
      R0 = R0 + R2;
      DM(0x2df858) = R0;

      R1 = DM(0, I1);                   // the accelerator's base: CTL1
      I0 = R1;
      R0 = R0 - R0;
      DM(0, I0) = R0;                   // CTL1 = 0
      R2 = 4;
      R2 = R1 + R2;
      I0 = R2;
      R0 = DM(0, I0);                   // DMASTAT: the read clears WDONE and ACDONE
      R2 = 0x70;
      R2 = R1 + R2;
      I0 = R2;
      R0 = DM(1, I1);
      DM(0, I0) = R0;                   // CHNPTR
      R2 = 4;
      R2 = R1 + R2;
      I0 = R2;                          // DMASTAT, for the poll
      R2 = DM(2, I1);                   // CTL1
      I1 = R1;
      R5 = R5 - R5;                     // reads
      R6 = 0x40;                        // ACDONE
      R3 = 1000000;                     // LIMIT
      R4 = EMUCLK;
      DM(0, I1) = R2;                   // start

.GLOBAL wr_acc_poll.;
wr_acc_poll.:
      R0 = DM(0, I0);
      R2 = R0 AND R6;
      IF NE JUMP 0x16f87e;              // -> wr_acc_done.
      R2 = 1;
      R5 = R5 + R2;
      COMP(R5, R3);
      IF LT JUMP 0x16f870;              // -> wr_acc_poll.

.GLOBAL wr_acc_done.;
wr_acc_done.:
      R2 = EMUCLK;
      R2 = R2 - R4;
      DM(0, I2) = R2;                   // cycles
      DM(1, I2) = R0;                   // the DMASTAT read
      DM(2, I2) = R5;                   // reads
      R0 = R0 - R0;
      DM(0, I1) = R0;                   // CTL1 = 0
      R2 = 1;
      R7 = R7 - R2;
      JUMP 0x16f82b;                    // -> wr_acc_run.

.GLOBAL wr_acc_ran.;
wr_acc_ran.:
      R0 = 1;
      DM(0x2df840) = R0;                // PHASE: publish from now on
      JUMP 0x16f8e3;                    // -> wr_acc_out.

.GLOBAL wr_acc_pub.;
wr_acc_pub.:
      R0 = DM(0x2df844);
      R1 = 1;
      R0 = R0 + R1;
      DM(0x2df844) = R0;                // TICK
      R1 = 63;
      R0 = R0 AND R1;
      IF NE JUMP 0x16f8e3;              // -> wr_acc_out.
      R0 = DM(0x2df848);                // k
      R1 = LSHIFT R0 BY -1;
      R1 = LSHIFT R1 BY 2;
      R2 = 0x2dfa00;                    // PUBTAB
      R1 = R1 + R2;
      I0 = R1;
      R2 = DM(0, I0);                   // the word's address
      I0 = R2;
      R2 = DM(0, I0);                   // the word
      R3 = 1;
      R3 = R0 AND R3;
      IF EQ JUMP 0x16f8c6;              // -> wr_acc_low.
      R2 = LSHIFT R2 BY -16;            // k odd: the high half

.GLOBAL wr_acc_low.;
wr_acc_low.:
      R3 = 0xffff;
      R2 = R2 AND R3;                   // HALF
      R3 = 1;
      R4 = R0 + R3;                     // TAG = k + 1
      R2 = LSHIFT R2 BY 16;
      R2 = R2 OR R4;                    // halves swapped: the ColdFire reads TAG << 16 | HALF
      DM(0x2c49d8) = R2;                // reply word 2, both pages
      DM(0x2c59d8) = R2;
      R3 = DM(0x2df850);                // NHALVES
      COMP(R4, R3);
      IF LT JUMP 0x16f8e0;              // -> wr_acc_next.
      R4 = R4 - R4;

.GLOBAL wr_acc_next.;
wr_acc_next.:
      DM(0x2df848) = R4;                // PUBI

.GLOBAL wr_acc_out.;
wr_acc_out.:
      R0 = DM(0x2df800);
      R1 = DM(0x2df804);
      R2 = DM(0x2df808);
      R3 = DM(0x2df80c);
      R4 = DM(0x2df810);
      R5 = DM(0x2df814);
      R6 = DM(0x2df818);
      R7 = DM(0x2df81c);
      I0 = DM(0x2df820);
      I1 = DM(0x2df824);
      I2 = DM(0x2df828);
      JUMP 0x16f500;                    // -> wr_idle.
