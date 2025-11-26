# apu.pyx
# cython: language_level=3
# cython: boundscheck=False
# cython: wraparound=False
# cython: cdivision=True
# cython: initializedcheck=False

cimport cython
from libc.stdint cimport uint8_t, uint16_t, int16_t
from libc.math cimport floor
import numpy as np
cimport numpy as np
import ctypes

np.import_array()

# Intentar importar SDL2
try:
    import sdl2
    SDL2_AVAILABLE = True
except ImportError:
    SDL2_AVAILABLE = False

# Configuración
DEF SAMPLE_RATE = 22050
DEF BUFFER_SAMPLES = 512
DEF CHANNELS = 2


cdef class APU:
    """APU optimizado con Cython"""
    
    # Constantes
    cdef int CPU_FREQ
    cdef int CYCLES_PER_FRAME
    
    # Referencias
    cdef object mmu
    cdef object device_id  # SDL device ID
    
    # Estado general
    cdef public bint enabled
    cdef public bint master_enable
    
    # Volumen master
    cdef public int vol_left
    cdef public int vol_right
    
    # Panning (arrays de C)
    cdef bint[4] pan_left
    cdef bint[4] pan_right
    
    # Channel 1: Pulse + Sweep
    cdef public bint ch1_enabled
    cdef public bint ch1_dac
    cdef public int ch1_duty
    cdef public int ch1_freq
    cdef public int ch1_vol
    cdef public int ch1_vol_init
    cdef public bint ch1_env_add
    cdef public int ch1_env_period
    cdef public int ch1_length
    cdef public bint ch1_length_en
    cdef public int ch1_sweep_period
    cdef public bint ch1_sweep_neg
    cdef public int ch1_sweep_shift
    cdef double ch1_phase
    
    # Channel 2: Pulse
    cdef public bint ch2_enabled
    cdef public bint ch2_dac
    cdef public int ch2_duty
    cdef public int ch2_freq
    cdef public int ch2_vol
    cdef public int ch2_vol_init
    cdef public bint ch2_env_add
    cdef public int ch2_env_period
    cdef public int ch2_length
    cdef public bint ch2_length_en
    cdef double ch2_phase
    
    # Channel 3: Wave
    cdef public bint ch3_enabled
    cdef public bint ch3_dac
    cdef public int ch3_freq
    cdef public int ch3_vol_code
    cdef public int ch3_length
    cdef public bint ch3_length_en
    cdef uint8_t[32] ch3_wave
    cdef double ch3_phase
    
    # Channel 4: Noise
    cdef public bint ch4_enabled
    cdef public bint ch4_dac
    cdef public int ch4_vol
    cdef public int ch4_vol_init
    cdef public bint ch4_env_add
    cdef public int ch4_env_period
    cdef public int ch4_length
    cdef public bint ch4_length_en
    cdef public int ch4_clock_shift
    cdef public bint ch4_width
    cdef public int ch4_divisor
    cdef public int ch4_lfsr
    cdef double ch4_timer
    
    # Frame sequencer
    cdef int frame_seq
    
    # Duty table (4x8)
    cdef float[4][8] duty_table
    
    # Audio buffer
    cdef float[:] audio_buffer
    cdef object audio_buffer_np
    
    def __init__(self, mmu):
        self.mmu = mmu
        self.CPU_FREQ = 4194304
        self.CYCLES_PER_FRAME = 70224
        
        self.enabled = True
        self.master_enable = True
        self.device_id = 0
        
        # Volumen
        self.vol_left = 7
        self.vol_right = 7
        
        # Panning
        cdef int i
        for i in range(4):
            self.pan_left[i] = True
            self.pan_right[i] = True
        
        # Channel 1
        self.ch1_enabled = False
        self.ch1_dac = False
        self.ch1_duty = 2
        self.ch1_freq = 0
        self.ch1_vol = 0
        self.ch1_vol_init = 0
        self.ch1_env_add = False
        self.ch1_env_period = 0
        self.ch1_length = 0
        self.ch1_length_en = False
        self.ch1_sweep_period = 0
        self.ch1_sweep_neg = False
        self.ch1_sweep_shift = 0
        self.ch1_phase = 0.0
        
        # Channel 2
        self.ch2_enabled = False
        self.ch2_dac = False
        self.ch2_duty = 2
        self.ch2_freq = 0
        self.ch2_vol = 0
        self.ch2_vol_init = 0
        self.ch2_env_add = False
        self.ch2_env_period = 0
        self.ch2_length = 0
        self.ch2_length_en = False
        self.ch2_phase = 0.0
        
        # Channel 3
        self.ch3_enabled = False
        self.ch3_dac = False
        self.ch3_freq = 0
        self.ch3_vol_code = 0
        self.ch3_length = 0
        self.ch3_length_en = False
        for i in range(32):
            self.ch3_wave[i] = 0
        self.ch3_phase = 0.0
        
        # Channel 4
        self.ch4_enabled = False
        self.ch4_dac = False
        self.ch4_vol = 0
        self.ch4_vol_init = 0
        self.ch4_env_add = False
        self.ch4_env_period = 0
        self.ch4_length = 0
        self.ch4_length_en = False
        self.ch4_clock_shift = 0
        self.ch4_width = False
        self.ch4_divisor = 0
        self.ch4_lfsr = 0x7FFF
        self.ch4_timer = 0.0
        
        # Frame sequencer
        self.frame_seq = 0
        
        # Duty table initialization
        # Duty 0: 12.5% - _______X
        self.duty_table[0][0] = 0.0
        self.duty_table[0][1] = 0.0
        self.duty_table[0][2] = 0.0
        self.duty_table[0][3] = 0.0
        self.duty_table[0][4] = 0.0
        self.duty_table[0][5] = 0.0
        self.duty_table[0][6] = 0.0
        self.duty_table[0][7] = 1.0
        
        # Duty 1: 25% - X______X
        self.duty_table[1][0] = 1.0
        self.duty_table[1][1] = 0.0
        self.duty_table[1][2] = 0.0
        self.duty_table[1][3] = 0.0
        self.duty_table[1][4] = 0.0
        self.duty_table[1][5] = 0.0
        self.duty_table[1][6] = 0.0
        self.duty_table[1][7] = 1.0
        
        # Duty 2: 50% - X____XXX
        self.duty_table[2][0] = 1.0
        self.duty_table[2][1] = 0.0
        self.duty_table[2][2] = 0.0
        self.duty_table[2][3] = 0.0
        self.duty_table[2][4] = 0.0
        self.duty_table[2][5] = 1.0
        self.duty_table[2][6] = 1.0
        self.duty_table[2][7] = 1.0
        
        # Duty 3: 75% - _XXXXXX_
        self.duty_table[3][0] = 0.0
        self.duty_table[3][1] = 1.0
        self.duty_table[3][2] = 1.0
        self.duty_table[3][3] = 1.0
        self.duty_table[3][4] = 1.0
        self.duty_table[3][5] = 1.0
        self.duty_table[3][6] = 1.0
        self.duty_table[3][7] = 0.0
        
        # Audio buffer
        self.audio_buffer_np = np.zeros(BUFFER_SAMPLES * CHANNELS, dtype=np.float32)
        self.audio_buffer = self.audio_buffer_np
        
        # Inicializar SDL Audio
        self._init_audio()
    
    def _init_audio(self):
        """Inicializa SDL2 Audio"""
        if not SDL2_AVAILABLE:
            return
        
        if sdl2.SDL_WasInit(sdl2.SDL_INIT_AUDIO) == 0:
            if sdl2.SDL_InitSubSystem(sdl2.SDL_INIT_AUDIO) < 0:
                return
        
        spec = sdl2.SDL_AudioSpec(
            freq=SAMPLE_RATE,
            aformat=sdl2.AUDIO_F32SYS,
            channels=CHANNELS,
            samples=BUFFER_SAMPLES,
            callback=sdl2.SDL_AudioCallback(),
            userdata=None
        )
        
        obtained = sdl2.SDL_AudioSpec(
            freq=0, aformat=0, channels=0, samples=0,
            callback=sdl2.SDL_AudioCallback(), userdata=None
        )
        
        self.device_id = sdl2.SDL_OpenAudioDevice(
            None, 0, ctypes.byref(spec), ctypes.byref(obtained), 0
        )
        
        if self.device_id > 0:
            sdl2.SDL_PauseAudioDevice(self.device_id, 0)
            print(f"🔊 Audio: {SAMPLE_RATE}Hz")
        else:
            print("⚠ Audio no disponible")
    
    cpdef void end_frame(self):
        """Genera y envía audio al final de cada frame"""
        if self.device_id == 0 or not self.enabled:
            return
        
        # Verificar cola
        cdef int queued = sdl2.SDL_GetQueuedAudioSize(self.device_id)
        cdef int max_queued = BUFFER_SAMPLES * CHANNELS * 4 * 4
        
        if queued > max_queued:
            return
        
        # Generar audio
        self._generate_frame_audio()
        
        # Enviar a SDL
        sdl2.SDL_QueueAudio(
            self.device_id,
            self.audio_buffer_np.ctypes.data_as(ctypes.c_void_p),
            self.audio_buffer_np.nbytes
        )
    
    cdef void _generate_frame_audio(self):
        """Genera audio para un frame"""
        cdef int i, j
        cdef float left, right, s
        cdef float[:] buf = self.audio_buffer
        
        for i in range(BUFFER_SAMPLES):
            left = 0.0
            right = 0.0
            
            # Channel 1
            if self.ch1_enabled and self.ch1_dac and self.ch1_freq > 0:
                s = self._pulse_sample_ch1()
                if self.pan_left[0]:
                    left += s
                if self.pan_right[0]:
                    right += s
            
            # Channel 2
            if self.ch2_enabled and self.ch2_dac and self.ch2_freq > 0:
                s = self._pulse_sample_ch2()
                if self.pan_left[1]:
                    left += s
                if self.pan_right[1]:
                    right += s
            
            # Channel 3
            if self.ch3_enabled and self.ch3_dac and self.ch3_freq > 0:
                s = self._wave_sample()
                if self.pan_left[2]:
                    left += s
                if self.pan_right[2]:
                    right += s
            
            # Channel 4
            if self.ch4_enabled and self.ch4_dac:
                s = self._noise_sample()
                if self.pan_left[3]:
                    left += s
                if self.pan_right[3]:
                    right += s
            
            # Normalizar y aplicar volumen master
            left = (left / 60.0) * ((self.vol_left + 1) / 8.0)
            right = (right / 60.0) * ((self.vol_right + 1) / 8.0)
            
            # Clamp
            if left < -1.0:
                left = -1.0
            elif left > 1.0:
                left = 1.0
            
            if right < -1.0:
                right = -1.0
            elif right > 1.0:
                right = 1.0
            
            buf[i * 2] = left
            buf[i * 2 + 1] = right
        
        # Tick frame sequencer
        for j in range(8):
            self._tick_frame_seq()
    
    cdef inline float _pulse_sample_ch1(self):
        """Sample de Channel 1"""
        cdef double real_freq, phase
        cdef int pos
        
        if self.ch1_freq == 0:
            return 0.0
        
        real_freq = 131072.0 / (2048 - self.ch1_freq)
        
        self.ch1_phase += real_freq / SAMPLE_RATE
        if self.ch1_phase >= 1.0:
            self.ch1_phase -= 1.0
        
        pos = <int>(self.ch1_phase * 8) & 7
        return self.duty_table[self.ch1_duty][pos] * self.ch1_vol
    
    cdef inline float _pulse_sample_ch2(self):
        """Sample de Channel 2"""
        cdef double real_freq
        cdef int pos
        
        if self.ch2_freq == 0:
            return 0.0
        
        real_freq = 131072.0 / (2048 - self.ch2_freq)
        
        self.ch2_phase += real_freq / SAMPLE_RATE
        if self.ch2_phase >= 1.0:
            self.ch2_phase -= 1.0
        
        pos = <int>(self.ch2_phase * 8) & 7
        return self.duty_table[self.ch2_duty][pos] * self.ch2_vol
    
    cdef inline float _wave_sample(self):
        """Sample de Channel 3"""
        cdef double real_freq
        cdef int pos, shift
        cdef uint8_t sample
        
        if self.ch3_vol_code == 0 or self.ch3_freq == 0:
            return 0.0
        
        real_freq = 65536.0 / (2048 - self.ch3_freq)
        
        self.ch3_phase += real_freq / SAMPLE_RATE
        if self.ch3_phase >= 1.0:
            self.ch3_phase -= 1.0
        
        pos = <int>(self.ch3_phase * 32) & 31
        sample = self.ch3_wave[pos]
        
        # Shift según volumen: 0=mute, 1=100%, 2=50%, 3=25%
        if self.ch3_vol_code == 1:
            shift = 0
        elif self.ch3_vol_code == 2:
            shift = 1
        elif self.ch3_vol_code == 3:
            shift = 2
        else:
            shift = 4  # mute
        
        return <float>(sample >> shift)
    
    cdef inline float _noise_sample(self):
        """Sample de Channel 4"""
        cdef int divisors[8]
        cdef int div, xor_bit
        cdef double freq
        
        if self.ch4_vol == 0:
            return 0.0
        
        # Divisor table
        divisors[0] = 8
        divisors[1] = 16
        divisors[2] = 32
        divisors[3] = 48
        divisors[4] = 64
        divisors[5] = 80
        divisors[6] = 96
        divisors[7] = 112
        
        div = divisors[self.ch4_divisor]
        
        if self.ch4_clock_shift < 14:
            freq = 262144.0 / (div << self.ch4_clock_shift)
        else:
            freq = 1.0
        
        self.ch4_timer += freq / SAMPLE_RATE
        
        while self.ch4_timer >= 1.0:
            self.ch4_timer -= 1.0
            xor_bit = (self.ch4_lfsr & 1) ^ ((self.ch4_lfsr >> 1) & 1)
            self.ch4_lfsr = (self.ch4_lfsr >> 1) | (xor_bit << 14)
            if self.ch4_width:
                self.ch4_lfsr = (self.ch4_lfsr & ~0x40) | (xor_bit << 6)
        
        if self.ch4_lfsr & 1:
            return 0.0
        else:
            return <float>self.ch4_vol
    
    cdef inline void _tick_frame_seq(self):
        """Frame sequencer tick"""
        cdef int step = self.frame_seq
        
        if step % 2 == 0:
            self._clock_lengths()
        
        if step == 7:
            self._clock_envelopes()
        
        self.frame_seq = (step + 1) & 7
    
    cdef inline void _clock_lengths(self):
        """Clock length counters"""
        if self.ch1_length_en and self.ch1_length > 0:
            self.ch1_length -= 1
            if self.ch1_length == 0:
                self.ch1_enabled = False
        
        if self.ch2_length_en and self.ch2_length > 0:
            self.ch2_length -= 1
            if self.ch2_length == 0:
                self.ch2_enabled = False
        
        if self.ch3_length_en and self.ch3_length > 0:
            self.ch3_length -= 1
            if self.ch3_length == 0:
                self.ch3_enabled = False
        
        if self.ch4_length_en and self.ch4_length > 0:
            self.ch4_length -= 1
            if self.ch4_length == 0:
                self.ch4_enabled = False
    
    cdef inline void _clock_envelopes(self):
        """Clock envelope units"""
        if self.ch1_env_period > 0:
            if self.ch1_env_add and self.ch1_vol < 15:
                self.ch1_vol += 1
            elif not self.ch1_env_add and self.ch1_vol > 0:
                self.ch1_vol -= 1
        
        if self.ch2_env_period > 0:
            if self.ch2_env_add and self.ch2_vol < 15:
                self.ch2_vol += 1
            elif not self.ch2_env_add and self.ch2_vol > 0:
                self.ch2_vol -= 1
        
        if self.ch4_env_period > 0:
            if self.ch4_env_add and self.ch4_vol < 15:
                self.ch4_vol += 1
            elif not self.ch4_env_add and self.ch4_vol > 0:
                self.ch4_vol -= 1
    
    cpdef void step(self, int cycles):
        """No-op: audio se genera en end_frame()"""
        pass
    
    # =========================================================================
    # LECTURA DE REGISTROS
    # =========================================================================
    
    cpdef uint8_t read(self, int addr):
        """Lee registro de audio"""
        addr &= 0x3F
        
        if addr == 0x10:
            return 0x80 | (self.ch1_sweep_period << 4) | (self.ch1_sweep_neg << 3) | self.ch1_sweep_shift
        elif addr == 0x11:
            return (self.ch1_duty << 6) | 0x3F
        elif addr == 0x12:
            return (self.ch1_vol_init << 4) | (self.ch1_env_add << 3) | self.ch1_env_period
        elif addr == 0x14:
            return 0xBF | (self.ch1_length_en << 6)
        elif addr == 0x16:
            return (self.ch2_duty << 6) | 0x3F
        elif addr == 0x17:
            return (self.ch2_vol_init << 4) | (self.ch2_env_add << 3) | self.ch2_env_period
        elif addr == 0x19:
            return 0xBF | (self.ch2_length_en << 6)
        elif addr == 0x1A:
            return 0x7F | (self.ch3_dac << 7)
        elif addr == 0x1C:
            return 0x9F | (self.ch3_vol_code << 5)
        elif addr == 0x1E:
            return 0xBF | (self.ch3_length_en << 6)
        elif addr == 0x21:
            return (self.ch4_vol_init << 4) | (self.ch4_env_add << 3) | self.ch4_env_period
        elif addr == 0x22:
            return (self.ch4_clock_shift << 4) | (self.ch4_width << 3) | self.ch4_divisor
        elif addr == 0x23:
            return 0xBF | (self.ch4_length_en << 6)
        elif addr == 0x24:
            return (self.vol_left << 4) | self.vol_right
        elif addr == 0x25:
            return ((self.pan_left[3] << 7) | (self.pan_left[2] << 6) |
                    (self.pan_left[1] << 5) | (self.pan_left[0] << 4) |
                    (self.pan_right[3] << 3) | (self.pan_right[2] << 2) |
                    (self.pan_right[1] << 1) | self.pan_right[0])
        elif addr == 0x26:
            return (0x70 | (self.master_enable << 7) |
                    (self.ch4_enabled << 3) | (self.ch3_enabled << 2) |
                    (self.ch2_enabled << 1) | self.ch1_enabled)
        elif 0x30 <= addr <= 0x3F:
            return (self.ch3_wave[(addr - 0x30) * 2] << 4) | self.ch3_wave[(addr - 0x30) * 2 + 1]
        
        return 0xFF
    
    # =========================================================================
    # ESCRITURA DE REGISTROS
    # =========================================================================
    
    cpdef void write(self, int addr, uint8_t value):
        """Escribe registro de audio"""
        cdef int idx
        
        addr &= 0x3F
        
        if not self.master_enable and addr != 0x26 and not (0x30 <= addr <= 0x3F):
            return
        
        # Channel 1
        if addr == 0x10:
            self.ch1_sweep_period = (value >> 4) & 7
            self.ch1_sweep_neg = (value & 8) != 0
            self.ch1_sweep_shift = value & 7
        
        elif addr == 0x11:
            self.ch1_duty = (value >> 6) & 3
            self.ch1_length = 64 - (value & 0x3F)
        
        elif addr == 0x12:
            self.ch1_vol_init = (value >> 4) & 0xF
            self.ch1_env_add = (value & 8) != 0
            self.ch1_env_period = value & 7
            self.ch1_dac = (value & 0xF8) != 0
            if not self.ch1_dac:
                self.ch1_enabled = False
        
        elif addr == 0x13:
            self.ch1_freq = (self.ch1_freq & 0x700) | value
        
        elif addr == 0x14:
            self.ch1_freq = (self.ch1_freq & 0xFF) | ((value & 7) << 8)
            self.ch1_length_en = (value & 0x40) != 0
            if value & 0x80:
                self.ch1_enabled = self.ch1_dac
                self.ch1_vol = self.ch1_vol_init
                if self.ch1_length == 0:
                    self.ch1_length = 64
        
        # Channel 2
        elif addr == 0x16:
            self.ch2_duty = (value >> 6) & 3
            self.ch2_length = 64 - (value & 0x3F)
        
        elif addr == 0x17:
            self.ch2_vol_init = (value >> 4) & 0xF
            self.ch2_env_add = (value & 8) != 0
            self.ch2_env_period = value & 7
            self.ch2_dac = (value & 0xF8) != 0
            if not self.ch2_dac:
                self.ch2_enabled = False
        
        elif addr == 0x18:
            self.ch2_freq = (self.ch2_freq & 0x700) | value
        
        elif addr == 0x19:
            self.ch2_freq = (self.ch2_freq & 0xFF) | ((value & 7) << 8)
            self.ch2_length_en = (value & 0x40) != 0
            if value & 0x80:
                self.ch2_enabled = self.ch2_dac
                self.ch2_vol = self.ch2_vol_init
                if self.ch2_length == 0:
                    self.ch2_length = 64
        
        # Channel 3
        elif addr == 0x1A:
            self.ch3_dac = (value & 0x80) != 0
            if not self.ch3_dac:
                self.ch3_enabled = False
        
        elif addr == 0x1B:
            self.ch3_length = 256 - value
        
        elif addr == 0x1C:
            self.ch3_vol_code = (value >> 5) & 3
        
        elif addr == 0x1D:
            self.ch3_freq = (self.ch3_freq & 0x700) | value
        
        elif addr == 0x1E:
            self.ch3_freq = (self.ch3_freq & 0xFF) | ((value & 7) << 8)
            self.ch3_length_en = (value & 0x40) != 0
            if value & 0x80:
                self.ch3_enabled = self.ch3_dac
                if self.ch3_length == 0:
                    self.ch3_length = 256
        
        # Channel 4
        elif addr == 0x20:
            self.ch4_length = 64 - (value & 0x3F)
        
        elif addr == 0x21:
            self.ch4_vol_init = (value >> 4) & 0xF
            self.ch4_env_add = (value & 8) != 0
            self.ch4_env_period = value & 7
            self.ch4_dac = (value & 0xF8) != 0
            if not self.ch4_dac:
                self.ch4_enabled = False
        
        elif addr == 0x22:
            self.ch4_clock_shift = (value >> 4) & 0xF
            self.ch4_width = (value & 8) != 0
            self.ch4_divisor = value & 7
        
        elif addr == 0x23:
            self.ch4_length_en = (value & 0x40) != 0
            if value & 0x80:
                self.ch4_enabled = self.ch4_dac
                self.ch4_vol = self.ch4_vol_init
                self.ch4_lfsr = 0x7FFF
                if self.ch4_length == 0:
                    self.ch4_length = 64
        
        # Control
        elif addr == 0x24:
            self.vol_left = (value >> 4) & 7
            self.vol_right = value & 7
        
        elif addr == 0x25:
            self.pan_left[3] = (value & 0x80) != 0
            self.pan_left[2] = (value & 0x40) != 0
            self.pan_left[1] = (value & 0x20) != 0
            self.pan_left[0] = (value & 0x10) != 0
            self.pan_right[3] = (value & 0x08) != 0
            self.pan_right[2] = (value & 0x04) != 0
            self.pan_right[1] = (value & 0x02) != 0
            self.pan_right[0] = (value & 0x01) != 0
        
        elif addr == 0x26:
            if self.master_enable and not (value & 0x80):
                # Power off
                self.ch1_enabled = False
                self.ch2_enabled = False
                self.ch3_enabled = False
                self.ch4_enabled = False
            self.master_enable = (value & 0x80) != 0
        
        # Wave RAM
        elif 0x30 <= addr <= 0x3F:
            idx = (addr - 0x30) * 2
            self.ch3_wave[idx] = (value >> 4) & 0xF
            self.ch3_wave[idx + 1] = value & 0xF
    
    def close(self):
        """Cierra el dispositivo de audio"""
        if self.device_id > 0:
            sdl2.SDL_ClearQueuedAudio(self.device_id)
            sdl2.SDL_CloseAudioDevice(self.device_id)
            self.device_id = 0
        print("🔇 Audio cerrado")