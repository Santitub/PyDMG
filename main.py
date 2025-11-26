#!/usr/bin/env python3
import sys
import os
import ctypes
import sdl2
import numpy as np

# Añadir el directorio actual al path para importar pydmg
sys.path.insert(0, os.path.dirname(__file__))

from pydmg import GameBoy

# Importar SaveState de forma segura
try:
    from pydmg.savestate import SaveState
    SAVESTATE_AVAILABLE = True
except ImportError:
    SAVESTATE_AVAILABLE = False

# Suprimir warnings de ALSA en Linux
try:
    ERROR_HANDLER_FUNC = ctypes.CFUNCTYPE(
        None, ctypes.c_char_p, ctypes.c_int,
        ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p
    )
    c_error_handler = ERROR_HANDLER_FUNC(lambda *args: None)
    asound = ctypes.cdll.LoadLibrary('libasound.so.2')
    asound.snd_lib_error_set_handler(c_error_handler)
except:
    pass

# Paletas de colores (tuplas RGB)
PALETTES = {
    'dmg': [(155, 188, 15), (139, 172, 15), (48, 98, 48), (15, 56, 15)],
    'gray': [(255, 255, 255), (192, 192, 192), (96, 96, 96), (0, 0, 0)],
    'green': [(224, 248, 208), (136, 192, 112), (52, 104, 86), (8, 24, 32)],
    'pocket': [(255, 255, 255), (170, 170, 170), (85, 85, 85), (0, 0, 0)],
}


class Emulator:
    """Emulador de Game Boy con SDL2"""
    
    SCREEN_WIDTH = 160
    SCREEN_HEIGHT = 144
    SCALE = 4
    
    def __init__(self):
        # Inicializar SDL2
        if sdl2.SDL_Init(sdl2.SDL_INIT_VIDEO | sdl2.SDL_INIT_AUDIO) < 0:
            raise RuntimeError(f"SDL2 init error: {sdl2.SDL_GetError()}")
        
        # Crear ventana
        self.window = sdl2.SDL_CreateWindow(
            b"Game Boy Emulator",
            sdl2.SDL_WINDOWPOS_CENTERED,
            sdl2.SDL_WINDOWPOS_CENTERED,
            self.SCREEN_WIDTH * self.SCALE,
            self.SCREEN_HEIGHT * self.SCALE,
            sdl2.SDL_WINDOW_SHOWN
        )
        if not self.window:
            raise RuntimeError(f"Window error: {sdl2.SDL_GetError()}")
        
        # Crear renderer
        self.renderer = sdl2.SDL_CreateRenderer(
            self.window, -1,
            sdl2.SDL_RENDERER_ACCELERATED | sdl2.SDL_RENDERER_PRESENTVSYNC
        )
        if not self.renderer:
            raise RuntimeError(f"Renderer error: {sdl2.SDL_GetError()}")
        
        # Crear textura para el framebuffer (RGB24)
        self.texture = sdl2.SDL_CreateTexture(
            self.renderer,
            sdl2.SDL_PIXELFORMAT_RGB24,
            sdl2.SDL_TEXTUREACCESS_STREAMING,
            self.SCREEN_WIDTH,
            self.SCREEN_HEIGHT
        )
        
        # Buffer de píxeles (RGB, 3 bytes por pixel)
        self.pixels = np.zeros((self.SCREEN_HEIGHT, self.SCREEN_WIDTH, 3), dtype=np.uint8)
        
        # Game Boy
        self.gameboy = None
        self.rom_path = None
        
        # Paleta actual
        self.palette_names = list(PALETTES.keys())
        self.palette_idx = 0
        self.palette = PALETTES[self.palette_names[0]]
        
        # Mapeo de teclas
        self.keymap = {
            sdl2.SDLK_RIGHT: 'right',
            sdl2.SDLK_LEFT: 'left',
            sdl2.SDLK_UP: 'up',
            sdl2.SDLK_DOWN: 'down',
            sdl2.SDLK_z: 'a',
            sdl2.SDLK_x: 'b',
            sdl2.SDLK_RETURN: 'start',
            sdl2.SDLK_RSHIFT: 'select',
            sdl2.SDLK_LSHIFT: 'select',
            sdl2.SDLK_a: 'a',
            sdl2.SDLK_s: 'b',
        }
        
        # Estado
        self.running = False
        self.paused = False
        self.turbo = False
        self.debug = False
        
        # Save states
        self.save_slot = 0
        
        # FPS
        self.fps_timer = sdl2.SDL_GetTicks()
        self.frame_count = 0
        self.fps = 0.0
    
    def load_rom(self, path):
        """Carga una ROM"""
        if not os.path.exists(path):
            print(f"❌ ROM no encontrada: {path}")
            return False
        
        self.rom_path = path
        self.gameboy = GameBoy()
        self.gameboy.load_rom(path)
        self._update_title()
        
        return True
    
    def _update_title(self):
        """Actualiza el título de la ventana"""
        if self.rom_path:
            rom_name = os.path.basename(self.rom_path)
            title = f"Game Boy - {rom_name} [Slot {self.save_slot}]"
            if self.paused:
                title += " (PAUSA)"
        else:
            title = "Game Boy Emulator"
        
        sdl2.SDL_SetWindowTitle(self.window, title.encode('utf-8'))
    
    def _save_state(self):
        """Guarda el estado actual"""
        if not SAVESTATE_AVAILABLE:
            print("⚠ Save states no disponibles")
            return
        
        if SaveState.save(self.gameboy, self.save_slot):
            print(f"💾 Estado guardado en slot {self.save_slot}")
    
    def _load_state(self):
        """Carga un estado guardado"""
        if not SAVESTATE_AVAILABLE:
            print("⚠ Save states no disponibles")
            return
        
        if SaveState.load(self.gameboy, self.save_slot):
            print(f"📂 Estado cargado desde slot {self.save_slot}")
    
    def handle_events(self):
        """Procesa eventos SDL2"""
        event = sdl2.SDL_Event()
        
        while sdl2.SDL_PollEvent(ctypes.byref(event)):
            if event.type == sdl2.SDL_QUIT:
                self.running = False
            
            elif event.type == sdl2.SDL_KEYDOWN:
                key = event.key.keysym.sym
                
                # Controles del emulador
                if key == sdl2.SDLK_ESCAPE:
                    self.running = False
                
                elif key == sdl2.SDLK_p:
                    self.paused = not self.paused
                    self._update_title()
                    print("⏸ PAUSA" if self.paused else "▶ PLAY")
                
                elif key == sdl2.SDLK_c:
                    self.palette_idx = (self.palette_idx + 1) % len(self.palette_names)
                    name = self.palette_names[self.palette_idx]
                    self.palette = PALETTES[name]
                    print(f"🎨 Paleta: {name}")
                
                elif key == sdl2.SDLK_m:
                    self.gameboy.toggle_audio()
                
                elif key == sdl2.SDLK_d:
                    self.debug = not self.debug
                    print(f"🔧 Debug: {'ON' if self.debug else 'OFF'}")
                
                elif key == sdl2.SDLK_r:
                    print("🔄 Reset")
                    self.gameboy = GameBoy()
                    self.gameboy.load_rom(self.rom_path)
                
                elif key == sdl2.SDLK_SPACE:
                    self.turbo = True
                
                # Save States
                elif key == sdl2.SDLK_F5:
                    self._save_state()
                
                elif key == sdl2.SDLK_F7:
                    self._load_state()
                
                elif key == sdl2.SDLK_F6:
                    self.save_slot = (self.save_slot - 1) % 10
                    self._update_title()
                    print(f"📍 Slot {self.save_slot}")
                
                elif key == sdl2.SDLK_F8:
                    self.save_slot = (self.save_slot + 1) % 10
                    self._update_title()
                    print(f"📍 Slot {self.save_slot}")
                
                elif sdl2.SDLK_0 <= key <= sdl2.SDLK_9:
                    self.save_slot = key - sdl2.SDLK_0
                    self._update_title()
                    print(f"📍 Slot {self.save_slot}")
                
                elif key == sdl2.SDLK_F1:
                    self._print_help()
                
                # Controles del juego
                elif key in self.keymap:
                    self.gameboy.press_button(self.keymap[key])
            
            elif event.type == sdl2.SDL_KEYUP:
                key = event.key.keysym.sym
                
                if key == sdl2.SDLK_SPACE:
                    self.turbo = False
                elif key in self.keymap:
                    self.gameboy.release_button(self.keymap[key])
    
    def _print_help(self):
        """Muestra la ayuda"""
        print("""
╔═══════════════════════════════════════════════╗
║                    AYUDA                      ║
╠═══════════════════════════════════════════════╣
║  JUEGO:                                       ║
║    Flechas      = D-Pad                       ║
║    Z / A        = Botón A                     ║
║    X / S        = Botón B                     ║
║    Enter        = Start                       ║
║    Shift        = Select                      ║
║                                               ║
║  EMULADOR:                                    ║
║    P            = Pausar                      ║
║    M            = Mute/Unmute                 ║
║    C            = Cambiar paleta              ║
║    R            = Reset                       ║
║    D            = Debug mode                  ║
║    Space        = Turbo (mantener)            ║
║    ESC          = Salir                       ║
║                                               ║
║  SAVE STATES:                                 ║
║    F5           = Guardar estado              ║
║    F7           = Cargar estado               ║
║    F6 / F8      = Slot anterior/siguiente     ║
║    0-9          = Seleccionar slot            ║
╚═══════════════════════════════════════════════╝
""")
    
    def render(self, framebuffer):
        """Renderiza el framebuffer a la pantalla"""
        # Convertir framebuffer (lista de listas) a pixels RGB
        # Esto funciona con lista de listas O numpy arrays
        for y in range(self.SCREEN_HEIGHT):
            for x in range(self.SCREEN_WIDTH):
                # Obtener índice de color (0-3)
                color_idx = framebuffer[y][x]
                # Obtener color RGB de la paleta
                r, g, b = self.palette[color_idx]
                # Escribir al buffer de píxeles
                self.pixels[y, x, 0] = r
                self.pixels[y, x, 1] = g
                self.pixels[y, x, 2] = b
        
        # Actualizar textura
        sdl2.SDL_UpdateTexture(
            self.texture,
            None,
            self.pixels.ctypes.data_as(ctypes.c_void_p),
            self.SCREEN_WIDTH * 3  # pitch = width * bytes_per_pixel
        )
        
        # Renderizar
        sdl2.SDL_RenderClear(self.renderer)
        sdl2.SDL_RenderCopy(self.renderer, self.texture, None, None)
        sdl2.SDL_RenderPresent(self.renderer)
    
    def _update_fps(self):
        """Actualiza el contador de FPS"""
        self.frame_count += 1
        current = sdl2.SDL_GetTicks()
        
        if current - self.fps_timer >= 1000:
            self.fps = self.frame_count * 1000.0 / (current - self.fps_timer)
            self.frame_count = 0
            self.fps_timer = current
            
            if self.debug:
                print(f"FPS: {self.fps:.1f}")
    
    def run(self):
        """Loop principal"""
        if not self.gameboy:
            print("❌ No hay ROM cargada")
            return
        
        self.running = True
        
        print("\n🎮 Emulación iniciada (F1 = Ayuda)")
        print(f"   Slot: {self.save_slot} | F5=Guardar | F7=Cargar\n")
        
        target_frame_time = 1000 // 60
        
        try:
            while self.running:
                frame_start = sdl2.SDL_GetTicks()
                
                self.handle_events()
                
                if not self.paused:
                    # Ejecutar frames
                    frames = 4 if self.turbo else 1
                    for _ in range(frames):
                        fb = self.gameboy.run_frame()
                    
                    self.render(fb)
                    self._update_fps()
                
                # Control de timing (solo si no está en turbo)
                if not self.turbo:
                    elapsed = sdl2.SDL_GetTicks() - frame_start
                    if elapsed < target_frame_time:
                        sdl2.SDL_Delay(target_frame_time - elapsed)
        
        except KeyboardInterrupt:
            print("\n⏹ Interrumpido")
        
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Limpia recursos"""
        if self.gameboy:
            self.gameboy.close()
        
        if self.texture:
            sdl2.SDL_DestroyTexture(self.texture)
        if self.renderer:
            sdl2.SDL_DestroyRenderer(self.renderer)
        if self.window:
            sdl2.SDL_DestroyWindow(self.window)
        
        sdl2.SDL_Quit()
        print("👋 Emulador cerrado")


def main():
    print("╔" + "═" * 48 + "╗")
    print("║          GAME BOY EMULATOR - PySDL2           ║")
    print("╚" + "═" * 48 + "╝")
    
    if len(sys.argv) < 2:
        print("\nUso: python main.py <rom.gb>")
        sys.exit(1)
    
    emu = Emulator()
    if emu.load_rom(sys.argv[1]):
        emu.run()


if __name__ == "__main__":
    main()