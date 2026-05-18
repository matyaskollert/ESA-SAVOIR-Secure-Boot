# BSW Test Suite Description

This document describes the hardware-in-the-loop (HIL) test suite for the Boot Software (BSW) bootloader running on the STM32F439ZI (Nucleo-F439ZI board). Tests are implemented in Python using pytest and communicate with the board over UART (ECSS packet protocol) and SWD (STM32CubeProgrammer CLI for flash/option-byte access).

---

## Hardware and Flash Layout

The MCU uses STM32 dual-bank Flash. The relevant sectors are:

| Region              | Address      | Sector | Role                                        |
|---------------------|--------------|--------|---------------------------------------------|
| SLOT_A (MAIN)       | 0x08020000   | 5      | Primary application image slot              |
| SLOT_B (UPDATE)     | 0x08040000   | 6      | Secondary / update image slot               |
| SWAP                | 0x08060000   | 7      | Temporary buffer for hardware image swap    |
| COMM                | 0x08080000   | 8      | Communication status word between BSW/ASW   |
| PROTECTED_BSW_STATE | 0x080A0000   | 9      | Rollback counter + primary slot flag        |
| REPORT              | 0x080C0000   | 10     | Circular buffer of up to 5 BSW event reports|

Write protection (OB_WRP) is applied at the sector level and is reconfigured by the BSW as part of lifecycle management.

---

## BSW Report Structure

After each significant boot event, the BSW writes a `bsw_report_t` record (20 bytes) to the REPORT flash sector. Each report contains:

- **magic** (4 bytes): 0xBEEF0042 — marks a valid entry
- **type** (1 byte): 0x01 = NOMINAL, 0x02 = UPDATE, 0x03 = SWAP
- **outcome** (1 byte): 0 = success, non-zero = failure code
- **primary_slot** (1 byte): 0 = SLOT_A, 1 = SLOT_B (at time of report)
- **rollback_counter** (4 bytes)
- **primary_version** / **secondary_version** (2 bytes each)
- **step_flags** (4 bytes): bitmask of completed steps within the operation

The test suite erases the REPORT sector before each test and verifies the report content after the BSW has run.

---

## Outcome Codes

### NOMINAL boot (type = 0x01)
| Outcome | Meaning                                         | Written in      |
|---------|-------------------------------------------------|-----------------|
| 0       | Success — image loaded and started              | boot.c          |
| 1       | setBootloaderStatus() failed                    | boot.c          |
| 2       | Flash CRC verification failed                   | boot.c          |
| 3       | Digital signature verification failed           | boot.c          |
| 4       | RAM CRC verification failed                     | boot.c          |
| 5       | checkSystemForNominal() failed (WRP violation)  | main_loop.c     |

### UPDATE (type = 0x02)
| Outcome | Meaning                                         | Written in              |
|---------|-------------------------------------------------|-------------------------|
| 0       | Success — image written to flash                | receiveUpdateData()     |
| 1–14    | Protocol/CRC/signature/flash errors during upload | receiveUpdateData()   |
| 15      | checkSystemForUpdate() failed (WRP violation)   | main_loop.c             |

### SWAP (type = 0x03)
| Outcome | Meaning                                              | Written in            |
|---------|------------------------------------------------------|-----------------------|
| 0       | Success — primary/secondary slot switched            | swapMainWithUpdate()  |
| 1       | oldImageHeader NULL (primary slot erased)            | swapMainWithUpdate()  |
| 2       | newImageHeader NULL (secondary slot erased)          | swapMainWithUpdate()  |
| 3       | Rollback counter logic error                         | swapMainWithUpdate()  |
| 4       | HAL_FLASH_Unlock/Lock failed (hardware swap only)   | swapMainWithUpdate()  |
| 5       | Flash sector write failed (hardware swap only)      | swapMainWithUpdate()  |
| 6       | setProtectedBswState() failed                        | swapMainWithUpdate()  |
| 7       | checkSystemForImageSwap() failed (WRP violation)     | main_loop.c           |
| 8       | checkUpdateVersion() failed (version below floor or NULL header) | main_loop.c |
| 9       | checkUpdateValidity() failed at CRC                  | main_loop.c           |
| 10      | checkUpdateValidity() failed at signature            | main_loop.c           |

---

## Test Files

### `test_boot.py` — Nominal Boot Path (command '1')

Tests the BSW boot sequence invoked by sending command byte `'1'` over UART.

#### TestBootValidImage
- **test_boot_successful**: Happy path. A valid signed image is present in SLOT_A. The BSW ACKs the boot command, performs Flash CRC validation, digital signature verification, and RAM CRC validation in sequence, then hands control to the application. The debug log must contain all three validation success messages and `"App STARTED"`. The NOMINAL report (outcome=0, all step flags set) must be present in flash.

#### TestBootNoImage
- **test_debug_log_reports_missing_header**: SLOT_A is erased (no image header). The BSW must log `"No valid header found"`. The report must show outcome=2 (CRC failure) with only SYSTEM_OK and STATUS_SET flags set.

#### TestBootCorruptCRC
- **test_debug_log_reports_crc_mismatch**: A valid image is written to SLOT_A with its CRC field deliberately corrupted (filled with 0xDEADBEEF). The BSW must log `"CRC mismatch in FLASH"` and `"0xdeadbeef"`. The report must show outcome=2 with only SYSTEM_OK and STATUS_SET flags set.

#### TestBootUnprotectedMainSector
- **test_nack_when_boot_sector_unprotected**: The write protection on SLOT_A (sector 5) is temporarily removed. The BSW must refuse to boot (NACK 11) because `checkSystemForNominal()` fails. The report must show outcome=5, step_flags=0.

#### TestBootUnprotectedBSWStateSector
- **test_nack_and_sectors_reprotected**: The write protection on the PROTECTED_BSW_STATE sector (sector 9) is temporarily removed while SLOT_A remains protected. The BSW must NACK 11. After the OB_Launch reset triggered by `setupSystemForNominal()`, both sectors must be re-protected. The report must show outcome=5, step_flags=0.

#### TestBootBothSectorsUnprotected
- **test_nack_wrp_error**: Both SLOT_A and PROTECTED_BSW_STATE are unprotected. The BSW must NACK 11, re-protect both sectors after reset, and write a report with outcome=5, step_flags=0.

#### TestBootBadMagic
- **test_debug_log_reports_no_valid_header**: An image with a corrupted magic field (0x0000 instead of 0xABCD) is flashed. `imageGetHeader()` returns NULL, causing `imageValidate()` to fail. The BSW must log `"No valid header found"`. Report: outcome=2, SYSTEM_OK|STATUS_SET set.

#### TestBootInvalidSignature
- **test_debug_log_reports_signature_failure**: An image with a tampered digital signature (but valid CRC, since the CRC is recomputed after corrupting the signature) is flashed. The BSW passes the Flash CRC check but fails at digital signature verification. The BSW must log `"Digital signature validation failed"`. Report: outcome=3, SYSTEM_OK|STATUS_SET|CRC_OK set.

#### TestBootNominalAutoFix
- **test_autofix_reprotects_and_next_boot_succeeds**: The SLOT_A sector is unprotected to trigger NACK 11 and the auto-fix reset. After the reset, both sectors must be re-protected and a subsequent boot command must succeed (ACK received).

---

### `test_update.py` — Firmware Update Path (command '2')

Tests the firmware upload sequence: command `'2'` → START_UPLOAD / DATA_CHUNK / END_UPLOAD exchange → image written to SLOT_B → system reset into SWAP state.

#### TestUpdateHappyPath
- **test_upload_completes_and_update_slot_correct**: A valid version-2 image is uploaded. The BSW must ACK, log `"Writing to flash"` and `"Flash write complete"`, and SLOT_B must contain the exact uploaded bytes with the correct magic (0xABCD) and version (2). The UPDATE report (outcome=0, all step flags set) must be in flash.

#### TestUpdateVersionTooLow
- **test_nack_on_version_below_floor**: With the rollback counter at 5 (floor=4), a version-3 image is uploaded. The BSW must NACK 9 on the first DATA_CHUNK (where it reads the image version). Report: outcome=9, only SYSTEM_OK flag set.
- **test_version_at_floor_is_accepted**: A version-4 image (exactly at the floor) must be accepted without NACK. Report: outcome=0, all UPDATE step flags set.

#### TestUpdateUnprotectedMainSector
- **test_nack_when_main_sector_unprotected**: SLOT_A (sector 5) is unprotected before sending command '2'. `checkSystemForUpdate()` detects the violation and the BSW must NACK 10. Report: outcome=15, step_flags=0.

#### TestUpdateUnprotectedBSWStateSector
- **test_nack_and_sectors_reprotected**: The PROTECTED_BSW_STATE sector is unprotected. The BSW must NACK 10, then `setupSystemForUpdate()` (which calls `setupSystemForNominal()`) re-protects SLOT_A and PROTECTED_BSW_STATE. Report: outcome=15, step_flags=0.

#### TestUpdateSectorProtectedDuringUpdate
- **test_nack_and_log_mentions_update_protected**: SLOT_B (the upload target) is write-protected in addition to the normally-protected sectors. `checkSystemForUpdate()` detects that the secondary slot is protected (cannot write to it) and NACKs 10. Report: outcome=15, step_flags=0.

#### TestUpdateStateAfterSuccess
- **test_system_state_after_successful_upload**: After a successful version-2 upload, the BSW calls `setupSystemForImageSwap()` which sets COMM=0xCC (SWAP), unlocks SLOT_A and PROTECTED_BSW_STATE, and resets. The test verifies COMM status, write-protection state, and SLOT_B version header after the OB_Launch reset completes. The UPDATE report must show outcome=0 with all flags set.

#### TestRollbackPrevention
- **test_nack9_and_counter_unchanged_after_rejection**: With counter=10 (floor=9), uploading version 8 must be NACKed with error code 9. The rollback counter must remain 10.
- **test_version_at_floor_is_accepted**: Version 9 (at the floor) must be accepted.

#### TestRollbackCounterBoundary
- **test_version_1_accepted_when_counter_is_0**: Counter=0 → floor=0; version 1 must be accepted.
- **test_version_1_accepted_when_counter_equals_window**: Counter=1 (= ROLLBACK_WINDOW=1) → floor=0; version 1 must be accepted.
- **test_version_below_floor_rejected_when_counter_gt_window**: Counter=3 → floor=2; version 1 must be rejected with NACK 9.

---

### `test_swap.py` — Image Swap Path (command '3')

Tests the image swap sequence invoked by sending command `'3'`. The swap checks system integrity (WRP state), validates the update image (version, CRC, signature), executes the slot switch, updates the rollback counter, and re-applies write protection.

#### TestSwapHappyPath
- **test_swap_performs_correctly**: Full happy path. SLOT_A=v1 (primary), SLOT_B=v2 (secondary), counter=1, COMM=0xCC, sectors unlocked as if after a successful upload. The BSW must ACK, perform the slot switch, advance the counter to 2, re-protect the new primary slot and PROTECTED_BSW_STATE, and leave the old primary (now secondary) unprotected. The SWAP report must show outcome=0 with all step flags set, and `primary_slot` must record SLOT_A (the slot that was primary before the swap).

#### TestSwapMainSectorStillProtected
- **test_nack_when_main_sector_still_protected**: COMM=0xCC but the primary slot (SLOT_A) is still write-protected. `checkSystemForImageSwap()` fails → NACK 12 → system reset for re-configuration. The first report in flash must have outcome=7.

#### TestSwapBSWStateSectorStillProtected
- **test_nack_when_bsw_state_sector_still_protected**: COMM=0xCC but PROTECTED_BSW_STATE is still write-protected. Same behaviour as above: NACK 12, first report outcome=7.

#### TestSwapBothSectorsStillProtected
- **test_nack_when_both_sectors_still_protected**: COMM=0xCC but both sectors remain protected. NACK 12 must be issued.

#### TestSwapBadUpdateSlot
Four sub-cases all starting from a valid swap-ready state but with a degraded SLOT_B:

- **test_nack_when_update_slot_empty**: SLOT_B is erased. `checkUpdateVersion()` gets a NULL header and fails → NACK. Report: outcome=8, only SYSTEM_OK set.
- **test_nack_when_update_has_bad_magic**: SLOT_B has a corrupted magic field (0x0000). `imageGetHeader()` returns NULL → same path as empty slot. Report: outcome=8, only SYSTEM_OK set.
- **test_nack_when_update_has_corrupt_crc**: SLOT_B has a valid magic/version but corrupted CRC. `checkUpdateValidity()` fails at `imageValidate()` → NACK. Report: outcome=9, SYSTEM_OK|VERSION_OK set.
- **test_nack_when_update_has_invalid_signature**: SLOT_B has valid CRC (recomputed after corrupting the signature) but a tampered signature. `checkUpdateValidity()` fails at `imageLoad()` → NACK. Report: outcome=10, SYSTEM_OK|VERSION_OK|CRC_OK set.

#### TestSwapVersionRejectionRecovery
- **test_nack_9_on_version_below_floor**: Counter=5 (floor=4), SLOT_B=v3 (below floor). `checkUpdateVersion()` rejects → NACK 9. Report: outcome=8 (version check failure written before the NACK), SYSTEM_OK only.

#### TestSwapRollbackCounterEdges
- **test_counter_not_incremented_when_already_current**: If the rollback counter is pre-set to 2 (equal to the new primary's version 2), the counter must remain 2 after the swap. Report: outcome=0, all flags set.
- **test_counter_updated_when_new_boot_is_higher**: With counter=1 and new primary version=2, the counter must advance to 2 after the swap. Report: outcome=0, all flags set.

#### TestSwapRollbackEnforcement
- **test_nack9_and_state_unchanged_after_rejection**: Counter=10 (floor=9), SLOT_B=v8. The swap command must be NACKed (error code 9). SLOT_A version and rollback counter must remain unchanged. Report: outcome=8, SYSTEM_OK only.

#### TestSwapPrimarySlotErased
- **test_swap_succeeds_when_primary_header_null**: SLOT_A (primary) is erased — no valid image header. SLOT_B=v2 (valid). The pre-swap checks (`checkUpdateVersion`, `checkUpdateValidity`) only inspect SLOT_B and pass, so the BSW ACKs the swap command. Inside `swapMainWithUpdate()`, `imageGetHeader(primarySlot)` returns NULL. The BSW logs a warning (`"Primary slot image header is NULL"`) and continues: the MAIN→SWAP backup step is skipped and only the UPDATE→MAIN write is performed. The swap must complete successfully (outcome=0), the primary slot must contain v2, and the rollback counter must advance to 2. All success step flags must be set.

---

### `test_lifecycle.py` — Multi-Step Lifecycle Scenarios

Tests that span multiple boot cycles, combining upload, swap, and boot operations.

#### TestFullUpdateCycle
- **test_full_cycle**: Complete v1 → v2 upgrade. Upload v2 to SLOT_B (autonomous mode), then perform the swap. After the swap:
  - Primary slot holds v2, secondary holds v1.
  - Rollback counter is 2.
  - New primary slot and PROTECTED_BSW_STATE are write-protected.
  - COMM status is NOMINAL (0xAA).
  - A subsequent autonomous boot must log `"CRC validation in RAM successful"`.
  - Two reports must be in flash: one UPDATE (outcome=0) and one SWAP (outcome=0).

#### TestConsecutiveSwaps
- **test_two_consecutive_upgrades**: Two full upload+swap cycles: v1→v2, then v2→v3. After both cycles, the primary slot must hold v3 and the rollback counter must be 3. Four reports must be in flash (UPDATE1, SWAP1, UPDATE2, SWAP2). The latest report must be a successful SWAP.

#### TestRollbackWithWindow
- **test_v1_rollback_accepted_and_boot_reverts**: After a v1→v2 upgrade (counter=2, floor=1), upload v1 (at the floor). The upload must succeed. After the swap, primary slot must hold v1. The latest report must be a successful SWAP.
- **test_version_below_floor_rejected_after_upgrade**: After two upgrades (v1→v2→v3, counter=3, floor=2), attempting to upload v1 must be NACKed (error code 9). The latest report must be an UPDATE with outcome=9.

#### TestAutomaticRollbackBothFail
- **test_both_boots_fail_leaves_standby**: SLOT_A=v2, SLOT_B=v1, counter=2. A simulated boot failure (COMM set to BOOT_ATTEMPTED) causes the BSW to detect the failure on the next power-on and trigger a rollback swap of v1 into the primary slot. A second simulated boot failure (v1 also fails) leaves no valid rollback candidate. The BSW must log `"Rollback not applicable"` and enter standby.

#### TestAutomaticRollbackSecondSucceeds
- **test_rollback_swap_then_second_boot_succeeds_and_confirms_nominal**: SLOT_A=v2 (synthetic, won't produce `"App STARTED"`), SLOT_B=real bootable ASW at v1, counter=2. After the first boot failure, the BSW swaps v1 into the primary slot. The next boot successfully runs the real ASW and the log must contain `"App STARTED"`.

---

### `test_protocol.py` — ECSS Packet Protocol Robustness

Tests that verify the BSW handles malformed, unexpected, or out-of-order packet sequences gracefully, without hanging, crashing, or corrupting the MAIN slot.

#### TestUnknownCommand
- **test_unknown_command_does_not_hang**: Sending an unrecognised command byte (`'X'`) must not block the BSW indefinitely.
- **test_unknown_command_does_not_corrupt_boot_slot**: After an unknown command, the first 32 bytes of SLOT_A must be identical to the pre-test snapshot.

#### TestCommandWithEmptyData
- **test_zero_length_command_does_not_hang**: A command packet with `data_length = 0` (no payload) must not cause a crash or infinite loop.

#### TestUploadStartErrors
- **test_nack_3_when_start_data_length_wrong**: A START_UPLOAD packet with 8 bytes of payload instead of the required 4 must produce NACK error code 3.
- **test_nack_2_when_wrong_service_type_at_start**: Sending a DATA_CHUNK packet where a START_UPLOAD is expected must produce NACK error code 2.

#### TestUploadChunkErrors
- **test_nack_7_when_wrong_service_type_in_chunk_phase**: After a valid START_UPLOAD exchange, sending another START_UPLOAD where a DATA_CHUNK is expected must produce NACK error code 7.

#### TestUploadEndBeforeAllData
- **test_end_before_all_data_acks_and_does_not_corrupt_boot**: Sending END_UPLOAD before all declared bytes have been transferred must be ACKed (the BSW exits the chunk loop early). The SLOT_A flash content must remain unchanged.

---

## Key Invariants Verified Across All Tests

1. **Write-protection integrity**: The BSW must never boot, update, or swap when required flash sectors are in an unexpected protection state. It must always restore the correct protection state before resetting.
2. **Rollback counter monotonicity**: The counter must never decrease. Upgrades to higher versions advance it; rollbacks within the allowed window do not decrease it.
3. **COMM status word consistency**: COMM transitions (NOMINAL ↔ SWAP ↔ BOOT_ATTEMPTED) must match the expected lifecycle state after each operation.
4. **Flash content integrity**: No operation must silently corrupt the primary image slot.
5. **Report accuracy**: Every significant operation (boot, update, swap) must write a BSW report to flash that accurately reflects which steps completed and the specific failure cause if applicable.
6. **No hangs**: The BSW must always respond (ACK, NACK, or log) within defined timeouts, even when presented with malformed input.
