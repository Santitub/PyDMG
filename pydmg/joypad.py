"""
Joypad
"""

class Joypad:
    __slots__ = ('mmu', 'buttons', 'select_buttons', 'select_dpad')
    
    def __init__(self, mmu):
        self.mmu = mmu
        self.buttons = {
            'right': 1, 'left': 1, 'up': 1, 'down': 1,
            'a': 1, 'b': 1, 'select': 1, 'start': 1
        }
        self.select_buttons = False
        self.select_dpad = False
    
    def write(self, value):
        self.select_buttons = not (value & 0x20)
        self.select_dpad = not (value & 0x10)
    
    def read(self):
        result = 0xCF
        
        if not self.select_buttons:
            result &= 0xDF
        if not self.select_dpad:
            result &= 0xEF
        
        if self.select_buttons:
            if not self.buttons['a']: result &= ~0x01
            if not self.buttons['b']: result &= ~0x02
            if not self.buttons['select']: result &= ~0x04
            if not self.buttons['start']: result &= ~0x08
        
        if self.select_dpad:
            if not self.buttons['right']: result &= ~0x01
            if not self.buttons['left']: result &= ~0x02
            if not self.buttons['up']: result &= ~0x04
            if not self.buttons['down']: result &= ~0x08
        
        return result
    
    def press(self, button):
        if button in self.buttons and self.buttons[button]:
            self.buttons[button] = 0
            self.mmu.io[0x0F] |= 0x10
    
    def release(self, button):
        if button in self.buttons:
            self.buttons[button] = 1