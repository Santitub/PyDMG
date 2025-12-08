# cython: language_level=3, boundscheck=False, wraparound=False, cdivision=True
"""
GameBoy Core - Con ticking preciso
"""

cimport cython

from pydmg.cpu import CPU
from pydmg.mmu import MMU
from pydmg.ppu import PPU
from pydmg.timer import Timer
from pydmg.joypad import Joypad

try:
    from pydmg.apu import APU
    APU_AVAILABLE = True
except:
    APU_AVAILABLE = False


cdef class GameBoy:
    cdef public object mmu
    cdef public object cpu
    cdef public object ppu
    cdef public object timer
    cdef public object joypad
    cdef public object apu
    cdef public bint audio_enabled
    
    def __init__(self):
        self.mmu = MMU()
        self.cpu = CPU(self.mmu)
        self.ppu = PPU(self.mmu)
        self.timer = Timer(self.mmu)
        self.joypad = Joypad(self.mmu)
        
        # Conectar componentes al MMU
        self.mmu.ppu = self.ppu
        self.mmu.timer = self.timer
        self.mmu.joypad = self.joypad
        
        # Conectar PPU y Timer al CPU para ticking preciso
        self.cpu.set_components(self.ppu, self.timer)
        
        self.apu = None
        self.audio_enabled = True
        
        if APU_AVAILABLE:
            try:
                self.apu = APU(self.mmu)
                self.mmu.apu = self.apu
            except Exception as e:
                print(f"⚠ APU: {e}")
    
    def load_rom(self, path):
        with open(path, 'rb') as f:
            data = f.read()
        self.mmu.load_rom(data, path)
    
    cpdef object run_frame(self):
        """Ejecuta hasta completar un frame"""
        cdef int max_steps = 70224 * 2  # Límite de seguridad
        cdef int steps = 0
        
        cpu_step = self.cpu.step
        ppu = self.ppu
        
        ppu.frame_ready = False
        
        # El CPU ahora hace tick interno, así que solo llamamos step
        while not ppu.frame_ready and steps < max_steps:
            cpu_step()
            steps += 1
        
        if self.apu is not None and self.audio_enabled:
            self.apu.end_frame()
        
        return ppu.framebuffer
    
    def press_button(self, button):
        self.joypad.press(button)
    
    def release_button(self, button):
        self.joypad.release(button)
    
    def toggle_audio(self):
        self.audio_enabled = not self.audio_enabled
        print(f"🔊 Audio: {'ON' if self.audio_enabled else 'OFF'}")
    
    def save(self):
        self.mmu.save_ram()
    
    def close(self):
        self.save()
        if self.apu is not None:
            self.apu.close()