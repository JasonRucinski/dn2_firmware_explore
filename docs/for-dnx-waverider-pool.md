# For DNX: renaming tables and the per-project wavetable pool

What the firmware will add to the Waverider store and the Data API, so that DNX's Library tab
(DNX option 1) and the instrument's PRESET/KIT page 2 (option A) can manage wavetables. Decided
by the owner on 2026-10-06:
- the pool is **per project**: up to 128 tables, chosen from the +Drive store, saved and loaded
  with the project;
- a sound remembers a **pool slot**.

The store itself, the index entry and the `/waverider` route are in `docs/waverider-store.md`; this
builds on them and changes none of it. **Status: revision 3, with DNX's answers of 2026-10-06
folded in (listed at the end). Built and passing in the emulator (2026-10-06): the rename
(§1), the records and the `/wavepool` route (§2), Waverider playing from record 0, and SAVE
PROJECT AS / LOAD PROJECT copying the records, CREATE NEW starting an empty list, and the
instrument's wavetable page (a second writer of record 0, below). Not built yet: RENAME
on the instrument.**

## The numbers (read this first)

One table has several numbers. Every field below says which one it carries.

| name | range | what it is |
|---|---|---|
| **store slot** | 0..255 | the index entry and the `/waverider/<n>` path (`docs/waverider-store.md`) |
| **pool index** | 0..127 | an entry in a project's pool list |
| **shown slot** | 1..128 | what both UIs display: pool index + 1 |
| **coarse** | 0..129 | what a sound stores in TBL1 / TBL2 (the parameter word's high byte) |
| **project slot** | 0..128 | which project a pool list belongs to: 1..128 as `/projects` numbers them, and **0 for the working project**. The only number here where 0 is not "the first": the listing names it `working` |

The conversions:
- coarse 0 and 1 are the built-in tables, Prim. and Harm. They're in no pool and have no shown
  slot;
- coarse c >= 2 is pool index c - 2, and shown slot c - 1;
- a pool entry holds a store slot.

So a sound reaches a table in two steps: its coarse gives a pool index, and the project's pool
list gives the store slot at that index.

Usage is DNX's to compute, with no route for it. Read TBL1 (slot 27) and TBL2 (slot 33) of every
sound whose machine is **5**, never 1. The two TBL saves the owner is making will locate those
bytes in a saved project.

## 1. Rename in place

**A write of the index entry alone.** Use the write you already use (`0x57` open, `0x58` chunks,
`0x59` commit) on `/waverider/<store slot>`, in the same container as a slot file, with a body of
exactly **128 bytes**: an entry, and no table after it. The firmware takes that as a rename.
- **Only the name is read: bytes 32..95.** Every other byte of the body is ignored, so the
  geometry, the hashes and the extent can't change, by construction rather than by comparison.
  A client needn't fetch the stored entry first; zeros are fine everywhere but the name.
- The name is checked as a stored name is: Windows-1252, NUL-terminated inside the 64 bytes.
- The slot must be in use. A free slot is refused.
- Only the index is written (the non-current group, then its superblock, generation + 1), never
  the slot's data. So a rename is one index write: no 512 KiB, and no risk to the samples.
- The refusals answer the way a write's do today: the commit returns an error, and
  `wr_write.last` says why.
- **How to prove it:** a read-back of the file can't match what was sent (the stored file is
  128 + N bytes). Re-list `/waverider` and compare the name at that slot, as a commit that can't
  refuse is proven today.

Today a body of 128 bytes or less is refused ("the file must be a 128-byte entry and a table").
This makes exactly 128 the rename and leaves everything else as it is.

## 2. The pool lists

### On the +Drive

The store region has 2,048 unused sectors between group B and slot 0's data: `0x600800..0x601000`.
Each project slot p (0..128) gets **two sectors**, written alternately like the index groups:
- **A at `0x600800 + p`**;
- **B at `0x600900 + p`**.

The two copies of one record are 256 sectors apart, not neighbours, for the same reason the index
groups are apart. 258 sectors in all, ending at `0x600981`.

The current record is the valid one with the higher generation; on a tie A wins. **If neither is
valid, the project's pool is empty** (revision 5, 2026-10-13; until then it followed the
store-order pool, which only a record with the flag below does now).

**A pool record**: 512 bytes, every multi-byte field big-endian, as in the store.

| offset | field |
|---|---|
| 0 | magic `"WRPL"` |
| 4 | version u16 = 2 (a version 1 record is read and converted, see Revision 4) |
| 6 | **project slot** u16: 0..128, and it must equal the record's place |
| 8 | generation u32: 1 or more in a stored record; 0 only in a read with no record behind it |
| 12 | entries in use u16: **the count of entries that are not `0xFFFF`** (not the highest used index + 1) |
| 14 | flags u16: bit 0 = **follows the store** (named *automatic* until 2026-10-13; the bit did not move); every other bit 0 |
| 16 | 128 × u16 (version 1: 127, the 128th read as `0xFFFF`): entry j is the **store slot** at **pool index** j, or `0xFFFF` for none |
| 272..507 | zero (version 1: 270..507) |
| 508 | xxHash32, seed 0, over bytes 0..507 |

**Follows the store** means "this project plays every stored table the pool can play, in store-slot
order, the first 128 of them". With the flag set, the entries are not used. It is a deliberate
opt-in: a project with no record at all plays **nothing** from the store (revision 5, below), and
only a stored record with this flag plays the store's order.

**Three states, as both sides name them** (DNX's `poolState`). Two read almost alike and
differ by one byte, the flags word's low half:

| state | generation | follows the store | what a sound reaches |
|---|---|---|---|
| empty | 0 (no stored record) | no | nothing: no table plays from the store until one is put in a pool |
| follows the store | 1 or more | yes | every playable table, in store-slot order, on purpose |
| list | 1 or more | no | exactly the entries, which may be none (a new project's) |

An entry may name a store slot that is free, or whose table the DSP can't play (not 16 × 512).
That pool slot then plays the built-in Prim., as an unknown slot does today. The record is valid
anyway: deleting a table must not break every project that uses it. DNX should warn about it,
not repair it on its own.

**What a record can't see.** An entry holds a store slot and nothing else. If a table is deleted
and a different one uploaded into the same store slot, every pool naming that slot plays the new
table, and nothing can tell. Carrying each entry's hash would take 128 × 6 bytes, which doesn't
fit in 512, so this is documented rather than widened.

**An upload shows up in an old project's pool by itself** (seen on the instrument,
waverider-wtpool1, 2026-10-06). That was the rule then: a project with no record followed the
store-order pool. **Revision 5 (2026-10-13) reversed it**: a project with no record is empty, as a
CREATE NEW project always was, and the owner read the old behaviour as a bug. Only a project
whose stored record has the follows-store flag is filled by an upload.

**What the store-order pool can't hold steady.** Its order is store-slot order, so an upload into a
free store slot below the others shifts every later pool index, and sounds in a follows-store
project then play other tables. That is today's behaviour, unchanged; writing an explicit record
pins a project.

### The route

**A new root entry, `wavepool`**, listing 129 entries, **0..128 = project slot**, with the same
long-form layout as `/waverider`'s:
- the name: `working` for 0, and the decimal project slot for 1..128 (`1`..`128`). DNX joins 1..128
  to the `/projects` names itself; the record holds no project name, because the stock project
  operations don't carry pools along (below), so only a join can be truthful;
- occupancy `01 01` when that project slot has a valid stored record (follows the store or not, empty or
  not), `00 00` when it has none (an empty pool);
- the size is 512; permissions `0x007e`.

**Occupancy says "a record exists", never "the user chose this pool".** A backup and restore of a
slot that had no record leaves a stored empty list there: it plays the same, but occupancy
flips from `00 00` to `01 01`. Nothing downstream should read intent into it.

The `/` reply then declares and carries 5 entries.

**The file**, both ways, is the same container as a `/waverider` file (31-byte header, payload,
12-byte trailer) around a 512-byte payload, the record:
- content kind **`0x50`** ('P'), not `0x57`, so a pool file sent to `/waverider` or read as a
  table is refused rather than misread;
- object version 2 (a version 1 file is accepted and converted);
- index (`0x15`) = the project slot, byte `0x18` = p;
- uncompressed length 512;
- **raw** (`0x1D` = 0), as `/waverider`.

- **Read:** `/wavepool/<project slot>`, as `/waverider/<n>` is read. It returns the current
  record. A project slot with no valid record returns what that project plays: the right magic,
  version and project slot, **generation 0**, the flag clear, every entry `0xFFFF`, the count 0, and
  a correct hash (revision 5; before it the flag was set and the entries were filled with the
  store-order pool). So a read always says what plays, and generation 0 is how to tell "no record"
  from a stored empty list. A stored follows-store record reads with its flag set, the entries
  filled with the store-order pool as it stands now, and its own generation.
  **A record read from a follows-store slot describes what plays; it is not a template for a
  write.** Written back unchanged it is refused (below). To edit such a pool, clear the flag,
  keep or change the entries, and write an explicit record.
- **Write:** `/wavepool/<project slot>`, the whole record.
  - **Checked:** the container (kind `0x50`, version 2 or 1, raw, length 512), the magic, the
    version, the project slot against the path, the flags (only bit 0), bytes 272..507
    zero (270..507 for version 1), and the hash.
  - **Without the follows-store flag, also checked:** every entry `0xFFFF` or 0..255, and the count
    against the entries.
  - **With the follows-store flag, also checked:** every entry `0xFFFF` and the count 0. **An
    follows-store write that carries entries is refused, not ignored**: otherwise read whole, edit
    entry j, write whole on a project with no record would report success, verify clean and
    discard the edit.
  - **The generation you send is a compare-and-swap** (DNX, 2026-10-06, before the instrument's
    pool page becomes a second writer of record 0). Send **0** for "no check", or the
    generation you read and expect to replace (0 also matches a slot with no record). A
    non-zero generation that isn't the current one is refused: another writer has written
    since, and its edit is kept. Either way the firmware writes the non-current sector with
    the current generation + 1. As with every commit refusal, the reply can't say so (the
    session has answered first). The read after the write shows it, by the **entries**,
    not the generation: if the other writer landed between your read and your write, the
    generation reads sent + 1 from *their* write while yours was refused. `wp_write.last`
    = 26 (16 + 10) says why, but only to a probe PEEK, which a user doesn't have.
  - **No partial writes:** the record is small, so it's always whole.
  - **How to prove it, one rule for both kinds:** read before, write, read after. **The
    generation advanced, and the fields the writer set came back.** For an explicit record those
    are the flags and the entries; for a follows-store one, only the flag, since it reads back with
    the entries filled, so the generation is the evidence that anything happened. With a
    compare-and-swap write, **the entries are the proof** and the generation only
    corroborates: a read-back without the list you sent means not written (a conflict, or
    a malformed record, refused the same silent way); reload, or write again with the
    current generation to overwrite. (A read-back that carries your list though another
    writer wrote it is the same pool either way.)
- **Delete:** not offered. A follows-store record (entries cleared) makes a project follow the store again, and an
  empty, explicit record (count 0) is a pool with nothing in it.

Every project's list is readable, not only the working project's. That is what lets DNX say
"this table is in three projects' pools" before a delete, with no other verb.

### What the instrument does with them

- **Project slot 0 is the working project's pool**: the one TBL plays and the instrument's pool page
  edits. It is kept with the working project, so it survives a reboot as everything else does
  (the working-project rule).
- **SAVE PROJECT to slot k** writes record k as record 0 reads: a stored record is copied, and
  with no record 0 an empty list is written. Either way k then has a record of its own.
- **LOAD PROJECT k** writes record 0 as record k reads, then refills the DSP's pool from it: a
  stored record is copied, and with no record at k an empty list is written. One sector
  write either way, so an interrupted load leaves the old pool or the new one, never a mix.
- **A write to record 0 from DNX** refills the DSP's pool, as a write to the store does today
  (`wr_store.changes`). A write to any other record changes only the +Drive.
- **While record 0 follows the store**, a store write refills the pool as today. While it is
  absent or an explicit list, a store write changes nothing that plays.
- **Editing the pool on the instrument** while record 0 follows the store first writes it out as an
  explicit record (what plays now), then applies the edit; with no record it starts from an empty
  list.
- **The instrument's edits can change several entries in one write** (since 2026-10-07, the
  stock-style lists; `wt_pool_add_many`, `wt_pool_clear_many`), so one generation step may cover
  a batch:
  - **ADD TO POOL** places each ticked table, in row order (store order), in the **first empty
    entry left at that moment**. A cleared entry is reused first: clear shown slot 3, add six,
    and the first of the six lands at 3.
  - A table already in the pool is skipped and takes no entry. When the pool fills, the rest
    aren't added; the title says how many were.
  - **CLEAR SLOT** empties every ticked entry; the others don't move.

### A pool entry whose table is gone (asked by DNX, 2026-10-14)

A pool entry holds a **store slot number**, and a sound's TBL holds a **pool position** (TBL 2
is pool entry 0, shown as T:001). The two are never checked against each other except when the
pool fills. Read from the code (`csrc/waverider/pool.c`, `wtedit.c`, `wtlist.c`,
`csrc/wrstore/route.c`); where something ran, it says so.

1. **What plays.** When the pool fills, entry j becomes a table only if store slot n holds a
   table the DSP can play (`wr_store_playable`: in use, 1 to 64 waves of 64 to 4096 points, a
   power of two, in its own extent). Otherwise entry j is empty, and a sound whose TBL points at
   it **plays Prim.**, exactly as a TBL past the pool's count does. The page lists that entry as
   **MISSING**, and LOAD on it says ITS TABLE WAS DELETED. The pool's count is the last entry
   that holds a table, plus one, so a missing entry at the end shortens the range TBL can be
   turned through; a sound already pointing past it keeps its value and plays Prim. On the
   instrument: step 10 of the `waverider-wtpool1-usbprobe` test (2026-10-06) was a delete
   followed by MISSING and Prim.; the owner reported "all programmed tests pass", but that step
   was marked optional and whether it ran is not recorded.
2. **The entry survives untouched.** Neither delete touches any pool list: the instrument's
   DELETE (`wt_store_delete`) and DNX's delete over USB (`0x5c`, `wr_commit_fill`) both write a
   free index entry for slot n and nothing else. Every project's list keeps naming slot n until
   CLEAR SLOT empties that entry, or DNX writes the list without it.
3. **ADD TO POOL treats it as occupied.** It fills the first entry holding no slot number
   (`0xFFFF`); an entry naming an empty store slot is not that, so it is never reused by an add.
   And adding slot n itself while an entry still names it says ALREADY IN THE POOL and adds
   nothing.
4. **A new table written to the same store slot plays there.** Yes: the next fill finds slot n
   playable again, and every pool entry naming n, in every project, plays the new table, however
   unrelated, under its new name. The instrument never writes a table into a slot (only DNX
   does, choosing the slot number), so whether this happens is up to the writer: writing new
   tables to free slots that no pool list names avoids it. This is why neither side clears
   entries on anyone's behalf: clearing would free the entry, the next ADD TO POOL would fill it,
   and every sound still pointing at that position would play the added table instead.
5. **A region erase is different.** `/wavepool/129` (`docs/for-dnx-waverider-erase.md`) zeroes
   the store's index **and both sets of pool records** for every project. Afterwards no entry
   names any slot: there is nothing MISSING, every project's pool is empty, and every sound with
   TBL at T:001 or above plays Prim. (count 0). A table written later to any slot plays nowhere
   until it is added to a pool. Then it lands in the first empty entry, T:001 on an empty pool,
   so a sound still set to T:001 plays it: a sound follows its pool position, not a table. In the
   emulator (`scripts/emu_waverider_erase.py`, 11 of 11, 2026-10-13): after the erase, project 0
   reads as an empty pool (generation 0, no flag, no entries) and neither listing has anything.

**Not covered yet (it needs the stock project operations hooked):** copying, moving, clearing or
deleting a project from the instrument's own project manager doesn't carry its pool list along. The
pool record stays at the old project slot. Until that is built, DNX should treat a pool record as
belonging to whatever project now sits in that slot, and say so when it can tell.

## 3. What changes for the pool you see today

**Revision 5 changes this**: every project with no record (every project saved so far, by stock
firmware or by DNX) has an empty pool from the build that carries it. Tracks that played a pool
table play Prim. until a table is put in the project's pool; no migration is written. A
project DNX writes to slot k plays from the moment it loads; the pool write is not a second
step that has to happen with it. There is no first-boot migration: record 0 absent is the
ordinary case.

## Not in the firmware: DNX's backup

`backup.ts` covers projects, soundbanks and kits, so neither `/waverider` nor `/wavepool` is in a
full backup today: a restored project gets sounds pointing at tables that aren't on the card. That
is DNX's to add; the pool makes it matter more than the store alone did. So does
`STORED_FORM_BY_ROOT`, which needs `wavepool` listed as raw.

## Changes from revision 1 (DNX, 2026-10-06)

1. **Rename reads only the name** (bytes 32..95) and ignores the rest, instead of requiring every
   other byte to equal the stored entry. Same guarantee by construction, no stale-hash input, no
   read before the write.
2. **The project-slot numbering stays** (1..128 as `/projects`, 0 = working); the listing names
   entry 0 `working`.
3. **A and B are 256 sectors apart** (`0x600800 + p`, `0x600900 + p`), not neighbours.
4. **Entries in use** is defined: the count of entries that are not `0xFFFF`. It is now a u16,
   with a flags u16 beside it.
5. ~~**No valid record means the store-order pool**, not an empty one.~~ **Reversed in revision 5
   (2026-10-13): no valid record means an empty pool.** The follows-store flag stays, as the one
   sector write that makes a project play the store's order on purpose.
6. **The file form** is stated: the transfer container, kind `0x50`, raw, a 512-byte payload.
7. **Two blind spots documented**: a reused store slot, and the store-order pool's order.

## Changes from revision 2 (DNX, 2026-10-06)

1. **A follows-store write with entries is refused** (every entry `0xFFFF`, count 0), not ignored.
   A read of a follows-store slot describes what plays and is not a template for a write.
2. **The write proof is one rule**: the generation advanced, and the fields the writer set came
   back.
3. **Occupancy means a record exists**, not a user's choice (a restore can flip it).

## Built (2026-10-06, emulator)

- **Rename** (`csrc/wrstore/route.c`): `scripts/emu_waverider_rename.py`, 7/7. The body's
  other 64 bytes are sent as `0xA5` and ignored; the listing shows the new name; a full
  read-back has the stored entry but for the name, and the table unchanged; a free slot is
  refused at the first chunk; a name with no NUL writes nothing.
- **`/wavepool`** (`csrc/wrstore/poolroute.c` over `records.c`):
  `scripts/emu_waverider_wavepool.py`, 12/12. `/` carries 5 entries, `wavepool` last;
  the listing is 0..128 with 0 `working`; a no-record read is generation 0, follows the store,
  entries filled; a follows-store write carrying entries is refused; explicit writes read
  back with generation 1 then 2 (the second sending the generation it replaces); a stale
  generation (1, then 77) is refused and the record stays at 2; a stored follows-store record
  reads back filled; a bad hash, project slot, reserved byte or count writes nothing; a
  kind `0x57` container, 511 bytes and project slot 129 are refused with a message.
- **Waverider plays record 0** (`csrc/waverider/pool.c`): `scripts/emu_waverider_pool.py`,
  10/10 with no record (the store-order pool, as before) and 10/10 with `--record` (a list
  `[3, 5, 0]`: entry 0 is slot 3, entry 1 empty since slot 5 is not playable, entry 2
  slot 0, count 3).
- Not measured: which of a record's two sectors a write lands in. The read-back proves
  the generation, not the sector; the alternation is by the code (records.c).
- **SAVE PROJECT AS and LOAD PROJECT** (`csrc/wrstore/projects.c`): hooks at the entries of
  `0x400f6960(this, slot, progress)`, the save to a slot, and `0x400f6a2c(handle, slot,
  project, progress)`, LOAD PROJECT's read. Both slots are 0-based; 128 is the working
  copy, which every save, load, boot and CREATE NEW also writes, and which the hooks
  leave alone. Measured on stock 1.11 first (panel_drive `--regs-at`): SAVE PROJECT AS 002
  is save(1) then save(128); LOAD PROJECT 002 is load(1) then save(128); CREATE NEW is
  save(128) alone. `scripts/emu_waverider_projects.py`, 6/6, the panel doing what the owner
  would and the Data API reading the records:
  - SAVE AS 002 with no record 0: record 2 is a stored follows-store record;
  - record 0 written as `[3, NONE, 0]`, SAVE AS 003: record 3 is that list;
  - record 0 written as `[7]`, LOAD 003: record 0 is `[3, NONE, 0]` again;
  - LOAD 002: record 0 follows the store;
  - `wr_projects`: 2 saves, 2 loads, none failed.
- **CREATE NEW starts an empty list** (the owner, 2026-10-06: "like the sound pool"). After
  CREATE NEW's save of the new working project (`0x400428c0`, its call of `0x40040288` at
  `0x40042b60`, reached from the LOAD list through `0x4009ab30`, measured), record 0 is
  written as an empty list: stored, count 0, explicit. So a new project's TBL reaches
  only Prim. and Harm. until tables are added to its pool. Projects saved before the lists
  keep the store-order pool, so none goes silent. **Not measured:** `0x400428c0`'s two other
  callers (`0x4009c3a2`, `0x400f66fc`) were never reached in a test. That they also make a
  new working project, and so get the same empty list, is read from where they sit in the
  code, not observed.
  `scripts/emu_waverider_projects.py`, now 7/7: CREATE NEW after LOAD 002 leaves record 0
  empty, stored, explicit, generation advanced; `wr_projects.created` 1.

## Changes from revision 3 (DNX, 2026-10-06)

1. **The generation sent on a write is a compare-and-swap**: 0 for no check, or the current
   generation; any other is refused. It closes the lost update between two writers of record
   0 (DNX and the instrument's pool page), with no field added. The proof of such a write
   is the entries read back, not the generation (DNX: a refused write next to the other
   writer's still reads sent + 1).
- **The instrument's wavetable page** (PRESET/KIT page 2, `csrc/waverider/wtmenu.c`,
  `wtlist.c`, `wtedit.c`) writes too. Every edit is one in-place write of record 0 with
  generation + 1, so a DNX write sending the generation it read before is refused:
  - ADD TO POOL: a store slot into record 0's first `0xFFFF` entry;
  - CLEAR SLOT: an entry back to `0xFFFF`;
  - a project on the store-order pool (or with no record) gets what plays written out as a
    list, then the edit;
  - DELETE (asked first): frees the store slot's index entry, a new index generation as a
    `0x5c` delete makes. **No record is changed, record 0 included** (warn, don't repair,
    one rule): ADD TO POOL fills the first `0xFFFF` entry, so clearing the slot would hand
    every sound still on it an unrelated new table, where a dangling entry plays Prim.
    (DNX, 2026-10-06). The lists show such an entry as MISSING, it doesn't count as free,
    LOAD refuses it, and CLEAR SLOT frees it on purpose;
  - LOAD: the active track's TBL1 / TBL2 in the kit sound; no record change.
  Emulator: each step's frames, and record 0 still `[3, 5, 0]` gen 1 after a DELETE, read
  over the Data API.

## Revision 4 (agreed with DNX, 2026-10-06; built: `csrc/wrstore/records.c`, RECORD_VERSION 2): 128 pool slots

> **Note, 2026-10-13:** the sections above were written for version 1 and have been corrected to
> version 2 (DNX pointed out the lag; DNX's emulator test wrote a version 2 record to project slot 7
> and read it back). This section is kept as the record of what changed and why. The firmware
> stores only version 2; it converts a version 1 record in place when it reads one.

The owner: a pool of 128 tables, beside the 128-sound pool. Built on
`feature/waverider-pool-128`; until then `waverider-wtpool1` is v1 (127).

- **Numbers:** pool index 0..127, shown slot 001..128, coarse 0..129 (0 and 1 still Prim. and
  Harm., 2..129 the pool; still a byte). TBL's range goes to 129. The store-order pool is the
  first 128 playable tables in store-slot order.
- **Record version 2:** the same 512 bytes and header; 128 × u16 entries at 16..271;
  reserved zero 272..507; the hash at 508. The count is still the entries that are not
  `0xFFFF`, now at most 128. **Both version fields say 2**: the container's object version
  (`0x11`) and the record's own (offset 4). They describe the same thing and never disagree;
  a reader checks both.
- **Version 1 stays readable:** 127 entries, the 128th read as `0xFFFF` (v1 reserves its
  bytes, 270..271, as zero, which would otherwise name store slot 0). Reads always return v2.
  Writes:
  - **a v1 write is accepted and converted**, not refused: a refusal at the commit can't
    speak, and v1 to v2 is total, lossless and unambiguous (127 entries and an empty 128th);
  - the firmware stores only v2; SAVE, LOAD and CREATE NEW copy as v2;
  - **the condition, not the rule:** a future version that changes what a field *means*,
    rather than adding one, is refused instead, because converting it would silently give
    wrong data.
- **Both sides model 128 entries for either version** (DNX: the last `undefined` for a v1
  record): the version decides the bytes, not the shape a caller sees.
- **The DSP:** the load area starts 4 KiB lower, at `0x807ff000`: the pool directory at its
  start, table j at `0x80800000 + 16 KiB × j` as before, so 128 tables fill the 2 MiB that
  127 and the directory shared.
- **Vectors:** the firmware produces v2 vectors once built; DNX's three v1 vectors stay as
  read cases (the v1 compatibility path's regression).
- Not added: a hash per referenced table (128 of them don't fit in the reserved bytes); the
  reused-store-slot blind spot stays documented.

## Revision 5 (2026-10-13; owner's call): a project with no pool plays no wavetable

The owner opened a project on the +Drive that predates the records and saw every stored table in
its pool. He read it as a bug: "A project with no pool should not play any wavetable and the pool
should show empty." So:

- **No valid record** is an empty pool. A read of such a slot returns generation 0, flags 0,
  count 0, all 128 entries `0xFFFF`, a correct hash. The container and the 512 bytes are as
  before; only the values differ.
- **The follows-store flag stays** (bit 0), as a deliberate opt-in, and records that already carry it
  keep their meaning. Reading one still fills the entries; writing one back with entries is
  still refused.
- Writing back a read of an empty slot stores an empty explicit list. That read-then-write case
  is harmless now.
- SAVE AS and LOAD of a project with no record copy "empty" (an empty list), not a follows-store
  record. CREATE NEW is unchanged (an empty list).
- **Existing projects go silent** on their pool, with no migration. Tracks that played pool tables
  play Prim. (TBL 2 and up) until a table is put in a pool.
- The erase control (`docs/for-dnx-waverider-erase.md`) is unaffected; after it, every project reads
  as empty.
