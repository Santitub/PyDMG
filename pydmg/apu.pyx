# cython: language_level=3, boundscheck=False, wraparound=False, cdivision=True
"""
APU - Cython optimizado
"""

cimport cython
from libc.stdint cimport uint8_t, uint16_t
from libc.math cimport floor
import numpy as np
cimport numpy as np

np.import_array()

cdef int SAMPLE_RATE = 22050
cdef int BUFFER_SAMPLES = 512

cdef float[4][8] DUTY_TABLE = [
    [0, 0, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 1, 1, 1],
    [0, 1, 1, 1, 1, 1, 1, 0],
]

cdef class APU:
    cdef object mmu
    cdef public bint enabled, master_enable
    cdef public int vol_left, vol_right
    cdef public list pan_left, pan_right
    
    # Channel 1
    cdef public bint ch1_enabled, ch1_dac, ch1_env_add, ch1_length_en, ch1_sweep_neg
    cdef public int ch1_duty, ch1_freq, ch1_vol, ch1_vol_init, ch1_env_period
    cdef public int ch1_length, ch1_sweep_period, ch1_sweep_shift
    cdef public float ch1_phase
    
    # Channel 2
    cdef public bint ch2_enabled, ch2_dac, ch2_env_add, ch2_length_en
    cdef public int ch2_duty, ch2_freq, ch2_vol, ch2_vol_init, ch2_env_period, ch2_length
    cdef public float ch2_phase
    
    # Channel 3
    cdef public bint ch3_enabled, ch3_dac, ch3_length_en
    cdef public int ch3_freq, ch3_vol_code, ch3_length
    cdef public float ch3_phase
    cdef public np.ndarray ch3_wave
    
    # Channel 4
    cdef public bint ch4_enabled, ch4_dac, ch4_env_add, ch4_length_en, ch4_width
    cdef public int ch4_vol, ch4_vol_init, ch4_env_period, ch4_length
    cdef public int ch4_clock_shift, ch4_divisor, ch4_lfsr
    cdef public float ch4_timer
    
    cdef public int frame_seq
    cdef public np.ndarray audio_buffer
    cdef public int device_id
    
    def __init__(self, mmu):
        self.mmu = mmu
        self.enabled = True
        self.master_enable = True
        self.vol_left = 7
        self.vol_right = 7
        self.pan_left = [True, True, True, True]
        self.pan_right = [True, True, True, True]
        
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
        
        self.ch3_enabled = False
        self.ch3_dac = False
        self.ch3_freq = 0
        self.ch3_vol_code = 0
        self.ch3_length = 0
        self.ch3_length_en = False
        self.ch3_wave = np.zeros(32, dtype=np.uint8)
        self.ch3_phase = 0.0
        
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
        
        self.frame_seq = 0
        self.audio_buffer = np.zeros(BUFFER_SAMPLES * 2, dtype=np.float32)
        self.device_id = 0
        
        self._init_audio()
    
    def _init_audio(self):
        try:
            import sdl2
            import ctypes
            
            if sdl2.SDL_WasInit(sdl2.SDL_INIT_AUDIO) == 0:
                if sdl2.SDL_InitSubSystem(sdl2.SDL_INIT_AUDIO) < 0:
                    return
            
            spec = sdl2.SDL_AudioSpec(
                freq=SAMPLE_RATE,
                aformat=sdl2.AUDIO_F32SYS,
                channels=2,
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
        except:
            pass
    
    cpdef void end_frame(self):
        cdef int i
        cdef float left, right, s
        cdef float[:] buf = self.audio_buffer
        
        if self.device_id == 0 or not self.enabled:
            return
        
        try:
            import sdl2
            import ctypes
            
            queued = sdl2.SDL_GetQueuedAudioSize(self.device_id)
            if queued > BUFFER_SAMPLES * 2 * 4 * 4:
                return
        except:
            return
        
        for i in range(BUFFER_SAMPLES):
            left = 0.0
            right = 0.0
            
            if self.ch1_enabled and self.ch1_dac and self.ch1_freq > 0:
                s = self._pulse_sample(1)
                if self.pan_left[0]: left += s
                if self.pan_right[0]: right += s
            
            if self.ch2_enabled and self.ch2_dac and self.ch2_freq > 0:
                s = self._pulse_sample(2)
                if self.pan_left[1]: left += s
                if self.pan_right[1]: right += s
            
            if self.ch3_enabled and self.ch3_dac and self.ch3_freq > 0:
                s = self._wave_sample()
                if self.pan_left[2]: left += s
                if self.pan_right[2]: right += s
            
            if self.ch4_enabled and self.ch4_dac:
                s = self._noise_sample()
                if self.pan_left[3]: left += s
                if self.pan_right[3]: right += s
            
            left = (left / 60.0) * ((self.vol_left + 1) / 8.0)
            right = (right / 60.0) * ((self.vol_right + 1) / 8.0)
            
            if left > 1.0: left = 1.0
            if left < -1.0: left = -1.0
            if right > 1.0: right = 1.0
            if right < -1.0: right = -1.0
            
            buf[i * 2] = left
            buf[i * 2 + 1] = right
        
        for _ in range(8):
            self._tick_frame_seq()
        
        try:
            import sdl2
            import ctypes
            sdl2.SDL_QueueAudio(
                self.device_id,
                self.audio_buffer.ctypes.data_as(ctypes.c_void_p),
                self.audio_buffer.nbytes
            )
        except:
            pass
    
    cdef float _pulse_sample(self, int ch):
        cdef int freq, duty, vol, pos
        cdef float real_freq, phase
        
        if ch == 1:
            freq = self.ch1_freq
            duty = self.ch1_duty
            vol = self.ch1_vol
            real_freq = 131072.0 / (2048 - freq)
            self.ch1_phase += real_freq / SAMPLE_RATE
            if self.ch1_phase >= 1.0:
                self.ch1_phase -= 1.0
            phase = self.ch1_phase
        else:
            freq = self.ch2_freq
            duty = self.ch2_duty
            vol = self.ch2_vol
            real_freq = 131072.0 / (2048 - freq)
            self.ch2_phase += real_freq / SAMPLE_RATE
            if self.ch2_phase >= 1.0:
                self.ch2_phase -= 1.0
            phase = self.ch2_phase
        
        pos = <int>(phase * 8) & 7
        return DUTY_TABLE[duty][pos] * vol
    
    cdef float _wave_sample(self):
        cdef float real_freq
        cdef int pos, sample
        cdef int[4] shifts = [4, 0, 1, 2]
        
        if self.ch3_vol_code == 0:
            return 0.0
        
        real_freq = 65536.0 / (2048 - self.ch3_freq)
        self.ch3_phase += real_freq / SAMPLE_RATE
        if self.ch3_phase >= 1.0:
            self.ch3_phase -= 1.0
        
        pos = <int>(self.ch3_phase * 32) & 31
        sample = self.ch3_wave[pos]
        
        return <float>(sample >> shifts[self.ch3_vol_code])
    
    cdef float _noise_sample(self):
        cdef int[8] divisors = [8, 16, 32, 48, 64, 80, 96, 112]
        cdef int div, xor_val
        cdef float freq
        
        if self.ch4_vol == 0:
            return 0.0
        
        div = divisors[self.ch4_divisor]
        if self.ch4_clock_shift < 14:
            freq = 262144.0 / (div << self.ch4_clock_shift)
        else:
            freq = 1.0
        
        self.ch4_timer += freq / SAMPLE_RATE
        while self.ch4_timer >= 1.0:
            self.ch4_timer -= 1.0
            xor_val = (self.ch4_lfsr & 1) ^ ((self.ch4_lfsr >> 1) & 1)
            self.ch4_lfsr = (self.ch4_lfsr >> 1) | (xor_val << 14)
            if self.ch4_width:
                self.ch4_lfsr = (self.ch4_lfsr & ~0x40) | (xor_val << 6)
        
        if self.ch4_lfsr & 1:
            return 0.0
        return <float>self.ch4_vol
    
    cdef void _tick_frame_seq(self):
        cdef int step = self.frame_seq
        
        if step % 2 == 0:
            self._clock_lengths()
        
        if step == 7:
            self._clock_envelopes()
        
        self.frame_seq = (step + 1) & 7
    
    cdef void _clock_lengths(self):
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
    
    cdef void _clock_envelopes(self):
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
        pass
    
    def read(self, addr):
        addr &= 0x3F
        
        if addr == 0x10:
            return 0x80 | (self.ch1_sweep_period << 4) | (int(self.ch1_sweep_neg) << 3) | self.ch1_sweep_shift
        elif addr == 0x11:
            return (self.ch1_duty << 6) | 0x3F
        elif addr == 0x12:
            return (self.ch1_vol_init << 4) | (int(self.ch1_env_add) << 3) | self.ch1_env_period
        elif addr == 0x14:
            return 0xBF | (int(self.ch1_length_en) << 6)
        elif addr == 0x16:
            return (self.ch2_duty << 6) | 0x3F
        elif addr == 0x17:
            return (self.ch2_vol_init << 4) | (int(self.ch2_env_add) << 3) | self.ch2_env_period
        elif addr == 0x19:
            return 0xBF | (int(self.ch2_length_en) << 6)
        elif addr == 0x1A:
            return 0x7F | (int(self.ch3_dac) << 7)
        elif addr == 0x1C:
            return 0x9F | (self.ch3_vol_code << 5)
        elif addr == 0x1E:
            return 0xBF | (int(self.ch3_length_en) << 6)
        elif addr == 0x21:
            return (self.ch4_vol_init << 4) | (int(self.ch4_env_add) << 3) | self.ch4_env_period
        elif addr == 0x22:
            return (self.ch4_clock_shift << 4) | (int(self.ch4_width) << 3) | self.ch4_divisor
        elif addr == 0x23:
            return 0xBF | (int(self.ch4_length_en) << 6)
        elif addr == 0x24:
            return (self.vol_left << 4) | self.vol_right
        elif addr == 0x25:
            return ((int(self.pan_left[3]) << 7) | (int(self.pan_left[2]) << 6) |
                    (int(self.pan_left[1]) << 5) | (int(self.pan_left[0]) << 4) |
                    (int(self.pan_right[3]) << 3) | (int(self.pan_right[2]) << 2) |
                    (int(self.pan_right[1]) << 1) | int(self.pan_right[0]))
        elif addr == 0x26:
            return (0x70 | (int(self.master_enable) << 7) |
                    (int(self.ch4_enabled) << 3) | (int(self.ch3_enabled) << 2) |
                    (int(self.ch2_enabled) << 1) | int(self.ch1_enabled))
        elif 0x30 <= addr <= 0x3F:
            idx = (addr - 0x30) * 2
            return (self.ch3_wave[idx] << 4) | self.ch3_wave[idx + 1]
        return 0xFF
    
    def write(self, addr, value):
        addr &= 0x3F
        
        if not self.master_enable and addr != 0x26 and not (0x30 <= addr <= 0x3F):
            return
        
        if addr == 0x10:
            self.ch1_sweep_period = (value >> 4) & 7
            self.ch1_sweep_neg = bool(value & 8)
            self.ch1_sweep_shift = value & 7
        elif addr == 0x11:
            self.ch1_duty = (value >> 6) & 3
            self.ch1_length = 64 - (value & 0x3F)
        elif addr == 0x12:
            self.ch1_vol_init = (value >> 4) & 0xF
            self.ch1_env_add = bool(value & 8)
            self.ch1_env_period = value & 7
            self.ch1_dac = (value & 0xF8) != 0
            if not self.ch1_dac:
                self.ch1_enabled = False
        elif addr == 0x13:
            self.ch1_freq = (self.ch1_freq & 0x700) | value
        elif addr == 0x14:
            self.ch1_freq = (self.ch1_freq & 0xFF) | ((value & 7) << 8)
            self.ch1_length_en = bool(value & 0x40)
            if value & 0x80:
                self.ch1_enabled = self.ch1_dac
                self.ch1_vol = self.ch1_vol_init
                if self.ch1_length == 0:
                    self.ch1_length = 64
        elif addr == 0x16:
            self.ch2_duty = (value >> 6) & 3
            self.ch2_length = 64 - (value & 0x3F)
        elif addr == 0x17:
            self.ch2_vol_init = (value >> 4) & 0xF
            self.ch2_env_add = bool(value & 8)
            self.ch2_env_period = value & 7
            self.ch2_dac = (value & 0xF8) != 0
            if not self.ch2_dac:
                self.ch2_enabled = False
        elif addr == 0x18:
            self.ch2_freq = (self.ch2_freq & 0x700) | value
        elif addr == 0x19:
            self.ch2_freq = (self.ch2_freq & 0xFF) | ((value & 7) << 8)
            self.ch2_length_en = bool(value & 0x40)
            if value & 0x80:
                self.ch2_enabled = self.ch2_dac
                self.ch2_vol = self.ch2_vol_init
                if self.ch2_length == 0:
                    self.ch2_length = 64
        elif addr == 0x1A:
            self.ch3_dac = bool(value & 0x80)
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
            self.ch3_length_en = bool(value & 0x40)
            if value & 0x80:
                self.ch3_enabled = self.ch3_dac
                if self.ch3_length == 0:
                    self.ch3_length = 256
        elif addr == 0x20:
            self.ch4_length = 64 - (value & 0x3F)
        elif addr == 0x21:
            self.ch4_vol_init = (value >> 4) & 0xF
            self.ch4_env_add = bool(value & 8)
            self.ch4_env_period = value & 7
            self.ch4_dac = (value & 0xF8) != 0
            if not self.ch4_dac:
                self.ch4_enabled = False
        elif addr == 0x22:
            self.ch4_clock_shift = (value >> 4) & 0xF
            self.ch4_width = bool(value & 8)
            self.ch4_divisor = value & 7
        elif addr == 0x23:
            self.ch4_length_en = bool(value & 0x40)
            if value & 0x80:
                self.ch4_enabled = self.ch4_dac
                self.ch4_vol = self.ch4_vol_init
                self.ch4_lfsr = 0x7FFF
                if self.ch4_length == 0:
                    self.ch4_length = 64
        elif addr == 0x24:
            self.vol_left = (value >> 4) & 7
            self.vol_right = value & 7
        elif addr == 0x25:
            self.pan_left[3] = bool(value & 0x80)
            self.pan_left[2] = bool(value & 0x40)
            self.pan_left[1] = bool(value & 0x20)
            self.pan_left[0] = bool(value & 0x10)
            self.pan_right[3] = bool(value & 0x08)
            self.pan_right[2] = bool(value & 0x04)
            self.pan_right[1] = bool(value & 0x02)
            self.pan_right[0] = bool(value & 0x01)
        elif addr == 0x26:
            new_enable = bool(value & 0x80)
            if self.master_enable and not new_enable:
                self.ch1_enabled = self.ch2_enabled = self.ch3_enabled = self.ch4_enabled = False
            self.master_enable = new_enable
        elif 0x30 <= addr <= 0x3F:
            idx = (addr - 0x30) * 2
            self.ch3_wave[idx] = (value >> 4) & 0xF
            self.ch3_wave[idx + 1] = value & 0xF
    
    def close(self):
        if self.device_id > 0:
            try:
                import sdl2
                sdl2.SDL_ClearQueuedAudio(self.device_id)
                sdl2.SDL_CloseAudioDevice(self.device_id)
            except:
                pass
            self.device_id = 0