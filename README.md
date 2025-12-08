# PyDMG - Game Boy Emulator

[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/Santitub/PyDMG)

Un emulador de Game Boy Classic (DMG) completo y preciso escrito en Python con optimizaciones opcionales en Cython.

## 🎮 Características

- **CPU LR35902**: Implementación completa del conjunto de instrucciones con todos los modos de direccionamiento
- **PPU Preciso**: Renderizado de gráficos con soporte para fondo, ventana, sprites y todas las modalidades de visualización
- **APU con SDL2**: Sistema de audio de 4 canales (2×Pulse, Wave, Noise) con cola de audio eficiente
- **MBC Completo**: Soporte para MBC1, MBC2, MBC3 (con RTC) y MBC5
- **Save States**: Guardado y carga instantánea del estado del juego (10 slots)
- **SRAM Persistent**: Guardado automático de RAM externa para cartuchos con batería
- **Múltiples Paletas**: 4 paletas de color diferentes (DMG, Grayscale, Green, Pocket)
- **Controles Avanzados**: Modo turbo, pausa, debug mode y reset
- **Optimizable**: Soporte para compilar con Cython para máximo rendimiento

## 📁 Estructura del Repositorio

```
PyDMG/
├── README.md                 # Este archivo
├── LICENSE                   # Licencia MIT (pendiente de añadir)
├── requirements.txt          # Dependencias de Python
├── setup.py                 # Script de compilación de Cython
├── main.py                  # Punto de entrada del emulador
└── pydmg/                   # Paquete principal del emulador
    ├── __init__.py
    ├── cpu.py               # Implementación de CPU (Python puro)
    ├── cpu.pyx              # Implementación de CPU (Cython fuente)
    ├── ppu.py               # Implementación de PPU (Python puro)
    ├── ppu.pyx              # Implementación de PPU (Cython fuente)
    ├── mmu.py               # Memory Management Unit con MBC
    ├── apu.py               # Audio Processing Unit (Python puro)
    ├── apu.pyx              # Audio Processing Unit (Cython fuente)
    ├── timer.py             # Timer del sistema (Python puro)
    ├── timer.pyx            # Timer del sistema (Cython fuente)
    ├── joypad.py            # Manejo de entrada
    ├── savestate.py         # Sistema de save states
    ├── gameboy.py           # Clase principal del sistema
```

## ⚠️ Notas Importantes sobre la Estructura

1. **No hay módulos Cython pre-compilados**: Los archivos `.so` **NO están incluidos** en este repositorio. Debes compilarlos manualmente para obtener rendimiento aceptable.

2. **Carpetas dinámicas**: Las carpetas `roms/` y `saves/` deben crearse manualmente (ver instrucciones abajo).

## 🚀 Instalación y Compilación

### Requisitos Previos

- **Python 3.7+**
- **SDL2** (librería del sistema)
  - **Ubuntu/Debian**: `sudo apt-get install libsdl2-2.0-0`
  - **macOS**: `brew install sdl2`
  - **Windows**: Descargar desde [libsdl.org](https://github.com/libsdl-org/SDL/releases/tag/release-2.32.10)

### Instalación Completa (Obligatoria)

```bash
# Clonar el repositorio
git clone https://github.com/santitub/PyDMG.git
cd PyDMG

# Crear entorno virtual (recomendado)
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate

# Instalar dependencias
pip install -r requirements.txt

# Instalar Cython y compilador C (obligatorio)
pip install cython
# Ubuntu/Debian: sudo apt-get install build-essential
# macOS: xcode-select --install
# Windows: Instalar Visual Studio Build Tools

# Compilar extensiones Cython desde la RAÍZ del proyecto
python setup.py build_ext --inplace

# Verificar que se crearon los módulos .so/.pyd
ls -la pydmg/*.so  # Linux/macOS
dir pydmg\*.pyd    # Windows

# Ejecutar con la ROM que quieras
python main.py rom.gb
```

### Opciones de Instalación

#### **Versión Cython Compilada** (Recomendado, máximo rendimiento)
- Requiere: Cython + compilador C (GCC/Clang/MSVC)
- Compilar con: `python setup.py build_ext --inplace`
- Rendimiento: 60 FPS constantes con overhead mínimo
- **Este es el modo recomendado para jugar**

#### **Versión Python Pura** (Emergencia, solo si no puedes compilar)
- Solo instalar dependencias con `pip install -r requirements.txt`
- No requiere compilador C
- Rendimiento: ~30-40 FPS en CPU moderna
- **Usar solo si la compilación falla definitivamente**

## 📂 Preparar ROMs y Guardados

```bash
# Crear carpeta para ROMs (obligatorio)
mkdir roms
cp /ruta/a/tus/roms/*.gb roms/

# Crear carpeta para guardados (opcional, se crea automáticamente)
mkdir saves

# Ejecutar con una ROM específica
python main.py roms/tu_juego.gb
```

**Nota**: Los archivos de guardado (`.sav` y `.st0-.st9`) se crean en el **mismo directorio que la ROM**, no en la carpeta `saves/` a menos que especifiques esa ruta.

## 🎮 Controles

### Controles del Juego
| Tecla | Botón Game Boy |
|-------|----------------|
| `↑ ↓ ← →` | D-Pad |
| `Z` / `A` | A |
| `X` / `S` | B |
| `Enter` | Start |
| `Shift` | Select |

### Controles del Emulador
| Tecla | Función |
|-------|---------|
| `P` | Pausar/Continuar |
| `M` | Silenciar/Activar audio |
| `C` | Cambiar paleta de color |
| `R` | Resetear el juego |
| `D` | Toggle debug mode (muestra FPS) |
| `Space` | Modo turbo (mantener pulsado) |
| `ESC` | Salir del emulador |

### Save States
| Tecla | Función |
|-------|---------|
| `F5` | Guardar estado (slot actual) |
| `F7` | Cargar estado (slot actual) |
| `F6` / `F8` | Slot anterior/siguiente |
| `0-9` | Seleccionar slot directamente |

**Tip**: El slot actual se muestra en el título de la ventana.

## ⚙️ Configuración

### Dependencias

**requirements.txt:**
```
PySDL2>=0.9.14
numpy>=1.19.0
Cython>=0.29.0  # Obligatorio para compilar
```

### Archivos de Configuración

- **Python puro**: Usa `cpu.py` y `ppu.py` si los módulos Cython no están disponibles
- **Cython**: Los archivos `.so` tienen prioridad automática si están presentes

## 🔧 Desarrollo

### Arquitectura del Emulador

```
┌─────────────────────────────────────────┐
│              main.py                    │
│     (SDL2 Frontend + Event Loop)        │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│        pydmg/gameboy.py                 │
│      (Coordinator + Frame Synchrony)    │
└──────┬──────────────────┬───────────────┘
       │                  │
┌──────▼──────┐    ┌─────▼──────┐
│  cpu.py/so  │    │  ppu.py/so │
│   (LR35902) │    │ (Renderer) │
└──────┬──────┘    └─────┬──────┘
       │                 │
┌──────▼──────┐    ┌─────▼──────┐
│   mmu.py    │◄──►│  apu.py    │
│ (Memory +   │    │ (Audio)    │
│   MBC)      │    └────────────┘
└──────┬──────┘
       │
┌──────▼──────┐
│ timer.py    │
│ joypad.py   │
│ savestate.py│
└─────────────┘
```

### Perfiles de Rendimiento

| Modo | FPS Promedio | Uso CPU | Requisitos |
|------|--------------|---------|------------|
| Python puro | 30-40 | 80-100% | Sin compilar (emergencia) |
| Cython compilado | 60 estable | 30-50% | Requiere `setup.py build_ext` |

## 🐛 Solución de Problemas

### **"SDL2 no encontrado"**
```bash
# Verificar instalación
python -c "import sdl2; print(sdl2.__version__)"

# En Linux, si hay errores de ALSA:
# El código ya silencia warnings de ALSA automáticamente
```

### **Error al compilar Cython**
```bash
# Verifica que tienes el compilador C instalado
gcc --version  # Linux/macOS

# En Windows, usa el "x64 Native Tools Command Prompt for VS"
python setup.py build_ext --inplace
```

### **Error al cargar módulos después de compilar**
```bash
# Si aparece "no module named 'pydmg.cpu'":
# 1. Verifica que estás en el directorio raíz del proyecto
# 2. Reinstala las dependencias: pip install -r requirements.txt
# 3. Recompila de nuevo: python setup.py build_ext --inplace
# 4. Verifica que se crearon los archivos .so/.pyd en pydmg/
```

### **Audio con chasquidos**
- Asegurar que `SDL2_AVAILABLE = True` en `pydmg/apu.py`
- Verificar `BUFFER_SAMPLES = 512` (puede aumentarse si hay lag)

### **Render lento**
- **Solución 1**: Asegúrate de haber compilado los módulos Cython
- **Solución 2**: Verifica que los archivos `.so` existen en `pydmg/`
- **Solución 3**: Activa turbo con `Space` o cierra otras aplicaciones

## 🤝 Contribuciones

¡Las contribuciones son bienvenidas!

1. Haz fork del repositorio
2. Crea una rama (`git checkout -b feature/nueva-caracteristica`)
3. Haz commit de tus cambios (`git commit -am 'Añadir nueva característica'`)
4. Push a la ranga (`git push origin feature/nueva-caracteristica`)
5. Abre un Pull Request

**⚠️ Disclaimer**: Este emulador es para fines educacionales y de preservación. Asegúrate de tener los derechos legales sobre las ROMs que utilizas.
