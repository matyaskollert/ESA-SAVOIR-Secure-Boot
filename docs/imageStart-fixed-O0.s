08000e30 <imageStart>:
 8000e30:       b580            push    {r7, lr}
 8000e32:       b086            sub     sp, #24
 8000e34:       af00            add     r7, sp, #0
 8000e36:       4b1c            ldr     r3, [pc, #112]  @ (8000ea8 <imageStart+0x78>)
 8000e38:       613b            str     r3, [r7, #16]
 8000e3a:       6939            ldr     r1, [r7, #16]
 8000e3c:       481b            ldr     r0, [pc, #108]  @ (8000eac <imageStart+0x7c>)
 8000e3e:       f011 ff4d       bl      8012cdc <iprintf>
 8000e42:       b672            cpsid   i
 8000e44:       bf00            nop
 8000e46:       4b1a            ldr     r3, [pc, #104]  @ (8000eb0 <imageStart+0x80>)
 8000e48:       2200            movs    r2, #0
 8000e4a:       601a            str     r2, [r3, #0]
 8000e4c:       2300            movs    r3, #0
 8000e4e:       617b            str     r3, [r7, #20]
 8000e50:       e010            b.n     8000e74 <imageStart+0x44>
 8000e52:       4a18            ldr     r2, [pc, #96]   @ (8000eb4 <imageStart+0x84>)
 8000e54:       697b            ldr     r3, [r7, #20]
 8000e56:       3320            adds    r3, #32
 8000e58:       f04f 31ff       mov.w   r1, #4294967295 @ 0xffffffff
 8000e5c:       f842 1023       str.w   r1, [r2, r3, lsl #2]
 8000e60:       4a14            ldr     r2, [pc, #80]   @ (8000eb4 <imageStart+0x84>)
 8000e62:       697b            ldr     r3, [r7, #20]
 8000e64:       3360            adds    r3, #96 @ 0x60
 8000e66:       f04f 31ff       mov.w   r1, #4294967295 @ 0xffffffff
 8000e6a:       f842 1023       str.w   r1, [r2, r3, lsl #2]
 8000e6e:       697b            ldr     r3, [r7, #20]
 8000e70:       3301            adds    r3, #1
 8000e72:       617b            str     r3, [r7, #20]
 8000e74:       697b            ldr     r3, [r7, #20]
 8000e76:       2b07            cmp     r3, #7
 8000e78:       ddeb            ble.n   8000e52 <imageStart+0x22>
 8000e7a:       f001 fa3f       bl      80022fc <HAL_DeInit>
 8000e7e:       693b            ldr     r3, [r7, #16]
 8000e80:       681b            ldr     r3, [r3, #0]
 8000e82:       60fb            str     r3, [r7, #12]
 8000e84:       693b            ldr     r3, [r7, #16]
 8000e86:       3304            adds    r3, #4
 8000e88:       681b            ldr     r3, [r3, #0]
 8000e8a:       60bb            str     r3, [r7, #8]
 8000e8c:       4a0a            ldr     r2, [pc, #40]   @ (8000eb8 <imageStart+0x88>)
 8000e8e:       693b            ldr     r3, [r7, #16]
 8000e90:       6093            str     r3, [r2, #8]
 8000e92:       68fb            ldr     r3, [r7, #12]
 8000e94:       607b            str     r3, [r7, #4]
 8000e96:       687b            ldr     r3, [r7, #4]
 8000e98:       f383 8808       msr     MSP, r3
 8000e9c:       bf00            nop
 8000e9e:       68bb            ldr     r3, [r7, #8]
 8000ea0:       4798            blx     r3
 8000ea2:       bf00            nop
 8000ea4:       e7fd            b.n     8000ea2 <imageStart+0x72>
 8000ea6:       bf00            nop
 8000ea8:       20009400        .word   0x20009400
 8000eac:       08013bd0        .word   0x08013bd0
 8000eb0:       e000e010        .word   0xe000e010
 8000eb4:       e000e100        .word   0xe000e100
 8000eb8:       e000ed00        .word   0xe000ed00