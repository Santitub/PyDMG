# cython: language_level=3, boundscheck=False, wraparound=False, cdivision=True
"""
PPU - Cython optimizado (CORREGIDO)
"""

cimport cython
from libc.stdint cimport uint8_t, uint16_t
from libc.string cimport memset
import numpy as np
cimport numpy as np

np.import_array()


cdef class PPU:
    # Constantes
    cdef int SCREEN_WIDTH
    cdef int SCREEN_HEIGHT
    
    # Referencias
    cdef object mmu
    
    # Framebuffer
    cdef public np.ndarray framebuffer
    cdef uint8_t[:, :] fb_view
    
    # Registros públicos
    cdef public uint8_t lcdc, _stat, scy, scx, ly, lyc
    cdef public uint8_t bgp, obp0, obp1, wy, wx
    cdef public int mode, cycles, window_line
    cdef public bint frame_ready
    
    # Paletas como arrays individuales
    cdef uint8_t bg_pal_0, bg_pal_1, bg_pal_2, bg_pal_3
    cdef uint8_t obj_pal0_0, obj_pal0_1, obj_pal0_2, obj_pal0_3
    cdef uint8_t obj_pal1_0, obj_pal1_1, obj_pal1_2, obj_pal1_3
    
    # Line buffers
    cdef np.ndarray _line_buffer_arr
    cdef np.ndarray _bg_priority_arr
    cdef uint8_t[:] line_buffer
    cdef uint8_t[:] bg_priority
    
    def __init__(self, mmu):
        self.SCREEN_WIDTH = 160
        self.SCREEN_HEIGHT = 144
        
        self.mmu = mmu
        self.framebuffer = np.zeros((144, 160), dtype=np.uint8)
        self.fb_view = self.framebuffer
        
        self._line_buffer_arr = np.zeros(160, dtype=np.uint8)
        self._bg_priority_arr = np.zeros(160, dtype=np.uint8)
        self.line_buffer = self._line_buffer_arr
        self.bg_priority = self._bg_priority_arr
        
        self.lcdc = 0x91
        self._stat = 0x85
        self.scy = 0
        self.scx = 0
        self.ly = 0
        self.lyc = 0
        self.bgp = 0xFC
        self.obp0 = 0xFF
        self.obp1 = 0xFF
        self.wy = 0
        self.wx = 0
        
        self.mode = 2
        self.cycles = 0
        self.frame_ready = False
        self.window_line = 0
        
        # Inicializar paletas
        self.bg_pal_0 = self.bg_pal_1 = self.bg_pal_2 = self.bg_pal_3 = 0
        self.obj_pal0_0 = self.obj_pal0_1 = self.obj_pal0_2 = self.obj_pal0_3 = 0
        self.obj_pal1_0 = self.obj_pal1_1 = self.obj_pal1_2 = self.obj_pal1_3 = 0
    
    @property
    def stat(self):
        return (self._stat & 0xFC) | self.mode
    
    @stat.setter
    def stat(self, value):
        self._stat = value
    
    cpdef void step(self, int cycles):
        if not (self.lcdc & 0x80):
            return
        
        self.cycles += cycles
        
        if self.mode == 2:  # OAM
            if self.cycles >= 80:
                self.cycles -= 80
                self.mode = 3
        
        elif self.mode == 3:  # Transfer
            if self.cycles >= 172:
                self.cycles -= 172
                self.mode = 0
                self._render_scanline()
                if self._stat & 0x08:
                    self.mmu.io[0x0F] |= 0x02
        
        elif self.mode == 0:  # HBlank
            if self.cycles >= 204:
                self.cycles -= 204
                self.ly += 1
                
                if self.ly == 144:
                    self.mode = 1
                    self.frame_ready = True
                    self.mmu.io[0x0F] |= 0x01
                    if self._stat & 0x10:
                        self.mmu.io[0x0F] |= 0x02
                else:
                    self.mode = 2
                    if self._stat & 0x20:
                        self.mmu.io[0x0F] |= 0x02
                
                self._check_lyc()
        
        elif self.mode == 1:  # VBlank
            if self.cycles >= 456:
                self.cycles -= 456
                self.ly += 1
                
                if self.ly >= 154:
                    self.ly = 0
                    self.window_line = 0
                    self.mode = 2
                    if self._stat & 0x20:
                        self.mmu.io[0x0F] |= 0x02
                
                self._check_lyc()
    
    cdef inline void _check_lyc(self):
        if self.ly == self.lyc:
            self._stat |= 0x04
            if self._stat & 0x40:
                self.mmu.io[0x0F] |= 0x02
        else:
            self._stat &= ~0x04
    
    cdef inline void _decode_bg_palette(self, uint8_t val):
        self.bg_pal_0 = val & 0x03
        self.bg_pal_1 = (val >> 2) & 0x03
        self.bg_pal_2 = (val >> 4) & 0x03
        self.bg_pal_3 = (val >> 6) & 0x03
    
    cdef inline void _decode_obj0_palette(self, uint8_t val):
        self.obj_pal0_0 = val & 0x03
        self.obj_pal0_1 = (val >> 2) & 0x03
        self.obj_pal0_2 = (val >> 4) & 0x03
        self.obj_pal0_3 = (val >> 6) & 0x03
    
    cdef inline void _decode_obj1_palette(self, uint8_t val):
        self.obj_pal1_0 = val & 0x03
        self.obj_pal1_1 = (val >> 2) & 0x03
        self.obj_pal1_2 = (val >> 4) & 0x03
        self.obj_pal1_3 = (val >> 6) & 0x03
    
    cdef inline uint8_t _get_bg_color(self, uint8_t idx):
        if idx == 0: return self.bg_pal_0
        elif idx == 1: return self.bg_pal_1
        elif idx == 2: return self.bg_pal_2
        else: return self.bg_pal_3
    
    cdef inline uint8_t _get_obj0_color(self, uint8_t idx):
        if idx == 0: return self.obj_pal0_0
        elif idx == 1: return self.obj_pal0_1
        elif idx == 2: return self.obj_pal0_2
        else: return self.obj_pal0_3
    
    cdef inline uint8_t _get_obj1_color(self, uint8_t idx):
        if idx == 0: return self.obj_pal1_0
        elif idx == 1: return self.obj_pal1_1
        elif idx == 2: return self.obj_pal1_2
        else: return self.obj_pal1_3
    
    cdef void _render_scanline(self):
        cdef int x
        cdef uint8_t[:] lb = self.line_buffer
        cdef uint8_t[:] bp = self.bg_priority
        
        if self.ly >= 144:
            return
        
        # Decodificar paletas
        self._decode_bg_palette(self.bgp)
        self._decode_obj0_palette(self.obp0)
        self._decode_obj1_palette(self.obp1)
        
        # Limpiar buffers
        for x in range(160):
            lb[x] = 0
            bp[x] = 0
        
        # Renderizar capas
        if self.lcdc & 0x01:
            self._render_background()
        
        if (self.lcdc & 0x20) and self.wy <= self.ly:
            self._render_window()
        
        if self.lcdc & 0x02:
            self._render_sprites()
        
        # Copiar al framebuffer
        for x in range(160):
            self.fb_view[self.ly, x] = lb[x]
    
    cdef void _render_background(self):
        cdef uint16_t tile_map, tile_addr
        cdef int y, tile_row, pixel_row, screen_x, x, tile_col, pixel_col
        cdef uint16_t map_addr, line_offset
        cdef uint8_t tile_num, low, high, color_bit
        cdef bint use_signed
        cdef object vram = self.mmu.vram
        cdef uint8_t[:] lb = self.line_buffer
        cdef uint8_t[:] bp = self.bg_priority
        
        tile_map = 0x9C00 if (self.lcdc & 0x08) else 0x9800
        use_signed = not (self.lcdc & 0x10)
        
        y = (self.ly + self.scy) & 0xFF
        tile_row = y >> 3
        pixel_row = y & 7
        
        for screen_x in range(160):
            x = (screen_x + self.scx) & 0xFF
            tile_col = x >> 3
            pixel_col = 7 - (x & 7)
            
            map_addr = tile_map + (tile_row << 5) + tile_col - 0x8000
            tile_num = vram[map_addr]
            
            if use_signed:
                if tile_num > 127:
                    tile_addr = 0x9000 + ((<int>tile_num - 256) << 4) - 0x8000
                else:
                    tile_addr = 0x9000 + (tile_num << 4) - 0x8000
            else:
                tile_addr = tile_num << 4
            
            line_offset = pixel_row << 1
            low = vram[tile_addr + line_offset]
            high = vram[tile_addr + line_offset + 1]
            
            color_bit = ((high >> pixel_col) & 1) << 1
            color_bit |= (low >> pixel_col) & 1
            
            lb[screen_x] = self._get_bg_color(color_bit)
            bp[screen_x] = color_bit
    
    cdef void _render_window(self):
        cdef int wx, tile_row, pixel_row, screen_x, win_x, tile_col, pixel_col
        cdef uint16_t tile_map, map_addr, tile_addr, line_offset
        cdef uint8_t tile_num, low, high, color_bit
        cdef bint use_signed, rendered = False
        cdef object vram = self.mmu.vram
        cdef uint8_t[:] lb = self.line_buffer
        cdef uint8_t[:] bp = self.bg_priority
        cdef int start_x
        
        wx = self.wx - 7
        if wx >= 160:
            return
        
        tile_map = 0x9C00 if (self.lcdc & 0x40) else 0x9800
        use_signed = not (self.lcdc & 0x10)
        
        tile_row = self.window_line >> 3
        pixel_row = self.window_line & 7
        
        start_x = 0 if wx < 0 else wx
        
        for screen_x in range(start_x, 160):
            win_x = screen_x - wx
            if win_x < 0:
                continue
            
            rendered = True
            tile_col = win_x >> 3
            pixel_col = 7 - (win_x & 7)
            
            map_addr = tile_map + (tile_row << 5) + tile_col - 0x8000
            tile_num = vram[map_addr]
            
            if use_signed:
                if tile_num > 127:
                    tile_addr = 0x9000 + ((<int>tile_num - 256) << 4) - 0x8000
                else:
                    tile_addr = 0x9000 + (tile_num << 4) - 0x8000
            else:
                tile_addr = tile_num << 4
            
            line_offset = pixel_row << 1
            low = vram[tile_addr + line_offset]
            high = vram[tile_addr + line_offset + 1]
            
            color_bit = ((high >> pixel_col) & 1) << 1
            color_bit |= (low >> pixel_col) & 1
            
            lb[screen_x] = self._get_bg_color(color_bit)
            bp[screen_x] = color_bit
        
        if rendered:
            self.window_line += 1
    
    cdef void _render_sprites(self):
        cdef int sprite_height, i, y, x, count = 0
        cdef list sprites = []
        cdef object oam = self.mmu.oam
        cdef tuple sprite_tuple
        
        sprite_height = 16 if (self.lcdc & 0x04) else 8
        
        for i in range(40):
            y = oam[i * 4] - 16
            if y <= self.ly < y + sprite_height:
                x = oam[i * 4 + 1] - 8
                sprites.append((x, i))
                count += 1
                if count >= 10:
                    break
        
        # Ordenar por X (para prioridad)
        sprites.sort(key=lambda s: s[0], reverse=True)
        
        for sprite_tuple in sprites:
            self._render_sprite(sprite_tuple[1], sprite_height)
    
    cdef void _render_sprite(self, int idx, int height):
        cdef int y, x, sprite_line, pixel, screen_x, bit
        cdef uint8_t tile_num, attrs, low, high, color_bit, color
        cdef bint priority, y_flip, x_flip, use_pal1
        cdef uint16_t tile_addr
        cdef object oam = self.mmu.oam
        cdef object vram = self.mmu.vram
        cdef uint8_t[:] lb = self.line_buffer
        cdef uint8_t[:] bp = self.bg_priority
        
        y = oam[idx * 4] - 16
        x = oam[idx * 4 + 1] - 8
        tile_num = oam[idx * 4 + 2]
        attrs = oam[idx * 4 + 3]
        
        priority = (attrs & 0x80) != 0
        y_flip = (attrs & 0x40) != 0
        x_flip = (attrs & 0x20) != 0
        use_pal1 = (attrs & 0x10) != 0
        
        if height == 16:
            tile_num &= 0xFE
        
        sprite_line = self.ly - y
        if y_flip:
            sprite_line = height - 1 - sprite_line
        
        tile_addr = (tile_num << 4) + (sprite_line << 1)
        low = vram[tile_addr]
        high = vram[tile_addr + 1]
        
        for pixel in range(8):
            screen_x = x + pixel
            if 0 <= screen_x < 160:
                if x_flip:
                    bit = pixel
                else:
                    bit = 7 - pixel
                
                color_bit = ((high >> bit) & 1) << 1
                color_bit |= (low >> bit) & 1
                
                # Color 0 es transparente
                if color_bit == 0:
                    continue
                
                # Prioridad BG
                if priority and bp[screen_x] != 0:
                    continue
                
                # Obtener color de la paleta correcta
                if use_pal1:
                    color = self._get_obj1_color(color_bit)
                else:
                    color = self._get_obj0_color(color_bit)
                
                lb[screen_x] = color