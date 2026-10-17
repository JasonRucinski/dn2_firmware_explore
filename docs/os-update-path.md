# The OS update over USB: what the running OS checks before it erases

Read from the Digitone II **1.11** MAIN OS on 2026-10-17, by static disassembly
(`m68k-linux-gnu-objdump -m m68k:cfv4e`). Nothing here was run on an
instrument or in the emulator. The question came from the owner, who described
what an update through Elektron Transfer does:

1. If reception stops before the end, the update cancels and nothing is flashed.
2. If reception finishes but the file is bad, the unit reboots with its
   installed OS untouched.
3. Only when reception and the checks both succeed does the unit erase flash
   and write the new OS.

The code agrees with all three, with one correction to point 2: the running OS
**verifies** the file before it erases, but it does **not unpack** it. The
sections are decompressed on the next boot, after the old OS is gone.

## The image base is `0x40000400`

The section 3 binary loads at `0x40000400`, not `0x40000000`. Of 15,835 `pea`
immediates in the code, 2,506 land on the start of a string at this base,
against about 250 at every other candidate base. Every address below uses it.

## The normal path: `OsUpgradeMenuView`

The view's strings sit at `0x4021f34e` to `0x4021f40d`: `OS UPGRADE`,
`Waiting for SysEx`, `Receiving`, `Checksum Error`, `PREPARING...`,
`ERASING FLASH...`, `UPGRADE OS NOW?`, `CANCEL OS UPGRADE?`, and the four
failure texts `Missing data!`, `Checksum error!`, `No power adapter` and
`Downgrade not possible`.

### Reception (`processOsUpgradeMessage`, `0x401095f8`)

The view takes progress events from the SysEx receiver:

| Event | Action |
|---|---|
| 21 | Updates the `Receiving` bar with the received and total counts |
| 22 | `Checksum Error`: calls `setUpgradeFail` (`0x40109416`) |
| 20 | Reception is complete. Asks the delegate, then can open `UPGRADE OS NOW?` |
| 23 | Closes the view (`0x40108ab4`) |

At the end of reception the receiver runs the file check (below) once
(`0x40129e1c`). A pass sets its state to 3, and a failure reports the error.

### The file check (`0x400dbc4c`)

It returns 1 for a good file, 3 or 4 for a bad one:

1. **`0x40122418`, the container checksum.** It sums `word ^ index` over
   `size / 4` words from `+8`, and compares the sum with the word at `+4`. It is
   the same `[u32 size][u32 checksum][container]` layout that the recovery
   bootstrap checks (`docs/bootstrap.md`). A failure returns 3.
2. **`0x400d2a60`, the HMAC-SHA256 trailer.** It reads the 11 bytes
   `"Multiplier\0"` at `0x40210592`, derives a 32-byte key with the XOR
   constant at `0x4021b537`, and checks the digest over the container. A failure
   returns 4.

This answers an open question in `docs/ele3-format.md`. The running OS does
check the HMAC trailer, not only the checksums.

### Flashing (`performFlashInBackground`)

The background routine at `0x40108e64` is reached only from
`performFlashInBackground` (one reference, `0x401092de`):

1. It shows `ERASING FLASH...`. The text appears before the last check runs.
2. It fetches the received image (`0x4012173a`). No image returns 2,
   `Missing data!`.
3. It runs the file check again. Any result other than 1 returns that code.
4. It calls `0x400dbc80` (a jump to `0x400f1e26`, not read).
5. It calls the writer, `0x40138e24`. That is the writer's only caller.

The writer runs the file check a **third** time and returns early if it fails.
Then it:

1. erases the flash blocks from `0x80000` that the container covers
   (`0x401354ee`, one call per block, the block size from `0x40135f2a`);
2. writes the container from `+8` in pages (`0x40135dc6`);
3. waits (`0x4013464c(3000000)`), masks the interrupts (`SR = 0x2700`), writes 0
   to `0x48000000`, and writes `0x80` to `0xec090000`. That is the same reset
   the recovery bootstrap uses.

The result codes map to the failure texts in `0x40109598`: 2 is
`Missing data!`, 3 and 4 are `Checksum error!`, 5 is `No power adapter`, and 6
is `Downgrade not possible`. Where codes 5 and 6 are produced was not traced.

## What this confirms, and what it does not

| Owner's point | Code |
|---|---|
| 1. A stopped reception flashes nothing | **Confirmed.** The erase and the write are reachable only through `performFlashInBackground`, after the view sees reception complete |
| 2. A bad file leaves the installed OS | **Confirmed for a file that fails the checksum or the HMAC.** All three checks run before the first erase |
| 3. Erase, then write, only after both succeed | **Confirmed.** The order is: check, erase from `0x80000`, write, reset |

Not covered by these checks:

- **A file that passes the checksum and the HMAC but does not unpack or boot.**
  The writer copies the compressed container. The updater and MAIN OS
  decompress it on the next boot, after the erase. Our build gates
  (`dnfw inspect`, `boot_gate`, `check_coldfire`) exist for this case.
- **A power cut during the erase or the write.** Whether the unit can still
  reach recovery depends on the loader below `0x80000`, and that loader is not
  read.

Not read:

- whether a failure reboots or only closes the view. The fail dialog's button
  (`0x4010871c`) calls the delegate's virtual function at `+16` with 0 or 1, and
  the delegate's class is not resolved;
- what makes the view open `UPGRADE OS NOW?` (the delegate's virtual function at
  `+12`), so whether the unit asks for a confirmation;
- how a stopped reception is detected (a timeout or a cancel);
- where codes 5 and 6 come from.

## The maintenance-mode path is different

The service console (`docs/service-commands.md`) has its own `#UPGRADE` and
`#FULL_UPGRADE` in the service task (`0x400cd48e`):

1. `#UPGRADE` allocates a buffer and replies `READY FOR BOOTSTRAP`.
2. A `!` binary frame brings the bootstrap. The task replies `READY FOR OS`.
3. A second frame brings the OS. The task checks only the `ELE3` magic at
   `+0x20008` and the device type 52 at `+0x2000c`. A failure replies with an
   error, shows `OS UPGRADE FAILED / INVALID FILE` (`0x400d036c`) and writes
   nothing.
4. Then it erases and writes from `0x80000` in 512-byte pages, replies, and
   shows `OS UPGRADE COMPLETE / PLEASE REBOOT` (`0x400d031c`).

This path does not check the container checksum or the HMAC. It needs
maintenance mode, which a power-on key combination enters, so a tool cannot
start it alone.

## For a flashing tool

The normal path is the one to automate. A tool sends the same `.syx` over USB
MIDI to the running OS, as Transfer does. The OS rejects a damaged or wrongly
signed file before it erases anything. The remaining risk is a correctly
signed image that does not boot, and that is what the build gates exist for.
