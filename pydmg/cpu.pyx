# cpu.pyx
# cython: language_level=3
# cython: boundscheck=False
# cython: wraparound=False
# cython: cdivision=True
# cython: initializedcheck=False

cimport cython
from libc.stdint cimport uint8_t, uint16_t, int8_t, int16_t

cdef class CPU:
    # Atributos tipados
    cdef object mmu
    
    # Registros como C types
    cdef public uint8_t a, b, c, d, e, f, h, l
    cdef public uint16_t sp, pc
    cdef public bint halted, ime, halt_bug
    cdef public int ei_delay
    cdef public int cycles
    
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
        self.ei_delay = 0
        self.halt_bug = False
        self.cycles = 0
    
    # =========================================================================
    # PROPIEDADES DE REGISTROS
    # =========================================================================
    
    @property
    def hl(self):
        return (self.h << 8) | self.l
    
    @hl.setter
    def hl(self, uint16_t value):
        self.h = (value >> 8) & 0xFF
        self.l = value & 0xFF
    
    @property
    def bc(self):
        return (self.b << 8) | self.c
    
    @bc.setter
    def bc(self, uint16_t value):
        self.b = (value >> 8) & 0xFF
        self.c = value & 0xFF
    
    @property
    def de(self):
        return (self.d << 8) | self.e
    
    @de.setter
    def de(self, uint16_t value):
        self.d = (value >> 8) & 0xFF
        self.e = value & 0xFF
    
    @property
    def af(self):
        return (self.a << 8) | self.f
    
    @af.setter
    def af(self, uint16_t value):
        self.a = (value >> 8) & 0xFF
        self.f = value & 0xF0
    
    # =========================================================================
    # MÉTODOS INLINE
    # =========================================================================
    
    cdef inline void _tick(self, int m_cycles=1):
        cdef int t = m_cycles << 2
        self.cycles += t
        
        if self.mmu.timer is not None:
            self.mmu.timer.step(t)
        if self.mmu.ppu is not None:
            self.mmu.ppu.step(t)
    
    cdef inline uint8_t _fetch(self):
        cdef uint8_t v
        cdef uint16_t pc = self.pc
        
        v = self.mmu.read(pc)
        self.pc = (pc + 1) & 0xFFFF
        self._tick(1)
        return v
    
    cdef inline uint16_t _fetch_word(self):
        cdef uint8_t lo = self._fetch()
        cdef uint8_t hi = self._fetch()
        return (hi << 8) | lo
    
    cdef inline uint8_t _read(self, uint16_t addr):
        self._tick(1)
        return self.mmu.read(addr)
    
    cdef inline void _write(self, uint16_t addr, uint8_t v):
        self._tick(1)
        self.mmu.write(addr, v)
    
    cdef inline void _push_word(self, uint16_t value):
        self.sp = (self.sp - 1) & 0xFFFF
        self._write(self.sp, (value >> 8) & 0xFF)
        self.sp = (self.sp - 1) & 0xFFFF
        self._write(self.sp, value & 0xFF)
    
    cdef inline uint16_t _pop_word(self):
        cdef uint8_t lo = self._read(self.sp)
        self.sp = (self.sp + 1) & 0xFFFF
        cdef uint8_t hi = self._read(self.sp)
        self.sp = (self.sp + 1) & 0xFFFF
        return (hi << 8) | lo
    
    # =========================================================================
    # GETTERS/SETTERS DE REGISTROS
    # =========================================================================
    
    cdef inline uint8_t _get_reg(self, int r):
        if r == 0: return self.b
        elif r == 1: return self.c
        elif r == 2: return self.d
        elif r == 3: return self.e
        elif r == 4: return self.h
        elif r == 5: return self.l
        elif r == 6: return self._read((self.h << 8) | self.l)
        else: return self.a
    
    cdef inline void _set_reg(self, int r, uint8_t v):
        if r == 0: self.b = v
        elif r == 1: self.c = v
        elif r == 2: self.d = v
        elif r == 3: self.e = v
        elif r == 4: self.h = v
        elif r == 5: self.l = v
        elif r == 6: self._write((self.h << 8) | self.l, v)
        else: self.a = v
    
    # =========================================================================
    # STEP PRINCIPAL
    # =========================================================================
    
    cpdef int step(self):
        cdef uint8_t opcode, ie, if_reg, pending, mask
        cdef int i
        
        self.cycles = 0
        
        # EI delay
        if self.ei_delay > 0:
            self.ei_delay -= 1
            if self.ei_delay == 0:
                self.ime = True
        
        # Interrupciones
        ie = self.mmu.ie
        if_reg = self.mmu.io[0x0F]
        pending = ie & if_reg & 0x1F
        
        if self.ime and pending:
            self.halted = False
            self.ime = False
            
            for i in range(5):
                mask = 1 << i
                if pending & mask:
                    self.mmu.io[0x0F] = if_reg & ~mask
                    self._tick(2)
                    self._push_word(self.pc)
                    self.pc = 0x0040 + (i << 3)
                    self._tick(1)
                    return self.cycles
        
        if self.halted:
            if pending:
                self.halted = False
            else:
                self._tick(1)
                return self.cycles
        
        # Fetch y ejecutar
        opcode = self._fetch()
        self._execute(opcode)
        
        return self.cycles
    
    # =========================================================================
    # EJECUCIÓN PRINCIPAL
    # =========================================================================
    
    cdef void _execute(self, uint8_t op):
        cdef uint8_t n, v, r, lo, hi
        cdef uint16_t addr, hl, bc, de
        cdef int8_t offset
        cdef int result, c
        
        # NOP
        if op == 0x00:
            pass
        
        # LD BC,nn
        elif op == 0x01:
            self.c = self._fetch()
            self.b = self._fetch()
        
        # LD (BC),A
        elif op == 0x02:
            self._write((self.b << 8) | self.c, self.a)
        
        # INC BC
        elif op == 0x03:
            bc = ((self.b << 8) | self.c) + 1
            self.b = (bc >> 8) & 0xFF
            self.c = bc & 0xFF
            self._tick(1)
        
        # INC B
        elif op == 0x04:
            v = self.b
            r = (v + 1) & 0xFF
            self.f = (self.f & 0x10) | (0x80 if r == 0 else 0) | (0x20 if (v & 0xF) == 0xF else 0)
            self.b = r
        
        # DEC B
        elif op == 0x05:
            v = self.b
            r = (v - 1) & 0xFF
            self.f = (self.f & 0x10) | 0x40 | (0x80 if r == 0 else 0) | (0x20 if (v & 0xF) == 0 else 0)
            self.b = r
        
        # LD B,n
        elif op == 0x06:
            self.b = self._fetch()
        
        # RLCA
        elif op == 0x07:
            c = self.a >> 7
            self.a = ((self.a << 1) | c) & 0xFF
            self.f = c << 4
        
        # LD (nn),SP
        elif op == 0x08:
            addr = self._fetch_word()
            self._write(addr, self.sp & 0xFF)
            self._write((addr + 1) & 0xFFFF, self.sp >> 8)
        
        # ADD HL,BC
        elif op == 0x09:
            hl = (self.h << 8) | self.l
            bc = (self.b << 8) | self.c
            result = hl + bc
            self.f = (self.f & 0x80) | (0x20 if (hl & 0xFFF) + (bc & 0xFFF) > 0xFFF else 0) | (0x10 if result > 0xFFFF else 0)
            self.h = (result >> 8) & 0xFF
            self.l = result & 0xFF
            self._tick(1)
        
        # LD A,(BC)
        elif op == 0x0A:
            self.a = self._read((self.b << 8) | self.c)
        
        # DEC BC
        elif op == 0x0B:
            bc = ((self.b << 8) | self.c) - 1
            self.b = (bc >> 8) & 0xFF
            self.c = bc & 0xFF
            self._tick(1)
        
        # INC C
        elif op == 0x0C:
            v = self.c
            r = (v + 1) & 0xFF
            self.f = (self.f & 0x10) | (0x80 if r == 0 else 0) | (0x20 if (v & 0xF) == 0xF else 0)
            self.c = r
        
        # DEC C
        elif op == 0x0D:
            v = self.c
            r = (v - 1) & 0xFF
            self.f = (self.f & 0x10) | 0x40 | (0x80 if r == 0 else 0) | (0x20 if (v & 0xF) == 0 else 0)
            self.c = r
        
        # LD C,n
        elif op == 0x0E:
            self.c = self._fetch()
        
        # RRCA
        elif op == 0x0F:
            c = self.a & 1
            self.a = (self.a >> 1) | (c << 7)
            self.f = c << 4
        
        # STOP
        elif op == 0x10:
            self._fetch()
        
        # LD DE,nn
        elif op == 0x11:
            self.e = self._fetch()
            self.d = self._fetch()
        
        # LD (DE),A
        elif op == 0x12:
            self._write((self.d << 8) | self.e, self.a)
        
        # INC DE
        elif op == 0x13:
            de = ((self.d << 8) | self.e) + 1
            self.d = (de >> 8) & 0xFF
            self.e = de & 0xFF
            self._tick(1)
        
        # INC D
        elif op == 0x14:
            v = self.d
            r = (v + 1) & 0xFF
            self.f = (self.f & 0x10) | (0x80 if r == 0 else 0) | (0x20 if (v & 0xF) == 0xF else 0)
            self.d = r
        
        # DEC D
        elif op == 0x15:
            v = self.d
            r = (v - 1) & 0xFF
            self.f = (self.f & 0x10) | 0x40 | (0x80 if r == 0 else 0) | (0x20 if (v & 0xF) == 0 else 0)
            self.d = r
        
        # LD D,n
        elif op == 0x16:
            self.d = self._fetch()
        
        # RLA
        elif op == 0x17:
            c = self.a >> 7
            self.a = ((self.a << 1) | ((self.f >> 4) & 1)) & 0xFF
            self.f = c << 4
        
        # JR n
        elif op == 0x18:
            n = self._fetch()
            if n > 127:
                offset = <int8_t>(n - 256)
            else:
                offset = <int8_t>n
            self.pc = (self.pc + offset) & 0xFFFF
            self._tick(1)
        
        # ADD HL,DE
        elif op == 0x19:
            hl = (self.h << 8) | self.l
            de = (self.d << 8) | self.e
            result = hl + de
            self.f = (self.f & 0x80) | (0x20 if (hl & 0xFFF) + (de & 0xFFF) > 0xFFF else 0) | (0x10 if result > 0xFFFF else 0)
            self.h = (result >> 8) & 0xFF
            self.l = result & 0xFF
            self._tick(1)
        
        # LD A,(DE)
        elif op == 0x1A:
            self.a = self._read((self.d << 8) | self.e)
        
        # DEC DE
        elif op == 0x1B:
            de = ((self.d << 8) | self.e) - 1
            self.d = (de >> 8) & 0xFF
            self.e = de & 0xFF
            self._tick(1)
        
        # INC E
        elif op == 0x1C:
            v = self.e
            r = (v + 1) & 0xFF
            self.f = (self.f & 0x10) | (0x80 if r == 0 else 0) | (0x20 if (v & 0xF) == 0xF else 0)
            self.e = r
        
        # DEC E
        elif op == 0x1D:
            v = self.e
            r = (v - 1) & 0xFF
            self.f = (self.f & 0x10) | 0x40 | (0x80 if r == 0 else 0) | (0x20 if (v & 0xF) == 0 else 0)
            self.e = r
        
        # LD E,n
        elif op == 0x1E:
            self.e = self._fetch()
        
        # RRA
        elif op == 0x1F:
            c = self.a & 1
            self.a = (self.a >> 1) | ((self.f << 3) & 0x80)
            self.f = c << 4
        
        # JR NZ,n
        elif op == 0x20:
            n = self._fetch()
            if not (self.f & 0x80):
                if n > 127:
                    offset = <int8_t>(n - 256)
                else:
                    offset = <int8_t>n
                self.pc = (self.pc + offset) & 0xFFFF
                self._tick(1)
        
        # LD HL,nn
        elif op == 0x21:
            self.l = self._fetch()
            self.h = self._fetch()
        
        # LDI (HL),A
        elif op == 0x22:
            hl = (self.h << 8) | self.l
            self._write(hl, self.a)
            hl = (hl + 1) & 0xFFFF
            self.h = hl >> 8
            self.l = hl & 0xFF
        
        # INC HL
        elif op == 0x23:
            hl = ((self.h << 8) | self.l) + 1
            self.h = (hl >> 8) & 0xFF
            self.l = hl & 0xFF
            self._tick(1)
        
        # INC H
        elif op == 0x24:
            v = self.h
            r = (v + 1) & 0xFF
            self.f = (self.f & 0x10) | (0x80 if r == 0 else 0) | (0x20 if (v & 0xF) == 0xF else 0)
            self.h = r
        
        # DEC H
        elif op == 0x25:
            v = self.h
            r = (v - 1) & 0xFF
            self.f = (self.f & 0x10) | 0x40 | (0x80 if r == 0 else 0) | (0x20 if (v & 0xF) == 0 else 0)
            self.h = r
        
        # LD H,n
        elif op == 0x26:
            self.h = self._fetch()
        
        # DAA
        elif op == 0x27:
            self._daa()
        
        # JR Z,n
        elif op == 0x28:
            n = self._fetch()
            if self.f & 0x80:
                if n > 127:
                    offset = <int8_t>(n - 256)
                else:
                    offset = <int8_t>n
                self.pc = (self.pc + offset) & 0xFFFF
                self._tick(1)
        
        # ADD HL,HL
        elif op == 0x29:
            hl = (self.h << 8) | self.l
            result = hl << 1
            self.f = (self.f & 0x80) | (0x20 if (hl & 0xFFF) * 2 > 0xFFF else 0) | (0x10 if result > 0xFFFF else 0)
            self.h = (result >> 8) & 0xFF
            self.l = result & 0xFF
            self._tick(1)
        
        # LDI A,(HL)
        elif op == 0x2A:
            hl = (self.h << 8) | self.l
            self.a = self._read(hl)
            hl = (hl + 1) & 0xFFFF
            self.h = hl >> 8
            self.l = hl & 0xFF
        
        # DEC HL
        elif op == 0x2B:
            hl = ((self.h << 8) | self.l) - 1
            self.h = (hl >> 8) & 0xFF
            self.l = hl & 0xFF
            self._tick(1)
        
        # INC L
        elif op == 0x2C:
            v = self.l
            r = (v + 1) & 0xFF
            self.f = (self.f & 0x10) | (0x80 if r == 0 else 0) | (0x20 if (v & 0xF) == 0xF else 0)
            self.l = r
        
        # DEC L
        elif op == 0x2D:
            v = self.l
            r = (v - 1) & 0xFF
            self.f = (self.f & 0x10) | 0x40 | (0x80 if r == 0 else 0) | (0x20 if (v & 0xF) == 0 else 0)
            self.l = r
        
        # LD L,n
        elif op == 0x2E:
            self.l = self._fetch()
        
        # CPL
        elif op == 0x2F:
            self.a ^= 0xFF
            self.f |= 0x60
        
        # JR NC,n
        elif op == 0x30:
            n = self._fetch()
            if not (self.f & 0x10):
                if n > 127:
                    offset = <int8_t>(n - 256)
                else:
                    offset = <int8_t>n
                self.pc = (self.pc + offset) & 0xFFFF
                self._tick(1)
        
        # LD SP,nn
        elif op == 0x31:
            self.sp = self._fetch_word()
        
        # LDD (HL),A
        elif op == 0x32:
            hl = (self.h << 8) | self.l
            self._write(hl, self.a)
            hl = (hl - 1) & 0xFFFF
            self.h = hl >> 8
            self.l = hl & 0xFF
        
        # INC SP
        elif op == 0x33:
            self.sp = (self.sp + 1) & 0xFFFF
            self._tick(1)
        
        # INC (HL)
        elif op == 0x34:
            hl = (self.h << 8) | self.l
            v = self._read(hl)
            r = (v + 1) & 0xFF
            self.f = (self.f & 0x10) | (0x80 if r == 0 else 0) | (0x20 if (v & 0xF) == 0xF else 0)
            self._write(hl, r)
        
        # DEC (HL)
        elif op == 0x35:
            hl = (self.h << 8) | self.l
            v = self._read(hl)
            r = (v - 1) & 0xFF
            self.f = (self.f & 0x10) | 0x40 | (0x80 if r == 0 else 0) | (0x20 if (v & 0xF) == 0 else 0)
            self._write(hl, r)
        
        # LD (HL),n
        elif op == 0x36:
            n = self._fetch()
            self._write((self.h << 8) | self.l, n)
        
        # SCF
        elif op == 0x37:
            self.f = (self.f & 0x80) | 0x10
        
        # JR C,n
        elif op == 0x38:
            n = self._fetch()
            if self.f & 0x10:
                if n > 127:
                    offset = <int8_t>(n - 256)
                else:
                    offset = <int8_t>n
                self.pc = (self.pc + offset) & 0xFFFF
                self._tick(1)
        
        # ADD HL,SP
        elif op == 0x39:
            hl = (self.h << 8) | self.l
            result = hl + self.sp
            self.f = (self.f & 0x80) | (0x20 if (hl & 0xFFF) + (self.sp & 0xFFF) > 0xFFF else 0) | (0x10 if result > 0xFFFF else 0)
            self.h = (result >> 8) & 0xFF
            self.l = result & 0xFF
            self._tick(1)
        
        # LDD A,(HL)
        elif op == 0x3A:
            hl = (self.h << 8) | self.l
            self.a = self._read(hl)
            hl = (hl - 1) & 0xFFFF
            self.h = hl >> 8
            self.l = hl & 0xFF
        
        # DEC SP
        elif op == 0x3B:
            self.sp = (self.sp - 1) & 0xFFFF
            self._tick(1)
        
        # INC A
        elif op == 0x3C:
            v = self.a
            r = (v + 1) & 0xFF
            self.f = (self.f & 0x10) | (0x80 if r == 0 else 0) | (0x20 if (v & 0xF) == 0xF else 0)
            self.a = r
        
        # DEC A
        elif op == 0x3D:
            v = self.a
            r = (v - 1) & 0xFF
            self.f = (self.f & 0x10) | 0x40 | (0x80 if r == 0 else 0) | (0x20 if (v & 0xF) == 0 else 0)
            self.a = r
        
        # LD A,n
        elif op == 0x3E:
            self.a = self._fetch()
        
        # CCF
        elif op == 0x3F:
            self.f = (self.f & 0x80) | ((self.f ^ 0x10) & 0x10)
        
        # LD r,r' y HALT (0x40-0x7F)
        elif 0x40 <= op <= 0x7F:
            if op == 0x76:
                self._halt()
            else:
                self._ld_r_r(op)
        
        # ALU (0x80-0xBF)
        elif 0x80 <= op <= 0xBF:
            self._alu(op)
        
        # 0xC0 - 0xFF
        else:
            self._execute_cx_fx(op)
    
    cdef void _execute_cx_fx(self, uint8_t op):
        cdef uint8_t n, lo, hi
        cdef uint16_t addr
        cdef int8_t sn
        cdef int result, c
        
        # RET NZ
        if op == 0xC0:
            self._tick(1)
            if not (self.f & 0x80):
                self.pc = self._pop_word()
                self._tick(1)
        
        # POP BC
        elif op == 0xC1:
            addr = self._pop_word()
            self.b = addr >> 8
            self.c = addr & 0xFF
        
        # JP NZ,nn
        elif op == 0xC2:
            addr = self._fetch_word()
            if not (self.f & 0x80):
                self.pc = addr
                self._tick(1)
        
        # JP nn
        elif op == 0xC3:
            self.pc = self._fetch_word()
            self._tick(1)
        
        # CALL NZ,nn
        elif op == 0xC4:
            addr = self._fetch_word()
            if not (self.f & 0x80):
                self._tick(1)
                self._push_word(self.pc)
                self.pc = addr
        
        # PUSH BC
        elif op == 0xC5:
            self._tick(1)
            self._push_word((self.b << 8) | self.c)
        
        # ADD A,n
        elif op == 0xC6:
            n = self._fetch()
            result = self.a + n
            self.f = (0x80 if (result & 0xFF) == 0 else 0) | \
                     (0x20 if (self.a & 0xF) + (n & 0xF) > 0xF else 0) | \
                     (0x10 if result > 0xFF else 0)
            self.a = result & 0xFF
        
        # RST 00
        elif op == 0xC7:
            self._tick(1)
            self._push_word(self.pc)
            self.pc = 0x00
        
        # RET Z
        elif op == 0xC8:
            self._tick(1)
            if self.f & 0x80:
                self.pc = self._pop_word()
                self._tick(1)
        
        # RET
        elif op == 0xC9:
            self.pc = self._pop_word()
            self._tick(1)
        
        # JP Z,nn
        elif op == 0xCA:
            addr = self._fetch_word()
            if self.f & 0x80:
                self.pc = addr
                self._tick(1)
        
        # CB prefix
        elif op == 0xCB:
            self._cb()
        
        # CALL Z,nn
        elif op == 0xCC:
            addr = self._fetch_word()
            if self.f & 0x80:
                self._tick(1)
                self._push_word(self.pc)
                self.pc = addr
        
        # CALL nn
        elif op == 0xCD:
            addr = self._fetch_word()
            self._tick(1)
            self._push_word(self.pc)
            self.pc = addr
        
        # ADC A,n
        elif op == 0xCE:
            n = self._fetch()
            c = (self.f >> 4) & 1
            result = self.a + n + c
            self.f = (0x80 if (result & 0xFF) == 0 else 0) | \
                     (0x20 if (self.a & 0xF) + (n & 0xF) + c > 0xF else 0) | \
                     (0x10 if result > 0xFF else 0)
            self.a = result & 0xFF
        
        # RST 08
        elif op == 0xCF:
            self._tick(1)
            self._push_word(self.pc)
            self.pc = 0x08
        
        # RET NC
        elif op == 0xD0:
            self._tick(1)
            if not (self.f & 0x10):
                self.pc = self._pop_word()
                self._tick(1)
        
        # POP DE
        elif op == 0xD1:
            addr = self._pop_word()
            self.d = addr >> 8
            self.e = addr & 0xFF
        
        # JP NC,nn
        elif op == 0xD2:
            addr = self._fetch_word()
            if not (self.f & 0x10):
                self.pc = addr
                self._tick(1)
        
        # CALL NC,nn
        elif op == 0xD4:
            addr = self._fetch_word()
            if not (self.f & 0x10):
                self._tick(1)
                self._push_word(self.pc)
                self.pc = addr
        
        # PUSH DE
        elif op == 0xD5:
            self._tick(1)
            self._push_word((self.d << 8) | self.e)
        
        # SUB n
        elif op == 0xD6:
            n = self._fetch()
            result = self.a - n
            self.f = 0x40 | (0x80 if (result & 0xFF) == 0 else 0) | \
                     (0x20 if (self.a & 0xF) < (n & 0xF) else 0) | \
                     (0x10 if result < 0 else 0)
            self.a = result & 0xFF
        
        # RST 10
        elif op == 0xD7:
            self._tick(1)
            self._push_word(self.pc)
            self.pc = 0x10
        
        # RET C
        elif op == 0xD8:
            self._tick(1)
            if self.f & 0x10:
                self.pc = self._pop_word()
                self._tick(1)
        
        # RETI
        elif op == 0xD9:
            self.pc = self._pop_word()
            self._tick(1)
            self.ime = True
        
        # JP C,nn
        elif op == 0xDA:
            addr = self._fetch_word()
            if self.f & 0x10:
                self.pc = addr
                self._tick(1)
        
        # CALL C,nn
        elif op == 0xDC:
            addr = self._fetch_word()
            if self.f & 0x10:
                self._tick(1)
                self._push_word(self.pc)
                self.pc = addr
        
        # SBC A,n
        elif op == 0xDE:
            n = self._fetch()
            c = (self.f >> 4) & 1
            result = self.a - n - c
            self.f = 0x40 | (0x80 if (result & 0xFF) == 0 else 0) | \
                     (0x20 if (self.a & 0xF) < (n & 0xF) + c else 0) | \
                     (0x10 if result < 0 else 0)
            self.a = result & 0xFF
        
        # RST 18
        elif op == 0xDF:
            self._tick(1)
            self._push_word(self.pc)
            self.pc = 0x18
        
        # LDH (n),A
        elif op == 0xE0:
            n = self._fetch()
            self._write(0xFF00 + n, self.a)
        
        # POP HL
        elif op == 0xE1:
            addr = self._pop_word()
            self.h = addr >> 8
            self.l = addr & 0xFF
        
        # LDH (C),A
        elif op == 0xE2:
            self._write(0xFF00 + self.c, self.a)
        
        # PUSH HL
        elif op == 0xE5:
            self._tick(1)
            self._push_word((self.h << 8) | self.l)
        
        # AND n
        elif op == 0xE6:
            self.a &= self._fetch()
            self.f = 0x20 | (0x80 if self.a == 0 else 0)
        
        # RST 20
        elif op == 0xE7:
            self._tick(1)
            self._push_word(self.pc)
            self.pc = 0x20
        
        # ADD SP,n
        elif op == 0xE8:
            n = self._fetch()
            if n > 127:
                sn = <int8_t>(n - 256)
            else:
                sn = <int8_t>n
            self.f = (0x20 if (self.sp & 0xF) + (n & 0xF) > 0xF else 0) | \
                     (0x10 if (self.sp & 0xFF) + n > 0xFF else 0)
            self.sp = (self.sp + sn) & 0xFFFF
            self._tick(2)
        
        # JP HL
        elif op == 0xE9:
            self.pc = (self.h << 8) | self.l
        
        # LD (nn),A
        elif op == 0xEA:
            addr = self._fetch_word()
            self._write(addr, self.a)
        
        # XOR n
        elif op == 0xEE:
            self.a ^= self._fetch()
            self.f = 0x80 if self.a == 0 else 0
        
        # RST 28
        elif op == 0xEF:
            self._tick(1)
            self._push_word(self.pc)
            self.pc = 0x28
        
        # LDH A,(n)
        elif op == 0xF0:
            n = self._fetch()
            self.a = self._read(0xFF00 + n)
        
        # POP AF
        elif op == 0xF1:
            addr = self._pop_word()
            self.a = addr >> 8
            self.f = addr & 0xF0
        
        # LDH A,(C)
        elif op == 0xF2:
            self.a = self._read(0xFF00 + self.c)
        
        # DI
        elif op == 0xF3:
            self.ime = False
            self.ei_delay = 0
        
        # PUSH AF
        elif op == 0xF5:
            self._tick(1)
            self._push_word((self.a << 8) | self.f)
        
        # OR n
        elif op == 0xF6:
            self.a |= self._fetch()
            self.f = 0x80 if self.a == 0 else 0
        
        # RST 30
        elif op == 0xF7:
            self._tick(1)
            self._push_word(self.pc)
            self.pc = 0x30
        
        # LD HL,SP+n
        elif op == 0xF8:
            n = self._fetch()
            if n > 127:
                sn = <int8_t>(n - 256)
            else:
                sn = <int8_t>n
            self.f = (0x20 if (self.sp & 0xF) + (n & 0xF) > 0xF else 0) | \
                     (0x10 if (self.sp & 0xFF) + n > 0xFF else 0)
            addr = (self.sp + sn) & 0xFFFF
            self.h = addr >> 8
            self.l = addr & 0xFF
            self._tick(1)
        
        # LD SP,HL
        elif op == 0xF9:
            self.sp = (self.h << 8) | self.l
            self._tick(1)
        
        # LD A,(nn)
        elif op == 0xFA:
            addr = self._fetch_word()
            self.a = self._read(addr)
        
        # EI
        elif op == 0xFB:
            self.ei_delay = 1
        
        # CP n
        elif op == 0xFE:
            n = self._fetch()
            result = self.a - n
            self.f = 0x40 | (0x80 if (result & 0xFF) == 0 else 0) | \
                     (0x20 if (self.a & 0xF) < (n & 0xF) else 0) | \
                     (0x10 if result < 0 else 0)
        
        # RST 38
        elif op == 0xFF:
            self._tick(1)
            self._push_word(self.pc)
            self.pc = 0x38
    
    # =========================================================================
    # INSTRUCCIONES AUXILIARES
    # =========================================================================
    
    cdef void _halt(self):
        cdef uint8_t ie = self.mmu.ie
        cdef uint8_t if_reg = self.mmu.io[0x0F]
        cdef uint8_t pending = ie & if_reg & 0x1F
        
        if self.ime:
            self.halted = True
        elif pending:
            self.halt_bug = True
        else:
            self.halted = True
    
    cdef void _daa(self):
        cdef int a = self.a
        cdef int correction = 0
        cdef bint set_carry = False
        cdef uint8_t f = self.f
        
        if f & 0x20 or (not (f & 0x40) and (a & 0xF) > 9):
            correction |= 0x06
        
        if f & 0x10 or (not (f & 0x40) and a > 0x99):
            correction |= 0x60
            set_carry = True
        
        if f & 0x40:
            a = (a - correction) & 0xFF
        else:
            a = (a + correction) & 0xFF
        
        self.a = a
        self.f = (f & 0x40) | (0x80 if a == 0 else 0) | (0x10 if set_carry else 0)
    
    cdef void _ld_r_r(self, uint8_t op):
        cdef int src = op & 0x07
        cdef int dst = (op >> 3) & 0x07
        cdef uint8_t v = self._get_reg(src)
        self._set_reg(dst, v)
    
    cdef void _alu(self, uint8_t op):
        cdef int src = op & 0x07
        cdef int alu_op = (op >> 3) & 0x07
        cdef uint8_t v = self._get_reg(src)
        cdef uint8_t a = self.a
        cdef int r, c
        
        if alu_op == 0:  # ADD
            r = a + v
            self.f = (0x80 if (r & 0xFF) == 0 else 0) | \
                     (0x20 if (a & 0xF) + (v & 0xF) > 0xF else 0) | \
                     (0x10 if r > 0xFF else 0)
            self.a = r & 0xFF
        
        elif alu_op == 1:  # ADC
            c = (self.f >> 4) & 1
            r = a + v + c
            self.f = (0x80 if (r & 0xFF) == 0 else 0) | \
                     (0x20 if (a & 0xF) + (v & 0xF) + c > 0xF else 0) | \
                     (0x10 if r > 0xFF else 0)
            self.a = r & 0xFF
        
        elif alu_op == 2:  # SUB
            r = a - v
            self.f = 0x40 | (0x80 if (r & 0xFF) == 0 else 0) | \
                     (0x20 if (a & 0xF) < (v & 0xF) else 0) | \
                     (0x10 if r < 0 else 0)
            self.a = r & 0xFF
        
        elif alu_op == 3:  # SBC
            c = (self.f >> 4) & 1
            r = a - v - c
            self.f = 0x40 | (0x80 if (r & 0xFF) == 0 else 0) | \
                     (0x20 if (a & 0xF) < (v & 0xF) + c else 0) | \
                     (0x10 if r < 0 else 0)
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
            self.f = 0x40 | (0x80 if (r & 0xFF) == 0 else 0) | \
                     (0x20 if (a & 0xF) < (v & 0xF) else 0) | \
                     (0x10 if r < 0 else 0)
    
    cdef void _cb(self):
        cdef uint8_t op = self._fetch()
        cdef int reg = op & 0x07
        cdef int cb_op = op >> 3
        cdef uint8_t v, c
        cdef uint16_t hl
        cdef int bit
        
        # Leer valor
        if reg == 6:
            hl = (self.h << 8) | self.l
            v = self._read(hl)
        else:
            v = self._get_reg(reg)
        
        if cb_op < 8:  # Rotaciones/Shifts
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
            
            # Escribir resultado
            if reg == 6:
                self._write(hl, v)
            else:
                self._set_reg(reg, v)
        
        elif cb_op < 16:  # BIT
            bit = cb_op - 8
            self.f = (self.f & 0x10) | 0x20 | (0x80 if not (v & (1 << bit)) else 0)
        
        elif cb_op < 24:  # RES
            bit = cb_op - 16
            v &= ~(1 << bit)
            if reg == 6:
                self._write(hl, v)
            else:
                self._set_reg(reg, v)
        
        else:  # SET
            bit = cb_op - 24
            v |= 1 << bit
            if reg == 6:
                self._write(hl, v)
            else:
                self._set_reg(reg, v)