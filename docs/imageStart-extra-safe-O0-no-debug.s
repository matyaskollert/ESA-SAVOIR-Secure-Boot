08000e30 <imageStart>:
 8000e30:       b580            push    {r7, lr}
 8000e32:       b086            sub     sp, #24
 8000e34:       af00            add     r7, sp, #0
 8000e36:       4b22            ldr     r3, [pc, #136]  @ (8000ec0 <imageStart+0x90>)
 8000e38:       613b            str     r3, [r7, #16]
 8000e3a:       6939            ldr     r1, [r7, #16]
 8000e3c:       4821            ldr     r0, [pc, #132]  @ (8000ec4 <imageStart+0x94>)
 8000e3e:       f011 ff69       bl      8012d14 <iprintf>
 8000e42:       b672            cpsid   i
 8000e44:       bf00            nop
 8000e46:       4b20            ldr     r3, [pc, #128]  @ (8000ec8 <imageStart+0x98>)
 8000e48:       2200            movs    r2, #0
 8000e4a:       601a            str     r2, [r3, #0]
 8000e4c:       2300            movs    r3, #0
 8000e4e:       617b            str     r3, [r7, #20]
 8000e50:       e010            b.n     8000e74 <imageStart+0x44>
 8000e52:       4a1e            ldr     r2, [pc, #120]  @ (8000ecc <imageStart+0x9c>)
 8000e54:       697b            ldr     r3, [r7, #20]
 8000e56:       3320            adds    r3, #32
 8000e58:       f04f 31ff       mov.w   r1, #4294967295 @ 0xffffffff
 8000e5c:       f842 1023       str.w   r1, [r2, r3, lsl #2]
 8000e60:       4a1a            ldr     r2, [pc, #104]  @ (8000ecc <imageStart+0x9c>)
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
 8000e7a:       f001 fa5b       bl      8002334 <HAL_DeInit>
 8000e7e:       693b            ldr     r3, [r7, #16]
 8000e80:       681b            ldr     r3, [r3, #0]
 8000e82:       60fb            str     r3, [r7, #12]
 8000e84:       693b            ldr     r3, [r7, #16]
 8000e86:       3304            adds    r3, #4
 8000e88:       681b            ldr     r3, [r3, #0]
 8000e8a:       60bb            str     r3, [r7, #8]
 8000e8c:       4a10            ldr     r2, [pc, #64]   @ (8000ed0 <imageStart+0xa0>)
 8000e8e:       693b            ldr     r3, [r7, #16]
 8000e90:       6093            str     r3, [r2, #8]
 8000e92:       f3bf 8f4f       dsb     sy
 8000e96:       bf00            nop
 8000e98:       f3bf 8f6f       isb     sy
 8000e9c:       bf00            nop
 8000e9e:       68fb            ldr     r3, [r7, #12]
 8000ea0:       607b            str     r3, [r7, #4]
 8000ea2:       687b            ldr     r3, [r7, #4]
 8000ea4:       f383 8808       msr     MSP, r3
 8000ea8:       bf00            nop
 8000eaa:       f3bf 8f4f       dsb     sy
 8000eae:       bf00            nop
 8000eb0:       f3bf 8f6f       isb     sy
 8000eb4:       bf00            nop
 8000eb6:       68bb            ldr     r3, [r7, #8]
 8000eb8:       4798            blx     r3
 8000eba:       bf00            nop
 8000ebc:       e7fd            b.n     8000eba <imageStart+0x8a>
 8000ebe:       bf00            nop
 8000ec0:       20009400        .word   0x20009400
 8000ec4:       08013c08        .word   0x08013c08
 8000ec8:       e000e010        .word   0xe000e010
 8000ecc:       e000e100        .word   0xe000e100
 8000ed0:       e000ed00        .word   0xe000ed00