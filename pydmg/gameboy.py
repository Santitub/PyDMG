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


class GameBoy:
    __slots__ = ('mmu', 'cpu', 'ppu', 'timer', 'joypad', 'apu', 'audio_enabled')
    
    CYCLES_PER_FRAME = 70224
    
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
    
    def step(self):
        # NOTA: CPU.step() ya llama internamente a timer.step() y ppu.step()
        # a través de _tick(), así que NO debemos llamarlos de nuevo aquí
        cycles = self.cpu.step()
        return cycles
    
    def run_frame(self):
        self.ppu.frame_ready = False
        cycles = 0
        
        while not self.ppu.frame_ready and cycles < self.CYCLES_PER_FRAME * 2:
            cycles += self.step()
        
        if self.apu and self.audio_enabled:
            self.apu.end_frame()
        
        return self.ppu.framebuffer
    
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
        if self.apu:
            self.apu.close()