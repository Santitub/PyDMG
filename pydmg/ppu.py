"""
Picture Processing Unit
"""

class PPU:
    # Constantes
    SCREEN_WIDTH = 160
    SCREEN_HEIGHT = 144
    VBLANK_START = 144
    SCANLINES_TOTAL = 154
    
    # Modos del PPU
    MODE_HBLANK = 0
    MODE_VBLANK = 1
    MODE_OAM = 2
    MODE_TRANSFER = 3
    
    # Duraciones en ciclos
    OAM_CYCLES = 80
    TRANSFER_CYCLES = 172
    HBLANK_CYCLES = 204
    SCANLINE_CYCLES = 456
    
    def __init__(self, mmu):
        self.mmu = mmu
        
        # Frame buffer (160x144 pixels, escala de grises 0-3)
        self.framebuffer = [[0] * self.SCREEN_WIDTH for _ in range(self.SCREEN_HEIGHT)]
        
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
        
        # Estado interno
        self.mode = self.MODE_OAM
        self.cycles = 0
        self.frame_ready = False
        self.window_line = 0
        
        # Paletas decodificadas
        self.bg_palette = [0, 1, 2, 3]
        self.obj_palette0 = [0, 1, 2, 3]
        self.obj_palette1 = [0, 1, 2, 3]
    
    @property
    def stat(self):
        return (self._stat & 0xFC) | self.mode
    
    @stat.setter
    def stat(self, value):
        self._stat = value
    
    def step(self, cycles):
        """Avanza el PPU por el número de ciclos dado"""
        if not (self.lcdc & 0x80):  # LCD apagado
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
                # Renderizar la línea actual
                self._render_scanline()
                # STAT interrupt para HBLANK
                if self._stat & 0x08:
                    self.mmu.io[0x0F] |= 0x02
        
        elif self.mode == self.MODE_HBLANK:
            if self.cycles >= self.HBLANK_CYCLES:
                self.cycles -= self.HBLANK_CYCLES
                self.ly += 1
                
                if self.ly == self.VBLANK_START:
                    self.mode = self.MODE_VBLANK
                    self.frame_ready = True
                    # VBlank interrupt
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
                
                if self.ly >= self.SCANLINES_TOTAL:
                    self.ly = 0
                    self.window_line = 0
                    self.mode = self.MODE_OAM
                    if self._stat & 0x20:
                        self.mmu.io[0x0F] |= 0x02
                
                self._check_lyc()
    
    def _check_lyc(self):
        """Verifica comparación LY == LYC"""
        if self.ly == self.lyc:
            self._stat |= 0x04
            if self._stat & 0x40:
                self.mmu.io[0x0F] |= 0x02
        else:
            self._stat &= ~0x04
    
    def _decode_palette(self, value):
        """Decodifica un byte de paleta a 4 colores"""
        return [
            (value >> 0) & 0x03,
            (value >> 2) & 0x03,
            (value >> 4) & 0x03,
            (value >> 6) & 0x03
        ]
    
    def _get_tile_data(self, tile_num, signed=False):
        """Obtiene los datos de un tile"""
        if self.lcdc & 0x10:  # 8000 addressing mode
            addr = 0x8000 + (tile_num * 16)
        else:  # 8800 addressing mode (signed)
            if tile_num > 127:
                tile_num -= 256
            addr = 0x9000 + (tile_num * 16)
        
        return addr
    
    def _render_scanline(self):
        """Renderiza una línea de scan"""
        if self.ly >= self.SCREEN_HEIGHT:
            return
        
        # Decodificar paletas
        self.bg_palette = self._decode_palette(self.bgp)
        self.obj_palette0 = self._decode_palette(self.obp0)
        self.obj_palette1 = self._decode_palette(self.obp1)
        
        # Renderizar fondo
        if self.lcdc & 0x01:
            self._render_background()
        else:
            for x in range(self.SCREEN_WIDTH):
                self.framebuffer[self.ly][x] = 0
        
        # Renderizar ventana
        if (self.lcdc & 0x20) and self.wy <= self.ly:
            self._render_window()
        
        # Renderizar sprites
        if self.lcdc & 0x02:
            self._render_sprites()
    
    def _render_background(self):
        """Renderiza la capa de fondo"""
        # Seleccionar tile map
        tile_map = 0x9C00 if (self.lcdc & 0x08) else 0x9800
        
        y = (self.ly + self.scy) & 0xFF
        tile_row = y // 8
        pixel_row = y % 8
        
        for screen_x in range(self.SCREEN_WIDTH):
            x = (screen_x + self.scx) & 0xFF
            tile_col = x // 8
            pixel_col = 7 - (x % 8)
            
            # Obtener número de tile
            map_addr = tile_map + (tile_row * 32) + tile_col
            tile_num = self.mmu.vram[map_addr - 0x8000]
            
            # Obtener datos del tile
            tile_addr = self._get_tile_data(tile_num)
            line_offset = pixel_row * 2
            
            low = self.mmu.vram[(tile_addr + line_offset) - 0x8000]
            high = self.mmu.vram[(tile_addr + line_offset + 1) - 0x8000]
            
            # Extraer color del pixel
            color_bit = ((high >> pixel_col) & 1) << 1
            color_bit |= (low >> pixel_col) & 1
            
            color = self.bg_palette[color_bit]
            self.framebuffer[self.ly][screen_x] = color
    
    def _render_window(self):
        """Renderiza la capa de ventana"""
        wx = self.wx - 7
        if wx >= self.SCREEN_WIDTH:
            return
        
        # Seleccionar tile map
        tile_map = 0x9C00 if (self.lcdc & 0x40) else 0x9800
        
        tile_row = self.window_line // 8
        pixel_row = self.window_line % 8
        
        rendered = False
        for screen_x in range(max(0, wx), self.SCREEN_WIDTH):
            win_x = screen_x - wx
            if win_x < 0:
                continue
            
            rendered = True
            tile_col = win_x // 8
            pixel_col = 7 - (win_x % 8)
            
            map_addr = tile_map + (tile_row * 32) + tile_col
            tile_num = self.mmu.vram[map_addr - 0x8000]
            
            tile_addr = self._get_tile_data(tile_num)
            line_offset = pixel_row * 2
            
            low = self.mmu.vram[(tile_addr + line_offset) - 0x8000]
            high = self.mmu.vram[(tile_addr + line_offset + 1) - 0x8000]
            
            color_bit = ((high >> pixel_col) & 1) << 1
            color_bit |= (low >> pixel_col) & 1
            
            color = self.bg_palette[color_bit]
            self.framebuffer[self.ly][screen_x] = color
        
        if rendered:
            self.window_line += 1
    
    def _render_sprites(self):
        """Renderiza los sprites (OBJ)"""
        sprite_height = 16 if (self.lcdc & 0x04) else 8
        sprites_on_line = []
        
        # Encontrar sprites en esta línea (máximo 10)
        for i in range(40):
            y = self.mmu.oam[i * 4] - 16
            x = self.mmu.oam[i * 4 + 1] - 8
            
            if y <= self.ly < y + sprite_height:
                sprites_on_line.append((x, i))
                if len(sprites_on_line) >= 10:
                    break
        
        # Ordenar por coordenada X (prioridad)
        sprites_on_line.sort(key=lambda s: s[0], reverse=True)
        
        for x, sprite_idx in sprites_on_line:
            self._render_sprite(sprite_idx, sprite_height)
    
    def _render_sprite(self, sprite_idx, height):
        """Renderiza un sprite individual"""
        y = self.mmu.oam[sprite_idx * 4] - 16
        x = self.mmu.oam[sprite_idx * 4 + 1] - 8
        tile_num = self.mmu.oam[sprite_idx * 4 + 2]
        attrs = self.mmu.oam[sprite_idx * 4 + 3]
        
        # Atributos
        priority = attrs & 0x80
        y_flip = attrs & 0x40
        x_flip = attrs & 0x20
        palette = self.obj_palette1 if (attrs & 0x10) else self.obj_palette0
        
        # Para sprites de 8x16, ignorar bit 0 del tile number
        if height == 16:
            tile_num &= 0xFE
        
        # Línea del sprite a renderizar
        sprite_line = self.ly - y
        if y_flip:
            sprite_line = height - 1 - sprite_line
        
        # Obtener datos del tile
        tile_addr = 0x8000 + (tile_num * 16) + (sprite_line * 2)
        low = self.mmu.vram[tile_addr - 0x8000]
        high = self.mmu.vram[tile_addr + 1 - 0x8000]
        
        for pixel in range(8):
            screen_x = x + pixel
            if 0 <= screen_x < self.SCREEN_WIDTH:
                bit = pixel if x_flip else (7 - pixel)
                
                color_bit = ((high >> bit) & 1) << 1
                color_bit |= (low >> bit) & 1
                
                # El color 0 es transparente para sprites
                if color_bit == 0:
                    continue
                
                # Si tiene prioridad BG y el fondo no es color 0, no dibujar
                if priority and self.framebuffer[self.ly][screen_x] != 0:
                    continue
                
                self.framebuffer[self.ly][screen_x] = palette[color_bit]