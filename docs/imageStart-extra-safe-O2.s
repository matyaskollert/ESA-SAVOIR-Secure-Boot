08000a40 <imageStart>:
 8000a40:       b508            push    {r3, lr}
 8000a42:       4916            ldr     r1, [pc, #88]   @ (8000a9c <imageStart+0x5c>)
 8000a44:       4816            ldr     r0, [pc, #88]   @ (8000aa0 <imageStart+0x60>)
 8000a46:       f008 fc8b       bl      8009360 <iprintf>
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
 8000a70:       f000 feb2       bl      80017d8 <HAL_DeInit>
 8000a74:       4b0b            ldr     r3, [pc, #44]   @ (8000aa4 <imageStart+0x64>)
 8000a76:       490c            ldr     r1, [pc, #48]   @ (8000aa8 <imageStart+0x68>)
 8000a78:       4808            ldr     r0, [pc, #32]   @ (8000a9c <imageStart+0x5c>)
 8000a7a:       f8d3 2400       ldr.w   r2, [r3, #1024] @ 0x400
 8000a7e:       f8d3 3404       ldr.w   r3, [r3, #1028] @ 0x404
 8000a82:       6088            str     r0, [r1, #8]
 8000a84:       f3bf 8f4f       dsb     sy
 8000a88:       f3bf 8f6f       isb     sy
 8000a8c:       f382 8808       msr     MSP, r2
 8000a90:       f3bf 8f4f       dsb     sy
 8000a94:       f3bf 8f6f       isb     sy
 8000a98:       4798            blx     r3
 8000a9a:       e7fe            b.n     8000a9a <imageStart+0x5a>
 8000a9c:       20009400        .word   0x20009400
 8000aa0:       0800a233        .word   0x0800a233
 8000aa4:       20009000        .word   0x20009000
 8000aa8:       e000ed00        .word   0xe000ed00