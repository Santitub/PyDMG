"""
PPU Optimizado con NumPy
"""
import numpy as np


class PPU:
    SCREEN_WIDTH = 160
    SCREEN_HEIGHT = 144
    
    MODE_HBLANK = 0
    MODE_VBLANK = 1
    MODE_OAM = 2
    MODE_TRANSFER = 3
    
    OAM_CYCLES = 80
    TRANSFER_CYCLES = 172
    HBLANK_CYCLES = 204
    SCANLINE_CYCLES = 456
    
    def __init__(self, mmu):
        self.mmu = mmu
        
        # Framebuffer como numpy array
        self.framebuffer = np.zeros((self.SCREEN_HEIGHT, self.SCREEN_WIDTH), dtype=np.uint8)
        
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
        
        self.mode = self.MODE_OAM
        self.cycles = 0
        self.frame_ready = False
        self.window_line = 0
        
        # Pre-compute paletas
        self.bg_palette = np.array([0, 1, 2, 3], dtype=np.uint8)
        self.obj_palette0 = np.array([0, 1, 2, 3], dtype=np.uint8)
        self.obj_palette1 = np.array([0, 1, 2, 3], dtype=np.uint8)
        
        # Line buffer para optimizar renderizado
        self._line_buffer = np.zeros(self.SCREEN_WIDTH, dtype=np.uint8)
        self._bg_priority = np.zeros(self.SCREEN_WIDTH, dtype=np.uint8)
    
    @property
    def stat(self):
        return (self._stat & 0xFC) | self.mode
    
    @stat.setter
    def stat(self, value):
        self._stat = value
    
    def step(self, cycles):
        if not (self.lcdc & 0x80):
            return
        
        self.cycles += cycles
        
        if self.mode == self.MODE_OAM:
            if self.cycles >= self.OAM_CYCLES:
                self.cycles -= self.OAM_CYCLES
                self.mode = self.MODE_TRANSFER
        
        elif self.mode == self.MODE_TRANSFER:
            if self.cycles >= self.TRANSFER_CYCLES:
                self.cycles -= self.TRANSFER_CYCLES
                self.mode = self.MODE_HBLANK
                self._render_scanline()
                if self._stat & 0x08:
                    self.mmu.io[0x0F] |= 0x02
        
        elif self.mode == self.MODE_HBLANK:
            if self.cycles >= self.HBLANK_CYCLES:
                self.cycles -= self.HBLANK_CYCLES
                self.ly += 1
                
                if self.ly == 144:
                    self.mode = self.MODE_VBLANK
                    self.frame_ready = True
                    self.mmu.io[0x0F] |= 0x01
                    if self._stat & 0x10:
                        self.mmu.io[0x0F] |= 0x02
                else:
                    self.mode = self.MODE_OAM
                    if self._stat & 0x20:
                        self.mmu.io[0x0F] |= 0x02
                
                self._check_lyc()
        
        elif self.mode == self.MODE_VBLANK:
            if self.cycles >= self.SCANLINE_CYCLES:
                self.cycles -= self.SCANLINE_CYCLES
                self.ly += 1
                
                if self.ly >= 154:
                    self.ly = 0
                    self.window_line = 0
                    self.mode = self.MODE_OAM
                    if self._stat & 0x20:
                        self.mmu.io[0x0F] |= 0x02
                
                self._check_lyc()
    
    def _check_lyc(self):
        if self.ly == self.lyc:
            self._stat |= 0x04
            if self._stat & 0x40:
                self.mmu.io[0x0F] |= 0x02
        else:
            self._stat &= ~0x04
    
    def _decode_palette(self, value):
        return np.array([
            (value >> 0) & 3,
            (value >> 2) & 3,
            (value >> 4) & 3,
            (value >> 6) & 3
        ], dtype=np.uint8)
    
    def _render_scanline(self):
        if self.ly >= self.SCREEN_HEIGHT:
            return
        
        self.bg_palette = self._decode_palette(self.bgp)
        self.obj_palette0 = self._decode_palette(self.obp0)
        self.obj_palette1 = self._decode_palette(self.obp1)
        
        # Clear line buffer
        self._line_buffer.fill(0)
        self._bg_priority.fill(0)
        
        if self.lcdc & 0x01:
            self._render_background()
        
        if (self.lcdc & 0x20) and self.wy <= self.ly:
            self._render_window()
        
        if self.lcdc & 0x02:
            self._render_sprites()
        
        # Copy to framebuffer
        self.framebuffer[self.ly] = self._line_buffer
    
    def _render_background(self):
        tile_map = 0x9C00 if (self.lcdc & 0x08) else 0x9800
        use_signed = not (self.lcdc & 0x10)
        
        y = (self.ly + self.scy) & 0xFF
        tile_row = y >> 3
        pixel_row = y & 7
        
        vram = self.mmu.vram
        
        for screen_x in range(self.SCREEN_WIDTH):
            x = (screen_x + self.scx) & 0xFF
            tile_col = x >> 3
            pixel_col = 7 - (x & 7)
            
            map_addr = tile_map + (tile_row << 5) + tile_col - 0x8000
            tile_num = vram[map_addr]
            
            if use_signed:
                if tile_num > 127:
                    tile_num -= 256
                tile_addr = 0x9000 + (tile_num << 4) - 0x8000
            else:
                tile_addr = (tile_num << 4)
            
            line_offset = pixel_row << 1
            low = vram[tile_addr + line_offset]
            high = vram[tile_addr + line_offset + 1]
            
            color_bit = ((high >> pixel_col) & 1) << 1
            color_bit |= (low >> pixel_col) & 1
            
            self._line_buffer[screen_x] = self.bg_palette[color_bit]
            self._bg_priority[screen_x] = color_bit
    
    def _render_window(self):
        wx = self.wx - 7
        if wx >= self.SCREEN_WIDTH:
            return
        
        tile_map = 0x9C00 if (self.lcdc & 0x40) else 0x9800
        use_signed = not (self.lcdc & 0x10)
        
        tile_row = self.window_line >> 3
        pixel_row = self.window_line & 7
        
        vram = self.mmu.vram
        rendered = False
        
        start_x = max(0, wx)
        for screen_x in range(start_x, self.SCREEN_WIDTH):
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
                    tile_num -= 256
                tile_addr = 0x9000 + (tile_num << 4) - 0x8000
            else:
                tile_addr = (tile_num << 4)
            
            line_offset = pixel_row << 1
            low = vram[tile_addr + line_offset]
            high = vram[tile_addr + line_offset + 1]
            
            color_bit = ((high >> pixel_col) & 1) << 1
            color_bit |= (low >> pixel_col) & 1
            
            self._line_buffer[screen_x] = self.bg_palette[color_bit]
            self._bg_priority[screen_x] = color_bit
        
        if rendered:
            self.window_line += 1
    
    def _render_sprites(self):
        sprite_height = 16 if (self.lcdc & 0x04) else 8
        oam = self.mmu.oam
        vram = self.mmu.vram
        
        sprites = []
        for i in range(40):
            y = oam[i * 4] - 16
            if y <= self.ly < y + sprite_height:
                x = oam[i * 4 + 1] - 8
                sprites.append((x, i))
                if len(sprites) >= 10:
                    break
        
        sprites.sort(key=lambda s: s[0], reverse=True)
        
        for x, idx in sprites:
            y = oam[idx * 4] - 16
            tile_num = oam[idx * 4 + 2]
            attrs = oam[idx * 4 + 3]
            
            priority = attrs & 0x80
            y_flip = attrs & 0x40
            x_flip = attrs & 0x20
            palette = self.obj_palette1 if (attrs & 0x10) else self.obj_palette0
            
            if sprite_height == 16:
                tile_num &= 0xFE
            
            sprite_line = self.ly - y
            if y_flip:
                sprite_line = sprite_height - 1 - sprite_line
            
            tile_addr = (tile_num << 4) + (sprite_line << 1)
            low = vram[tile_addr]
            high = vram[tile_addr + 1]
            
            for pixel in range(8):
                screen_x = x + pixel
                if 0 <= screen_x < self.SCREEN_WIDTH:
                    bit = pixel if x_flip else (7 - pixel)
                    
                    color_bit = ((high >> bit) & 1) << 1
                    color_bit |= (low >> bit) & 1
                    
                    if color_bit == 0:
                        continue
                    
                    if priority and self._bg_priority[screen_x] != 0:
                        continue
                    
                    self._line_buffer[screen_x] = palette[color_bit]