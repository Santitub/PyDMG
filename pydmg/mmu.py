"""
Memory Management Unit
"""

import os
import time

class MBC:
    """Clase base para Memory Bank Controllers"""
    
    def __init__(self, rom, ram_size):
        self.rom = rom
        self.ram = bytearray(ram_size) if ram_size > 0 else bytearray(0x2000)
        self.ram_enabled = False
        self.rom_bank = 1
        self.ram_bank = 0
    
    def read_rom(self, addr):
        if addr < 0x4000:
            return self.rom[addr] if addr < len(self.rom) else 0xFF
        else:
            bank_addr = (self.rom_bank * 0x4000) + (addr - 0x4000)
            return self.rom[bank_addr] if bank_addr < len(self.rom) else 0xFF
    
    def read_ram(self, addr):
        if not self.ram_enabled:
            return 0xFF
        offset = (self.ram_bank * 0x2000) + (addr - 0xA000)
        return self.ram[offset] if offset < len(self.ram) else 0xFF
    
    def write_ram(self, addr, value):
        if not self.ram_enabled:
            return
        offset = (self.ram_bank * 0x2000) + (addr - 0xA000)
        if offset < len(self.ram):
            self.ram[offset] = value
    
    def write_control(self, addr, value):
        pass


class NoMBC(MBC):
    """ROM sin MBC (32KB máximo)"""
    
    def read_rom(self, addr):
        return self.rom[addr] if addr < len(self.rom) else 0xFF


class MBC1(MBC):
    """MBC1 - Hasta 2MB ROM / 32KB RAM"""
    
    def __init__(self, rom, ram_size):
        super().__init__(rom, ram_size)
        self.mode = 0  # 0 = ROM mode, 1 = RAM mode
        self.rom_bank_low = 1
        self.rom_bank_high = 0
    
    def read_rom(self, addr):
        if addr < 0x4000:
            if self.mode == 1:
                bank = (self.rom_bank_high << 5) * 0x4000
                return self.rom[bank + addr] if bank + addr < len(self.rom) else 0xFF
            return self.rom[addr] if addr < len(self.rom) else 0xFF
        else:
            bank = ((self.rom_bank_high << 5) | self.rom_bank_low)
            bank_addr = (bank * 0x4000) + (addr - 0x4000)
            return self.rom[bank_addr] if bank_addr < len(self.rom) else 0xFF
    
    def read_ram(self, addr):
        if not self.ram_enabled:
            return 0xFF
        bank = self.ram_bank if self.mode == 1 else 0
        offset = (bank * 0x2000) + (addr - 0xA000)
        return self.ram[offset] if offset < len(self.ram) else 0xFF
    
    def write_ram(self, addr, value):
        if not self.ram_enabled:
            return
        bank = self.ram_bank if self.mode == 1 else 0
        offset = (bank * 0x2000) + (addr - 0xA000)
        if offset < len(self.ram):
            self.ram[offset] = value
    
    def write_control(self, addr, value):
        if addr < 0x2000:
            # RAM Enable
            self.ram_enabled = (value & 0x0F) == 0x0A
        elif addr < 0x4000:
            # ROM Bank Low (5 bits)
            self.rom_bank_low = value & 0x1F
            if self.rom_bank_low == 0:
                self.rom_bank_low = 1
        elif addr < 0x6000:
            # RAM Bank / ROM Bank High (2 bits)
            self.rom_bank_high = value & 0x03
            self.ram_bank = value & 0x03
        else:
            # Mode Select
            self.mode = value & 0x01


class MBC2(MBC):
    """MBC2 - Hasta 256KB ROM / 512x4 bits RAM integrada"""
    
    def __init__(self, rom, ram_size):
        super().__init__(rom, 512)  # MBC2 tiene 512 bytes de RAM interna
    
    def read_ram(self, addr):
        if not self.ram_enabled:
            return 0xFF
        offset = (addr - 0xA000) & 0x1FF  # Solo 512 bytes
        return self.ram[offset] | 0xF0  # Solo 4 bits bajos son válidos
    
    def write_ram(self, addr, value):
        if not self.ram_enabled:
            return
        offset = (addr - 0xA000) & 0x1FF
        self.ram[offset] = value & 0x0F  # Solo 4 bits
    
    def write_control(self, addr, value):
        if addr < 0x4000:
            if addr & 0x100:
                # ROM Bank (bit 8 = 1)
                self.rom_bank = value & 0x0F
                if self.rom_bank == 0:
                    self.rom_bank = 1
            else:
                # RAM Enable (bit 8 = 0)
                self.ram_enabled = (value & 0x0F) == 0x0A


class MBC3(MBC):
    """MBC3 - Hasta 2MB ROM / 32KB RAM / RTC"""
    
    def __init__(self, rom, ram_size):
        super().__init__(rom, ram_size)
        self.rtc_select = 0
        self.rtc_latched = False
        self.rtc_latch_value = 0
        
        # Registros RTC
        self.rtc = {
            0x08: 0,  # Seconds
            0x09: 0,  # Minutes
            0x0A: 0,  # Hours
            0x0B: 0,  # Day Low
            0x0C: 0,  # Day High / Flags
        }
        self.rtc_latched_data = dict(self.rtc)
        self.rtc_start_time = int(time.time())
    
    def _update_rtc(self):
        """Actualiza el RTC basado en tiempo real"""
        if self.rtc[0x0C] & 0x40:  # Halt flag
            return
        
        elapsed = int(time.time()) - self.rtc_start_time
        
        seconds = elapsed % 60
        minutes = (elapsed // 60) % 60
        hours = (elapsed // 3600) % 24
        days = elapsed // 86400
        
        self.rtc[0x08] = seconds
        self.rtc[0x09] = minutes
        self.rtc[0x0A] = hours
        self.rtc[0x0B] = days & 0xFF
        self.rtc[0x0C] = (self.rtc[0x0C] & 0xFE) | ((days >> 8) & 0x01)
        
        if days > 511:
            self.rtc[0x0C] |= 0x80  # Day overflow
    
    def read_ram(self, addr):
        if not self.ram_enabled:
            return 0xFF
        
        if 0x08 <= self.rtc_select <= 0x0C:
            # RTC Register
            if self.rtc_latched:
                return self.rtc_latched_data.get(self.rtc_select, 0xFF)
            self._update_rtc()
            return self.rtc.get(self.rtc_select, 0xFF)
        else:
            # RAM
            offset = (self.ram_bank * 0x2000) + (addr - 0xA000)
            return self.ram[offset] if offset < len(self.ram) else 0xFF
    
    def write_ram(self, addr, value):
        if not self.ram_enabled:
            return
        
        if 0x08 <= self.rtc_select <= 0x0C:
            # RTC Register
            self.rtc[self.rtc_select] = value
            if self.rtc_select == 0x0C and not (value & 0x40):
                self.rtc_start_time = int(time.time())
        else:
            # RAM
            offset = (self.ram_bank * 0x2000) + (addr - 0xA000)
            if offset < len(self.ram):
                self.ram[offset] = value
    
    def write_control(self, addr, value):
        if addr < 0x2000:
            # RAM/RTC Enable
            self.ram_enabled = (value & 0x0F) == 0x0A
        elif addr < 0x4000:
            # ROM Bank
            self.rom_bank = value & 0x7F
            if self.rom_bank == 0:
                self.rom_bank = 1
        elif addr < 0x6000:
            # RAM Bank / RTC Select
            if value <= 0x03:
                self.ram_bank = value
                self.rtc_select = 0
            elif 0x08 <= value <= 0x0C:
                self.rtc_select = value
        else:
            # Latch RTC
            if self.rtc_latch_value == 0 and value == 1:
                self._update_rtc()
                self.rtc_latched_data = dict(self.rtc)
                self.rtc_latched = True
            if value == 0:
                self.rtc_latched = False
            self.rtc_latch_value = value


class MBC5(MBC):
    """MBC5 - Hasta 8MB ROM / 128KB RAM"""
    
    def __init__(self, rom, ram_size):
        super().__init__(rom, ram_size)
        self.rom_bank_low = 1
        self.rom_bank_high = 0
    
    def read_rom(self, addr):
        if addr < 0x4000:
            return self.rom[addr] if addr < len(self.rom) else 0xFF
        else:
            bank = (self.rom_bank_high << 8) | self.rom_bank_low
            bank_addr = (bank * 0x4000) + (addr - 0x4000)
            return self.rom[bank_addr] if bank_addr < len(self.rom) else 0xFF
    
    def write_control(self, addr, value):
        if addr < 0x2000:
            # RAM Enable
            self.ram_enabled = (value & 0x0F) == 0x0A
        elif addr < 0x3000:
            # ROM Bank Low (8 bits)
            self.rom_bank_low = value
        elif addr < 0x4000:
            # ROM Bank High (1 bit)
            self.rom_bank_high = value & 0x01
        elif addr < 0x6000:
            # RAM Bank (4 bits)
            self.ram_bank = value & 0x0F


class MMU:
    """Memory Management Unit con soporte MBC completo"""
    
    __slots__ = (
        'vram', 'wram', 'oam', 'hram', 'io', 'ie',
        'mbc', 'rom_path', 'cart_type', 'rom_size', 'ram_size',
        'ppu', 'timer', 'joypad', 'apu'
    )
    
    # Tipos de cartucho
    CART_TYPES = {
        0x00: ('ROM', NoMBC),
        0x01: ('MBC1', MBC1),
        0x02: ('MBC1+RAM', MBC1),
        0x03: ('MBC1+RAM+BATTERY', MBC1),
        0x05: ('MBC2', MBC2),
        0x06: ('MBC2+BATTERY', MBC2),
        0x08: ('ROM+RAM', NoMBC),
        0x09: ('ROM+RAM+BATTERY', NoMBC),
        0x0F: ('MBC3+TIMER+BATTERY', MBC3),
        0x10: ('MBC3+TIMER+RAM+BATTERY', MBC3),
        0x11: ('MBC3', MBC3),
        0x12: ('MBC3+RAM', MBC3),
        0x13: ('MBC3+RAM+BATTERY', MBC3),
        0x19: ('MBC5', MBC5),
        0x1A: ('MBC5+RAM', MBC5),
        0x1B: ('MBC5+RAM+BATTERY', MBC5),
        0x1C: ('MBC5+RUMBLE', MBC5),
        0x1D: ('MBC5+RUMBLE+RAM', MBC5),
        0x1E: ('MBC5+RUMBLE+RAM+BATTERY', MBC5),
    }
    
    # Tamaños de ROM
    ROM_SIZES = {
        0x00: 32 * 1024,      # 32KB
        0x01: 64 * 1024,      # 64KB
        0x02: 128 * 1024,     # 128KB
        0x03: 256 * 1024,     # 256KB
        0x04: 512 * 1024,     # 512KB
        0x05: 1024 * 1024,    # 1MB
        0x06: 2048 * 1024,    # 2MB
        0x07: 4096 * 1024,    # 4MB
        0x08: 8192 * 1024,    # 8MB
    }
    
    # Tamaños de RAM
    RAM_SIZES = {
        0x00: 0,
        0x01: 2 * 1024,       # 2KB
        0x02: 8 * 1024,       # 8KB
        0x03: 32 * 1024,      # 32KB
        0x04: 128 * 1024,     # 128KB
        0x05: 64 * 1024,      # 64KB
    }
    
    def __init__(self):
        # Memoria interna
        self.vram = bytearray(0x2000)
        self.wram = bytearray(0x2000)
        self.oam = bytearray(0xA0)
        self.hram = bytearray(0x7F)
        self.io = bytearray(0x80)
        self.ie = 0
        
        # MBC
        self.mbc = None
        self.rom_path = None
        self.cart_type = 0
        self.rom_size = 0
        self.ram_size = 0
        
        # Componentes
        self.ppu = None
        self.timer = None
        self.joypad = None
        self.apu = None
        
        self._init_io()
    
    def _init_io(self):
        """Inicializa registros I/O"""
        defaults = {
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
        """Carga una ROM"""
        self.rom_path = path
        
        # Leer cabecera
        self.cart_type = data[0x147] if len(data) > 0x147 else 0
        rom_size_code = data[0x148] if len(data) > 0x148 else 0
        ram_size_code = data[0x149] if len(data) > 0x149 else 0
        
        self.rom_size = self.ROM_SIZES.get(rom_size_code, len(data))
        self.ram_size = self.RAM_SIZES.get(ram_size_code, 0)
        
        # Obtener tipo de MBC
        cart_info = self.CART_TYPES.get(self.cart_type, ('Unknown', MBC1))
        cart_name, mbc_class = cart_info
        
        # Crear MBC
        self.mbc = mbc_class(bytearray(data), self.ram_size)
        
        # Cargar save si existe
        if path and self._has_battery():
            self._load_save()
        
        # Info
        title = bytes(data[0x134:0x144]).decode('ascii', errors='ignore').rstrip('\x00')
        print(f"📀 {title}")
        print(f"   MBC: {cart_name}")
        print(f"   ROM: {len(data) // 1024}KB, RAM: {self.ram_size // 1024}KB")
    
    def _has_battery(self):
        """Verifica si el cartucho tiene batería"""
        return self.cart_type in (0x03, 0x06, 0x09, 0x0F, 0x10, 0x13, 0x1B, 0x1E)
    
    def _get_save_path(self):
        """Obtiene la ruta del archivo de guardado"""
        if self.rom_path:
            return os.path.splitext(self.rom_path)[0] + '.sav'
        return None
    
    def _load_save(self):
        """Carga RAM externa desde archivo"""
        save_path = self._get_save_path()
        if save_path and os.path.exists(save_path):
            try:
                with open(save_path, 'rb') as f:
                    data = f.read()
                    if len(data) <= len(self.mbc.ram):
                        self.mbc.ram[:len(data)] = data
                        print(f"💾 Save cargado: {save_path}")
            except Exception as e:
                print(f"⚠ Error cargando save: {e}")
    
    def save_ram(self):
        """Guarda RAM externa a archivo"""
        if not self._has_battery():
            return
        
        save_path = self._get_save_path()
        if save_path and len(self.mbc.ram) > 0:
            try:
                with open(save_path, 'wb') as f:
                    f.write(self.mbc.ram)
                print(f"💾 Save guardado: {save_path}")
            except Exception as e:
                print(f"⚠ Error guardando save: {e}")
    
    def read(self, addr):
        """Lee un byte de memoria"""
        addr &= 0xFFFF
        
        # ROM (0x0000-0x7FFF)
        if addr < 0x8000:
            return self.mbc.read_rom(addr) if self.mbc else 0xFF
        
        # VRAM (0x8000-0x9FFF)
        if addr < 0xA000:
            return self.vram[addr - 0x8000]
        
        # External RAM (0xA000-0xBFFF)
        if addr < 0xC000:
            return self.mbc.read_ram(addr) if self.mbc else 0xFF
        
        # WRAM (0xC000-0xDFFF)
        if addr < 0xE000:
            return self.wram[addr - 0xC000]
        
        # Echo RAM (0xE000-0xFDFF)
        if addr < 0xFE00:
            return self.wram[addr - 0xE000]
        
        # OAM (0xFE00-0xFE9F)
        if addr < 0xFEA0:
            return self.oam[addr - 0xFE00]
        
        # Unusable (0xFEA0-0xFEFF)
        if addr < 0xFF00:
            return 0xFF
        
        # I/O (0xFF00-0xFF7F)
        if addr < 0xFF80:
            return self._read_io(addr)
        
        # HRAM (0xFF80-0xFFFE)
        if addr < 0xFFFF:
            return self.hram[addr - 0xFF80]
        
        # IE (0xFFFF)
        return self.ie
    
    def write(self, addr, value):
        """Escribe un byte a memoria"""
        addr &= 0xFFFF
        value &= 0xFF
        
        # MBC Control (0x0000-0x7FFF)
        if addr < 0x8000:
            if self.mbc:
                self.mbc.write_control(addr, value)
            return
        
        # VRAM (0x8000-0x9FFF)
        if addr < 0xA000:
            self.vram[addr - 0x8000] = value
            return
        
        # External RAM (0xA000-0xBFFF)
        if addr < 0xC000:
            if self.mbc:
                self.mbc.write_ram(addr, value)
            return
        
        # WRAM (0xC000-0xDFFF)
        if addr < 0xE000:
            self.wram[addr - 0xC000] = value
            return
        
        # Echo RAM (0xE000-0xFDFF)
        if addr < 0xFE00:
            self.wram[addr - 0xE000] = value
            return
        
        # OAM (0xFE00-0xFE9F)
        if addr < 0xFEA0:
            self.oam[addr - 0xFE00] = value
            return
        
        # Unusable (0xFEA0-0xFEFF)
        if addr < 0xFF00:
            return
        
        # I/O (0xFF00-0xFF7F)
        if addr < 0xFF80:
            self._write_io(addr, value)
            return
        
        # HRAM (0xFF80-0xFFFE)
        if addr < 0xFFFF:
            self.hram[addr - 0xFF80] = value
            return
        
        # IE (0xFFFF)
        self.ie = value
    
    def _read_io(self, addr):
        """Lee registro I/O"""
        reg = addr & 0x7F
        
        if reg == 0x00:  # Joypad
            return self.joypad.read() if self.joypad else 0xFF
        
        if reg == 0x04:  # DIV
            return self.timer.div if self.timer else self.io[reg]
        
        if reg == 0x05:  # TIMA
            return self.timer.tima if self.timer else self.io[reg]
        
        if 0x10 <= reg <= 0x3F:  # Audio
            return self.apu.read(reg) if self.apu else self.io[reg]
        
        if reg == 0x41:  # STAT
            if self.ppu:
                return (self.ppu.stat & 0xFC) | self.ppu.mode
            return self.io[reg]
        
        if reg == 0x44:  # LY
            return self.ppu.ly if self.ppu else self.io[reg]
        
        return self.io[reg]
    
    def _write_io(self, addr, value):
        """Escribe registro I/O"""
        reg = addr & 0x7F
        
        if reg == 0x00:  # Joypad
            if self.joypad:
                self.joypad.write(value)
        
        elif reg == 0x04:  # DIV - Reset on write
            if self.timer:
                self.timer.div = 0
            self.io[reg] = 0
            return
        
        elif reg == 0x05:  # TIMA
            if self.timer:
                self.timer.tima = value
        
        elif reg == 0x06:  # TMA
            if self.timer:
                self.timer.tma = value
        
        elif reg == 0x07:  # TAC
            if self.timer:
                self.timer.tac = value
        
        elif 0x10 <= reg <= 0x3F:  # Audio
            if self.apu:
                self.apu.write(reg, value)
        
        elif reg == 0x40:  # LCDC
            if self.ppu:
                self.ppu.lcdc = value
        
        elif reg == 0x41:  # STAT
            if self.ppu:
                self.ppu.stat = (self.ppu.stat & 0x07) | (value & 0xF8)
        
        elif reg == 0x42:  # SCY
            if self.ppu:
                self.ppu.scy = value
        
        elif reg == 0x43:  # SCX
            if self.ppu:
                self.ppu.scx = value
        
        elif reg == 0x45:  # LYC
            if self.ppu:
                self.ppu.lyc = value
        
        elif reg == 0x46:  # DMA
            self._dma(value)
        
        elif reg == 0x47:  # BGP
            if self.ppu:
                self.ppu.bgp = value
        
        elif reg == 0x48:  # OBP0
            if self.ppu:
                self.ppu.obp0 = value
        
        elif reg == 0x49:  # OBP1
            if self.ppu:
                self.ppu.obp1 = value
        
        elif reg == 0x4A:  # WY
            if self.ppu:
                self.ppu.wy = value
        
        elif reg == 0x4B:  # WX
            if self.ppu:
                self.ppu.wx = value
        
        self.io[reg] = value
    
    def _dma(self, value):
        """Transfiere 160 bytes a OAM"""
        src = value << 8
        for i in range(0xA0):
            self.oam[i] = self.read(src + i)