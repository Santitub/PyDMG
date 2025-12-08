# cython: language_level=3, boundscheck=False, wraparound=False, cdivision=True
"""
Timer - Cython optimizado
"""

cimport cython
from libc.stdint cimport uint8_t, uint16_t

cdef int[4] FREQS = [1024, 16, 64, 256]

cdef class Timer:
    cdef object mmu
    cdef public uint16_t _div
    cdef public uint8_t tima, tma, tac
    cdef public int tima_cycles
    
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
    
    cpdef void step(self, int cycles):
        cdef int freq
        
        self._div = (self._div + cycles) & 0xFFFF
        
        if self.tac & 0x04:
            self.tima_cycles += cycles
            freq = FREQS[self.tac & 0x03]
            
            while self.tima_cycles >= freq:
                self.tima_cycles -= freq
                self.tima = (self.tima + 1) & 0xFF
                
                if self.tima == 0:
                    self.tima = self.tma
                    self.mmu.io[0x0F] |= 0x04