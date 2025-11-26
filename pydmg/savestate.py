"""
Sistema de Save States
"""

import os
import zlib
import struct


class SaveState:
    """Maneja guardado y carga de estados"""
    
    MAGIC = b'GBSS'
    VERSION = 1
    
    @staticmethod
    def _get_path(gameboy, slot):
        """Obtiene la ruta del archivo de save state"""
        if not hasattr(gameboy, 'mmu') or not gameboy.mmu.rom_path:
            return None
        base = os.path.splitext(gameboy.mmu.rom_path)[0]
        return f"{base}.st{slot}"
    
    @staticmethod
    def save(gameboy, slot=0):
        """Guarda el estado"""
        path = SaveState._get_path(gameboy, slot)
        if not path:
            print("⚠ No hay ROM cargada")
            return False
        
        try:
            data = SaveState._serialize(gameboy)
            compressed = zlib.compress(data, 6)
            
            with open(path, 'wb') as f:
                f.write(SaveState.MAGIC)
                f.write(struct.pack('<I', SaveState.VERSION))
                f.write(struct.pack('<I', len(data)))
                f.write(struct.pack('<I', len(compressed)))
                f.write(compressed)
            
            return True
        except Exception as e:
            print(f"❌ Error guardando: {e}")
            return False
    
    @staticmethod
    def load(gameboy, slot=0):
        """Carga el estado"""
        path = SaveState._get_path(gameboy, slot)
        if not path:
            print("⚠ No hay ROM cargada")
            return False
        
        if not os.path.exists(path):
            print(f"⚠ No existe save en slot {slot}")
            return False
        
        try:
            with open(path, 'rb') as f:
                magic = f.read(4)
                if magic != SaveState.MAGIC:
                    print("❌ Archivo inválido")
                    return False
                
                version = struct.unpack('<I', f.read(4))[0]
                orig_size = struct.unpack('<I', f.read(4))[0]
                comp_size = struct.unpack('<I', f.read(4))[0]
                
                compressed = f.read(comp_size)
                data = zlib.decompress(compressed)
                
                SaveState._deserialize(gameboy, data)
            
            return True
        except Exception as e:
            print(f"❌ Error cargando: {e}")
            return False
    
    @staticmethod
    def _framebuffer_to_bytes(framebuffer):
        """Convierte el framebuffer a bytes (compatible con lista o numpy)"""
        # Si es numpy array
        if hasattr(framebuffer, 'tobytes'):
            return framebuffer.tobytes()
        
        # Si es lista de listas
        data = bytearray()
        for row in framebuffer:
            for pixel in row:
                data.append(pixel & 0xFF)
        return bytes(data)
    
    @staticmethod
    def _bytes_to_framebuffer(data, framebuffer):
        """Restaura el framebuffer desde bytes (compatible con lista o numpy)"""
        # Si es numpy array
        if hasattr(framebuffer, 'reshape'):
            import numpy as np
            new_fb = np.frombuffer(data, dtype=np.uint8).reshape((144, 160)).copy()
            framebuffer[:] = new_fb
            return
        
        # Si es lista de listas
        idx = 0
        for y in range(144):
            for x in range(160):
                if idx < len(data):
                    framebuffer[y][x] = data[idx]
                    idx += 1
    
    @staticmethod
    def _serialize(gb):
        """Serializa el estado del emulador"""
        data = bytearray()
        
        # === CPU ===
        cpu = gb.cpu
        data.extend(struct.pack('<BBBBBBBB',
            cpu.a, cpu.f, cpu.b, cpu.c, cpu.d, cpu.e, cpu.h, cpu.l))
        data.extend(struct.pack('<HH', cpu.sp, cpu.pc))
        data.extend(struct.pack('<BBB',
            1 if cpu.halted else 0,
            1 if cpu.ime else 0,
            1 if getattr(cpu, 'ime_next', False) else 0))
        
        # === MMU ===
        mmu = gb.mmu
        data.extend(mmu.vram)
        data.extend(mmu.wram)
        data.extend(mmu.oam)
        data.extend(mmu.hram)
        data.extend(mmu.io)
        data.extend(struct.pack('<B', mmu.ie))
        
        # === MBC ===
        if hasattr(mmu, 'mbc') and mmu.mbc:
            mbc = mmu.mbc
            data.extend(struct.pack('<B', 1))  # has MBC
            data.extend(struct.pack('<I', len(mbc.ram)))
            data.extend(mbc.ram)
            data.extend(struct.pack('<BHH',
                1 if mbc.ram_enabled else 0,
                mbc.rom_bank,
                mbc.ram_bank))
        else:
            data.extend(struct.pack('<B', 0))  # no MBC
        
        # === PPU ===
        ppu = gb.ppu
        
        # stat puede ser property o variable
        stat_val = ppu._stat if hasattr(ppu, '_stat') else ppu.stat
        
        # window_line puede tener diferentes nombres
        window_line = getattr(ppu, 'window_line', getattr(ppu, 'wly', 0))
        
        data.extend(struct.pack('<BBBBBBBBBB',
            ppu.lcdc, 
            stat_val,
            ppu.scy, ppu.scx,
            ppu.ly, ppu.lyc, 
            ppu.bgp, ppu.obp0, ppu.obp1, ppu.wy))
        data.extend(struct.pack('<BHH',
            ppu.wx,
            ppu.mode,
            ppu.cycles))
        data.extend(struct.pack('<H', window_line))
        data.extend(struct.pack('<B', 1 if ppu.frame_ready else 0))
        
        # Framebuffer (compatible con lista o numpy)
        fb_bytes = SaveState._framebuffer_to_bytes(ppu.framebuffer)
        data.extend(fb_bytes)
        
        # === Timer ===
        timer = gb.timer
        div_val = getattr(timer, '_div', getattr(timer, 'internal_counter', 0))
        tima_cycles = getattr(timer, 'tima_cycles', 0)
        data.extend(struct.pack('<HBBBI',
            div_val, timer.tima, timer.tma, timer.tac, tima_cycles))
        
        # === Joypad ===
        jp = gb.joypad
        buttons = 0
        for i, key in enumerate(['right', 'left', 'up', 'down', 'a', 'b', 'select', 'start']):
            if not jp.buttons.get(key, 1):
                buttons |= (1 << i)
        data.extend(struct.pack('<BBB',
            buttons,
            1 if jp.select_buttons else 0,
            1 if jp.select_dpad else 0))
        
        return bytes(data)
    
    @staticmethod
    def _deserialize(gb, data):
        """Restaura el estado del emulador"""
        offset = 0
        
        def read(n):
            nonlocal offset
            result = data[offset:offset+n]
            offset += n
            return result
        
        def unpack(fmt):
            nonlocal offset
            size = struct.calcsize(fmt)
            result = struct.unpack(fmt, data[offset:offset+size])
            offset += size
            return result
        
        # === CPU ===
        cpu = gb.cpu
        cpu.a, cpu.f, cpu.b, cpu.c, cpu.d, cpu.e, cpu.h, cpu.l = unpack('<BBBBBBBB')
        cpu.sp, cpu.pc = unpack('<HH')
        halted, ime, ime_next = unpack('<BBB')
        cpu.halted = halted == 1
        cpu.ime = ime == 1
        if hasattr(cpu, 'ime_next'):
            cpu.ime_next = ime_next == 1
        
        # === MMU ===
        mmu = gb.mmu
        mmu.vram[:] = read(len(mmu.vram))
        mmu.wram[:] = read(len(mmu.wram))
        mmu.oam[:] = read(len(mmu.oam))
        mmu.hram[:] = read(len(mmu.hram))
        mmu.io[:] = read(len(mmu.io))
        mmu.ie = unpack('<B')[0]
        
        # === MBC ===
        has_mbc = unpack('<B')[0]
        if has_mbc:
            ram_size = unpack('<I')[0]
            ram_data = read(ram_size)
            if hasattr(mmu, 'mbc') and mmu.mbc:
                mbc = mmu.mbc
                if len(ram_data) <= len(mbc.ram):
                    mbc.ram[:len(ram_data)] = ram_data
                ram_enabled, mbc.rom_bank, mbc.ram_bank = unpack('<BHH')
                mbc.ram_enabled = ram_enabled == 1
            else:
                unpack('<BHH')  # Saltar datos
        
        # === PPU ===
        ppu = gb.ppu
        (lcdc, stat, scy, scx, ly, lyc, 
         bgp, obp0, obp1, wy) = unpack('<BBBBBBBBBB')
        wx, mode, cycles = unpack('<BHH')
        window_line = unpack('<H')[0]
        frame_ready = unpack('<B')[0]
        
        ppu.lcdc = lcdc
        if hasattr(ppu, '_stat'):
            ppu._stat = stat
        ppu.scy = scy
        ppu.scx = scx
        ppu.ly = ly
        ppu.lyc = lyc
        ppu.bgp = bgp
        ppu.obp0 = obp0
        ppu.obp1 = obp1
        ppu.wy = wy
        ppu.wx = wx
        ppu.mode = mode
        ppu.cycles = cycles
        ppu.frame_ready = frame_ready == 1
        
        # Restaurar window_line
        if hasattr(ppu, 'window_line'):
            ppu.window_line = window_line
        elif hasattr(ppu, 'wly'):
            ppu.wly = window_line
        
        # Framebuffer (144 * 160 = 23040 bytes)
        fb_data = read(144 * 160)
        SaveState._bytes_to_framebuffer(fb_data, ppu.framebuffer)
        
        # === Timer ===
        timer = gb.timer
        div_val, tima, tma, tac, tima_cycles = unpack('<HBBBI')
        
        if hasattr(timer, '_div'):
            timer._div = div_val
        elif hasattr(timer, 'internal_counter'):
            timer.internal_counter = div_val
        
        timer.tima = tima
        timer.tma = tma
        timer.tac = tac
        
        if hasattr(timer, 'tima_cycles'):
            timer.tima_cycles = tima_cycles
        
        # === Joypad ===
        jp = gb.joypad
        buttons, sel_btn, sel_dpad = unpack('<BBB')
        for i, key in enumerate(['right', 'left', 'up', 'down', 'a', 'b', 'select', 'start']):
            jp.buttons[key] = 0 if (buttons & (1 << i)) else 1
        jp.select_buttons = sel_btn == 1
        jp.select_dpad = sel_dpad == 1