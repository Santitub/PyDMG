# ppu.pyx
# cython: language_level=3
# cython: boundscheck=False
# cython: wraparound=False
# cython: cdivision=True
# cython: initializedcheck=False

cimport cython
from libc.stdint cimport uint8_t, uint16_t, int8_t
import numpy as np
cimport numpy as np

np.import_array()

cdef class PPU:
    # Constantes
    cdef readonly int SCREEN_WIDTH
    cdef readonly int SCREEN_HEIGHT
    
    # MMU reference
    cdef object mmu
    
    # Framebuffer - DEBE ser public para acceso desde Python
    cdef public object framebuffer
    cdef uint8_t[:, :] fb_view  # View 2D para acceso rápido
    
    # Registros públicos
    cdef public uint8_t lcdc, _stat, scy, scx, ly, lyc
    cdef public uint8_t bgp, obp0, obp1, wy, wx
    cdef public int mode, cycles, window_line
    cdef public bint frame_ready
    
    # Cache de paletas
    cdef uint8_t[4] bg_palette
    cdef uint8_t[4] obj_palette0
    cdef uint8_t[4] obj_palette1
    
    # Buffer de prioridad
    cdef uint8_t[160] bg_priority
    
    def __init__(self, mmu):
        self.SCREEN_WIDTH = 160
        self.SCREEN_HEIGHT = 144
        
        self.mmu = mmu
        
        # Framebuffer 2D para compatibilidad con main.py (accede como fb[y][x])
        self.framebuffer = np.zeros((144, 160), dtype=np.uint8)
        self.fb_view = self.framebuffer
        
        # Registros
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
        
        # Estado
        self.mode = 2  # OAM
        self.cycles = 0
        self.frame_ready = False
        self.window_line = 0
        
        # Inicializar paletas
        cdef int i
        for i in range(4):
            self.bg_palette[i] = i
            self.obj_palette0[i] = i
            self.obj_palette1[i] = i
    
    @property
    def stat(self):
        return (self._stat & 0xFC) | self.mode
    
    @stat.setter
    def stat(self, uint8_t value):
        self._stat = value
    
    cpdef void step(self, int cycles):
        """Avanza el PPU"""
        if not (self.lcdc & 0x80):
            return
        
        self.cycles += cycles
        
        if self.mode == 2:  # OAM Search
            if self.cycles >= 80:
                self.cycles -= 80
                self.mode = 3
        
        elif self.mode == 3:  # Pixel Transfer
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
                    self.mmu.io[0x0F] |= 0x01  # VBlank interrupt
                    if self._stat & 0x10:
                        self.mmu.io[0x0F] |= 0x02
                else:
                    self.mode = 2
                    if self._stat & 0x20:
                        self.mmu.io[0x0F] |= 0x02
                
                self._check_lyc()
        
        else:  # VBlank (mode 1)
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
    
    cdef inline void _update_palettes(self):
        """Actualiza cache de paletas"""
        cdef uint8_t p = self.bgp
        self.bg_palette[0] = p & 0x03
        self.bg_palette[1] = (p >> 2) & 0x03
        self.bg_palette[2] = (p >> 4) & 0x03
        self.bg_palette[3] = (p >> 6) & 0x03
        
        p = self.obp0
        self.obj_palette0[0] = p & 0x03
        self.obj_palette0[1] = (p >> 2) & 0x03
        self.obj_palette0[2] = (p >> 4) & 0x03
        self.obj_palette0[3] = (p >> 6) & 0x03
        
        p = self.obp1
        self.obj_palette1[0] = p & 0x03
        self.obj_palette1[1] = (p >> 2) & 0x03
        self.obj_palette1[2] = (p >> 4) & 0x03
        self.obj_palette1[3] = (p >> 6) & 0x03
    
    cdef void _render_scanline(self):
        """Renderiza una línea completa"""
        cdef int ly = self.ly
        cdef uint8_t lcdc = self.lcdc
        cdef int i
        
        if ly >= 144:
            return
        
        self._update_palettes()
        
        # Reset priority buffer
        for i in range(160):
            self.bg_priority[i] = 0
        
        # Renderizar fondo
        if lcdc & 0x01:
            self._render_bg(ly)
        else:
            for i in range(160):
                self.fb_view[ly, i] = 0
        
        # Renderizar ventana
        if (lcdc & 0x20) and self.wy <= ly:
            self._render_window(ly)
        
        # Renderizar sprites
        if lcdc & 0x02:
            self._render_sprites(ly)
    
    cdef void _render_bg(self, int ly):
        """Renderiza línea de fondo"""
        cdef uint8_t[:] vram = self.mmu.vram
        cdef uint8_t[:, :] fb = self.fb_view
        
        cdef int tile_map_base = 0x1C00 if (self.lcdc & 0x08) else 0x1800
        cdef bint signed_tiles = not (self.lcdc & 0x10)
        
        cdef int y = (ly + self.scy) & 0xFF
        cdef int tile_row = y >> 3
        cdef int pixel_row = y & 7
        cdef int scx = self.scx
        
        cdef int screen_x, x, tile_col
        cdef int map_addr, tile_addr, line_addr
        cdef int tile_num_signed
        cdef uint8_t tile_num, lo, hi, color_idx
        cdef int bit
        
        for screen_x in range(160):
            x = (screen_x + scx) & 0xFF
            tile_col = x >> 3
            
            # Obtener número de tile
            map_addr = tile_map_base + (tile_row * 32) + tile_col
            tile_num = vram[map_addr]
            
            # Calcular dirección de datos del tile
            if signed_tiles:
                # Modo $8800: tiles -128 a 127, base en $9000
                if tile_num < 128:
                    tile_addr = 0x1000 + tile_num * 16
                else:
                    tile_addr = 0x1000 + (tile_num - 256) * 16
            else:
                # Modo $8000: tiles 0-255, base en $8000
                tile_addr = tile_num * 16
            
            # Leer bytes del tile
            line_addr = tile_addr + (pixel_row * 2)
            lo = vram[line_addr]
            hi = vram[line_addr + 1]
            
            # Extraer color (bit 7 = pixel izquierdo, bit 0 = pixel derecho)
            bit = 7 - (x & 7)
            color_idx = ((hi >> bit) & 1) << 1
            color_idx |= (lo >> bit) & 1
            
            fb[ly, screen_x] = self.bg_palette[color_idx]
            self.bg_priority[screen_x] = 1 if color_idx != 0 else 0
    
    cdef void _render_window(self, int ly):
        """Renderiza línea de ventana"""
        cdef int wx = self.wx - 7
        
        if wx >= 160:
            return
        
        cdef uint8_t[:] vram = self.mmu.vram
        cdef uint8_t[:, :] fb = self.fb_view
        
        cdef int tile_map_base = 0x1C00 if (self.lcdc & 0x40) else 0x1800
        cdef bint signed_tiles = not (self.lcdc & 0x10)
        
        cdef int window_y = self.window_line
        cdef int tile_row = window_y >> 3
        cdef int pixel_row = window_y & 7
        
        cdef int screen_x, win_x, tile_col
        cdef int map_addr, tile_addr, line_addr
        cdef uint8_t tile_num, lo, hi, color_idx
        cdef int bit
        cdef bint rendered = False
        cdef int start_x = wx if wx >= 0 else 0
        
        for screen_x in range(start_x, 160):
            win_x = screen_x - wx
            if win_x < 0:
                continue
            
            rendered = True
            tile_col = win_x >> 3
            
            map_addr = tile_map_base + (tile_row * 32) + tile_col
            tile_num = vram[map_addr]
            
            if signed_tiles:
                if tile_num < 128:
                    tile_addr = 0x1000 + tile_num * 16
                else:
                    tile_addr = 0x1000 + (tile_num - 256) * 16
            else:
                tile_addr = tile_num * 16
            
            line_addr = tile_addr + (pixel_row * 2)
            lo = vram[line_addr]
            hi = vram[line_addr + 1]
            
            bit = 7 - (win_x & 7)
            color_idx = ((hi >> bit) & 1) << 1
            color_idx |= (lo >> bit) & 1
            
            fb[ly, screen_x] = self.bg_palette[color_idx]
            self.bg_priority[screen_x] = 1 if color_idx != 0 else 0
        
        if rendered:
            self.window_line += 1
    
    cdef void _render_sprites(self, int ly):
        """Renderiza sprites en la línea actual"""
        cdef uint8_t[:] oam = self.mmu.oam
        cdef uint8_t[:] vram = self.mmu.vram
        cdef uint8_t[:, :] fb = self.fb_view
        
        cdef int sprite_height = 16 if (self.lcdc & 0x04) else 8
        
        # Buscar sprites visibles en esta línea (máximo 10)
        cdef int[10] sprite_x
        cdef int[10] sprite_indices
        cdef int sprite_count = 0
        cdef int i, j, base, y, x
        
        for i in range(40):
            base = i * 4
            y = oam[base] - 16
            
            if y <= ly < y + sprite_height:
                sprite_x[sprite_count] = oam[base + 1] - 8
                sprite_indices[sprite_count] = base
                sprite_count += 1
                if sprite_count >= 10:
                    break
        
        if sprite_count == 0:
            return
        
        # Ordenar por X descendente (para prioridad correcta en DMG)
        cdef int temp_x, temp_idx
        for i in range(sprite_count - 1):
            for j in range(sprite_count - 1 - i):
                if sprite_x[j] < sprite_x[j + 1]:
                    temp_x = sprite_x[j]
                    sprite_x[j] = sprite_x[j + 1]
                    sprite_x[j + 1] = temp_x
                    temp_idx = sprite_indices[j]
                    sprite_indices[j] = sprite_indices[j + 1]
                    sprite_indices[j + 1] = temp_idx
        
        # Renderizar sprites
        cdef int tile_num, attrs, sprite_line, tile_addr
        cdef int screen_x, bit, pixel
        cdef uint8_t lo, hi, color_idx
        cdef bint bg_over_obj, y_flip, x_flip, use_pal1
        
        for i in range(sprite_count):
            x = sprite_x[i]
            base = sprite_indices[i]
            
            y = oam[base] - 16
            tile_num = oam[base + 2]
            attrs = oam[base + 3]
            
            bg_over_obj = (attrs & 0x80) != 0
            y_flip = (attrs & 0x40) != 0
            x_flip = (attrs & 0x20) != 0
            use_pal1 = (attrs & 0x10) != 0
            
            # Para sprites 8x16, ignorar bit 0 del tile
            if sprite_height == 16:
                tile_num &= 0xFE
            
            # Calcular línea dentro del sprite
            sprite_line = ly - y
            if y_flip:
                sprite_line = sprite_height - 1 - sprite_line
            
            # Dirección de datos
            tile_addr = tile_num * 16 + sprite_line * 2
            lo = vram[tile_addr]
            hi = vram[tile_addr + 1]
            
            # Dibujar 8 pixels
            for pixel in range(8):
                screen_x = x + pixel
                
                if 0 <= screen_x < 160:
                    # Calcular bit a leer
                    # Sin flip: pixel 0 lee bit 7, pixel 7 lee bit 0
                    # Con flip: pixel 0 lee bit 0, pixel 7 lee bit 7
                    if x_flip:
                        bit = pixel
                    else:
                        bit = 7 - pixel
                    
                    color_idx = ((hi >> bit) & 1) << 1
                    color_idx |= (lo >> bit) & 1
                    
                    # Color 0 es transparente
                    if color_idx == 0:
                        continue
                    
                    # Prioridad: si bg_over_obj y hay color de fondo, no dibujar
                    if bg_over_obj and self.bg_priority[screen_x]:
                        continue
                    
                    # Dibujar pixel con paleta correspondiente
                    if use_pal1:
                        fb[ly, screen_x] = self.obj_palette1[color_idx]
                    else:
                        fb[ly, screen_x] = self.obj_palette0[color_idx]