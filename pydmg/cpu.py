"""
CPU Sharp LR35902
"""

class CPU:
    __slots__ = (
        'mmu', 'a', 'b', 'c', 'd', 'e', 'f', 'h', 'l',
        'sp', 'pc', 'halted', 'ime', 'ime_next', 'cycles'
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
        self.cycles = 0
    
    def step(self):
        # Inline interrupt check
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
        
        # Fetch
        mmu = self.mmu
        pc = self.pc
        op = mmu.read(pc)
        self.pc = (pc + 1) & 0xFFFF
        
        # Execute - inline para velocidad
        cycles = self._execute(op)
        
        if self.ime_next:
            self.ime = True
            self.ime_next = False
        
        return cycles
    
    def _execute(self, op):
        """Ejecuta opcode - optimizado"""
        mmu = self.mmu
        
        # NOP
        if op == 0x00:
            return 4
        
        # LD BC,nn
        elif op == 0x01:
            self.c = mmu.read(self.pc)
            self.b = mmu.read(self.pc + 1)
            self.pc = (self.pc + 2) & 0xFFFF
            return 12
        
        # LD (BC),A
        elif op == 0x02:
            mmu.write((self.b << 8) | self.c, self.a)
            return 8
        
        # INC BC
        elif op == 0x03:
            bc = ((self.b << 8) | self.c) + 1
            self.b = (bc >> 8) & 0xFF
            self.c = bc & 0xFF
            return 8
        
        # INC B
        elif op == 0x04:
            r = (self.b + 1) & 0xFF
            self.f = (self.f & 0x10) | (0x80 if r == 0 else 0) | (0x20 if (self.b & 0xF) == 0xF else 0)
            self.b = r
            return 4
        
        # DEC B
        elif op == 0x05:
            r = (self.b - 1) & 0xFF
            self.f = (self.f & 0x10) | 0x40 | (0x80 if r == 0 else 0) | (0x20 if (self.b & 0xF) == 0 else 0)
            self.b = r
            return 4
        
        # LD B,n
        elif op == 0x06:
            self.b = mmu.read(self.pc)
            self.pc = (self.pc + 1) & 0xFFFF
            return 8
        
        # RLCA
        elif op == 0x07:
            c = self.a >> 7
            self.a = ((self.a << 1) | c) & 0xFF
            self.f = c << 4
            return 4
        
        # LD (nn),SP
        elif op == 0x08:
            addr = mmu.read(self.pc) | (mmu.read(self.pc + 1) << 8)
            self.pc = (self.pc + 2) & 0xFFFF
            mmu.write(addr, self.sp & 0xFF)
            mmu.write(addr + 1, self.sp >> 8)
            return 20
        
        # ADD HL,BC
        elif op == 0x09:
            hl = (self.h << 8) | self.l
            bc = (self.b << 8) | self.c
            r = hl + bc
            self.f = (self.f & 0x80) | (0x20 if (hl & 0xFFF) + (bc & 0xFFF) > 0xFFF else 0) | (0x10 if r > 0xFFFF else 0)
            self.h = (r >> 8) & 0xFF
            self.l = r & 0xFF
            return 8
        
        # LD A,(BC)
        elif op == 0x0A:
            self.a = mmu.read((self.b << 8) | self.c)
            return 8
        
        # DEC BC
        elif op == 0x0B:
            bc = (((self.b << 8) | self.c) - 1) & 0xFFFF
            self.b = bc >> 8
            self.c = bc & 0xFF
            return 8
        
        # INC C
        elif op == 0x0C:
            r = (self.c + 1) & 0xFF
            self.f = (self.f & 0x10) | (0x80 if r == 0 else 0) | (0x20 if (self.c & 0xF) == 0xF else 0)
            self.c = r
            return 4
        
        # DEC C
        elif op == 0x0D:
            r = (self.c - 1) & 0xFF
            self.f = (self.f & 0x10) | 0x40 | (0x80 if r == 0 else 0) | (0x20 if (self.c & 0xF) == 0 else 0)
            self.c = r
            return 4
        
        # LD C,n
        elif op == 0x0E:
            self.c = mmu.read(self.pc)
            self.pc = (self.pc + 1) & 0xFFFF
            return 8
        
        # RRCA
        elif op == 0x0F:
            c = self.a & 1
            self.a = (self.a >> 1) | (c << 7)
            self.f = c << 4
            return 4
        
        # STOP
        elif op == 0x10:
            self.pc = (self.pc + 1) & 0xFFFF
            return 4
        
        # LD DE,nn
        elif op == 0x11:
            self.e = mmu.read(self.pc)
            self.d = mmu.read(self.pc + 1)
            self.pc = (self.pc + 2) & 0xFFFF
            return 12
        
        # LD (DE),A
        elif op == 0x12:
            mmu.write((self.d << 8) | self.e, self.a)
            return 8
        
        # INC DE
        elif op == 0x13:
            de = ((self.d << 8) | self.e) + 1
            self.d = (de >> 8) & 0xFF
            self.e = de & 0xFF
            return 8
        
        # INC D
        elif op == 0x14:
            r = (self.d + 1) & 0xFF
            self.f = (self.f & 0x10) | (0x80 if r == 0 else 0) | (0x20 if (self.d & 0xF) == 0xF else 0)
            self.d = r
            return 4
        
        # DEC D
        elif op == 0x15:
            r = (self.d - 1) & 0xFF
            self.f = (self.f & 0x10) | 0x40 | (0x80 if r == 0 else 0) | (0x20 if (self.d & 0xF) == 0 else 0)
            self.d = r
            return 4
        
        # LD D,n
        elif op == 0x16:
            self.d = mmu.read(self.pc)
            self.pc = (self.pc + 1) & 0xFFFF
            return 8
        
        # RLA
        elif op == 0x17:
            c = self.a >> 7
            self.a = ((self.a << 1) | ((self.f >> 4) & 1)) & 0xFF
            self.f = c << 4
            return 4
        
        # JR n
        elif op == 0x18:
            offset = mmu.read(self.pc)
            self.pc = (self.pc + 1) & 0xFFFF
            if offset > 127:
                offset -= 256
            self.pc = (self.pc + offset) & 0xFFFF
            return 12
        
        # ADD HL,DE
        elif op == 0x19:
            hl = (self.h << 8) | self.l
            de = (self.d << 8) | self.e
            r = hl + de
            self.f = (self.f & 0x80) | (0x20 if (hl & 0xFFF) + (de & 0xFFF) > 0xFFF else 0) | (0x10 if r > 0xFFFF else 0)
            self.h = (r >> 8) & 0xFF
            self.l = r & 0xFF
            return 8
        
        # LD A,(DE)
        elif op == 0x1A:
            self.a = mmu.read((self.d << 8) | self.e)
            return 8
        
        # DEC DE
        elif op == 0x1B:
            de = (((self.d << 8) | self.e) - 1) & 0xFFFF
            self.d = de >> 8
            self.e = de & 0xFF
            return 8
        
        # INC E
        elif op == 0x1C:
            r = (self.e + 1) & 0xFF
            self.f = (self.f & 0x10) | (0x80 if r == 0 else 0) | (0x20 if (self.e & 0xF) == 0xF else 0)
            self.e = r
            return 4
        
        # DEC E
        elif op == 0x1D:
            r = (self.e - 1) & 0xFF
            self.f = (self.f & 0x10) | 0x40 | (0x80 if r == 0 else 0) | (0x20 if (self.e & 0xF) == 0 else 0)
            self.e = r
            return 4
        
        # LD E,n
        elif op == 0x1E:
            self.e = mmu.read(self.pc)
            self.pc = (self.pc + 1) & 0xFFFF
            return 8
        
        # RRA
        elif op == 0x1F:
            c = self.a & 1
            self.a = (self.a >> 1) | ((self.f << 3) & 0x80)
            self.f = c << 4
            return 4
        
        # JR NZ,n
        elif op == 0x20:
            offset = mmu.read(self.pc)
            self.pc = (self.pc + 1) & 0xFFFF
            if not (self.f & 0x80):
                if offset > 127:
                    offset -= 256
                self.pc = (self.pc + offset) & 0xFFFF
                return 12
            return 8
        
        # LD HL,nn
        elif op == 0x21:
            self.l = mmu.read(self.pc)
            self.h = mmu.read(self.pc + 1)
            self.pc = (self.pc + 2) & 0xFFFF
            return 12
        
        # LDI (HL),A
        elif op == 0x22:
            hl = (self.h << 8) | self.l
            mmu.write(hl, self.a)
            hl = (hl + 1) & 0xFFFF
            self.h = hl >> 8
            self.l = hl & 0xFF
            return 8
        
        # INC HL
        elif op == 0x23:
            hl = ((self.h << 8) | self.l) + 1
            self.h = (hl >> 8) & 0xFF
            self.l = hl & 0xFF
            return 8
        
        # INC H
        elif op == 0x24:
            r = (self.h + 1) & 0xFF
            self.f = (self.f & 0x10) | (0x80 if r == 0 else 0) | (0x20 if (self.h & 0xF) == 0xF else 0)
            self.h = r
            return 4
        
        # DEC H
        elif op == 0x25:
            r = (self.h - 1) & 0xFF
            self.f = (self.f & 0x10) | 0x40 | (0x80 if r == 0 else 0) | (0x20 if (self.h & 0xF) == 0 else 0)
            self.h = r
            return 4
        
        # LD H,n
        elif op == 0x26:
            self.h = mmu.read(self.pc)
            self.pc = (self.pc + 1) & 0xFFFF
            return 8
        
        # DAA
        elif op == 0x27:
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
        
        # JR Z,n
        elif op == 0x28:
            offset = mmu.read(self.pc)
            self.pc = (self.pc + 1) & 0xFFFF
            if self.f & 0x80:
                if offset > 127:
                    offset -= 256
                self.pc = (self.pc + offset) & 0xFFFF
                return 12
            return 8
        
        # ADD HL,HL
        elif op == 0x29:
            hl = (self.h << 8) | self.l
            r = hl + hl
            self.f = (self.f & 0x80) | (0x20 if (hl & 0xFFF) * 2 > 0xFFF else 0) | (0x10 if r > 0xFFFF else 0)
            self.h = (r >> 8) & 0xFF
            self.l = r & 0xFF
            return 8
        
        # LDI A,(HL)
        elif op == 0x2A:
            hl = (self.h << 8) | self.l
            self.a = mmu.read(hl)
            hl = (hl + 1) & 0xFFFF
            self.h = hl >> 8
            self.l = hl & 0xFF
            return 8
        
        # DEC HL
        elif op == 0x2B:
            hl = (((self.h << 8) | self.l) - 1) & 0xFFFF
            self.h = hl >> 8
            self.l = hl & 0xFF
            return 8
        
        # INC L
        elif op == 0x2C:
            r = (self.l + 1) & 0xFF
            self.f = (self.f & 0x10) | (0x80 if r == 0 else 0) | (0x20 if (self.l & 0xF) == 0xF else 0)
            self.l = r
            return 4
        
        # DEC L
        elif op == 0x2D:
            r = (self.l - 1) & 0xFF
            self.f = (self.f & 0x10) | 0x40 | (0x80 if r == 0 else 0) | (0x20 if (self.l & 0xF) == 0 else 0)
            self.l = r
            return 4
        
        # LD L,n
        elif op == 0x2E:
            self.l = mmu.read(self.pc)
            self.pc = (self.pc + 1) & 0xFFFF
            return 8
        
        # CPL
        elif op == 0x2F:
            self.a ^= 0xFF
            self.f |= 0x60
            return 4
        
        # JR NC,n
        elif op == 0x30:
            offset = mmu.read(self.pc)
            self.pc = (self.pc + 1) & 0xFFFF
            if not (self.f & 0x10):
                if offset > 127:
                    offset -= 256
                self.pc = (self.pc + offset) & 0xFFFF
                return 12
            return 8
        
        # LD SP,nn
        elif op == 0x31:
            self.sp = mmu.read(self.pc) | (mmu.read(self.pc + 1) << 8)
            self.pc = (self.pc + 2) & 0xFFFF
            return 12
        
        # LDD (HL),A
        elif op == 0x32:
            hl = (self.h << 8) | self.l
            mmu.write(hl, self.a)
            hl = (hl - 1) & 0xFFFF
            self.h = hl >> 8
            self.l = hl & 0xFF
            return 8
        
        # INC SP
        elif op == 0x33:
            self.sp = (self.sp + 1) & 0xFFFF
            return 8
        
        # INC (HL)
        elif op == 0x34:
            hl = (self.h << 8) | self.l
            v = mmu.read(hl)
            r = (v + 1) & 0xFF
            self.f = (self.f & 0x10) | (0x80 if r == 0 else 0) | (0x20 if (v & 0xF) == 0xF else 0)
            mmu.write(hl, r)
            return 12
        
        # DEC (HL)
        elif op == 0x35:
            hl = (self.h << 8) | self.l
            v = mmu.read(hl)
            r = (v - 1) & 0xFF
            self.f = (self.f & 0x10) | 0x40 | (0x80 if r == 0 else 0) | (0x20 if (v & 0xF) == 0 else 0)
            mmu.write(hl, r)
            return 12
        
        # LD (HL),n
        elif op == 0x36:
            mmu.write((self.h << 8) | self.l, mmu.read(self.pc))
            self.pc = (self.pc + 1) & 0xFFFF
            return 12
        
        # SCF
        elif op == 0x37:
            self.f = (self.f & 0x80) | 0x10
            return 4
        
        # JR C,n
        elif op == 0x38:
            offset = mmu.read(self.pc)
            self.pc = (self.pc + 1) & 0xFFFF
            if self.f & 0x10:
                if offset > 127:
                    offset -= 256
                self.pc = (self.pc + offset) & 0xFFFF
                return 12
            return 8
        
        # ADD HL,SP
        elif op == 0x39:
            hl = (self.h << 8) | self.l
            r = hl + self.sp
            self.f = (self.f & 0x80) | (0x20 if (hl & 0xFFF) + (self.sp & 0xFFF) > 0xFFF else 0) | (0x10 if r > 0xFFFF else 0)
            self.h = (r >> 8) & 0xFF
            self.l = r & 0xFF
            return 8
        
        # LDD A,(HL)
        elif op == 0x3A:
            hl = (self.h << 8) | self.l
            self.a = mmu.read(hl)
            hl = (hl - 1) & 0xFFFF
            self.h = hl >> 8
            self.l = hl & 0xFF
            return 8
        
        # DEC SP
        elif op == 0x3B:
            self.sp = (self.sp - 1) & 0xFFFF
            return 8
        
        # INC A
        elif op == 0x3C:
            r = (self.a + 1) & 0xFF
            self.f = (self.f & 0x10) | (0x80 if r == 0 else 0) | (0x20 if (self.a & 0xF) == 0xF else 0)
            self.a = r
            return 4
        
        # DEC A
        elif op == 0x3D:
            r = (self.a - 1) & 0xFF
            self.f = (self.f & 0x10) | 0x40 | (0x80 if r == 0 else 0) | (0x20 if (self.a & 0xF) == 0 else 0)
            self.a = r
            return 4
        
        # LD A,n
        elif op == 0x3E:
            self.a = mmu.read(self.pc)
            self.pc = (self.pc + 1) & 0xFFFF
            return 8
        
        # CCF
        elif op == 0x3F:
            self.f = (self.f & 0x80) | ((self.f ^ 0x10) & 0x10)
            return 4
        
        # LD B,B - LD A,A (0x40-0x7F excepto 0x76)
        elif 0x40 <= op <= 0x7F:
            if op == 0x76:  # HALT
                self.halted = True
                return 4
            return self._ld_r_r(op)
        
        # ADD/ADC/SUB/SBC/AND/XOR/OR/CP (0x80-0xBF)
        elif 0x80 <= op <= 0xBF:
            return self._alu(op)
        
        # RET NZ
        elif op == 0xC0:
            if not (self.f & 0x80):
                self.pc = mmu.read(self.sp) | (mmu.read(self.sp + 1) << 8)
                self.sp = (self.sp + 2) & 0xFFFF
                return 20
            return 8
        
        # POP BC
        elif op == 0xC1:
            self.c = mmu.read(self.sp)
            self.b = mmu.read(self.sp + 1)
            self.sp = (self.sp + 2) & 0xFFFF
            return 12
        
        # JP NZ,nn
        elif op == 0xC2:
            addr = mmu.read(self.pc) | (mmu.read(self.pc + 1) << 8)
            self.pc = (self.pc + 2) & 0xFFFF
            if not (self.f & 0x80):
                self.pc = addr
                return 16
            return 12
        
        # JP nn
        elif op == 0xC3:
            self.pc = mmu.read(self.pc) | (mmu.read(self.pc + 1) << 8)
            return 16
        
        # CALL NZ,nn
        elif op == 0xC4:
            addr = mmu.read(self.pc) | (mmu.read(self.pc + 1) << 8)
            self.pc = (self.pc + 2) & 0xFFFF
            if not (self.f & 0x80):
                self.sp = (self.sp - 2) & 0xFFFF
                mmu.write(self.sp, self.pc & 0xFF)
                mmu.write(self.sp + 1, self.pc >> 8)
                self.pc = addr
                return 24
            return 12
        
        # PUSH BC
        elif op == 0xC5:
            self.sp = (self.sp - 2) & 0xFFFF
            mmu.write(self.sp, self.c)
            mmu.write(self.sp + 1, self.b)
            return 16
        
        # ADD A,n
        elif op == 0xC6:
            n = mmu.read(self.pc)
            self.pc = (self.pc + 1) & 0xFFFF
            r = self.a + n
            self.f = (0x80 if (r & 0xFF) == 0 else 0) | (0x20 if (self.a & 0xF) + (n & 0xF) > 0xF else 0) | (0x10 if r > 0xFF else 0)
            self.a = r & 0xFF
            return 8
        
        # RST 00
        elif op == 0xC7:
            self.sp = (self.sp - 2) & 0xFFFF
            mmu.write(self.sp, self.pc & 0xFF)
            mmu.write(self.sp + 1, self.pc >> 8)
            self.pc = 0x00
            return 16
        
        # RET Z
        elif op == 0xC8:
            if self.f & 0x80:
                self.pc = mmu.read(self.sp) | (mmu.read(self.sp + 1) << 8)
                self.sp = (self.sp + 2) & 0xFFFF
                return 20
            return 8
        
        # RET
        elif op == 0xC9:
            self.pc = mmu.read(self.sp) | (mmu.read(self.sp + 1) << 8)
            self.sp = (self.sp + 2) & 0xFFFF
            return 16
        
        # JP Z,nn
        elif op == 0xCA:
            addr = mmu.read(self.pc) | (mmu.read(self.pc + 1) << 8)
            self.pc = (self.pc + 2) & 0xFFFF
            if self.f & 0x80:
                self.pc = addr
                return 16
            return 12
        
        # CB prefix
        elif op == 0xCB:
            return self._cb(mmu.read(self.pc))
        
        # CALL Z,nn
        elif op == 0xCC:
            addr = mmu.read(self.pc) | (mmu.read(self.pc + 1) << 8)
            self.pc = (self.pc + 2) & 0xFFFF
            if self.f & 0x80:
                self.sp = (self.sp - 2) & 0xFFFF
                mmu.write(self.sp, self.pc & 0xFF)
                mmu.write(self.sp + 1, self.pc >> 8)
                self.pc = addr
                return 24
            return 12
        
        # CALL nn
        elif op == 0xCD:
            addr = mmu.read(self.pc) | (mmu.read(self.pc + 1) << 8)
            self.pc = (self.pc + 2) & 0xFFFF
            self.sp = (self.sp - 2) & 0xFFFF
            mmu.write(self.sp, self.pc & 0xFF)
            mmu.write(self.sp + 1, self.pc >> 8)
            self.pc = addr
            return 24
        
        # ADC A,n
        elif op == 0xCE:
            n = mmu.read(self.pc)
            self.pc = (self.pc + 1) & 0xFFFF
            c = (self.f >> 4) & 1
            r = self.a + n + c
            self.f = (0x80 if (r & 0xFF) == 0 else 0) | (0x20 if (self.a & 0xF) + (n & 0xF) + c > 0xF else 0) | (0x10 if r > 0xFF else 0)
            self.a = r & 0xFF
            return 8
        
        # RST 08
        elif op == 0xCF:
            self.sp = (self.sp - 2) & 0xFFFF
            mmu.write(self.sp, self.pc & 0xFF)
            mmu.write(self.sp + 1, self.pc >> 8)
            self.pc = 0x08
            return 16
        
        # RET NC
        elif op == 0xD0:
            if not (self.f & 0x10):
                self.pc = mmu.read(self.sp) | (mmu.read(self.sp + 1) << 8)
                self.sp = (self.sp + 2) & 0xFFFF
                return 20
            return 8
        
        # POP DE
        elif op == 0xD1:
            self.e = mmu.read(self.sp)
            self.d = mmu.read(self.sp + 1)
            self.sp = (self.sp + 2) & 0xFFFF
            return 12
        
        # JP NC,nn
        elif op == 0xD2:
            addr = mmu.read(self.pc) | (mmu.read(self.pc + 1) << 8)
            self.pc = (self.pc + 2) & 0xFFFF
            if not (self.f & 0x10):
                self.pc = addr
                return 16
            return 12
        
        # CALL NC,nn
        elif op == 0xD4:
            addr = mmu.read(self.pc) | (mmu.read(self.pc + 1) << 8)
            self.pc = (self.pc + 2) & 0xFFFF
            if not (self.f & 0x10):
                self.sp = (self.sp - 2) & 0xFFFF
                mmu.write(self.sp, self.pc & 0xFF)
                mmu.write(self.sp + 1, self.pc >> 8)
                self.pc = addr
                return 24
            return 12
        
        # PUSH DE
        elif op == 0xD5:
            self.sp = (self.sp - 2) & 0xFFFF
            mmu.write(self.sp, self.e)
            mmu.write(self.sp + 1, self.d)
            return 16
        
        # SUB n
        elif op == 0xD6:
            n = mmu.read(self.pc)
            self.pc = (self.pc + 1) & 0xFFFF
            r = self.a - n
            self.f = 0x40 | (0x80 if (r & 0xFF) == 0 else 0) | (0x20 if (self.a & 0xF) < (n & 0xF) else 0) | (0x10 if r < 0 else 0)
            self.a = r & 0xFF
            return 8
        
        # RST 10
        elif op == 0xD7:
            self.sp = (self.sp - 2) & 0xFFFF
            mmu.write(self.sp, self.pc & 0xFF)
            mmu.write(self.sp + 1, self.pc >> 8)
            self.pc = 0x10
            return 16
        
        # RET C
        elif op == 0xD8:
            if self.f & 0x10:
                self.pc = mmu.read(self.sp) | (mmu.read(self.sp + 1) << 8)
                self.sp = (self.sp + 2) & 0xFFFF
                return 20
            return 8
        
        # RETI
        elif op == 0xD9:
            self.pc = mmu.read(self.sp) | (mmu.read(self.sp + 1) << 8)
            self.sp = (self.sp + 2) & 0xFFFF
            self.ime = True
            return 16
        
        # JP C,nn
        elif op == 0xDA:
            addr = mmu.read(self.pc) | (mmu.read(self.pc + 1) << 8)
            self.pc = (self.pc + 2) & 0xFFFF
            if self.f & 0x10:
                self.pc = addr
                return 16
            return 12
        
        # CALL C,nn
        elif op == 0xDC:
            addr = mmu.read(self.pc) | (mmu.read(self.pc + 1) << 8)
            self.pc = (self.pc + 2) & 0xFFFF
            if self.f & 0x10:
                self.sp = (self.sp - 2) & 0xFFFF
                mmu.write(self.sp, self.pc & 0xFF)
                mmu.write(self.sp + 1, self.pc >> 8)
                self.pc = addr
                return 24
            return 12
        
        # SBC A,n
        elif op == 0xDE:
            n = mmu.read(self.pc)
            self.pc = (self.pc + 1) & 0xFFFF
            c = (self.f >> 4) & 1
            r = self.a - n - c
            self.f = 0x40 | (0x80 if (r & 0xFF) == 0 else 0) | (0x20 if (self.a & 0xF) < (n & 0xF) + c else 0) | (0x10 if r < 0 else 0)
            self.a = r & 0xFF
            return 8
        
        # RST 18
        elif op == 0xDF:
            self.sp = (self.sp - 2) & 0xFFFF
            mmu.write(self.sp, self.pc & 0xFF)
            mmu.write(self.sp + 1, self.pc >> 8)
            self.pc = 0x18
            return 16
        
        # LDH (n),A
        elif op == 0xE0:
            mmu.write(0xFF00 + mmu.read(self.pc), self.a)
            self.pc = (self.pc + 1) & 0xFFFF
            return 12
        
        # POP HL
        elif op == 0xE1:
            self.l = mmu.read(self.sp)
            self.h = mmu.read(self.sp + 1)
            self.sp = (self.sp + 2) & 0xFFFF
            return 12
        
        # LDH (C),A
        elif op == 0xE2:
            mmu.write(0xFF00 + self.c, self.a)
            return 8
        
        # PUSH HL
        elif op == 0xE5:
            self.sp = (self.sp - 2) & 0xFFFF
            mmu.write(self.sp, self.l)
            mmu.write(self.sp + 1, self.h)
            return 16
        
        # AND n
        elif op == 0xE6:
            self.a &= mmu.read(self.pc)
            self.pc = (self.pc + 1) & 0xFFFF
            self.f = 0x20 | (0x80 if self.a == 0 else 0)
            return 8
        
        # RST 20
        elif op == 0xE7:
            self.sp = (self.sp - 2) & 0xFFFF
            mmu.write(self.sp, self.pc & 0xFF)
            mmu.write(self.sp + 1, self.pc >> 8)
            self.pc = 0x20
            return 16
        
        # ADD SP,n
        elif op == 0xE8:
            n = mmu.read(self.pc)
            self.pc = (self.pc + 1) & 0xFFFF
            if n > 127:
                n -= 256
            r = self.sp + n
            self.f = (0x20 if (self.sp & 0xF) + (n & 0xF) > 0xF else 0) | (0x10 if (self.sp & 0xFF) + (n & 0xFF) > 0xFF else 0)
            self.sp = r & 0xFFFF
            return 16
        
        # JP HL
        elif op == 0xE9:
            self.pc = (self.h << 8) | self.l
            return 4
        
        # LD (nn),A
        elif op == 0xEA:
            addr = mmu.read(self.pc) | (mmu.read(self.pc + 1) << 8)
            self.pc = (self.pc + 2) & 0xFFFF
            mmu.write(addr, self.a)
            return 16
        
        # XOR n
        elif op == 0xEE:
            self.a ^= mmu.read(self.pc)
            self.pc = (self.pc + 1) & 0xFFFF
            self.f = 0x80 if self.a == 0 else 0
            return 8
        
        # RST 28
        elif op == 0xEF:
            self.sp = (self.sp - 2) & 0xFFFF
            mmu.write(self.sp, self.pc & 0xFF)
            mmu.write(self.sp + 1, self.pc >> 8)
            self.pc = 0x28
            return 16
        
        # LDH A,(n)
        elif op == 0xF0:
            self.a = mmu.read(0xFF00 + mmu.read(self.pc))
            self.pc = (self.pc + 1) & 0xFFFF
            return 12
        
        # POP AF
        elif op == 0xF1:
            self.f = mmu.read(self.sp) & 0xF0
            self.a = mmu.read(self.sp + 1)
            self.sp = (self.sp + 2) & 0xFFFF
            return 12
        
        # LDH A,(C)
        elif op == 0xF2:
            self.a = mmu.read(0xFF00 + self.c)
            return 8
        
        # DI
        elif op == 0xF3:
            self.ime = False
            return 4
        
        # PUSH AF
        elif op == 0xF5:
            self.sp = (self.sp - 2) & 0xFFFF
            mmu.write(self.sp, self.f)
            mmu.write(self.sp + 1, self.a)
            return 16
        
        # OR n
        elif op == 0xF6:
            self.a |= mmu.read(self.pc)
            self.pc = (self.pc + 1) & 0xFFFF
            self.f = 0x80 if self.a == 0 else 0
            return 8
        
        # RST 30
        elif op == 0xF7:
            self.sp = (self.sp - 2) & 0xFFFF
            mmu.write(self.sp, self.pc & 0xFF)
            mmu.write(self.sp + 1, self.pc >> 8)
            self.pc = 0x30
            return 16
        
        # LD HL,SP+n
        elif op == 0xF8:
            n = mmu.read(self.pc)
            self.pc = (self.pc + 1) & 0xFFFF
            if n > 127:
                n -= 256
            r = self.sp + n
            self.f = (0x20 if (self.sp & 0xF) + (n & 0xF) > 0xF else 0) | (0x10 if (self.sp & 0xFF) + (n & 0xFF) > 0xFF else 0)
            self.h = (r >> 8) & 0xFF
            self.l = r & 0xFF
            return 12
        
        # LD SP,HL
        elif op == 0xF9:
            self.sp = (self.h << 8) | self.l
            return 8
        
        # LD A,(nn)
        elif op == 0xFA:
            addr = mmu.read(self.pc) | (mmu.read(self.pc + 1) << 8)
            self.pc = (self.pc + 2) & 0xFFFF
            self.a = mmu.read(addr)
            return 16
        
        # EI
        elif op == 0xFB:
            self.ime_next = True
            return 4
        
        # CP n
        elif op == 0xFE:
            n = mmu.read(self.pc)
            self.pc = (self.pc + 1) & 0xFFFF
            r = self.a - n
            self.f = 0x40 | (0x80 if (r & 0xFF) == 0 else 0) | (0x20 if (self.a & 0xF) < (n & 0xF) else 0) | (0x10 if r < 0 else 0)
            return 8
        
        # RST 38
        elif op == 0xFF:
            self.sp = (self.sp - 2) & 0xFFFF
            mmu.write(self.sp, self.pc & 0xFF)
            mmu.write(self.sp + 1, self.pc >> 8)
            self.pc = 0x38
            return 16
        
        return 4
    
    def _ld_r_r(self, op):
        """LD r,r optimizado"""
        src_idx = op & 0x07
        dst_idx = (op >> 3) & 0x07
        
        # Obtener valor fuente
        if src_idx == 0: v = self.b
        elif src_idx == 1: v = self.c
        elif src_idx == 2: v = self.d
        elif src_idx == 3: v = self.e
        elif src_idx == 4: v = self.h
        elif src_idx == 5: v = self.l
        elif src_idx == 6:
            v = self.mmu.read((self.h << 8) | self.l)
        else: v = self.a
        
        # Guardar en destino
        if dst_idx == 0: self.b = v
        elif dst_idx == 1: self.c = v
        elif dst_idx == 2: self.d = v
        elif dst_idx == 3: self.e = v
        elif dst_idx == 4: self.h = v
        elif dst_idx == 5: self.l = v
        elif dst_idx == 6:
            self.mmu.write((self.h << 8) | self.l, v)
            return 8
        else: self.a = v
        
        return 8 if src_idx == 6 else 4
    
    def _alu(self, op):
        """ALU ops optimizado"""
        src_idx = op & 0x07
        alu_op = (op >> 3) & 0x07
        
        # Obtener valor
        if src_idx == 0: v = self.b
        elif src_idx == 1: v = self.c
        elif src_idx == 2: v = self.d
        elif src_idx == 3: v = self.e
        elif src_idx == 4: v = self.h
        elif src_idx == 5: v = self.l
        elif src_idx == 6:
            v = self.mmu.read((self.h << 8) | self.l)
        else: v = self.a
        
        a = self.a
        
        if alu_op == 0:  # ADD
            r = a + v
            self.f = (0x80 if (r & 0xFF) == 0 else 0) | (0x20 if (a & 0xF) + (v & 0xF) > 0xF else 0) | (0x10 if r > 0xFF else 0)
            self.a = r & 0xFF
        elif alu_op == 1:  # ADC
            c = (self.f >> 4) & 1
            r = a + v + c
            self.f = (0x80 if (r & 0xFF) == 0 else 0) | (0x20 if (a & 0xF) + (v & 0xF) + c > 0xF else 0) | (0x10 if r > 0xFF else 0)
            self.a = r & 0xFF
        elif alu_op == 2:  # SUB
            r = a - v
            self.f = 0x40 | (0x80 if (r & 0xFF) == 0 else 0) | (0x20 if (a & 0xF) < (v & 0xF) else 0) | (0x10 if r < 0 else 0)
            self.a = r & 0xFF
        elif alu_op == 3:  # SBC
            c = (self.f >> 4) & 1
            r = a - v - c
            self.f = 0x40 | (0x80 if (r & 0xFF) == 0 else 0) | (0x20 if (a & 0xF) < (v & 0xF) + c else 0) | (0x10 if r < 0 else 0)
            self.a = r & 0xFF
        elif alu_op == 4:  # AND
            self.a = a & v
            self.f = 0x20 | (0x80 if self.a == 0 else 0)
        elif alu_op == 5:  # XOR
            self.a = a ^ v
            self.f = 0x80 if self.a == 0 else 0
        elif alu_op == 6:  # OR
            self.a = a | v
            self.f = 0x80 if self.a == 0 else 0
        else:  # CP
            r = a - v
            self.f = 0x40 | (0x80 if (r & 0xFF) == 0 else 0) | (0x20 if (a & 0xF) < (v & 0xF) else 0) | (0x10 if r < 0 else 0)
        
        return 8 if src_idx == 6 else 4
    
    def _cb(self, op):
        """CB prefix ops"""
        self.pc = (self.pc + 1) & 0xFFFF
        
        reg_idx = op & 0x07
        cb_op = op >> 3
        
        # Obtener valor
        if reg_idx == 0: v = self.b
        elif reg_idx == 1: v = self.c
        elif reg_idx == 2: v = self.d
        elif reg_idx == 3: v = self.e
        elif reg_idx == 4: v = self.h
        elif reg_idx == 5: v = self.l
        elif reg_idx == 6:
            v = self.mmu.read((self.h << 8) | self.l)
        else: v = self.a
        
        if cb_op < 8:  # Rotates/shifts
            if cb_op == 0:  # RLC
                c = v >> 7
                v = ((v << 1) | c) & 0xFF
                self.f = (c << 4) | (0x80 if v == 0 else 0)
            elif cb_op == 1:  # RRC
                c = v & 1
                v = (v >> 1) | (c << 7)
                self.f = (c << 4) | (0x80 if v == 0 else 0)
            elif cb_op == 2:  # RL
                c = v >> 7
                v = ((v << 1) | ((self.f >> 4) & 1)) & 0xFF
                self.f = (c << 4) | (0x80 if v == 0 else 0)
            elif cb_op == 3:  # RR
                c = v & 1
                v = (v >> 1) | ((self.f << 3) & 0x80)
                self.f = (c << 4) | (0x80 if v == 0 else 0)
            elif cb_op == 4:  # SLA
                c = v >> 7
                v = (v << 1) & 0xFF
                self.f = (c << 4) | (0x80 if v == 0 else 0)
            elif cb_op == 5:  # SRA
                c = v & 1
                v = (v >> 1) | (v & 0x80)
                self.f = (c << 4) | (0x80 if v == 0 else 0)
            elif cb_op == 6:  # SWAP
                v = ((v & 0xF) << 4) | (v >> 4)
                self.f = 0x80 if v == 0 else 0
            else:  # SRL
                c = v & 1
                v = v >> 1
                self.f = (c << 4) | (0x80 if v == 0 else 0)
        elif cb_op < 16:  # BIT
            bit = cb_op - 8
            self.f = (self.f & 0x10) | 0x20 | (0x80 if not (v & (1 << bit)) else 0)
            return 12 if reg_idx == 6 else 8
        elif cb_op < 24:  # RES
            bit = cb_op - 16
            v &= ~(1 << bit)
        else:  # SET
            bit = cb_op - 24
            v |= 1 << bit
        
        # Guardar resultado
        if reg_idx == 0: self.b = v
        elif reg_idx == 1: self.c = v
        elif reg_idx == 2: self.d = v
        elif reg_idx == 3: self.e = v
        elif reg_idx == 4: self.h = v
        elif reg_idx == 5: self.l = v
        elif reg_idx == 6:
            self.mmu.write((self.h << 8) | self.l, v)
            return 16
        else: self.a = v
        
        return 8