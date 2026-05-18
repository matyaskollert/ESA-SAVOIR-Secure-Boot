/*
 @licstart  The following is the entire license notice for the JavaScript code in this file.

 The MIT License (MIT)

 Copyright (C) 1997-2020 by Dimitri van Heesch

 Permission is hereby granted, free of charge, to any person obtaining a copy of this software
 and associated documentation files (the "Software"), to deal in the Software without restriction,
 including without limitation the rights to use, copy, modify, merge, publish, distribute,
 sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is
 furnished to do so, subject to the following conditions:

 The above copyright notice and this permission notice shall be included in all copies or
 substantial portions of the Software.

 THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING
 BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
 NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
 DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

 @licend  The above is the entire license notice for the JavaScript code in this file
*/
var NAVTREE =
[
  [ "ESA_STM32SecureBoot", "index.html", [
    [ "ECSS-Inspired Packet Protocol", "md__e_c_s_s___p_r_o_t_o_c_o_l.html", [
      [ "Protocol Overview", "md__e_c_s_s___p_r_o_t_o_c_o_l.html#autotoc_md1", [
        [ "Packet Structure", "md__e_c_s_s___p_r_o_t_o_c_o_l.html#autotoc_md2", null ],
        [ "Primary Header Format", "md__e_c_s_s___p_r_o_t_o_c_o_l.html#autotoc_md3", null ],
        [ "Data Field", "md__e_c_s_s___p_r_o_t_o_c_o_l.html#autotoc_md4", null ]
      ] ],
      [ "Upload Protocol Sequence", "md__e_c_s_s___p_r_o_t_o_c_o_l.html#autotoc_md5", [
        [ "1. START_UPLOAD Phase", "md__e_c_s_s___p_r_o_t_o_c_o_l.html#autotoc_md6", null ],
        [ "2. DATA_CHUNK Phase", "md__e_c_s_s___p_r_o_t_o_c_o_l.html#autotoc_md7", null ],
        [ "3. END_UPLOAD Phase", "md__e_c_s_s___p_r_o_t_o_c_o_l.html#autotoc_md8", null ],
        [ "Error Handling", "md__e_c_s_s___p_r_o_t_o_c_o_l.html#autotoc_md9", null ]
      ] ],
      [ "Implementation Files", "md__e_c_s_s___p_r_o_t_o_c_o_l.html#autotoc_md10", [
        [ "Python (Host Side)", "md__e_c_s_s___p_r_o_t_o_c_o_l.html#autotoc_md11", null ],
        [ "Firmware (STM32 Side)", "md__e_c_s_s___p_r_o_t_o_c_o_l.html#autotoc_md12", null ]
      ] ],
      [ "Example Packet", "md__e_c_s_s___p_r_o_t_o_c_o_l.html#autotoc_md13", null ],
      [ "Advantages Over Simple Protocol", "md__e_c_s_s___p_r_o_t_o_c_o_l.html#autotoc_md14", null ],
      [ "Notes", "md__e_c_s_s___p_r_o_t_o_c_o_l.html#autotoc_md15", null ],
      [ "Future Enhancements", "md__e_c_s_s___p_r_o_t_o_c_o_l.html#autotoc_md16", null ],
      [ "References", "md__e_c_s_s___p_r_o_t_o_c_o_l.html#autotoc_md17", null ]
    ] ],
    [ "Secure Boot Proof of Concept repository", "md__r_e_a_d_m_e.html", [
      [ "Installation", "md__r_e_a_d_m_e.html#autotoc_md19", null ],
      [ "Build", "md__r_e_a_d_m_e.html#autotoc_md20", null ],
      [ "Build with CRC", "md__r_e_a_d_m_e.html#autotoc_md21", null ],
      [ "Run", "md__r_e_a_d_m_e.html#autotoc_md22", null ]
    ] ],
    [ "BSW Test Suite Description", "md__t_e_s_t___s_u_i_t_e___d_e_s_c_r_i_p_t_i_o_n.html", [
      [ "Hardware and Flash Layout", "md__t_e_s_t___s_u_i_t_e___d_e_s_c_r_i_p_t_i_o_n.html#autotoc_md25", null ],
      [ "BSW Report Structure", "md__t_e_s_t___s_u_i_t_e___d_e_s_c_r_i_p_t_i_o_n.html#autotoc_md27", null ],
      [ "Outcome Codes", "md__t_e_s_t___s_u_i_t_e___d_e_s_c_r_i_p_t_i_o_n.html#autotoc_md29", [
        [ "NOMINAL boot (type = 0x01)", "md__t_e_s_t___s_u_i_t_e___d_e_s_c_r_i_p_t_i_o_n.html#autotoc_md30", null ],
        [ "UPDATE (type = 0x02)", "md__t_e_s_t___s_u_i_t_e___d_e_s_c_r_i_p_t_i_o_n.html#autotoc_md31", null ],
        [ "SWAP (type = 0x03)", "md__t_e_s_t___s_u_i_t_e___d_e_s_c_r_i_p_t_i_o_n.html#autotoc_md32", null ]
      ] ],
      [ "Test Files", "md__t_e_s_t___s_u_i_t_e___d_e_s_c_r_i_p_t_i_o_n.html#autotoc_md34", [
        [ "<span class=\"tt\">test_boot.py</span> — Nominal Boot Path (command '1')", "md__t_e_s_t___s_u_i_t_e___d_e_s_c_r_i_p_t_i_o_n.html#autotoc_md35", [
          [ "TestBootValidImage", "md__t_e_s_t___s_u_i_t_e___d_e_s_c_r_i_p_t_i_o_n.html#autotoc_md36", null ],
          [ "TestBootNoImage", "md__t_e_s_t___s_u_i_t_e___d_e_s_c_r_i_p_t_i_o_n.html#autotoc_md37", null ],
          [ "TestBootCorruptCRC", "md__t_e_s_t___s_u_i_t_e___d_e_s_c_r_i_p_t_i_o_n.html#autotoc_md38", null ],
          [ "TestBootUnprotectedMainSector", "md__t_e_s_t___s_u_i_t_e___d_e_s_c_r_i_p_t_i_o_n.html#autotoc_md39", null ],
          [ "TestBootUnprotectedBSWStateSector", "md__t_e_s_t___s_u_i_t_e___d_e_s_c_r_i_p_t_i_o_n.html#autotoc_md40", null ],
          [ "TestBootBothSectorsUnprotected", "md__t_e_s_t___s_u_i_t_e___d_e_s_c_r_i_p_t_i_o_n.html#autotoc_md41", null ],
          [ "TestBootBadMagic", "md__t_e_s_t___s_u_i_t_e___d_e_s_c_r_i_p_t_i_o_n.html#autotoc_md42", null ],
          [ "TestBootInvalidSignature", "md__t_e_s_t___s_u_i_t_e___d_e_s_c_r_i_p_t_i_o_n.html#autotoc_md43", null ],
          [ "TestBootNominalAutoFix", "md__t_e_s_t___s_u_i_t_e___d_e_s_c_r_i_p_t_i_o_n.html#autotoc_md44", null ]
        ] ],
        [ "<span class=\"tt\">test_update.py</span> — Firmware Update Path (command '2')", "md__t_e_s_t___s_u_i_t_e___d_e_s_c_r_i_p_t_i_o_n.html#autotoc_md46", [
          [ "TestUpdateHappyPath", "md__t_e_s_t___s_u_i_t_e___d_e_s_c_r_i_p_t_i_o_n.html#autotoc_md47", null ],
          [ "TestUpdateVersionTooLow", "md__t_e_s_t___s_u_i_t_e___d_e_s_c_r_i_p_t_i_o_n.html#autotoc_md48", null ],
          [ "TestUpdateUnprotectedMainSector", "md__t_e_s_t___s_u_i_t_e___d_e_s_c_r_i_p_t_i_o_n.html#autotoc_md49", null ],
          [ "TestUpdateUnprotectedBSWStateSector", "md__t_e_s_t___s_u_i_t_e___d_e_s_c_r_i_p_t_i_o_n.html#autotoc_md50", null ],
          [ "TestUpdateSectorProtectedDuringUpdate", "md__t_e_s_t___s_u_i_t_e___d_e_s_c_r_i_p_t_i_o_n.html#autotoc_md51", null ],
          [ "TestUpdateStateAfterSuccess", "md__t_e_s_t___s_u_i_t_e___d_e_s_c_r_i_p_t_i_o_n.html#autotoc_md52", null ],
          [ "TestRollbackPrevention", "md__t_e_s_t___s_u_i_t_e___d_e_s_c_r_i_p_t_i_o_n.html#autotoc_md53", null ],
          [ "TestRollbackCounterBoundary", "md__t_e_s_t___s_u_i_t_e___d_e_s_c_r_i_p_t_i_o_n.html#autotoc_md54", null ]
        ] ],
        [ "<span class=\"tt\">test_swap.py</span> — Image Swap Path (command '3')", "md__t_e_s_t___s_u_i_t_e___d_e_s_c_r_i_p_t_i_o_n.html#autotoc_md56", [
          [ "TestSwapHappyPath", "md__t_e_s_t___s_u_i_t_e___d_e_s_c_r_i_p_t_i_o_n.html#autotoc_md57", null ],
          [ "TestSwapMainSectorStillProtected", "md__t_e_s_t___s_u_i_t_e___d_e_s_c_r_i_p_t_i_o_n.html#autotoc_md58", null ],
          [ "TestSwapBSWStateSectorStillProtected", "md__t_e_s_t___s_u_i_t_e___d_e_s_c_r_i_p_t_i_o_n.html#autotoc_md59", null ],
          [ "TestSwapBothSectorsStillProtected", "md__t_e_s_t___s_u_i_t_e___d_e_s_c_r_i_p_t_i_o_n.html#autotoc_md60", null ],
          [ "TestSwapBadUpdateSlot", "md__t_e_s_t___s_u_i_t_e___d_e_s_c_r_i_p_t_i_o_n.html#autotoc_md61", null ],
          [ "TestSwapVersionRejectionRecovery", "md__t_e_s_t___s_u_i_t_e___d_e_s_c_r_i_p_t_i_o_n.html#autotoc_md62", null ],
          [ "TestSwapRollbackCounterEdges", "md__t_e_s_t___s_u_i_t_e___d_e_s_c_r_i_p_t_i_o_n.html#autotoc_md63", null ],
          [ "TestSwapRollbackEnforcement", "md__t_e_s_t___s_u_i_t_e___d_e_s_c_r_i_p_t_i_o_n.html#autotoc_md64", null ],
          [ "TestSwapPrimarySlotErased", "md__t_e_s_t___s_u_i_t_e___d_e_s_c_r_i_p_t_i_o_n.html#autotoc_md65", null ]
        ] ],
        [ "<span class=\"tt\">test_lifecycle.py</span> — Multi-Step Lifecycle Scenarios", "md__t_e_s_t___s_u_i_t_e___d_e_s_c_r_i_p_t_i_o_n.html#autotoc_md67", [
          [ "TestFullUpdateCycle", "md__t_e_s_t___s_u_i_t_e___d_e_s_c_r_i_p_t_i_o_n.html#autotoc_md68", null ],
          [ "TestConsecutiveSwaps", "md__t_e_s_t___s_u_i_t_e___d_e_s_c_r_i_p_t_i_o_n.html#autotoc_md69", null ],
          [ "TestRollbackWithWindow", "md__t_e_s_t___s_u_i_t_e___d_e_s_c_r_i_p_t_i_o_n.html#autotoc_md70", null ],
          [ "TestAutomaticRollbackBothFail", "md__t_e_s_t___s_u_i_t_e___d_e_s_c_r_i_p_t_i_o_n.html#autotoc_md71", null ],
          [ "TestAutomaticRollbackSecondSucceeds", "md__t_e_s_t___s_u_i_t_e___d_e_s_c_r_i_p_t_i_o_n.html#autotoc_md72", null ]
        ] ],
        [ "<span class=\"tt\">test_protocol.py</span> — ECSS Packet Protocol Robustness", "md__t_e_s_t___s_u_i_t_e___d_e_s_c_r_i_p_t_i_o_n.html#autotoc_md74", [
          [ "TestUnknownCommand", "md__t_e_s_t___s_u_i_t_e___d_e_s_c_r_i_p_t_i_o_n.html#autotoc_md75", null ],
          [ "TestCommandWithEmptyData", "md__t_e_s_t___s_u_i_t_e___d_e_s_c_r_i_p_t_i_o_n.html#autotoc_md76", null ],
          [ "TestUploadStartErrors", "md__t_e_s_t___s_u_i_t_e___d_e_s_c_r_i_p_t_i_o_n.html#autotoc_md77", null ],
          [ "TestUploadChunkErrors", "md__t_e_s_t___s_u_i_t_e___d_e_s_c_r_i_p_t_i_o_n.html#autotoc_md78", null ],
          [ "TestUploadEndBeforeAllData", "md__t_e_s_t___s_u_i_t_e___d_e_s_c_r_i_p_t_i_o_n.html#autotoc_md79", null ]
        ] ]
      ] ],
      [ "Key Invariants Verified Across All Tests", "md__t_e_s_t___s_u_i_t_e___d_e_s_c_r_i_p_t_i_o_n.html#autotoc_md81", null ]
    ] ]
  ] ]
];

var NAVTREEINDEX =
[
"index.html"
];

const SYNCONMSG = 'click to disable panel synchronization';
const SYNCOFFMSG = 'click to enable panel synchronization';
const LISTOFALLMEMBERS = 'List of all members';