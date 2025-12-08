# cython: language_level=3, boundscheck=False, wraparound=False, cdivision=True
"""
Memory Management Unit - Cython optimizado (CORREGIDO)
"""

cimport cython
from libc.stdint cimport uint8_t, uint16_t, int8_t
import os
import time


# ============================================================================
# MBC Classes (como clases Python normales para compatibilidad)
# ============================================================================

class MBC:
    """Clase base para Memory Bank Controllers"""
    
    def __init__(self, rom, ram_size):
        self.rom = bytearray(rom)
        self.ram = bytearray(ram_size) if ram_size > 0 else bytearray(0x2000)
        self.ram_enabled = False
        self.rom_bank = 1
        self.ram_bank = 0
        self.rom_len = len(self.rom)
        self.ram_len = len(self.ram)
    
    def read_rom(self, addr):
        if addr < 0x4000:
            if addr < self.rom_len:
                return self.rom[addr]
            return 0xFF
        else:
            bank_addr = (self.rom_bank * 0x4000) + (addr - 0x4000)
            if bank_addr < self.rom_len:
                return self.rom[bank_addr]
            return 0xFF
    
    def read_ram(self, addr):
        if not self.ram_enabled:
            return 0xFF
        offset = (self.ram_bank * 0x2000) + (addr - 0xA000)
        if offset < self.ram_len:
            return self.ram[offset]
        return 0xFF
    
    def write_ram(self, addr, value):
        if not self.ram_enabled:
            return
        offset = (self.ram_bank * 0x2000) + (addr - 0xA000)
        if offset < self.ram_len:
            self.ram[offset] = value
    
    def write_control(self, addr, value):
        pass


class NoMBC(MBC):
    """ROM sin MBC"""
    
    def read_rom(self, addr):
        if addr < self.rom_len:
            return self.rom[addr]
        return 0xFF


class MBC1(MBC):
    """MBC1"""
    
    def __init__(self, rom, ram_size):
        super().__init__(rom, ram_size)
        self.mode = 0
        self.rom_bank_low = 1
        self.rom_bank_high = 0
    
    def read_rom(self, addr):
        if addr < 0x4000:
            if self.mode == 1:
                bank = (self.rom_bank_high << 5) * 0x4000
                if bank + addr < self.rom_len:
                    return self.rom[bank + addr]
                return 0xFF
            if addr < self.rom_len:
                return self.rom[addr]
            return 0xFF
        else:
            bank = (self.rom_bank_high << 5) | self.rom_bank_low
            bank_addr = (bank * 0x4000) + (addr - 0x4000)
            if bank_addr < self.rom_len:
                return self.rom[bank_addr]
            return 0xFF
    
    def read_ram(self, addr):
        if not self.ram_enabled:
            return 0xFF
        bank = self.ram_bank if self.mode == 1 else 0
        offset = (bank * 0x2000) + (addr - 0xA000)
        if offset < self.ram_len:
            return self.ram[offset]
        return 0xFF
    
    def write_ram(self, addr, value):
        if not self.ram_enabled:
            return
        bank = self.ram_bank if self.mode == 1 else 0
        offset = (bank * 0x2000) + (addr - 0xA000)
        if offset < self.ram_len:
            self.ram[offset] = value
    
    def write_control(self, addr, value):
        if addr < 0x2000:
            self.ram_enabled = (value & 0x0F) == 0x0A
        elif addr < 0x4000:
            self.rom_bank_low = value & 0x1F
            if self.rom_bank_low == 0:
                self.rom_bank_low = 1
        elif addr < 0x6000:
            self.rom_bank_high = value & 0x03
            self.ram_bank = value & 0x03
        else:
            self.mode = value & 0x01


class MBC2(MBC):
    """MBC2"""
    
    def __init__(self, rom, ram_size):
        super().__init__(rom, 512)
    
    def read_ram(self, addr):
        if not self.ram_enabled:
            return 0xFF
        offset = (addr - 0xA000) & 0x1FF
        return self.ram[offset] | 0xF0
    
    def write_ram(self, addr, value):
        if not self.ram_enabled:
            return
        offset = (addr - 0xA000) & 0x1FF
        self.ram[offset] = value & 0x0F
    
    def write_control(self, addr, value):
        if addr < 0x4000:
            if addr & 0x100:
                self.rom_bank = value & 0x0F
                if self.rom_bank == 0:
                    self.rom_bank = 1
            else:
                self.ram_enabled = (value & 0x0F) == 0x0A


class MBC3(MBC):
    """MBC3 con RTC"""
    
    def __init__(self, rom, ram_size):
        super().__init__(rom, ram_size)
        self.rtc_select = 0
        self.rtc_latched = False
        self.rtc_latch_value = 0
        self.rtc = {0x08: 0, 0x09: 0, 0x0A: 0, 0x0B: 0, 0x0C: 0}
        self.rtc_latched_data = dict(self.rtc)
        self.rtc_start_time = int(time.time())
    
    def _update_rtc(self):
        if self.rtc[0x0C] & 0x40:
            return
        
        elapsed = int(time.time()) - self.rtc_start_time
        self.rtc[0x08] = elapsed % 60
        self.rtc[0x09] = (elapsed // 60) % 60
        self.rtc[0x0A] = (elapsed // 3600) % 24
        days = elapsed // 86400
        self.rtc[0x0B] = days & 0xFF
        self.rtc[0x0C] = (self.rtc[0x0C] & 0xFE) | ((days >> 8) & 0x01)
        if days > 511:
            self.rtc[0x0C] |= 0x80
    
    def read_ram(self, addr):
        if not self.ram_enabled:
            return 0xFF
        
        if 0x08 <= self.rtc_select <= 0x0C:
            if self.rtc_latched:
                return self.rtc_latched_data.get(self.rtc_select, 0xFF)
            self._update_rtc()
            return self.rtc.get(self.rtc_select, 0xFF)
        else:
            offset = (self.ram_bank * 0x2000) + (addr - 0xA000)
            if offset < self.ram_len:
                return self.ram[offset]
            return 0xFF
    
    def write_ram(self, addr, value):
        if not self.ram_enabled:
            return
        
        if 0x08 <= self.rtc_select <= 0x0C:
            self.rtc[self.rtc_select] = value
            if self.rtc_select == 0x0C and not (value & 0x40):
                self.rtc_start_time = int(time.time())
        else:
            offset = (self.ram_bank * 0x2000) + (addr - 0xA000)
            if offset < self.ram_len:
                self.ram[offset] = value
    
    def write_control(self, addr, value):
        if addr < 0x2000:
            self.ram_enabled = (value & 0x0F) == 0x0A
        elif addr < 0x4000:
            self.rom_bank = value & 0x7F
            if self.rom_bank == 0:
                self.rom_bank = 1
        elif addr < 0x6000:
            if value <= 0x03:
                self.ram_bank = value
                self.rtc_select = 0
            elif 0x08 <= value <= 0x0C:
                self.rtc_select = value
        else:
            if self.rtc_latch_value == 0 and value == 1:
                self._update_rtc()
                self.rtc_latched_data = dict(self.rtc)
                self.rtc_latched = True
            if value == 0:
                self.rtc_latched = False
            self.rtc_latch_value = value


class MBC5(MBC):
    """MBC5"""
    
    def __init__(self, rom, ram_size):
        super().__init__(rom, ram_size)
        self.rom_bank_low = 1
        self.rom_bank_high = 0
    
    def read_rom(self, addr):
        if addr < 0x4000:
            if addr < self.rom_len:
                return self.rom[addr]
            return 0xFF
        else:
            bank = (self.rom_bank_high << 8) | self.rom_bank_low
            bank_addr = (bank * 0x4000) + (addr - 0x4000)
            if bank_addr < self.rom_len:
                return self.rom[bank_addr]
            return 0xFF
    
    def write_control(self, addr, value):
        if addr < 0x2000:
            self.ram_enabled = (value & 0x0F) == 0x0A
        elif addr < 0x3000:
            self.rom_bank_low = value
        elif addr < 0x4000:
            self.rom_bank_high = value & 0x01
        elif addr < 0x6000:
            self.ram_bank = value & 0x0F


# ============================================================================
# Constantes
# ============================================================================

ROM_SIZES = {
    0x00: 32 * 1024, 0x01: 64 * 1024, 0x02: 128 * 1024,
    0x03: 256 * 1024, 0x04: 512 * 1024, 0x05: 1024 * 1024,
    0x06: 2048 * 1024, 0x07: 4096 * 1024, 0x08: 8192 * 1024,
}

RAM_SIZES = {
    0x00: 0, 0x01: 2 * 1024, 0x02: 8 * 1024,
    0x03: 32 * 1024, 0x04: 128 * 1024, 0x05: 64 * 1024,
}

BATTERY_TYPES = {0x03, 0x06, 0x09, 0x0F, 0x10, 0x13, 0x1B, 0x1E}


# ============================================================================
# MMU Principal
# ============================================================================

cdef class MMU:
    """Memory Management Unit optimizado"""
    
    cdef public bytearray vram
    cdef public bytearray wram
    cdef public bytearray oam
    cdef public bytearray hram
    cdef public bytearray io
    cdef public uint8_t ie
    
    cdef public object mbc
    cdef public str rom_path
    cdef public int cart_type
    cdef public int rom_size
    cdef public int ram_size
    
    cdef public object ppu
    cdef public object timer
    cdef public object joypad
    cdef public object apu
    
    def __init__(self):
        self.vram = bytearray(0x2000)
        self.wram = bytearray(0x2000)
        self.oam = bytearray(0xA0)
        self.hram = bytearray(0x7F)
        self.io = bytearray(0x80)
        self.ie = 0
        
        self.mbc = None
        self.rom_path = None
        self.cart_type = 0
        self.rom_size = 0
        self.ram_size = 0
        
        self.ppu = None
        self.timer = None
        self.joypad = None
        self.apu = None
        
        self._init_io()
    
    cdef void _init_io(self):
        cdef dict defaults = {
            0x00: 0xCF, 0x01: 0x00, 0x02: 0x7E, 0x04: 0xAB,
            0x05: 0x00, 0x06: 0x00, 0x07: 0xF8, 0x0F: 0xE1,
            0x10: 0x80, 0x11: 0xBF, 0x12: 0xF3, 0x14: 0xBF,
            0x16: 0x3F, 0x17: 0x00, 0x19: 0xBF, 0x1A: 0x7F,
            0x1B: 0xFF, 0x1C: 0x9F, 0x1E: 0xBF, 0x20: 0xFF,
            0x21: 0x00, 0x22: 0x00, 0x23: 0xBF, 0x24: 0x77,
            0x25: 0xF3, 0x26: 0xF1, 0x40: 0x91, 0x41: 0x85,
            0x42: 0x00, 0x43: 0x00, 0x44: 0x00, 0x45: 0x00,
            0x46: 0xFF, 0x47: 0xFC, 0x48: 0xFF, 0x49: 0xFF,
            0x4A: 0x00, 0x4B: 0x00,
        }
        for addr, val in defaults.items():
            self.io[addr] = val
    
    def load_rom(self, data, path=None):
        self.rom_path = path
        
        self.cart_type = data[0x147] if len(data) > 0x147 else 0
        rom_size_code = data[0x148] if len(data) > 0x148 else 0
        ram_size_code = data[0x149] if len(data) > 0x149 else 0
        
        self.rom_size = ROM_SIZES.get(rom_size_code, len(data))
        self.ram_size = RAM_SIZES.get(ram_size_code, 0)
        
        # Crear MBC apropiado
        if self.cart_type == 0x00:
            self.mbc = NoMBC(data, self.ram_size)
            cart_name = "ROM"
        elif self.cart_type in (0x01, 0x02, 0x03):
            self.mbc = MBC1(data, self.ram_size)
            cart_name = "MBC1"
        elif self.cart_type in (0x05, 0x06):
            self.mbc = MBC2(data, self.ram_size)
            cart_name = "MBC2"
        elif self.cart_type in (0x0F, 0x10, 0x11, 0x12, 0x13):
            self.mbc = MBC3(data, self.ram_size)
            cart_name = "MBC3"
        elif self.cart_type in (0x19, 0x1A, 0x1B, 0x1C, 0x1D, 0x1E):
            self.mbc = MBC5(data, self.ram_size)
            cart_name = "MBC5"
        else:
            self.mbc = MBC1(data, self.ram_size)
            cart_name = "Unknown->MBC1"
        
        # Cargar save
        if path and self.cart_type in BATTERY_TYPES:
            self._load_save()
        
        title = bytes(data[0x134:0x144]).decode('ascii', errors='ignore').rstrip('\x00')
        print(f"📀 {title}")
        print(f"   MBC: {cart_name}")
        print(f"   ROM: {len(data) // 1024}KB, RAM: {self.ram_size // 1024}KB")
    
    cdef void _load_save(self):
        cdef str save_path
        if self.rom_path:
            base, _ = os.path.splitext(self.rom_path)
            save_path = base + '.sav'
            if os.path.exists(save_path):
                try:
                    with open(save_path, 'rb') as f:
                        data = f.read()
                    if len(data) <= len(self.mbc.ram):
                        self.mbc.ram[:len(data)] = data
                        print(f"💾 Save cargado: {save_path}")
                except Exception as e:
                    print(f"⚠ Error cargando save: {e}")
    
    def save_ram(self):
        if self.cart_type not in BATTERY_TYPES:
            return
        
        if self.rom_path:
            base, _ = os.path.splitext(self.rom_path)
            save_path = base + '.sav'
            if len(self.mbc.ram) > 0:
                try:
                    with open(save_path, 'wb') as f:
                        f.write(self.mbc.ram)
                    print(f"💾 Save guardado: {save_path}")
                except Exception as e:
                    print(f"⚠ Error guardando save: {e}")
    
    cpdef uint8_t read(self, uint16_t addr):
        addr &= 0xFFFF
        
        if addr < 0x8000:
            if self.mbc is not None:
                return self.mbc.read_rom(addr)
            return 0xFF
        
        if addr < 0xA000:
            return self.vram[addr - 0x8000]
        
        if addr < 0xC000:
            if self.mbc is not None:
                return self.mbc.read_ram(addr)
            return 0xFF
        
        if addr < 0xE000:
            return self.wram[addr - 0xC000]
        
        if addr < 0xFE00:
            return self.wram[addr - 0xE000]
        
        if addr < 0xFEA0:
            return self.oam[addr - 0xFE00]
        
        if addr < 0xFF00:
            return 0xFF
        
        if addr < 0xFF80:
            return self._read_io(addr)
        
        if addr < 0xFFFF:
            return self.hram[addr - 0xFF80]
        
        return self.ie
    
    cpdef void write(self, uint16_t addr, uint8_t value):
        addr &= 0xFFFF
        value &= 0xFF
        
        if addr < 0x8000:
            if self.mbc is not None:
                self.mbc.write_control(addr, value)
            return
        
        if addr < 0xA000:
            self.vram[addr - 0x8000] = value
            return
        
        if addr < 0xC000:
            if self.mbc is not None:
                self.mbc.write_ram(addr, value)
            return
        
        if addr < 0xE000:
            self.wram[addr - 0xC000] = value
            return
        
        if addr < 0xFE00:
            self.wram[addr - 0xE000] = value
            return
        
        if addr < 0xFEA0:
            self.oam[addr - 0xFE00] = value
            return
        
        if addr < 0xFF00:
            return
        
        if addr < 0xFF80:
            self._write_io(addr, value)
            return
        
        if addr < 0xFFFF:
            self.hram[addr - 0xFF80] = value
            return
        
        self.ie = value
    
    cdef uint8_t _read_io(self, uint16_t addr):
        cdef int reg = addr & 0x7F
        
        if reg == 0x00:
            if self.joypad is not None:
                return self.joypad.read()
            return 0xFF
        
        if reg == 0x04:
            if self.timer is not None:
                return self.timer.div
            return self.io[reg]
        
        if reg == 0x05:
            if self.timer is not None:
                return self.timer.tima
            return self.io[reg]
        
        if 0x10 <= reg <= 0x3F:
            if self.apu is not None:
                return self.apu.read(reg)
            return self.io[reg]
        
        if reg == 0x41:
            if self.ppu is not None:
                return (self.ppu.stat & 0xFC) | self.ppu.mode
            return self.io[reg]
        
        if reg == 0x44:
            if self.ppu is not None:
                return self.ppu.ly
            return self.io[reg]
        
        return self.io[reg]
    
    cdef void _write_io(self, uint16_t addr, uint8_t value):
        cdef int reg = addr & 0x7F
        
        if reg == 0x00:
            if self.joypad is not None:
                self.joypad.write(value)
        
        elif reg == 0x04:
            if self.timer is not None:
                self.timer.div = 0
            self.io[reg] = 0
            return
        
        elif reg == 0x05:
            if self.timer is not None:
                self.timer.tima = value
        
        elif reg == 0x06:
            if self.timer is not None:
                self.timer.tma = value
        
        elif reg == 0x07:
            if self.timer is not None:
                self.timer.tac = value
        
        elif 0x10 <= reg <= 0x3F:
            if self.apu is not None:
                self.apu.write(reg, value)
        
        elif reg == 0x40:
            if self.ppu is not None:
                self.ppu.lcdc = value
        
        elif reg == 0x41:
            if self.ppu is not None:
                self.ppu.stat = (self.ppu.stat & 0x07) | (value & 0xF8)
        
        elif reg == 0x42:
            if self.ppu is not None:
                self.ppu.scy = value
        
        elif reg == 0x43:
            if self.ppu is not None:
                self.ppu.scx = value
        
        elif reg == 0x45:
            if self.ppu is not None:
                self.ppu.lyc = value
        
        elif reg == 0x46:
            self._dma(value)
        
        elif reg == 0x47:
            if self.ppu is not None:
                self.ppu.bgp = value
        
        elif reg == 0x48:
            if self.ppu is not None:
                self.ppu.obp0 = value
        
        elif reg == 0x49:
            if self.ppu is not None:
                self.ppu.obp1 = value
        
        elif reg == 0x4A:
            if self.ppu is not None:
                self.ppu.wy = value
        
        elif reg == 0x4B:
            if self.ppu is not None:
                self.ppu.wx = value
        
        self.io[reg] = value
    
    cdef void _dma(self, uint8_t value):
        cdef uint16_t src = <uint16_t>(value) << 8
        cdef int i
        for i in range(0xA0):
            self.oam[i] = self.read(src + i)