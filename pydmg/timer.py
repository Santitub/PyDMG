"""
Timer
"""

class Timer:
    __slots__ = ('mmu', '_div', 'tima', 'tma', 'tac', 'tima_cycles')
    
    FREQS = [1024, 16, 64, 256]
    
    def __init__(self, mmu):
        self.mmu = mmu
        self._div = 0
        self.tima = 0
        self.tma = 0
        self.tac = 0
        self.tima_cycles = 0
    
    @property
    def div(self):
        return (self._div >> 8) & 0xFF
    
    @div.setter
    def div(self, value):
        self._div = 0
    
    def step(self, cycles):
        self._div = (self._div + cycles) & 0xFFFF
        
        if self.tac & 0x04:
            self.tima_cycles += cycles
            freq = self.FREQS[self.tac & 0x03]
            
            while self.tima_cycles >= freq:
                self.tima_cycles -= freq
                self.tima = (self.tima + 1) & 0xFF
                
                if self.tima == 0:
                    self.tima = self.tma
                    self.mmu.io[0x0F] |= 0x04