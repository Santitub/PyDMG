# cython: language_level=3, boundscheck=False, wraparound=False, cdivision=True
"""
CPU Sharp LR35902 - Con timing preciso por M-cycle
"""

cimport cython
from libc.stdint cimport uint8_t, uint16_t, int8_t


cdef class CPU:
    # Registros
    cdef public uint8_t a, b, c, d, e, f, h, l
    cdef public uint16_t sp, pc
    cdef public bint halted, ime, ime_next
    
    # HALT bug
    cdef bint halt_bug
    
    # MMU y componentes
    cdef object mmu
    cdef object ppu
    cdef object timer
    
    # Dispatch tables
    cdef object _ops
    cdef object _cb_ops
    
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
        self.halt_bug = False
        
        self.ppu = None
        self.timer = None
        
        self._ops = self._build_ops()
        self._cb_ops = self._build_cb_ops()
    
    def set_components(self, ppu, timer):
        """Conecta PPU y Timer para ticking preciso"""
        self.ppu = ppu
        self.timer = timer
    
    cdef inline void _tick(self, int cycles):
        """Tick de componentes - llamado en cada acceso a memoria"""
        if self.timer is not None:
            self.timer.step(cycles)
        if self.ppu is not None:
            self.ppu.step(cycles)
    
    cdef inline uint8_t _read(self, uint16_t addr):
        """Lee memoria con tick de 4 ciclos"""
        self._tick(4)
        return self.mmu.read(addr)
    
    cdef inline void _write(self, uint16_t addr, uint8_t value):
        """Escribe memoria con tick de 4 ciclos"""
        self._tick(4)
        self.mmu.write(addr, value)
    
    cdef inline uint8_t _fetch(self):
        """Fetch con tick - también maneja HALT bug"""
        cdef uint8_t val = self._read(self.pc)
        if self.halt_bug:
            self.halt_bug = False
            # No incrementar PC (bug de HALT)
        else:
            self.pc = (self.pc + 1) & 0xFFFF
        return val
    
    cdef inline uint16_t _fetch16(self):
        """Fetch 16-bit con ticks correctos"""
        cdef uint8_t lo = self._fetch()
        cdef uint8_t hi = self._fetch()
        return (hi << 8) | lo
    
    cdef inline void _push(self, uint16_t value):
        """Push con ticks correctos"""
        self._tick(4)  # Ciclo interno
        self.sp = (self.sp - 1) & 0xFFFF
        self._write(self.sp, (value >> 8) & 0xFF)
        self.sp = (self.sp - 1) & 0xFFFF
        self._write(self.sp, value & 0xFF)
    
    cdef inline uint16_t _pop(self):
        """Pop con ticks correctos"""
        cdef uint8_t lo = self._read(self.sp)
        self.sp = (self.sp + 1) & 0xFFFF
        cdef uint8_t hi = self._read(self.sp)
        self.sp = (self.sp + 1) & 0xFFFF
        return (hi << 8) | lo
    
    cpdef int step(self):
        """Ejecuta una instrucción - retorna ciclos para compatibilidad"""
        cdef uint8_t ie, if_reg, pending, op
        cdef int i
        cdef int cycles_start, cycles_end
        
        # Manejar interrupciones
        ie = self.mmu.ie
        if_reg = self.mmu.io[0x0F]
        pending = ie & if_reg & 0x1F
        
        if self.ime and pending:
            self.ime = False
            self.halted = False
            
            # Encontrar interrupción con mayor prioridad
            for i in range(5):
                if pending & (1 << i):
                    self.mmu.io[0x0F] = if_reg & ~(1 << i)
                    
                    # Push PC (con ticks)
                    self._tick(4)  # Ciclos internos
                    self._tick(4)
                    self.sp = (self.sp - 1) & 0xFFFF
                    self._write(self.sp, (self.pc >> 8) & 0xFF)
                    self.sp = (self.sp - 1) & 0xFFFF
                    self._write(self.sp, self.pc & 0xFF)
                    
                    self.pc = 0x0040 + (i << 3)
                    return 20
        
        # HALT
        if self.halted:
            if pending:
                self.halted = False
            else:
                self._tick(4)
                return 4
        
        # Fetch opcode
        op = self._fetch()
        
        # Ejecutar
        self._ops[op]()
        
        # EI delay
        if self.ime_next:
            self.ime = True
            self.ime_next = False
        
        # Nota: Los ciclos ya se contaron en _tick(), 
        # retornamos 0 para indicar que ya se procesaron
        return 0
    
    cdef inline uint8_t _inc8(self, uint8_t v):
        cdef uint8_t r = (v + 1) & 0xFF
        self.f = (self.f & 0x10) | (0x80 if r == 0 else 0) | (0x20 if (v & 0xF) == 0xF else 0)
        return r
    
    cdef inline uint8_t _dec8(self, uint8_t v):
        cdef uint8_t r = (v - 1) & 0xFF
        self.f = (self.f & 0x10) | 0x40 | (0x80 if r == 0 else 0) | (0x20 if (v & 0xF) == 0 else 0)
        return r
    
    cdef inline uint16_t _get_hl(self):
        return (self.h << 8) | self.l
    
    cdef inline void _set_hl(self, uint16_t val):
        self.h = (val >> 8) & 0xFF
        self.l = val & 0xFF
    
    cdef inline uint8_t _get_reg(self, int idx):
        if idx == 0: return self.b
        elif idx == 1: return self.c
        elif idx == 2: return self.d
        elif idx == 3: return self.e
        elif idx == 4: return self.h
        elif idx == 5: return self.l
        elif idx == 6: return self._read(self._get_hl())
        else: return self.a
    
    cdef inline void _set_reg(self, int idx, uint8_t val):
        if idx == 0: self.b = val
        elif idx == 1: self.c = val
        elif idx == 2: self.d = val
        elif idx == 3: self.e = val
        elif idx == 4: self.h = val
        elif idx == 5: self.l = val
        elif idx == 6: self._write(self._get_hl(), val)
        else: self.a = val
    
    def _build_ops(self):
        ops = [None] * 256
        
        # NOP
        def op_00():
            pass
        ops[0x00] = op_00
        
        # LD BC,nn
        def op_01():
            self.c = self._fetch()
            self.b = self._fetch()
        ops[0x01] = op_01
        
        # LD (BC),A
        def op_02():
            self._write((self.b << 8) | self.c, self.a)
        ops[0x02] = op_02
        
        # INC BC
        def op_03():
            self._tick(4)  # Ciclo interno
            bc = ((self.b << 8) | self.c) + 1
            self.b = (bc >> 8) & 0xFF
            self.c = bc & 0xFF
        ops[0x03] = op_03
        
        # INC B
        def op_04():
            self.b = self._inc8(self.b)
        ops[0x04] = op_04
        
        # DEC B
        def op_05():
            self.b = self._dec8(self.b)
        ops[0x05] = op_05
        
        # LD B,n
        def op_06():
            self.b = self._fetch()
        ops[0x06] = op_06
        
        # RLCA
        def op_07():
            c = self.a >> 7
            self.a = ((self.a << 1) | c) & 0xFF
            self.f = c << 4
        ops[0x07] = op_07
        
        # LD (nn),SP
        def op_08():
            addr = self._fetch16()
            self._write(addr, self.sp & 0xFF)
            self._write(addr + 1, (self.sp >> 8) & 0xFF)
        ops[0x08] = op_08
        
        # ADD HL,BC
        def op_09():
            self._tick(4)  # Ciclo interno
            hl = self._get_hl()
            bc = (self.b << 8) | self.c
            r = hl + bc
            self.f = (self.f & 0x80) | (0x20 if (hl & 0xFFF) + (bc & 0xFFF) > 0xFFF else 0) | (0x10 if r > 0xFFFF else 0)
            self._set_hl(r & 0xFFFF)
        ops[0x09] = op_09
        
        # LD A,(BC)
        def op_0A():
            self.a = self._read((self.b << 8) | self.c)
        ops[0x0A] = op_0A
        
        # DEC BC
        def op_0B():
            self._tick(4)
            bc = (((self.b << 8) | self.c) - 1) & 0xFFFF
            self.b = bc >> 8
            self.c = bc & 0xFF
        ops[0x0B] = op_0B
        
        # INC C
        def op_0C():
            self.c = self._inc8(self.c)
        ops[0x0C] = op_0C
        
        # DEC C
        def op_0D():
            self.c = self._dec8(self.c)
        ops[0x0D] = op_0D
        
        # LD C,n
        def op_0E():
            self.c = self._fetch()
        ops[0x0E] = op_0E
        
        # RRCA
        def op_0F():
            c = self.a & 1
            self.a = (self.a >> 1) | (c << 7)
            self.f = c << 4
        ops[0x0F] = op_0F
        
        # STOP
        def op_10():
            self._fetch()  # Lee y descarta byte
        ops[0x10] = op_10
        
        # LD DE,nn
        def op_11():
            self.e = self._fetch()
            self.d = self._fetch()
        ops[0x11] = op_11
        
        # LD (DE),A
        def op_12():
            self._write((self.d << 8) | self.e, self.a)
        ops[0x12] = op_12
        
        # INC DE
        def op_13():
            self._tick(4)
            de = ((self.d << 8) | self.e) + 1
            self.d = (de >> 8) & 0xFF
            self.e = de & 0xFF
        ops[0x13] = op_13
        
        # INC D
        def op_14():
            self.d = self._inc8(self.d)
        ops[0x14] = op_14
        
        # DEC D
        def op_15():
            self.d = self._dec8(self.d)
        ops[0x15] = op_15
        
        # LD D,n
        def op_16():
            self.d = self._fetch()
        ops[0x16] = op_16
        
        # RLA
        def op_17():
            c = self.a >> 7
            self.a = ((self.a << 1) | ((self.f >> 4) & 1)) & 0xFF
            self.f = c << 4
        ops[0x17] = op_17
        
        # JR n
        def op_18():
            offset = self._fetch()
            if offset > 127:
                offset -= 256
            self._tick(4)  # Ciclo interno para salto
            self.pc = (self.pc + offset) & 0xFFFF
        ops[0x18] = op_18
        
        # ADD HL,DE
        def op_19():
            self._tick(4)
            hl = self._get_hl()
            de = (self.d << 8) | self.e
            r = hl + de
            self.f = (self.f & 0x80) | (0x20 if (hl & 0xFFF) + (de & 0xFFF) > 0xFFF else 0) | (0x10 if r > 0xFFFF else 0)
            self._set_hl(r & 0xFFFF)
        ops[0x19] = op_19
        
        # LD A,(DE)
        def op_1A():
            self.a = self._read((self.d << 8) | self.e)
        ops[0x1A] = op_1A
        
        # DEC DE
        def op_1B():
            self._tick(4)
            de = (((self.d << 8) | self.e) - 1) & 0xFFFF
            self.d = de >> 8
            self.e = de & 0xFF
        ops[0x1B] = op_1B
        
        # INC E
        def op_1C():
            self.e = self._inc8(self.e)
        ops[0x1C] = op_1C
        
        # DEC E
        def op_1D():
            self.e = self._dec8(self.e)
        ops[0x1D] = op_1D
        
        # LD E,n
        def op_1E():
            self.e = self._fetch()
        ops[0x1E] = op_1E
        
        # RRA
        def op_1F():
            c = self.a & 1
            self.a = (self.a >> 1) | ((self.f << 3) & 0x80)
            self.f = c << 4
        ops[0x1F] = op_1F
        
        # JR NZ,n
        def op_20():
            offset = self._fetch()
            if not (self.f & 0x80):
                if offset > 127:
                    offset -= 256
                self._tick(4)
                self.pc = (self.pc + offset) & 0xFFFF
        ops[0x20] = op_20
        
        # LD HL,nn
        def op_21():
            self.l = self._fetch()
            self.h = self._fetch()
        ops[0x21] = op_21
        
        # LDI (HL),A
        def op_22():
            hl = self._get_hl()
            self._write(hl, self.a)
            self._set_hl((hl + 1) & 0xFFFF)
        ops[0x22] = op_22
        
        # INC HL
        def op_23():
            self._tick(4)
            self._set_hl((self._get_hl() + 1) & 0xFFFF)
        ops[0x23] = op_23
        
        # INC H
        def op_24():
            self.h = self._inc8(self.h)
        ops[0x24] = op_24
        
        # DEC H
        def op_25():
            self.h = self._dec8(self.h)
        ops[0x25] = op_25
        
        # LD H,n
        def op_26():
            self.h = self._fetch()
        ops[0x26] = op_26
        
        # DAA
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
        ops[0x27] = op_27
        
        # JR Z,n
        def op_28():
            offset = self._fetch()
            if self.f & 0x80:
                if offset > 127:
                    offset -= 256
                self._tick(4)
                self.pc = (self.pc + offset) & 0xFFFF
        ops[0x28] = op_28
        
        # ADD HL,HL
        def op_29():
            self._tick(4)
            hl = self._get_hl()
            r = hl + hl
            self.f = (self.f & 0x80) | (0x20 if (hl & 0xFFF) * 2 > 0xFFF else 0) | (0x10 if r > 0xFFFF else 0)
            self._set_hl(r & 0xFFFF)
        ops[0x29] = op_29
        
        # LDI A,(HL)
        def op_2A():
            hl = self._get_hl()
            self.a = self._read(hl)
            self._set_hl((hl + 1) & 0xFFFF)
        ops[0x2A] = op_2A
        
        # DEC HL
        def op_2B():
            self._tick(4)
            self._set_hl((self._get_hl() - 1) & 0xFFFF)
        ops[0x2B] = op_2B
        
        # INC L
        def op_2C():
            self.l = self._inc8(self.l)
        ops[0x2C] = op_2C
        
        # DEC L
        def op_2D():
            self.l = self._dec8(self.l)
        ops[0x2D] = op_2D
        
        # LD L,n
        def op_2E():
            self.l = self._fetch()
        ops[0x2E] = op_2E
        
        # CPL
        def op_2F():
            self.a ^= 0xFF
            self.f |= 0x60
        ops[0x2F] = op_2F
        
        # JR NC,n
        def op_30():
            offset = self._fetch()
            if not (self.f & 0x10):
                if offset > 127:
                    offset -= 256
                self._tick(4)
                self.pc = (self.pc + offset) & 0xFFFF
        ops[0x30] = op_30
        
        # LD SP,nn
        def op_31():
            self.sp = self._fetch16()
        ops[0x31] = op_31
        
        # LDD (HL),A
        def op_32():
            hl = self._get_hl()
            self._write(hl, self.a)
            self._set_hl((hl - 1) & 0xFFFF)
        ops[0x32] = op_32
        
        # INC SP
        def op_33():
            self._tick(4)
            self.sp = (self.sp + 1) & 0xFFFF
        ops[0x33] = op_33
        
        # INC (HL)
        def op_34():
            hl = self._get_hl()
            v = self._read(hl)
            self._write(hl, self._inc8(v))
        ops[0x34] = op_34
        
        # DEC (HL)
        def op_35():
            hl = self._get_hl()
            v = self._read(hl)
            self._write(hl, self._dec8(v))
        ops[0x35] = op_35
        
        # LD (HL),n
        def op_36():
            self._write(self._get_hl(), self._fetch())
        ops[0x36] = op_36
        
        # SCF
        def op_37():
            self.f = (self.f & 0x80) | 0x10
        ops[0x37] = op_37
        
        # JR C,n
        def op_38():
            offset = self._fetch()
            if self.f & 0x10:
                if offset > 127:
                    offset -= 256
                self._tick(4)
                self.pc = (self.pc + offset) & 0xFFFF
        ops[0x38] = op_38
        
        # ADD HL,SP
        def op_39():
            self._tick(4)
            hl = self._get_hl()
            r = hl + self.sp
            self.f = (self.f & 0x80) | (0x20 if (hl & 0xFFF) + (self.sp & 0xFFF) > 0xFFF else 0) | (0x10 if r > 0xFFFF else 0)
            self._set_hl(r & 0xFFFF)
        ops[0x39] = op_39
        
        # LDD A,(HL)
        def op_3A():
            hl = self._get_hl()
            self.a = self._read(hl)
            self._set_hl((hl - 1) & 0xFFFF)
        ops[0x3A] = op_3A
        
        # DEC SP
        def op_3B():
            self._tick(4)
            self.sp = (self.sp - 1) & 0xFFFF
        ops[0x3B] = op_3B
        
        # INC A
        def op_3C():
            self.a = self._inc8(self.a)
        ops[0x3C] = op_3C
        
        # DEC A
        def op_3D():
            self.a = self._dec8(self.a)
        ops[0x3D] = op_3D
        
        # LD A,n
        def op_3E():
            self.a = self._fetch()
        ops[0x3E] = op_3E
        
        # CCF
        def op_3F():
            self.f = (self.f & 0x80) | ((self.f ^ 0x10) & 0x10)
        ops[0x3F] = op_3F
        
        # LD r,r (0x40-0x7F)
        for opcode in range(0x40, 0x80):
            if opcode == 0x76:
                # HALT con bug fix
                def op_halt():
                    # Verificar HALT bug
                    ie = self.mmu.ie
                    if_reg = self.mmu.io[0x0F]
                    pending = ie & if_reg & 0x1F
                    
                    if not self.ime and pending:
                        # HALT bug: el siguiente byte se lee dos veces
                        self.halt_bug = True
                    else:
                        self.halted = True
                ops[0x76] = op_halt
            else:
                dst = (opcode >> 3) & 7
                src = opcode & 7
                
                def make_ld(d, s):
                    def op():
                        v = self._get_reg(s)
                        self._set_reg(d, v)
                    return op
                ops[opcode] = make_ld(dst, src)
        
        # ALU (0x80-0xBF)
        for opcode in range(0x80, 0xC0):
            alu = (opcode >> 3) & 7
            src = opcode & 7
            
            def make_alu(a, s):
                def op():
                    v = self._get_reg(s)
                    if a == 0:  # ADD
                        r = self.a + v
                        self.f = (0x80 if (r & 0xFF) == 0 else 0) | (0x20 if (self.a & 0xF) + (v & 0xF) > 0xF else 0) | (0x10 if r > 0xFF else 0)
                        self.a = r & 0xFF
                    elif a == 1:  # ADC
                        c = (self.f >> 4) & 1
                        r = self.a + v + c
                        self.f = (0x80 if (r & 0xFF) == 0 else 0) | (0x20 if (self.a & 0xF) + (v & 0xF) + c > 0xF else 0) | (0x10 if r > 0xFF else 0)
                        self.a = r & 0xFF
                    elif a == 2:  # SUB
                        r = self.a - v
                        self.f = 0x40 | (0x80 if (r & 0xFF) == 0 else 0) | (0x20 if (self.a & 0xF) < (v & 0xF) else 0) | (0x10 if r < 0 else 0)
                        self.a = r & 0xFF
                    elif a == 3:  # SBC
                        c = (self.f >> 4) & 1
                        r = self.a - v - c
                        self.f = 0x40 | (0x80 if (r & 0xFF) == 0 else 0) | (0x20 if (self.a & 0xF) < (v & 0xF) + c else 0) | (0x10 if r < 0 else 0)
                        self.a = r & 0xFF
                    elif a == 4:  # AND
                        self.a &= v
                        self.f = 0x20 | (0x80 if self.a == 0 else 0)
                    elif a == 5:  # XOR
                        self.a ^= v
                        self.f = 0x80 if self.a == 0 else 0
                    elif a == 6:  # OR
                        self.a |= v
                        self.f = 0x80 if self.a == 0 else 0
                    else:  # CP
                        r = self.a - v
                        self.f = 0x40 | (0x80 if (r & 0xFF) == 0 else 0) | (0x20 if (self.a & 0xF) < (v & 0xF) else 0) | (0x10 if r < 0 else 0)
                return op
            ops[opcode] = make_alu(alu, src)
        
        # RET NZ
        def op_C0():
            self._tick(4)  # Ciclo interno
            if not (self.f & 0x80):
                self.pc = self._pop()
                self._tick(4)  # Ciclo interno adicional
        ops[0xC0] = op_C0
        
        # POP BC
        def op_C1():
            bc = self._pop()
            self.b = bc >> 8
            self.c = bc & 0xFF
        ops[0xC1] = op_C1
        
        # JP NZ,nn
        def op_C2():
            addr = self._fetch16()
            if not (self.f & 0x80):
                self._tick(4)
                self.pc = addr
        ops[0xC2] = op_C2
        
        # JP nn
        def op_C3():
            self.pc = self._fetch16()
            self._tick(4)
        ops[0xC3] = op_C3
        
        # CALL NZ,nn
        def op_C4():
            addr = self._fetch16()
            if not (self.f & 0x80):
                self._push(self.pc)
                self.pc = addr
        ops[0xC4] = op_C4
        
        # PUSH BC
        def op_C5():
            self._push((self.b << 8) | self.c)
        ops[0xC5] = op_C5
        
        # ADD A,n
        def op_C6():
            n = self._fetch()
            r = self.a + n
            self.f = (0x80 if (r & 0xFF) == 0 else 0) | (0x20 if (self.a & 0xF) + (n & 0xF) > 0xF else 0) | (0x10 if r > 0xFF else 0)
            self.a = r & 0xFF
        ops[0xC6] = op_C6
        
        # RST 00
        def op_C7():
            self._push(self.pc)
            self.pc = 0x00
        ops[0xC7] = op_C7
        
        # RET Z
        def op_C8():
            self._tick(4)
            if self.f & 0x80:
                self.pc = self._pop()
                self._tick(4)
        ops[0xC8] = op_C8
        
        # RET
        def op_C9():
            self.pc = self._pop()
            self._tick(4)
        ops[0xC9] = op_C9
        
        # JP Z,nn
        def op_CA():
            addr = self._fetch16()
            if self.f & 0x80:
                self._tick(4)
                self.pc = addr
        ops[0xCA] = op_CA
        
        # CB prefix
        def op_CB():
            cb_op = self._fetch()
            self._cb_ops[cb_op]()
        ops[0xCB] = op_CB
        
        # CALL Z,nn
        def op_CC():
            addr = self._fetch16()
            if self.f & 0x80:
                self._push(self.pc)
                self.pc = addr
        ops[0xCC] = op_CC
        
        # CALL nn
        def op_CD():
            addr = self._fetch16()
            self._push(self.pc)
            self.pc = addr
        ops[0xCD] = op_CD
        
        # ADC A,n
        def op_CE():
            n = self._fetch()
            c = (self.f >> 4) & 1
            r = self.a + n + c
            self.f = (0x80 if (r & 0xFF) == 0 else 0) | (0x20 if (self.a & 0xF) + (n & 0xF) + c > 0xF else 0) | (0x10 if r > 0xFF else 0)
            self.a = r & 0xFF
        ops[0xCE] = op_CE
        
        # RST 08
        def op_CF():
            self._push(self.pc)
            self.pc = 0x08
        ops[0xCF] = op_CF
        
        # RET NC
        def op_D0():
            self._tick(4)
            if not (self.f & 0x10):
                self.pc = self._pop()
                self._tick(4)
        ops[0xD0] = op_D0
        
        # POP DE
        def op_D1():
            de = self._pop()
            self.d = de >> 8
            self.e = de & 0xFF
        ops[0xD1] = op_D1
        
        # JP NC,nn
        def op_D2():
            addr = self._fetch16()
            if not (self.f & 0x10):
                self._tick(4)
                self.pc = addr
        ops[0xD2] = op_D2
        
        # CALL NC,nn
        def op_D4():
            addr = self._fetch16()
            if not (self.f & 0x10):
                self._push(self.pc)
                self.pc = addr
        ops[0xD4] = op_D4
        
        # PUSH DE
        def op_D5():
            self._push((self.d << 8) | self.e)
        ops[0xD5] = op_D5
        
        # SUB n
        def op_D6():
            n = self._fetch()
            r = self.a - n
            self.f = 0x40 | (0x80 if (r & 0xFF) == 0 else 0) | (0x20 if (self.a & 0xF) < (n & 0xF) else 0) | (0x10 if r < 0 else 0)
            self.a = r & 0xFF
        ops[0xD6] = op_D6
        
        # RST 10
        def op_D7():
            self._push(self.pc)
            self.pc = 0x10
        ops[0xD7] = op_D7
        
        # RET C
        def op_D8():
            self._tick(4)
            if self.f & 0x10:
                self.pc = self._pop()
                self._tick(4)
        ops[0xD8] = op_D8
        
        # RETI
        def op_D9():
            self.pc = self._pop()
            self._tick(4)
            self.ime = True
        ops[0xD9] = op_D9
        
        # JP C,nn
        def op_DA():
            addr = self._fetch16()
            if self.f & 0x10:
                self._tick(4)
                self.pc = addr
        ops[0xDA] = op_DA
        
        # CALL C,nn
        def op_DC():
            addr = self._fetch16()
            if self.f & 0x10:
                self._push(self.pc)
                self.pc = addr
        ops[0xDC] = op_DC
        
        # SBC A,n
        def op_DE():
            n = self._fetch()
            c = (self.f >> 4) & 1
            r = self.a - n - c
            self.f = 0x40 | (0x80 if (r & 0xFF) == 0 else 0) | (0x20 if (self.a & 0xF) < (n & 0xF) + c else 0) | (0x10 if r < 0 else 0)
            self.a = r & 0xFF
        ops[0xDE] = op_DE
        
        # RST 18
        def op_DF():
            self._push(self.pc)
            self.pc = 0x18
        ops[0xDF] = op_DF
        
        # LDH (n),A
        def op_E0():
            self._write(0xFF00 + self._fetch(), self.a)
        ops[0xE0] = op_E0
        
        # POP HL
        def op_E1():
            hl = self._pop()
            self.h = hl >> 8
            self.l = hl & 0xFF
        ops[0xE1] = op_E1
        
        # LDH (C),A
        def op_E2():
            self._write(0xFF00 + self.c, self.a)
        ops[0xE2] = op_E2
        
        # PUSH HL
        def op_E5():
            self._push(self._get_hl())
        ops[0xE5] = op_E5
        
        # AND n
        def op_E6():
            self.a &= self._fetch()
            self.f = 0x20 | (0x80 if self.a == 0 else 0)
        ops[0xE6] = op_E6
        
        # RST 20
        def op_E7():
            self._push(self.pc)
            self.pc = 0x20
        ops[0xE7] = op_E7
        
        # ADD SP,n
        def op_E8():
            n = self._fetch()
            if n > 127:
                n -= 256
            self._tick(4)
            self._tick(4)
            r = self.sp + n
            self.f = (0x20 if (self.sp & 0xF) + (n & 0xF) > 0xF else 0) | (0x10 if (self.sp & 0xFF) + (n & 0xFF) > 0xFF else 0)
            self.sp = r & 0xFFFF
        ops[0xE8] = op_E8
        
        # JP HL
        def op_E9():
            self.pc = self._get_hl()
        ops[0xE9] = op_E9
        
        # LD (nn),A
        def op_EA():
            self._write(self._fetch16(), self.a)
        ops[0xEA] = op_EA
        
        # XOR n
        def op_EE():
            self.a ^= self._fetch()
            self.f = 0x80 if self.a == 0 else 0
        ops[0xEE] = op_EE
        
        # RST 28
        def op_EF():
            self._push(self.pc)
            self.pc = 0x28
        ops[0xEF] = op_EF
        
        # LDH A,(n)
        def op_F0():
            self.a = self._read(0xFF00 + self._fetch())
        ops[0xF0] = op_F0
        
        # POP AF
        def op_F1():
            af = self._pop()
            self.a = af >> 8
            self.f = af & 0xF0
        ops[0xF1] = op_F1
        
        # LDH A,(C)
        def op_F2():
            self.a = self._read(0xFF00 + self.c)
        ops[0xF2] = op_F2
        
        # DI
        def op_F3():
            self.ime = False
        ops[0xF3] = op_F3
        
        # PUSH AF
        def op_F5():
            self._push((self.a << 8) | self.f)
        ops[0xF5] = op_F5
        
        # OR n
        def op_F6():
            self.a |= self._fetch()
            self.f = 0x80 if self.a == 0 else 0
        ops[0xF6] = op_F6
        
        # RST 30
        def op_F7():
            self._push(self.pc)
            self.pc = 0x30
        ops[0xF7] = op_F7
        
        # LD HL,SP+n
        def op_F8():
            n = self._fetch()
            if n > 127:
                n -= 256
            self._tick(4)
            r = self.sp + n
            self.f = (0x20 if (self.sp & 0xF) + (n & 0xF) > 0xF else 0) | (0x10 if (self.sp & 0xFF) + (n & 0xFF) > 0xFF else 0)
            self._set_hl(r & 0xFFFF)
        ops[0xF8] = op_F8
        
        # LD SP,HL
        def op_F9():
            self._tick(4)
            self.sp = self._get_hl()
        ops[0xF9] = op_F9
        
        # LD A,(nn)
        def op_FA():
            self.a = self._read(self._fetch16())
        ops[0xFA] = op_FA
        
        # EI
        def op_FB():
            self.ime_next = True
        ops[0xFB] = op_FB
        
        # CP n
        def op_FE():
            n = self._fetch()
            r = self.a - n
            self.f = 0x40 | (0x80 if (r & 0xFF) == 0 else 0) | (0x20 if (self.a & 0xF) < (n & 0xF) else 0) | (0x10 if r < 0 else 0)
        ops[0xFE] = op_FE
        
        # RST 38
        def op_FF():
            self._push(self.pc)
            self.pc = 0x38
        ops[0xFF] = op_FF
        
        return ops
    
    def _build_cb_ops(self):
        cb = [None] * 256
        
        for opcode in range(256):
            reg = opcode & 7
            op_type = opcode >> 3
            
            if op_type == 0:  # RLC
                def make(r):
                    def op():
                        v = self._get_reg(r)
                        c = v >> 7
                        v = ((v << 1) | c) & 0xFF
                        self.f = (c << 4) | (0x80 if v == 0 else 0)
                        self._set_reg(r, v)
                    return op
                cb[opcode] = make(reg)
            elif op_type == 1:  # RRC
                def make(r):
                    def op():
                        v = self._get_reg(r)
                        c = v & 1
                        v = (v >> 1) | (c << 7)
                        self.f = (c << 4) | (0x80 if v == 0 else 0)
                        self._set_reg(r, v)
                    return op
                cb[opcode] = make(reg)
            elif op_type == 2:  # RL
                def make(r):
                    def op():
                        v = self._get_reg(r)
                        c = v >> 7
                        v = ((v << 1) | ((self.f >> 4) & 1)) & 0xFF
                        self.f = (c << 4) | (0x80 if v == 0 else 0)
                        self._set_reg(r, v)
                    return op
                cb[opcode] = make(reg)
            elif op_type == 3:  # RR
                def make(r):
                    def op():
                        v = self._get_reg(r)
                        c = v & 1
                        v = (v >> 1) | ((self.f << 3) & 0x80)
                        self.f = (c << 4) | (0x80 if v == 0 else 0)
                        self._set_reg(r, v)
                    return op
                cb[opcode] = make(reg)
            elif op_type == 4:  # SLA
                def make(r):
                    def op():
                        v = self._get_reg(r)
                        c = v >> 7
                        v = (v << 1) & 0xFF
                        self.f = (c << 4) | (0x80 if v == 0 else 0)
                        self._set_reg(r, v)
                    return op
                cb[opcode] = make(reg)
            elif op_type == 5:  # SRA
                def make(r):
                    def op():
                        v = self._get_reg(r)
                        c = v & 1
                        v = (v >> 1) | (v & 0x80)
                        self.f = (c << 4) | (0x80 if v == 0 else 0)
                        self._set_reg(r, v)
                    return op
                cb[opcode] = make(reg)
            elif op_type == 6:  # SWAP
                def make(r):
                    def op():
                        v = self._get_reg(r)
                        v = ((v & 0xF) << 4) | (v >> 4)
                        self.f = 0x80 if v == 0 else 0
                        self._set_reg(r, v)
                    return op
                cb[opcode] = make(reg)
            elif op_type == 7:  # SRL
                def make(r):
                    def op():
                        v = self._get_reg(r)
                        c = v & 1
                        v = v >> 1
                        self.f = (c << 4) | (0x80 if v == 0 else 0)
                        self._set_reg(r, v)
                    return op
                cb[opcode] = make(reg)
            elif 8 <= op_type < 16:  # BIT
                bit = op_type - 8
                def make(r, b):
                    def op():
                        v = self._get_reg(r)
                        self.f = (self.f & 0x10) | 0x20 | (0x80 if not (v & (1 << b)) else 0)
                    return op
                cb[opcode] = make(reg, bit)
            elif 16 <= op_type < 24:  # RES
                bit = op_type - 16
                def make(r, b):
                    def op():
                        v = self._get_reg(r) & ~(1 << b)
                        self._set_reg(r, v)
                    return op
                cb[opcode] = make(reg, bit)
            else:  # SET
                bit = op_type - 24
                def make(r, b):
                    def op():
                        v = self._get_reg(r) | (1 << b)
                        self._set_reg(r, v)
                    return op
                cb[opcode] = make(reg, bit)
        
        return cb