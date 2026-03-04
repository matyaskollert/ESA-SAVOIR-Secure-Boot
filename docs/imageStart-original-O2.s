08000a40 <imageStart>:
 8000a40:       b510            push    {r4, lr}
 8000a42:       4913            ldr     r1, [pc, #76]   @ (8000a90 <imageStart+0x50>)
 8000a44:       4813            ldr     r0, [pc, #76]   @ (8000a94 <imageStart+0x54>)
 8000a46:       f008 fc85       bl      8009354 <iprintf>
 8000a4a:       b672            cpsid   i
 8000a4c:       f04f 22e0       mov.w   r2, #3758153728 @ 0xe000e000
 8000a50:       2300            movs    r3, #0
 8000a52:       6113            str     r3, [r2, #16]
 8000a54:       f04f 31ff       mov.w   r1, #4294967295 @ 0xffffffff
 8000a58:       009a            lsls    r2, r3, #2
 8000a5a:       f102 4260       add.w   r2, r2, #3758096384     @ 0xe0000000
 8000a5e:       f502 4261       add.w   r2, r2, #57600  @ 0xe100
 8000a62:       3301            adds    r3, #1
 8000a64:       2b08            cmp     r3, #8
 8000a66:       f8c2 1080       str.w   r1, [r2, #128]  @ 0x80
 8000a6a:       f8c2 1180       str.w   r1, [r2, #384]  @ 0x180
 8000a6e:       d1f3            bne.n   8000a58 <imageStart+0x18>
 8000a70:       f000 feac       bl      80017cc <HAL_DeInit>
 8000a74:       4b08            ldr     r3, [pc, #32]   @ (8000a98 <imageStart+0x58>)
 8000a76:       4909            ldr     r1, [pc, #36]   @ (8000a9c <imageStart+0x5c>)
 8000a78:       4805            ldr     r0, [pc, #20]   @ (8000a90 <imageStart+0x50>)
 8000a7a:       f8d3 2400       ldr.w   r2, [r3, #1024] @ 0x400
 8000a7e:       f8d3 3404       ldr.w   r3, [r3, #1028] @ 0x404
 8000a82:       6088            str     r0, [r1, #8]
 8000a84:       f382 8808       msr     MSP, r2
 8000a88:       e8bd 4010       ldmia.w sp!, {r4, lr}
 8000a8c:       4718            bx      r3
 8000a8e:       bf00            nop
 8000a90:       20009400        .word   0x20009400
 8000a94:       0800a227        .word   0x0800a227
 8000a98:       20009000        .word   0x20009000
 8000a9c:       e000ed00        .word   0xe000ed00