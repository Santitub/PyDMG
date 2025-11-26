# PyDMG - Game Boy Emulator

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
- **Optimizado**: Módulos Cython pre-compilados para Linux x86_64/Python 3.12

## 📁 Estructura del Repositorio

```
PyDMG/
├── README.md                 # Este archivo
├── LICENSE                   # Licencia MIT (pendiente de añadir)
├── requirements.txt          # Dependencias de Python
├── setup.py                 # Script de compilación de Cython
├── main.py                  # Punto de entrada del emulador
├── sml.gb                   # ROM de ejemplo (Super Mario Land)
└── pydmg/                   # Paquete principal del emulador
    ├── __init__.py
    ├── cpu.py               # Implementación de CPU (Python puro)
    ├── cpu.pyx              # Implementación de CPU (Cython fuente)
    ├── cpu.cpython-312-x86_64-linux-gnu.so  # Módulo compilado (Linux)
    ├── ppu.py               # Implementación de PPU (Python puro)
    ├── ppu.pyx              # Implementación de PPU (Cython fuente)
    ├── ppu.cpython-312-x86_64-linux-gnu.so  # Módulo compilado (Linux)
    ├── mmu.py               # Memory Management Unit con MBC
    ├── apu.py               # Audio Processing Unit
    ├── timer.py             # Timer del sistema
    ├── joypad.py            # Manejo de entrada
    ├── savestate.py         # Sistema de save states
    ├── gameboy.py           # Clase principal del sistema
```

## ⚠️ Notas Importantes sobre la Estructura

1. **Módulos Cython pre-compilados**: Los archivos `.so` ya están compilados para **Python 3.12 en Linux x86_64**. Si usas otra versión de Python u otro sistema operativo, necesitarás recompilarlos.

2. **Carpetas faltantes**: Las carpetas `roms/` y `saves/` **no existen** en el repositorio y deben crearse manualmente (ver instrucciones abajo).

## 🚀 Instalación Rápida

### Requisitos Previos

- **Python 3.7+** (optimizado para 3.12)
- **SDL2** (librería del sistema)
  - **Ubuntu/Debian**: `sudo apt-get install libsdl2-2.0-0`
  - **macOS**: `brew install sdl2`
  - **Windows**: Descargar desde [libsdl.org](https://github.com/libsdl-org/SDL/releases/tag/release-2.32.10)

### Instalación Básica (Recomendado)

```bash
# Clonar el repositorio
git clone https://github.com/santitub/PyDMG.git
cd PyDMG

# Crear entorno virtual (recomendado)
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate

# Instalar dependencias
pip install -r requirements.txt

# Verificar que los módulos Cython funcionan
python -c "from pydmg import GameBoy; print('Módulos Cython cargados correctamente')"

# Ejecutar directamente con la ROM incluida
python main.py sml.gb
```

### Recompilación Cython (Solo si es necesario)

Si los módulos `.so` no funcionan en tu sistema:

```bash
# Instalar Cython y compilador
pip install cython
# Ubuntu/Debian: sudo apt-get install build-essential
# macOS: xcode-select --install
# Windows: Instalar Visual Studio Build Tools

# Compilar desde la RAÍZ del proyecto
python setup.py build_ext --inplace

# Verificar archivos generados
ls -la pydmg/*.so  # Linux/macOS
dir pydmg\*.pyd    # Windows
```

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
Cython>=0.29.0  # Opcional, solo para recompilar
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
| Python puro | 30-40 | 80-100% | Sin archivos `.so` |
| Cython pre-compilado | 60 estable | 30-50% | Archivos `.so` compatibles |
| Cython re-compilado | 60 estable | 30-50% | Compilación manual |

## 🐛 Solución de Problemas

### **"SDL2 no encontrado"**
```bash
# Verificar instalación
python -c "import sdl2; print(sdl2.__version__)"

# En Linux, si hay errores de ALSA:
# El código ya silencia warnings de ALSA automáticamente
```

### **Error al cargar módulos Cython**
```bash
# Si aparece "no module named 'pydmg.cpu'":
# 1. Verifica que estás en el directorio raíz del proyecto
# 2. Reinstala las dependencias: pip install -r requirements.txt
# 3. Si persiste, recompila: python setup.py build_ext --inplace
```

### **Audio con chasquidos**
- Asegurar que `SDL2_AVAILABLE = True` en `pydmg/apu.py`
- Verificar `BUFFER_SAMPLES = 512` (puede aumentarse si hay lag)

### **Render lento**
- **Solución 1**: Usa los módulos Cython pre-compilados
- **Solución 2**: Recompila manualmente si no son compatibles
- **Solución 3**: Activa turbo con `Space`

## 🤝 Contribuciones

¡Las contribuciones son bienvenidas!

1. Haz fork del repositorio
2. Crea una rama (`git checkout -b feature/nueva-caracteristica`)
3. Haz commit de tus cambios (`git commit -am 'Añadir nueva característica'`)
4. Push a la ranga (`git push origin feature/nueva-caracteristica`)
5. Abre un Pull Request

**⚠️ Disclaimer**: Este emulador es para fines educacionales y de preservación. Asegúrate de tener los derechos legales sobre las ROMs que utilizas.