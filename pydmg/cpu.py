"""
CPU Sharp LR35902 - Optimizado con dispatch table
"""

class CPU:
    __slots__ = (
        'mmu', 'a', 'b', 'c', 'd', 'e', 'f', 'h', 'l',
        'sp', 'pc', 'halted', 'ime', 'ime_next',
        '_ops', '_cb_ops'
    )
    
    def __init__(self, mmu):
        self.mmu = mmu
        self.a = 0x01
        self.f = 0xB0
        self.b = 0x00
        self.c = 0x13
        self.d = 0x00
        self.e = 0xD8
        self.h = 0x01
        self.l = 0x4D
        self.sp = 0xFFFE
        self.pc = 0x0100
        self.halted = False
        self.ime = False
        self.ime_next = False
        
        # Construir tablas de dispatch
        self._ops = self._build_ops()
        self._cb_ops = self._build_cb_ops()
    
    def step(self):
        # Interrupciones
        if self.ime:
            ie = self.mmu.ie
            if_reg = self.mmu.io[0x0F]
            pending = ie & if_reg & 0x1F
            if pending:
                self.ime = False
                self.halted = False
                for i in range(5):
                    if pending & (1 << i):
                        self.mmu.io[0x0F] = if_reg & ~(1 << i)
                        self.sp = (self.sp - 2) & 0xFFFF
                        self.mmu.write(self.sp, self.pc & 0xFF)
                        self.mmu.write(self.sp + 1, self.pc >> 8)
                        self.pc = 0x0040 + (i << 3)
                        return 20
        
        if self.halted:
            if self.mmu.ie & self.mmu.io[0x0F] & 0x1F:
                self.halted = False
            return 4
        
        # Fetch & Execute
        op = self.mmu.read(self.pc)
        self.pc = (self.pc + 1) & 0xFFFF
        cycles = self._ops[op]()
        
        if self.ime_next:
            self.ime = True
            self.ime_next = False
        
        return cycles
    
    def _build_ops(self):
        """Construye tabla de 256 handlers"""
        ops = [lambda: 4] * 256  # Default: NOP
        
        # Helpers inline
        def inc8(v):
            r = (v + 1) & 0xFF
            self.f = (self.f & 0x10) | (0x80 if r == 0 else 0) | (0x20 if (v & 0xF) == 0xF else 0)
            return r
        
        def dec8(v):
            r = (v - 1) & 0xFF
            self.f = (self.f & 0x10) | 0x40 | (0x80 if r == 0 else 0) | (0x20 if (v & 0xF) == 0 else 0)
            return r
        
        # 0x00 NOP
        ops[0x00] = lambda: 4
        
        # 0x01 LD BC,nn
        def op_01():
            self.c = self.mmu.read(self.pc)
            self.b = self.mmu.read(self.pc + 1)
            self.pc = (self.pc + 2) & 0xFFFF
            return 12
        ops[0x01] = op_01
        
        # 0x02 LD (BC),A
        def op_02():
            self.mmu.write((self.b << 8) | self.c, self.a)
            return 8
        ops[0x02] = op_02
        
        # 0x03 INC BC
        def op_03():
            bc = ((self.b << 8) | self.c) + 1
            self.b = (bc >> 8) & 0xFF
            self.c = bc & 0xFF
            return 8
        ops[0x03] = op_03
        
        # 0x04 INC B
        def op_04():
            self.b = inc8(self.b)
            return 4
        ops[0x04] = op_04
        
        # 0x05 DEC B
        def op_05():
            self.b = dec8(self.b)
            return 4
        ops[0x05] = op_05
        
        # 0x06 LD B,n
        def op_06():
            self.b = self.mmu.read(self.pc)
            self.pc = (self.pc + 1) & 0xFFFF
            return 8
        ops[0x06] = op_06
        
        # 0x07 RLCA
        def op_07():
            c = self.a >> 7
            self.a = ((self.a << 1) | c) & 0xFF
            self.f = c << 4
            return 4
        ops[0x07] = op_07
        
        # 0x08 LD (nn),SP
        def op_08():
            addr = self.mmu.read(self.pc) | (self.mmu.read(self.pc + 1) << 8)
            self.pc = (self.pc + 2) & 0xFFFF
            self.mmu.write(addr, self.sp & 0xFF)
            self.mmu.write(addr + 1, self.sp >> 8)
            return 20
        ops[0x08] = op_08
        
        # 0x09 ADD HL,BC
        def op_09():
            hl = (self.h << 8) | self.l
            bc = (self.b << 8) | self.c
            r = hl + bc
            self.f = (self.f & 0x80) | (0x20 if (hl & 0xFFF) + (bc & 0xFFF) > 0xFFF else 0) | (0x10 if r > 0xFFFF else 0)
            self.h = (r >> 8) & 0xFF
            self.l = r & 0xFF
            return 8
        ops[0x09] = op_09
        
        # 0x0A LD A,(BC)
        def op_0A():
            self.a = self.mmu.read((self.b << 8) | self.c)
            return 8
        ops[0x0A] = op_0A
        
        # 0x0B DEC BC
        def op_0B():
            bc = (((self.b << 8) | self.c) - 1) & 0xFFFF
            self.b = bc >> 8
            self.c = bc & 0xFF
            return 8
        ops[0x0B] = op_0B
        
        # 0x0C INC C
        def op_0C():
            self.c = inc8(self.c)
            return 4
        ops[0x0C] = op_0C
        
        # 0x0D DEC C
        def op_0D():
            self.c = dec8(self.c)
            return 4
        ops[0x0D] = op_0D
        
        # 0x0E LD C,n
        def op_0E():
            self.c = self.mmu.read(self.pc)
            self.pc = (self.pc + 1) & 0xFFFF
            return 8
        ops[0x0E] = op_0E
        
        # 0x0F RRCA
        def op_0F():
            c = self.a & 1
            self.a = (self.a >> 1) | (c << 7)
            self.f = c << 4
            return 4
        ops[0x0F] = op_0F
        
        # 0x10 STOP
        def op_10():
            self.pc = (self.pc + 1) & 0xFFFF
            return 4
        ops[0x10] = op_10
        
        # 0x11 LD DE,nn
        def op_11():
            self.e = self.mmu.read(self.pc)
            self.d = self.mmu.read(self.pc + 1)
            self.pc = (self.pc + 2) & 0xFFFF
            return 12
        ops[0x11] = op_11
        
        # 0x12 LD (DE),A
        def op_12():
            self.mmu.write((self.d << 8) | self.e, self.a)
            return 8
        ops[0x12] = op_12
        
        # 0x13 INC DE
        def op_13():
            de = ((self.d << 8) | self.e) + 1
            self.d = (de >> 8) & 0xFF
            self.e = de & 0xFF
            return 8
        ops[0x13] = op_13
        
        # 0x14 INC D
        def op_14():
            self.d = inc8(self.d)
            return 4
        ops[0x14] = op_14
        
        # 0x15 DEC D
        def op_15():
            self.d = dec8(self.d)
            return 4
        ops[0x15] = op_15
        
        # 0x16 LD D,n
        def op_16():
            self.d = self.mmu.read(self.pc)
            self.pc = (self.pc + 1) & 0xFFFF
            return 8
        ops[0x16] = op_16
        
        # 0x17 RLA
        def op_17():
            c = self.a >> 7
            self.a = ((self.a << 1) | ((self.f >> 4) & 1)) & 0xFF
            self.f = c << 4
            return 4
        ops[0x17] = op_17
        
        # 0x18 JR n
        def op_18():
            offset = self.mmu.read(self.pc)
            self.pc = (self.pc + 1) & 0xFFFF
            if offset > 127:
                offset -= 256
            self.pc = (self.pc + offset) & 0xFFFF
            return 12
        ops[0x18] = op_18
        
        # 0x19 ADD HL,DE
        def op_19():
            hl = (self.h << 8) | self.l
            de = (self.d << 8) | self.e
            r = hl + de
            self.f = (self.f & 0x80) | (0x20 if (hl & 0xFFF) + (de & 0xFFF) > 0xFFF else 0) | (0x10 if r > 0xFFFF else 0)
            self.h = (r >> 8) & 0xFF
            self.l = r & 0xFF
            return 8
        ops[0x19] = op_19
        
        # 0x1A LD A,(DE)
        def op_1A():
            self.a = self.mmu.read((self.d << 8) | self.e)
            return 8
        ops[0x1A] = op_1A
        
        # 0x1B DEC DE
        def op_1B():
            de = (((self.d << 8) | self.e) - 1) & 0xFFFF
            self.d = de >> 8
            self.e = de & 0xFF
            return 8
        ops[0x1B] = op_1B
        
        # 0x1C INC E
        def op_1C():
            self.e = inc8(self.e)
            return 4
        ops[0x1C] = op_1C
        
        # 0x1D DEC E
        def op_1D():
            self.e = dec8(self.e)
            return 4
        ops[0x1D] = op_1D
        
        # 0x1E LD E,n
        def op_1E():
            self.e = self.mmu.read(self.pc)
            self.pc = (self.pc + 1) & 0xFFFF
            return 8
        ops[0x1E] = op_1E
        
        # 0x1F RRA
        def op_1F():
            c = self.a & 1
            self.a = (self.a >> 1) | ((self.f << 3) & 0x80)
            self.f = c << 4
            return 4
        ops[0x1F] = op_1F
        
        # 0x20 JR NZ,n
        def op_20():
            offset = self.mmu.read(self.pc)
            self.pc = (self.pc + 1) & 0xFFFF
            if not (self.f & 0x80):
                if offset > 127:
                    offset -= 256
                self.pc = (self.pc + offset) & 0xFFFF
                return 12
            return 8
        ops[0x20] = op_20
        
        # 0x21 LD HL,nn
        def op_21():
            self.l = self.mmu.read(self.pc)
            self.h = self.mmu.read(self.pc + 1)
            self.pc = (self.pc + 2) & 0xFFFF
            return 12
        ops[0x21] = op_21
        
        # 0x22 LDI (HL),A
        def op_22():
            hl = (self.h << 8) | self.l
            self.mmu.write(hl, self.a)
            hl = (hl + 1) & 0xFFFF
            self.h = hl >> 8
            self.l = hl & 0xFF
            return 8
        ops[0x22] = op_22
        
        # 0x23 INC HL
        def op_23():
            hl = ((self.h << 8) | self.l) + 1
            self.h = (hl >> 8) & 0xFF
            self.l = hl & 0xFF
            return 8
        ops[0x23] = op_23
        
        # 0x24 INC H
        def op_24():
            self.h = inc8(self.h)
            return 4
        ops[0x24] = op_24
        
        # 0x25 DEC H
        def op_25():
            self.h = dec8(self.h)
            return 4
        ops[0x25] = op_25
        
        # 0x26 LD H,n
        def op_26():
            self.h = self.mmu.read(self.pc)
            self.pc = (self.pc + 1) & 0xFFFF
            return 8
        ops[0x26] = op_26
        
        # 0x27 DAA
        def op_27():
            a = self.a
            if self.f & 0x40:
                if self.f & 0x10:
                    a = (a - 0x60) & 0xFF
                if self.f & 0x20:
                    a = (a - 0x06) & 0xFF
            else:
                if (self.f & 0x10) or a > 0x99:
                    a = (a + 0x60) & 0xFF
                    self.f |= 0x10
                if (self.f & 0x20) or (a & 0xF) > 0x09:
                    a = (a + 0x06) & 0xFF
            self.a = a
            self.f = (self.f & 0x50) | (0x80 if a == 0 else 0)
            return 4
        ops[0x27] = op_27
        
        # 0x28 JR Z,n
        def op_28():
            offset = self.mmu.read(self.pc)
            self.pc = (self.pc + 1) & 0xFFFF
            if self.f & 0x80:
                if offset > 127:
                    offset -= 256
                self.pc = (self.pc + offset) & 0xFFFF
                return 12
            return 8
        ops[0x28] = op_28
        
        # 0x29 ADD HL,HL
        def op_29():
            hl = (self.h << 8) | self.l
            r = hl + hl
            self.f = (self.f & 0x80) | (0x20 if (hl & 0xFFF) * 2 > 0xFFF else 0) | (0x10 if r > 0xFFFF else 0)
            self.h = (r >> 8) & 0xFF
            self.l = r & 0xFF
            return 8
        ops[0x29] = op_29
        
        # 0x2A LDI A,(HL)
        def op_2A():
            hl = (self.h << 8) | self.l
            self.a = self.mmu.read(hl)
            hl = (hl + 1) & 0xFFFF
            self.h = hl >> 8
            self.l = hl & 0xFF
            return 8
        ops[0x2A] = op_2A
        
        # 0x2B DEC HL
        def op_2B():
            hl = (((self.h << 8) | self.l) - 1) & 0xFFFF
            self.h = hl >> 8
            self.l = hl & 0xFF
            return 8
        ops[0x2B] = op_2B
        
        # 0x2C INC L
        def op_2C():
            self.l = inc8(self.l)
            return 4
        ops[0x2C] = op_2C
        
        # 0x2D DEC L
        def op_2D():
            self.l = dec8(self.l)
            return 4
        ops[0x2D] = op_2D
        
        # 0x2E LD L,n
        def op_2E():
            self.l = self.mmu.read(self.pc)
            self.pc = (self.pc + 1) & 0xFFFF
            return 8
        ops[0x2E] = op_2E
        
        # 0x2F CPL
        def op_2F():
            self.a ^= 0xFF
            self.f |= 0x60
            return 4
        ops[0x2F] = op_2F
        
        # 0x30 JR NC,n
        def op_30():
            offset = self.mmu.read(self.pc)
            self.pc = (self.pc + 1) & 0xFFFF
            if not (self.f & 0x10):
                if offset > 127:
                    offset -= 256
                self.pc = (self.pc + offset) & 0xFFFF
                return 12
            return 8
        ops[0x30] = op_30
        
        # 0x31 LD SP,nn
        def op_31():
            self.sp = self.mmu.read(self.pc) | (self.mmu.read(self.pc + 1) << 8)
            self.pc = (self.pc + 2) & 0xFFFF
            return 12
        ops[0x31] = op_31
        
        # 0x32 LDD (HL),A
        def op_32():
            hl = (self.h << 8) | self.l
            self.mmu.write(hl, self.a)
            hl = (hl - 1) & 0xFFFF
            self.h = hl >> 8
            self.l = hl & 0xFF
            return 8
        ops[0x32] = op_32
        
        # 0x33 INC SP
        def op_33():
            self.sp = (self.sp + 1) & 0xFFFF
            return 8
        ops[0x33] = op_33
        
        # 0x34 INC (HL)
        def op_34():
            hl = (self.h << 8) | self.l
            v = self.mmu.read(hl)
            self.mmu.write(hl, inc8(v))
            return 12
        ops[0x34] = op_34
        
        # 0x35 DEC (HL)
        def op_35():
            hl = (self.h << 8) | self.l
            v = self.mmu.read(hl)
            self.mmu.write(hl, dec8(v))
            return 12
        ops[0x35] = op_35
        
        # 0x36 LD (HL),n
        def op_36():
            self.mmu.write((self.h << 8) | self.l, self.mmu.read(self.pc))
            self.pc = (self.pc + 1) & 0xFFFF
            return 12
        ops[0x36] = op_36
        
        # 0x37 SCF
        def op_37():
            self.f = (self.f & 0x80) | 0x10
            return 4
        ops[0x37] = op_37
        
        # 0x38 JR C,n
        def op_38():
            offset = self.mmu.read(self.pc)
            self.pc = (self.pc + 1) & 0xFFFF
            if self.f & 0x10:
                if offset > 127:
                    offset -= 256
                self.pc = (self.pc + offset) & 0xFFFF
                return 12
            return 8
        ops[0x38] = op_38
        
        # 0x39 ADD HL,SP
        def op_39():
            hl = (self.h << 8) | self.l
            r = hl + self.sp
            self.f = (self.f & 0x80) | (0x20 if (hl & 0xFFF) + (self.sp & 0xFFF) > 0xFFF else 0) | (0x10 if r > 0xFFFF else 0)
            self.h = (r >> 8) & 0xFF
            self.l = r & 0xFF
            return 8
        ops[0x39] = op_39
        
        # 0x3A LDD A,(HL)
        def op_3A():
            hl = (self.h << 8) | self.l
            self.a = self.mmu.read(hl)
            hl = (hl - 1) & 0xFFFF
            self.h = hl >> 8
            self.l = hl & 0xFF
            return 8
        ops[0x3A] = op_3A
        
        # 0x3B DEC SP
        def op_3B():
            self.sp = (self.sp - 1) & 0xFFFF
            return 8
        ops[0x3B] = op_3B
        
        # 0x3C INC A
        def op_3C():
            self.a = inc8(self.a)
            return 4
        ops[0x3C] = op_3C
        
        # 0x3D DEC A
        def op_3D():
            self.a = dec8(self.a)
            return 4
        ops[0x3D] = op_3D
        
        # 0x3E LD A,n
        def op_3E():
            self.a = self.mmu.read(self.pc)
            self.pc = (self.pc + 1) & 0xFFFF
            return 8
        ops[0x3E] = op_3E
        
        # 0x3F CCF
        def op_3F():
            self.f = (self.f & 0x80) | ((self.f ^ 0x10) & 0x10)
            return 4
        ops[0x3F] = op_3F
        
        # LD r,r (0x40-0x7F) excepto HALT
        regs_get = [
            lambda: self.b, lambda: self.c, lambda: self.d, lambda: self.e,
            lambda: self.h, lambda: self.l, lambda: self.mmu.read((self.h << 8) | self.l), lambda: self.a
        ]
        
        def make_ld_rr(dst, src):
            if dst == 6:  # (HL)
                def op():
                    self.mmu.write((self.h << 8) | self.l, regs_get[src]())
                    return 8
            elif src == 6:  # (HL)
                if dst == 0:
                    def op():
                        self.b = self.mmu.read((self.h << 8) | self.l)
                        return 8
                elif dst == 1:
                    def op():
                        self.c = self.mmu.read((self.h << 8) | self.l)
                        return 8
                elif dst == 2:
                    def op():
                        self.d = self.mmu.read((self.h << 8) | self.l)
                        return 8
                elif dst == 3:
                    def op():
                        self.e = self.mmu.read((self.h << 8) | self.l)
                        return 8
                elif dst == 4:
                    def op():
                        self.h = self.mmu.read((self.h << 8) | self.l)
                        return 8
                elif dst == 5:
                    def op():
                        self.l = self.mmu.read((self.h << 8) | self.l)
                        return 8
                else:
                    def op():
                        self.a = self.mmu.read((self.h << 8) | self.l)
                        return 8
            else:
                if dst == 0:
                    def op():
                        self.b = regs_get[src]()
                        return 4
                elif dst == 1:
                    def op():
                        self.c = regs_get[src]()
                        return 4
                elif dst == 2:
                    def op():
                        self.d = regs_get[src]()
                        return 4
                elif dst == 3:
                    def op():
                        self.e = regs_get[src]()
                        return 4
                elif dst == 4:
                    def op():
                        self.h = regs_get[src]()
                        return 4
                elif dst == 5:
                    def op():
                        self.l = regs_get[src]()
                        return 4
                else:
                    def op():
                        self.a = regs_get[src]()
                        return 4
            return op
        
        for opcode in range(0x40, 0x80):
            if opcode == 0x76:  # HALT
                def op_halt():
                    self.halted = True
                    return 4
                ops[0x76] = op_halt
            else:
                dst = (opcode >> 3) & 7
                src = opcode & 7
                ops[opcode] = make_ld_rr(dst, src)
        
        # ALU ops (0x80-0xBF)
        def make_alu(alu_op, src):
            get_val = regs_get[src]
            cycles = 8 if src == 6 else 4
            
            if alu_op == 0:  # ADD
                def op():
                    v = get_val()
                    r = self.a + v
                    self.f = (0x80 if (r & 0xFF) == 0 else 0) | (0x20 if (self.a & 0xF) + (v & 0xF) > 0xF else 0) | (0x10 if r > 0xFF else 0)
                    self.a = r & 0xFF
                    return cycles
            elif alu_op == 1:  # ADC
                def op():
                    v = get_val()
                    c = (self.f >> 4) & 1
                    r = self.a + v + c
                    self.f = (0x80 if (r & 0xFF) == 0 else 0) | (0x20 if (self.a & 0xF) + (v & 0xF) + c > 0xF else 0) | (0x10 if r > 0xFF else 0)
                    self.a = r & 0xFF
                    return cycles
            elif alu_op == 2:  # SUB
                def op():
                    v = get_val()
                    r = self.a - v
                    self.f = 0x40 | (0x80 if (r & 0xFF) == 0 else 0) | (0x20 if (self.a & 0xF) < (v & 0xF) else 0) | (0x10 if r < 0 else 0)
                    self.a = r & 0xFF
                    return cycles
            elif alu_op == 3:  # SBC
                def op():
                    v = get_val()
                    c = (self.f >> 4) & 1
                    r = self.a - v - c
                    self.f = 0x40 | (0x80 if (r & 0xFF) == 0 else 0) | (0x20 if (self.a & 0xF) < (v & 0xF) + c else 0) | (0x10 if r < 0 else 0)
                    self.a = r & 0xFF
                    return cycles
            elif alu_op == 4:  # AND
                def op():
                    self.a &= get_val()
                    self.f = 0x20 | (0x80 if self.a == 0 else 0)
                    return cycles
            elif alu_op == 5:  # XOR
                def op():
                    self.a ^= get_val()
                    self.f = 0x80 if self.a == 0 else 0
                    return cycles
            elif alu_op == 6:  # OR
                def op():
                    self.a |= get_val()
                    self.f = 0x80 if self.a == 0 else 0
                    return cycles
            else:  # CP
                def op():
                    v = get_val()
                    r = self.a - v
                    self.f = 0x40 | (0x80 if (r & 0xFF) == 0 else 0) | (0x20 if (self.a & 0xF) < (v & 0xF) else 0) | (0x10 if r < 0 else 0)
                    return cycles
            return op
        
        for opcode in range(0x80, 0xC0):
            alu_op = (opcode >> 3) & 7
            src = opcode & 7
            ops[opcode] = make_alu(alu_op, src)
        
        # 0xC0 RET NZ
        def op_C0():
            if not (self.f & 0x80):
                self.pc = self.mmu.read(self.sp) | (self.mmu.read(self.sp + 1) << 8)
                self.sp = (self.sp + 2) & 0xFFFF
                return 20
            return 8
        ops[0xC0] = op_C0
        
        # 0xC1 POP BC
        def op_C1():
            self.c = self.mmu.read(self.sp)
            self.b = self.mmu.read(self.sp + 1)
            self.sp = (self.sp + 2) & 0xFFFF
            return 12
        ops[0xC1] = op_C1
        
        # 0xC2 JP NZ,nn
        def op_C2():
            addr = self.mmu.read(self.pc) | (self.mmu.read(self.pc + 1) << 8)
            self.pc = (self.pc + 2) & 0xFFFF
            if not (self.f & 0x80):
                self.pc = addr
                return 16
            return 12
        ops[0xC2] = op_C2
        
        # 0xC3 JP nn
        def op_C3():
            self.pc = self.mmu.read(self.pc) | (self.mmu.read(self.pc + 1) << 8)
            return 16
        ops[0xC3] = op_C3
        
        # 0xC4 CALL NZ,nn
        def op_C4():
            addr = self.mmu.read(self.pc) | (self.mmu.read(self.pc + 1) << 8)
            self.pc = (self.pc + 2) & 0xFFFF
            if not (self.f & 0x80):
                self.sp = (self.sp - 2) & 0xFFFF
                self.mmu.write(self.sp, self.pc & 0xFF)
                self.mmu.write(self.sp + 1, self.pc >> 8)
                self.pc = addr
                return 24
            return 12
        ops[0xC4] = op_C4
        
        # 0xC5 PUSH BC
        def op_C5():
            self.sp = (self.sp - 2) & 0xFFFF
            self.mmu.write(self.sp, self.c)
            self.mmu.write(self.sp + 1, self.b)
            return 16
        ops[0xC5] = op_C5
        
        # 0xC6 ADD A,n
        def op_C6():
            n = self.mmu.read(self.pc)
            self.pc = (self.pc + 1) & 0xFFFF
            r = self.a + n
            self.f = (0x80 if (r & 0xFF) == 0 else 0) | (0x20 if (self.a & 0xF) + (n & 0xF) > 0xF else 0) | (0x10 if r > 0xFF else 0)
            self.a = r & 0xFF
            return 8
        ops[0xC6] = op_C6
        
        # 0xC7 RST 00
        def op_C7():
            self.sp = (self.sp - 2) & 0xFFFF
            self.mmu.write(self.sp, self.pc & 0xFF)
            self.mmu.write(self.sp + 1, self.pc >> 8)
            self.pc = 0x00
            return 16
        ops[0xC7] = op_C7
        
        # 0xC8 RET Z
        def op_C8():
            if self.f & 0x80:
                self.pc = self.mmu.read(self.sp) | (self.mmu.read(self.sp + 1) << 8)
                self.sp = (self.sp + 2) & 0xFFFF
                return 20
            return 8
        ops[0xC8] = op_C8
        
        # 0xC9 RET
        def op_C9():
            self.pc = self.mmu.read(self.sp) | (self.mmu.read(self.sp + 1) << 8)
            self.sp = (self.sp + 2) & 0xFFFF
            return 16
        ops[0xC9] = op_C9
        
        # 0xCA JP Z,nn
        def op_CA():
            addr = self.mmu.read(self.pc) | (self.mmu.read(self.pc + 1) << 8)
            self.pc = (self.pc + 2) & 0xFFFF
            if self.f & 0x80:
                self.pc = addr
                return 16
            return 12
        ops[0xCA] = op_CA
        
        # 0xCB - CB prefix
        def op_CB():
            cb_op = self.mmu.read(self.pc)
            self.pc = (self.pc + 1) & 0xFFFF
            return self._cb_ops[cb_op]()
        ops[0xCB] = op_CB
        
        # 0xCC CALL Z,nn
        def op_CC():
            addr = self.mmu.read(self.pc) | (self.mmu.read(self.pc + 1) << 8)
            self.pc = (self.pc + 2) & 0xFFFF
            if self.f & 0x80:
                self.sp = (self.sp - 2) & 0xFFFF
                self.mmu.write(self.sp, self.pc & 0xFF)
                self.mmu.write(self.sp + 1, self.pc >> 8)
                self.pc = addr
                return 24
            return 12
        ops[0xCC] = op_CC
        
        # 0xCD CALL nn
        def op_CD():
            addr = self.mmu.read(self.pc) | (self.mmu.read(self.pc + 1) << 8)
            self.pc = (self.pc + 2) & 0xFFFF
            self.sp = (self.sp - 2) & 0xFFFF
            self.mmu.write(self.sp, self.pc & 0xFF)
            self.mmu.write(self.sp + 1, self.pc >> 8)
            self.pc = addr
            return 24
        ops[0xCD] = op_CD
        
        # 0xCE ADC A,n
        def op_CE():
            n = self.mmu.read(self.pc)
            self.pc = (self.pc + 1) & 0xFFFF
            c = (self.f >> 4) & 1
            r = self.a + n + c
            self.f = (0x80 if (r & 0xFF) == 0 else 0) | (0x20 if (self.a & 0xF) + (n & 0xF) + c > 0xF else 0) | (0x10 if r > 0xFF else 0)
            self.a = r & 0xFF
            return 8
        ops[0xCE] = op_CE
        
        # 0xCF RST 08
        def op_CF():
            self.sp = (self.sp - 2) & 0xFFFF
            self.mmu.write(self.sp, self.pc & 0xFF)
            self.mmu.write(self.sp + 1, self.pc >> 8)
            self.pc = 0x08
            return 16
        ops[0xCF] = op_CF
        
        # 0xD0 RET NC
        def op_D0():
            if not (self.f & 0x10):
                self.pc = self.mmu.read(self.sp) | (self.mmu.read(self.sp + 1) << 8)
                self.sp = (self.sp + 2) & 0xFFFF
                return 20
            return 8
        ops[0xD0] = op_D0
        
        # 0xD1 POP DE
        def op_D1():
            self.e = self.mmu.read(self.sp)
            self.d = self.mmu.read(self.sp + 1)
            self.sp = (self.sp + 2) & 0xFFFF
            return 12
        ops[0xD1] = op_D1
        
        # 0xD2 JP NC,nn
        def op_D2():
            addr = self.mmu.read(self.pc) | (self.mmu.read(self.pc + 1) << 8)
            self.pc = (self.pc + 2) & 0xFFFF
            if not (self.f & 0x10):
                self.pc = addr
                return 16
            return 12
        ops[0xD2] = op_D2
        
        # 0xD4 CALL NC,nn
        def op_D4():
            addr = self.mmu.read(self.pc) | (self.mmu.read(self.pc + 1) << 8)
            self.pc = (self.pc + 2) & 0xFFFF
            if not (self.f & 0x10):
                self.sp = (self.sp - 2) & 0xFFFF
                self.mmu.write(self.sp, self.pc & 0xFF)
                self.mmu.write(self.sp + 1, self.pc >> 8)
                self.pc = addr
                return 24
            return 12
        ops[0xD4] = op_D4
        
        # 0xD5 PUSH DE
        def op_D5():
            self.sp = (self.sp - 2) & 0xFFFF
            self.mmu.write(self.sp, self.e)
            self.mmu.write(self.sp + 1, self.d)
            return 16
        ops[0xD5] = op_D5
        
        # 0xD6 SUB n
        def op_D6():
            n = self.mmu.read(self.pc)
            self.pc = (self.pc + 1) & 0xFFFF
            r = self.a - n
            self.f = 0x40 | (0x80 if (r & 0xFF) == 0 else 0) | (0x20 if (self.a & 0xF) < (n & 0xF) else 0) | (0x10 if r < 0 else 0)
            self.a = r & 0xFF
            return 8
        ops[0xD6] = op_D6
        
        # 0xD7 RST 10
        def op_D7():
            self.sp = (self.sp - 2) & 0xFFFF
            self.mmu.write(self.sp, self.pc & 0xFF)
            self.mmu.write(self.sp + 1, self.pc >> 8)
            self.pc = 0x10
            return 16
        ops[0xD7] = op_D7
        
        # 0xD8 RET C
        def op_D8():
            if self.f & 0x10:
                self.pc = self.mmu.read(self.sp) | (self.mmu.read(self.sp + 1) << 8)
                self.sp = (self.sp + 2) & 0xFFFF
                return 20
            return 8
        ops[0xD8] = op_D8
        
        # 0xD9 RETI
        def op_D9():
            self.pc = self.mmu.read(self.sp) | (self.mmu.read(self.sp + 1) << 8)
            self.sp = (self.sp + 2) & 0xFFFF
            self.ime = True
            return 16
        ops[0xD9] = op_D9
        
        # 0xDA JP C,nn
        def op_DA():
            addr = self.mmu.read(self.pc) | (self.mmu.read(self.pc + 1) << 8)
            self.pc = (self.pc + 2) & 0xFFFF
            if self.f & 0x10:
                self.pc = addr
                return 16
            return 12
        ops[0xDA] = op_DA
        
        # 0xDC CALL C,nn
        def op_DC():
            addr = self.mmu.read(self.pc) | (self.mmu.read(self.pc + 1) << 8)
            self.pc = (self.pc + 2) & 0xFFFF
            if self.f & 0x10:
                self.sp = (self.sp - 2) & 0xFFFF
                self.mmu.write(self.sp, self.pc & 0xFF)
                self.mmu.write(self.sp + 1, self.pc >> 8)
                self.pc = addr
                return 24
            return 12
        ops[0xDC] = op_DC
        
        # 0xDE SBC A,n
        def op_DE():
            n = self.mmu.read(self.pc)
            self.pc = (self.pc + 1) & 0xFFFF
            c = (self.f >> 4) & 1
            r = self.a - n - c
            self.f = 0x40 | (0x80 if (r & 0xFF) == 0 else 0) | (0x20 if (self.a & 0xF) < (n & 0xF) + c else 0) | (0x10 if r < 0 else 0)
            self.a = r & 0xFF
            return 8
        ops[0xDE] = op_DE
        
        # 0xDF RST 18
        def op_DF():
            self.sp = (self.sp - 2) & 0xFFFF
            self.mmu.write(self.sp, self.pc & 0xFF)
            self.mmu.write(self.sp + 1, self.pc >> 8)
            self.pc = 0x18
            return 16
        ops[0xDF] = op_DF
        
        # 0xE0 LDH (n),A
        def op_E0():
            self.mmu.write(0xFF00 + self.mmu.read(self.pc), self.a)
            self.pc = (self.pc + 1) & 0xFFFF
            return 12
        ops[0xE0] = op_E0
        
        # 0xE1 POP HL
        def op_E1():
            self.l = self.mmu.read(self.sp)
            self.h = self.mmu.read(self.sp + 1)
            self.sp = (self.sp + 2) & 0xFFFF
            return 12
        ops[0xE1] = op_E1
        
        # 0xE2 LDH (C),A
        def op_E2():
            self.mmu.write(0xFF00 + self.c, self.a)
            return 8
        ops[0xE2] = op_E2
        
        # 0xE5 PUSH HL
        def op_E5():
            self.sp = (self.sp - 2) & 0xFFFF
            self.mmu.write(self.sp, self.l)
            self.mmu.write(self.sp + 1, self.h)
            return 16
        ops[0xE5] = op_E5
        
        # 0xE6 AND n
        def op_E6():
            self.a &= self.mmu.read(self.pc)
            self.pc = (self.pc + 1) & 0xFFFF
            self.f = 0x20 | (0x80 if self.a == 0 else 0)
            return 8
        ops[0xE6] = op_E6
        
        # 0xE7 RST 20
        def op_E7():
            self.sp = (self.sp - 2) & 0xFFFF
            self.mmu.write(self.sp, self.pc & 0xFF)
            self.mmu.write(self.sp + 1, self.pc >> 8)
            self.pc = 0x20
            return 16
        ops[0xE7] = op_E7
        
        # 0xE8 ADD SP,n
        def op_E8():
            n = self.mmu.read(self.pc)
            self.pc = (self.pc + 1) & 0xFFFF
            if n > 127:
                n -= 256
            r = self.sp + n
            self.f = (0x20 if (self.sp & 0xF) + (n & 0xF) > 0xF else 0) | (0x10 if (self.sp & 0xFF) + (n & 0xFF) > 0xFF else 0)
            self.sp = r & 0xFFFF
            return 16
        ops[0xE8] = op_E8
        
        # 0xE9 JP HL
        def op_E9():
            self.pc = (self.h << 8) | self.l
            return 4
        ops[0xE9] = op_E9
        
        # 0xEA LD (nn),A
        def op_EA():
            addr = self.mmu.read(self.pc) | (self.mmu.read(self.pc + 1) << 8)
            self.pc = (self.pc + 2) & 0xFFFF
            self.mmu.write(addr, self.a)
            return 16
        ops[0xEA] = op_EA
        
        # 0xEE XOR n
        def op_EE():
            self.a ^= self.mmu.read(self.pc)
            self.pc = (self.pc + 1) & 0xFFFF
            self.f = 0x80 if self.a == 0 else 0
            return 8
        ops[0xEE] = op_EE
        
        # 0xEF RST 28
        def op_EF():
            self.sp = (self.sp - 2) & 0xFFFF
            self.mmu.write(self.sp, self.pc & 0xFF)
            self.mmu.write(self.sp + 1, self.pc >> 8)
            self.pc = 0x28
            return 16
        ops[0xEF] = op_EF
        
        # 0xF0 LDH A,(n)
        def op_F0():
            self.a = self.mmu.read(0xFF00 + self.mmu.read(self.pc))
            self.pc = (self.pc + 1) & 0xFFFF
            return 12
        ops[0xF0] = op_F0
        
        # 0xF1 POP AF
        def op_F1():
            self.f = self.mmu.read(self.sp) & 0xF0
            self.a = self.mmu.read(self.sp + 1)
            self.sp = (self.sp + 2) & 0xFFFF
            return 12
        ops[0xF1] = op_F1
        
        # 0xF2 LDH A,(C)
        def op_F2():
            self.a = self.mmu.read(0xFF00 + self.c)
            return 8
        ops[0xF2] = op_F2
        
        # 0xF3 DI
        def op_F3():
            self.ime = False
            return 4
        ops[0xF3] = op_F3
        
        # 0xF5 PUSH AF
        def op_F5():
            self.sp = (self.sp - 2) & 0xFFFF
            self.mmu.write(self.sp, self.f)
            self.mmu.write(self.sp + 1, self.a)
            return 16
        ops[0xF5] = op_F5
        
        # 0xF6 OR n
        def op_F6():
            self.a |= self.mmu.read(self.pc)
            self.pc = (self.pc + 1) & 0xFFFF
            self.f = 0x80 if self.a == 0 else 0
            return 8
        ops[0xF6] = op_F6
        
        # 0xF7 RST 30
        def op_F7():
            self.sp = (self.sp - 2) & 0xFFFF
            self.mmu.write(self.sp, self.pc & 0xFF)
            self.mmu.write(self.sp + 1, self.pc >> 8)
            self.pc = 0x30
            return 16
        ops[0xF7] = op_F7
        
        # 0xF8 LD HL,SP+n
        def op_F8():
            n = self.mmu.read(self.pc)
            self.pc = (self.pc + 1) & 0xFFFF
            if n > 127:
                n -= 256
            r = self.sp + n
            self.f = (0x20 if (self.sp & 0xF) + (n & 0xF) > 0xF else 0) | (0x10 if (self.sp & 0xFF) + (n & 0xFF) > 0xFF else 0)
            self.h = (r >> 8) & 0xFF
            self.l = r & 0xFF
            return 12
        ops[0xF8] = op_F8
        
        # 0xF9 LD SP,HL
        def op_F9():
            self.sp = (self.h << 8) | self.l
            return 8
        ops[0xF9] = op_F9
        
        # 0xFA LD A,(nn)
        def op_FA():
            addr = self.mmu.read(self.pc) | (self.mmu.read(self.pc + 1) << 8)
            self.pc = (self.pc + 2) & 0xFFFF
            self.a = self.mmu.read(addr)
            return 16
        ops[0xFA] = op_FA
        
        # 0xFB EI
        def op_FB():
            self.ime_next = True
            return 4
        ops[0xFB] = op_FB
        
        # 0xFE CP n
        def op_FE():
            n = self.mmu.read(self.pc)
            self.pc = (self.pc + 1) & 0xFFFF
            r = self.a - n
            self.f = 0x40 | (0x80 if (r & 0xFF) == 0 else 0) | (0x20 if (self.a & 0xF) < (n & 0xF) else 0) | (0x10 if r < 0 else 0)
            return 8
        ops[0xFE] = op_FE
        
        # 0xFF RST 38
        def op_FF():
            self.sp = (self.sp - 2) & 0xFFFF
            self.mmu.write(self.sp, self.pc & 0xFF)
            self.mmu.write(self.sp + 1, self.pc >> 8)
            self.pc = 0x38
            return 16
        ops[0xFF] = op_FF
        
        return ops
    
    def _build_cb_ops(self):
        """Construye tabla de 256 handlers para CB prefix"""
        cb = [lambda: 8] * 256
        
        regs_get = [
            lambda: self.b, lambda: self.c, lambda: self.d, lambda: self.e,
            lambda: self.h, lambda: self.l, lambda: self.mmu.read((self.h << 8) | self.l), lambda: self.a
        ]
        
        def set_reg(idx, val):
            if idx == 0: self.b = val
            elif idx == 1: self.c = val
            elif idx == 2: self.d = val
            elif idx == 3: self.e = val
            elif idx == 4: self.h = val
            elif idx == 5: self.l = val
            elif idx == 6: self.mmu.write((self.h << 8) | self.l, val)
            else: self.a = val
        
        for opcode in range(256):
            reg = opcode & 7
            op_type = opcode >> 3
            cycles = 16 if reg == 6 else 8
            
            if op_type == 0:  # RLC
                def make_rlc(r, c):
                    def op():
                        v = regs_get[r]()
                        carry = v >> 7
                        v = ((v << 1) | carry) & 0xFF
                        self.f = (carry << 4) | (0x80 if v == 0 else 0)
                        set_reg(r, v)
                        return c
                    return op
                cb[opcode] = make_rlc(reg, cycles)
            elif op_type == 1:  # RRC
                def make_rrc(r, c):
                    def op():
                        v = regs_get[r]()
                        carry = v & 1
                        v = (v >> 1) | (carry << 7)
                        self.f = (carry << 4) | (0x80 if v == 0 else 0)
                        set_reg(r, v)
                        return c
                    return op
                cb[opcode] = make_rrc(reg, cycles)
            elif op_type == 2:  # RL
                def make_rl(r, c):
                    def op():
                        v = regs_get[r]()
                        carry = v >> 7
                        v = ((v << 1) | ((self.f >> 4) & 1)) & 0xFF
                        self.f = (carry << 4) | (0x80 if v == 0 else 0)
                        set_reg(r, v)
                        return c
                    return op
                cb[opcode] = make_rl(reg, cycles)
            elif op_type == 3:  # RR
                def make_rr(r, c):
                    def op():
                        v = regs_get[r]()
                        carry = v & 1
                        v = (v >> 1) | ((self.f << 3) & 0x80)
                        self.f = (carry << 4) | (0x80 if v == 0 else 0)
                        set_reg(r, v)
                        return c
                    return op
                cb[opcode] = make_rr(reg, cycles)
            elif op_type == 4:  # SLA
                def make_sla(r, c):
                    def op():
                        v = regs_get[r]()
                        carry = v >> 7
                        v = (v << 1) & 0xFF
                        self.f = (carry << 4) | (0x80 if v == 0 else 0)
                        set_reg(r, v)
                        return c
                    return op
                cb[opcode] = make_sla(reg, cycles)
            elif op_type == 5:  # SRA
                def make_sra(r, c):
                    def op():
                        v = regs_get[r]()
                        carry = v & 1
                        v = (v >> 1) | (v & 0x80)
                        self.f = (carry << 4) | (0x80 if v == 0 else 0)
                        set_reg(r, v)
                        return c
                    return op
                cb[opcode] = make_sra(reg, cycles)
            elif op_type == 6:  # SWAP
                def make_swap(r, c):
                    def op():
                        v = regs_get[r]()
                        v = ((v & 0xF) << 4) | (v >> 4)
                        self.f = 0x80 if v == 0 else 0
                        set_reg(r, v)
                        return c
                    return op
                cb[opcode] = make_swap(reg, cycles)
            elif op_type == 7:  # SRL
                def make_srl(r, c):
                    def op():
                        v = regs_get[r]()
                        carry = v & 1
                        v = v >> 1
                        self.f = (carry << 4) | (0x80 if v == 0 else 0)
                        set_reg(r, v)
                        return c
                    return op
                cb[opcode] = make_srl(reg, cycles)
            elif 8 <= op_type < 16:  # BIT
                bit = op_type - 8
                def make_bit(r, b, c):
                    def op():
                        v = regs_get[r]()
                        self.f = (self.f & 0x10) | 0x20 | (0x80 if not (v & (1 << b)) else 0)
                        return 12 if r == 6 else 8
                    return op
                cb[opcode] = make_bit(reg, bit, cycles)
            elif 16 <= op_type < 24:  # RES
                bit = op_type - 16
                def make_res(r, b, c):
                    def op():
                        v = regs_get[r]() & ~(1 << b)
                        set_reg(r, v)
                        return c
                    return op
                cb[opcode] = make_res(reg, bit, cycles)
            else:  # SET
                bit = op_type - 24
                def make_set(r, b, c):
                    def op():
                        v = regs_get[r]() | (1 << b)
                        set_reg(r, v)
                        return c
                    return op
                cb[opcode] = make_set(reg, bit, cycles)
        
        return cb