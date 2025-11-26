# timer.pyx
# cython: language_level=3
# cython: boundscheck=False
# cython: wraparound=False
# cython: cdivision=True
# cython: initializedcheck=False

cimport cython
from libc.stdint cimport uint8_t, uint16_t

cdef class Timer:
    """Timer del Game Boy - Versión Cython optimizada"""
    
    # Frecuencias de timer (en ciclos de CPU)
    cdef int[4] FREQS
    
    # Referencia al MMU
    cdef object mmu
    
    # Registros internos
    cdef public uint16_t _div      # DIV interno (16-bit, solo se expone byte alto)
    cdef public uint8_t tima       # Timer counter
    cdef public uint8_t tma        # Timer modulo
    cdef public uint8_t tac        # Timer control
    cdef public int tima_cycles    # Contador de ciclos para TIMA
    
    def __init__(self, mmu):
        self.mmu = mmu
        
        # Frecuencias: 4096Hz, 262144Hz, 65536Hz, 16384Hz
        # En ciclos de CPU (4.194304 MHz)
        self.FREQS[0] = 1024  # 4096 Hz
        self.FREQS[1] = 16    # 262144 Hz
        self.FREQS[2] = 64    # 65536 Hz
        self.FREQS[3] = 256   # 16384 Hz
        
        self._div = 0
        self.tima = 0
        self.tma = 0
        self.tac = 0
        self.tima_cycles = 0
    
    @property
    def div(self):
        """Lee el registro DIV (byte alto del contador interno)"""
        return (self._div >> 8) & 0xFF
    
    @div.setter
    def div(self, value):
        """Escribir cualquier valor a DIV lo resetea a 0"""
        self._div = 0
    
    cpdef void step(self, int cycles):
        """
        Avanza el timer por el número de ciclos especificado.
        Llamado desde CPU._tick()
        """
        cdef int freq
        
        # Actualizar DIV (siempre cuenta, independiente de TAC)
        self._div = (self._div + cycles) & 0xFFFF
        
        # TIMA solo cuenta si está habilitado (bit 2 de TAC)
        if self.tac & 0x04:
            self.tima_cycles += cycles
            
            # Obtener frecuencia según bits 0-1 de TAC
            freq = self.FREQS[self.tac & 0x03]
            
            # Incrementar TIMA cuando se alcanza la frecuencia
            while self.tima_cycles >= freq:
                self.tima_cycles -= freq
                self.tima = (self.tima + 1) & 0xFF
                
                # Overflow: recargar con TMA y solicitar interrupción
                if self.tima == 0:
                    self.tima = self.tma
                    self.mmu.io[0x0F] |= 0x04  # Timer interrupt flag
    
    cpdef void reset(self):
        """Resetea el timer a su estado inicial"""
        self._div = 0
        self.tima = 0
        self.tma = 0
        self.tac = 0
        self.tima_cycles = 0