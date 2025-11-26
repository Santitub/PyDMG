""""
Audio Processing Unit
"""

import ctypes
import numpy as np

try:
    import sdl2
    SDL2_AVAILABLE = True
except ImportError:
    SDL2_AVAILABLE = False

# Configuración
SAMPLE_RATE = 22050
BUFFER_SAMPLES = 512  # Samples por frame de audio
CHANNELS = 2


class APU:
    """
    APU usando SDL_QueueAudio
    - Genera audio en lotes durante run_frame()
    - Sin callbacks - mucho más eficiente
    - Buffer manejado por SDL internamente
    """
    
    CPU_FREQ = 4194304
    CYCLES_PER_FRAME = 70224
    
    def __init__(self, mmu):
        self.mmu = mmu
        self.enabled = True
        self.master_enable = True
        
        # Volumen
        self.vol_left = 7
        self.vol_right = 7
        
        # Panning
        self.pan_left = [True, True, True, True]
        self.pan_right = [True, True, True, True]
        
        # Channel 1: Pulse + Sweep
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
        
        # Channel 2: Pulse
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
        
        # Channel 3: Wave
        self.ch3_enabled = False
        self.ch3_dac = False
        self.ch3_freq = 0
        self.ch3_vol_code = 0
        self.ch3_length = 0
        self.ch3_length_en = False
        self.ch3_wave = np.zeros(32, dtype=np.uint8)
        self.ch3_phase = 0.0
        
        # Channel 4: Noise
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
        
        # Duty table
        self.duty_table = np.array([
            [0, 0, 0, 0, 0, 0, 0, 1],
            [1, 0, 0, 0, 0, 0, 0, 1],
            [1, 0, 0, 0, 0, 1, 1, 1],
            [0, 1, 1, 1, 1, 1, 1, 0],
        ], dtype=np.float32)
        
        # Pre-allocate buffer
        self.audio_buffer = np.zeros(BUFFER_SAMPLES * CHANNELS, dtype=np.float32)
        
        # SDL
        self.device_id = 0
        self._init_audio()
    
    def _init_audio(self):
        """Inicializa SDL2 Audio sin callback"""
        if not SDL2_AVAILABLE:
            return
        
        if sdl2.SDL_WasInit(sdl2.SDL_INIT_AUDIO) == 0:
            if sdl2.SDL_InitSubSystem(sdl2.SDL_INIT_AUDIO) < 0:
                return
        
        # Spec sin callback
        spec = sdl2.SDL_AudioSpec(
            freq=SAMPLE_RATE,
            aformat=sdl2.AUDIO_F32SYS,
            channels=CHANNELS,
            samples=BUFFER_SAMPLES,
            callback=sdl2.SDL_AudioCallback(),  # NULL callback
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
    
    def end_frame(self):
        """
        Llamar al final de cada frame para generar y enviar audio
        Este es el método clave - genera audio una vez por frame
        """
        if self.device_id == 0 or not self.enabled:
            return
        
        # Verificar cuánto audio hay en cola
        queued = sdl2.SDL_GetQueuedAudioSize(self.device_id)
        
        # Si hay mucho audio en cola, no agregar más (evita lag)
        max_queued = BUFFER_SAMPLES * CHANNELS * 4 * 4  # 4 frames de buffer
        if queued > max_queued:
            return
        
        # Generar samples para este frame
        self._generate_frame_audio()
        
        # Enviar a SDL
        sdl2.SDL_QueueAudio(
            self.device_id,
            self.audio_buffer.ctypes.data_as(ctypes.c_void_p),
            self.audio_buffer.nbytes
        )
    
    def _generate_frame_audio(self):
        """Genera audio para un frame completo"""
        samples_per_frame = BUFFER_SAMPLES
        
        for i in range(samples_per_frame):
            left = 0.0
            right = 0.0
            
            # Channel 1
            if self.ch1_enabled and self.ch1_dac and self.ch1_freq > 0:
                s = self._pulse_sample(1)
                if self.pan_left[0]: left += s
                if self.pan_right[0]: right += s
            
            # Channel 2
            if self.ch2_enabled and self.ch2_dac and self.ch2_freq > 0:
                s = self._pulse_sample(2)
                if self.pan_left[1]: left += s
                if self.pan_right[1]: right += s
            
            # Channel 3
            if self.ch3_enabled and self.ch3_dac and self.ch3_freq > 0:
                s = self._wave_sample()
                if self.pan_left[2]: left += s
                if self.pan_right[2]: right += s
            
            # Channel 4
            if self.ch4_enabled and self.ch4_dac:
                s = self._noise_sample()
                if self.pan_left[3]: left += s
                if self.pan_right[3]: right += s
            
            # Normalizar
            left = (left / 60.0) * ((self.vol_left + 1) / 8.0)
            right = (right / 60.0) * ((self.vol_right + 1) / 8.0)
            
            # Clamp y guardar
            self.audio_buffer[i * 2] = max(-1.0, min(1.0, left))
            self.audio_buffer[i * 2 + 1] = max(-1.0, min(1.0, right))
        
        # Tick frame sequencer unas pocas veces por frame
        for _ in range(8):
            self._tick_frame_seq()
    
    def _pulse_sample(self, ch):
        """Genera sample de pulse"""
        if ch == 1:
            freq, duty, vol = self.ch1_freq, self.ch1_duty, self.ch1_vol
        else:
            freq, duty, vol = self.ch2_freq, self.ch2_duty, self.ch2_vol
        
        # Frecuencia real
        real_freq = 131072.0 / (2048 - freq)
        
        # Avanzar fase
        if ch == 1:
            self.ch1_phase += real_freq / SAMPLE_RATE
            if self.ch1_phase >= 1.0:
                self.ch1_phase -= 1.0
            phase = self.ch1_phase
        else:
            self.ch2_phase += real_freq / SAMPLE_RATE
            if self.ch2_phase >= 1.0:
                self.ch2_phase -= 1.0
            phase = self.ch2_phase
        
        pos = int(phase * 8) & 7
        return self.duty_table[duty][pos] * vol
    
    def _wave_sample(self):
        """Genera sample de wave"""
        if self.ch3_vol_code == 0:
            return 0.0
        
        real_freq = 65536.0 / (2048 - self.ch3_freq)
        
        self.ch3_phase += real_freq / SAMPLE_RATE
        if self.ch3_phase >= 1.0:
            self.ch3_phase -= 1.0
        
        pos = int(self.ch3_phase * 32) & 31
        sample = self.ch3_wave[pos]
        
        shifts = [4, 0, 1, 2]
        return float(sample >> shifts[self.ch3_vol_code])
    
    def _noise_sample(self):
        """Genera sample de noise"""
        if self.ch4_vol == 0:
            return 0.0
        
        divisors = [8, 16, 32, 48, 64, 80, 96, 112]
        div = divisors[self.ch4_divisor]
        freq = 262144.0 / (div << self.ch4_clock_shift) if self.ch4_clock_shift < 14 else 1.0
        
        self.ch4_timer += freq / SAMPLE_RATE
        while self.ch4_timer >= 1.0:
            self.ch4_timer -= 1.0
            xor = (self.ch4_lfsr & 1) ^ ((self.ch4_lfsr >> 1) & 1)
            self.ch4_lfsr = (self.ch4_lfsr >> 1) | (xor << 14)
            if self.ch4_width:
                self.ch4_lfsr = (self.ch4_lfsr & ~0x40) | (xor << 6)
        
        return 0.0 if (self.ch4_lfsr & 1) else float(self.ch4_vol)
    
    def _tick_frame_seq(self):
        """Frame sequencer"""
        step = self.frame_seq
        
        if step % 2 == 0:
            self._clock_lengths()
        
        if step == 7:
            self._clock_envelopes()
        
        self.frame_seq = (step + 1) & 7
    
    def _clock_lengths(self):
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
    
    def _clock_envelopes(self):
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
    
    def step(self, cycles):
        """No hace nada - el audio se genera en end_frame()"""
        pass
    
    # === Registros ===
    
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
        
        # Channel 1
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
        
        # Channel 2
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
        
        # Channel 3
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
        
        # Channel 4
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
        
        # Control
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
                # Power off
                self.ch1_enabled = self.ch2_enabled = self.ch3_enabled = self.ch4_enabled = False
            self.master_enable = new_enable
        
        # Wave RAM
        elif 0x30 <= addr <= 0x3F:
            idx = (addr - 0x30) * 2
            self.ch3_wave[idx] = (value >> 4) & 0xF
            self.ch3_wave[idx + 1] = value & 0xF
    
    def close(self):
        if self.device_id > 0:
            sdl2.SDL_ClearQueuedAudio(self.device_id)
            sdl2.SDL_CloseAudioDevice(self.device_id)
            self.device_id = 0
        print("🔇 Audio cerrado")