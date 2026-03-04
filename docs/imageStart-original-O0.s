08000e30 <imageStart>:
 8000e30:       b580            push    {r7, lr}
 8000e32:       b086            sub     sp, #24
 8000e34:       af00            add     r7, sp, #0
 8000e36:       4b1d            ldr     r3, [pc, #116]  @ (8000eac <imageStart+0x7c>)
 8000e38:       613b            str     r3, [r7, #16]
 8000e3a:       6939            ldr     r1, [r7, #16]
 8000e3c:       481c            ldr     r0, [pc, #112]  @ (8000eb0 <imageStart+0x80>)
 8000e3e:       f011 ff4f       bl      8012ce0 <iprintf>
 8000e42:       b672            cpsid   i
 8000e44:       bf00            nop
 8000e46:       4b1b            ldr     r3, [pc, #108]  @ (8000eb4 <imageStart+0x84>)
 8000e48:       2200            movs    r2, #0
 8000e4a:       601a            str     r2, [r3, #0]
 8000e4c:       2300            movs    r3, #0
 8000e4e:       617b            str     r3, [r7, #20]
 8000e50:       e010            b.n     8000e74 <imageStart+0x44>
 8000e52:       4a19            ldr     r2, [pc, #100]  @ (8000eb8 <imageStart+0x88>)
 8000e54:       697b            ldr     r3, [r7, #20]
 8000e56:       3320            adds    r3, #32
 8000e58:       f04f 31ff       mov.w   r1, #4294967295 @ 0xffffffff
 8000e5c:       f842 1023       str.w   r1, [r2, r3, lsl #2]
 8000e60:       4a15            ldr     r2, [pc, #84]   @ (8000eb8 <imageStart+0x88>)
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
 8000e7a:       f001 fa41       bl      8002300 <HAL_DeInit>
 8000e7e:       693b            ldr     r3, [r7, #16]
 8000e80:       681b            ldr     r3, [r3, #0]
 8000e82:       60fb            str     r3, [r7, #12]
 8000e84:       693b            ldr     r3, [r7, #16]
 8000e86:       3304            adds    r3, #4
 8000e88:       681b            ldr     r3, [r3, #0]
 8000e8a:       60bb            str     r3, [r7, #8]
 8000e8c:       4a0b            ldr     r2, [pc, #44]   @ (8000ebc <imageStart+0x8c>)
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
 8000ea4:       3718            adds    r7, #24
 8000ea6:       46bd            mov     sp, r7
 8000ea8:       bd80            pop     {r7, pc}
 8000eaa:       bf00            nop
 8000eac:       20009400        .word   0x20009400
 8000eb0:       08013bd4        .word   0x08013bd4
 8000eb4:       e000e010        .word   0xe000e010
 8000eb8:       e000e100        .word   0xe000e100
 8000ebc:       e000ed00        .word   0xe000ed00