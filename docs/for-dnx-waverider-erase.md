# For DNX: removing everything Waverider put on the +Drive

What the firmware adds so DNX can offer one settings button, beside "back up device", that returns
the +Drive's wavetable region to the state it had before the first table: every stored table, every
pool list, the store's own bookkeeping. Asked for by the owner on 2026-10-13: a user who wants the
unit as Elektron shipped it (a warranty claim, selling it) needs a way to get there that the stock
menus cannot give, because FORMAT +DRIVE and factory reset only touch stock's own slots and never
our region.

**Status: built and passing in the emulator (`scripts/emu_waverider_erase.py`). Not on an
instrument yet.** The capability bit is `0x80` (`erase`) in `/modinfo`; without it, the build has no
control and DNX must not offer the button.

## What a user should be told

- The erase has to run **before** the stock firmware goes back on: stock has no route to it.
  Someone who already flashed stock has to flash the Waverider build again, erase, and flash stock.
- It removes **all** tables and **all** pool lists, on every project. A project's TBL values keep
  their numbers and play Prim. afterwards, because the pool entries they named are gone.
- It cannot be undone by the firmware. The way back is a copy of every table saved as a file
  before the request is sent (as for a single delete). DNX has no restore from those files yet,
  so the text should say what the copies are for rather than imply an undo.
- It does not touch projects, presets, kits or samples. A project saved with Waverider tracks
  stays; what stock 1.11 does when it loads one is not tested.

## The control

`/wavepool/129`. Not a project: `/wavepool` still lists 0..128. It is written like a pool list:
the transfer container, **kind `0x50`, object version 2, index byte 129, 512 bytes, raw**. A read is
refused at the open (`the erase control cannot be read`).

The body is 512 bytes, big-endian, hashed like a record:

| offset | size | |
|---|---|---|
| 0 | u32 | magic `WRER`, `0x57524552` |
| 4 | u16 | version, `1` |
| 6 | u16 | `0` |
| 8 | u32 | **tables in use**: the entries `/waverider` listed as used when the user confirmed |
| 12 | u32 | **pool lists in use**: the project slots `/wavepool` listed as used |
| 16..507 | | zero |
| 508 | u32 | xxHash32, seed 0, over bytes 0..507 |

`dnfw.waverider.poolrecord.erase_request(tables, lists)` builds it.

**The counts are what the user saw.** The firmware counts the store itself at the commit and
refuses the request when either differs, so a confirmation made on a stale list cannot erase
tables that arrived since (another writer, the instrument's own page). Refresh, show the new
numbers, ask again.

## What the firmware does, in this order

1. **Zeroes the metadata:** both groups' superblock and index (sectors 0..64 of each), both
   sets of pool records (129 sectors each). From this write on the store reads as empty and every
   project follows the store again.
2. **TRIMs the whole region**, sectors `0x600000` for `0x41000` sectors (256 slots of 512 KiB and
   the metadata), with the driver's own TRIM, the call FORMAT +DRIVE makes for its slots.
3. Makes Waverider refill its pool: tracks that played a table play Prim. until a table is back.

A power loss between 1 and 2 leaves unreferenced table bytes and nothing else: the store is already
empty. Repeat the request (counts 0 and 0) to finish the TRIM.

## Verifying, and refusals

Refusals are **silent at the commit**, as for every write on this route: the session has already
answered. DNX proves the result the way it proves a delete:

- list `/waverider`: no entry used;
- list `/wavepool`: no entry used;
- read `/wavepool/0`: generation 0, flag bit 0 (follows the store) set, no entries.

If the lists still show what was there, the request was refused: a stale count, a bad hash, or
the +Drive write failed. The probe (`wp_write.last`, `wp_erase`) says which: `last` 4 erased, 5 the
TRIM returned an error (metadata is gone, data bytes remain), 3 a +Drive write failed, 16 + `WP_*`
refused.

## What is not shown

- The TRIM's effect on the card's contents is verified on the instrument only; the emulator's card
  model answers the erase commands without erasing. The check on a unit is a raw read of the
  region's first sectors (service mode, `#MMCDUMP 00600000 00000200`) after the erase.
- How long it takes on a unit. The metadata is 66 KiB of writes; the TRIM is one command over
  127 MiB. Show a busy state and do not time out under a minute.
- Stock 1.11 loading a project that was saved with Waverider tracks.
