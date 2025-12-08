from setuptools import setup, Extension, find_packages
from Cython.Build import cythonize
import numpy as np
import platform
import os
import glob
import shutil
import subprocess
from distutils.command.build_ext import build_ext

# ===== DETECCIÓN INTELIGENTE DE CPU =====
def is_modern_cpu():
    """
    Detecta si la CPU soporta instrucciones AVX2 (moderno)
    Retorna True para: Intel Haswell (4th gen)+, AMD Ryzen+
    Retorna False para: CPUs más antiguas
    """
    try:
        cpu_name = ""
        
        if platform.system() == "Windows":
            # Windows: WMIC
            output = subprocess.check_output("wmic cpu get name", shell=True).decode()
            cpu_name = output.lower().split('\n')[1].strip()
        elif platform.system() == "Linux":
            # Linux: /proc/cpuinfo
            with open("/proc/cpuinfo", "r") as f:
                for line in f:
                    if line.startswith("model name"):
                        cpu_name = line.lower().split(":")[1].strip()
                        break
        elif platform.system() == "Darwin":
            # macOS: sysctl
            output = subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"]).decode()
            cpu_name = output.lower().strip()
        
        # Lista de CPUs modernas (con AVX2)
        modern_keywords = [
            "haswell", "broadwell", "skylake", "kabylake", "coffeelake",
            "comet lake", "ice lake", "tiger lake", "alder lake", "raptor lake",
            "ryzen", "zen", "epyc", "threadripper"
        ]
        
        # Verificar si es moderno
        is_modern = any(keyword in cpu_name for keyword in modern_keywords)
        
        # Fallback: Intentar detectar AVX2 via CPUID (más preciso)
        if not is_modern and platform.system() == "Windows":
            try:
                import cpuinfo
                flags = cpuinfo.get_cpu_info().get('flags', [])
                is_modern = 'avx2' in flags
            except:
                pass
        
        print(f"🔍 CPU detectada: {cpu_name}")
        print(f"   {'✅ Moderna (AVX2 habilitado)' if is_modern else '⚠️  Antigua (modo de compatibilidad)'}")
        
        return is_modern
        
    except Exception as e:
        print(f"⚠️ No se pudo detectar CPU: {e}")
        print("   Usando modo de compatibilidad por seguridad")
        return False

IS_WINDOWS = platform.system() == "Windows"
IS_MODERN_CPU = is_modern_cpu()

# ===== FLAGS SEGÚN CPU =====
if IS_WINDOWS:
    # Windows: MSVC
    if IS_MODERN_CPU:
        # 🔥 MÁXIMO RENDIMIENTO
        COMPILER_FLAGS = [
            "/O2",                # Máxima velocidad
            "/fp:fast",           # Fast math
            "/arch:AVX2",         # SIMD AVX2 (crítico para PPU/APU)
            "/GL",                # Whole Program Optimization
            "/Oi",                # Funciones intrínsecas
            "/Oy",                # Omitir frame pointers
            "/W3",                # Warning level 3
            "/wd4244",            # Silenciar conversiones seguras
        ]
        LINK_FLAGS = [
            "/LTCG",              # Link Time Code Generation
            "/OPT:REF",           # Eliminar código muerto
            "/OPT:ICF",           # Fusionar funciones idénticas
        ]
    else:
        # ⚠️ COMPATIBILIDAD (CPU antigua, sin AVX2)
        COMPILER_FLAGS = [
            "/O2",                # Máxima velocidad
            "/fp:fast",           # Fast math (seguro en CPUs antiguas)
            "/W3",                # Warning level 3
            "/wd4244",            # Silenciar conversiones
        ]
        LINK_FLAGS = []  # Sin LTCG para compatibilidad
else:
    # Linux/macOS: GCC/Clang
    if IS_MODERN_CPU:
        # 🔥 MÁXIMO RENDIMIENTO
        COMPILER_FLAGS = [
            "-O3",                # Máxima optimización
            "-ffast-math",        # Fast math
            "-march=native",      # Optimizar para CPU EXACTA
            "-mtune=native",      # Tune para CPU EXACTA
            "-flto",              # Link Time Optimization
            "-funroll-loops",     # Unroll loops
            "-fomit-frame-pointer", # Reducir overhead
        ]
        LINK_FLAGS = ["-flto", "-O3"]
    else:
        # ⚠️ COMPATIBILIDAD
        COMPILER_FLAGS = [
            "-O2",                # Optimización segura
            "-ffast-math",        # Fast math
            "-march=x86-64",      # x64 genérico (sin instrucciones modernas)
            "-mtune=generic",     # Tune genérico
        ]
        LINK_FLAGS = ["-O2"]

# ===== LIMPIEZA POST-BUILD =====
KEEP_CYTHON_FILES = os.environ.get('KEEP_CYTHON_FILES', '').lower() in ('1', 'true', 'yes')

class PostBuildClean(build_ext):
    def run(self):
        super().run()
        if KEEP_CYTHON_FILES:
            return
        
        print("\n🧹 Limpiando archivos intermedios...")
        cleaned = 0
        
        for pattern in ["pydmg/*.c", "pydmg/*.cpp", "pydmg/*.html"]:
            for filepath in glob.glob(pattern):
                try:
                    os.remove(filepath)
                    cleaned += 1
                except:
                    pass
        
        if os.path.exists("build"):
            shutil.rmtree("build", ignore_errors=True)
            cleaned += 1
        
        print(f"  ✅ {cleaned} elementos eliminados")

# ===== EXTENSIONES =====
extensions = [
    Extension("pydmg.cpu", ["pydmg/cpu.pyx"], include_dirs=[np.get_include()],
              extra_compile_args=COMPILER_FLAGS, extra_link_args=LINK_FLAGS,
              define_macros=[("NPY_NO_DEPRECATED_API", "NPY_1_7_API_VERSION")]),
    Extension("pydmg.ppu", ["pydmg/ppu.pyx"], include_dirs=[np.get_include()],
              extra_compile_args=COMPILER_FLAGS, extra_link_args=LINK_FLAGS,
              define_macros=[("NPY_NO_DEPRECATED_API", "NPY_1_7_API_VERSION")]),
    Extension("pydmg.timer", ["pydmg/timer.pyx"], include_dirs=[np.get_include()],
              extra_compile_args=COMPILER_FLAGS, extra_link_args=LINK_FLAGS,
              define_macros=[("NPY_NO_DEPRECATED_API", "NPY_1_7_API_VERSION")]),
    Extension("pydmg.apu", ["pydmg/apu.pyx"], include_dirs=[np.get_include()],
              extra_compile_args=COMPILER_FLAGS, extra_link_args=LINK_FLAGS,
              define_macros=[("NPY_NO_DEPRECATED_API", "NPY_1_7_API_VERSION")]),
    Extension("pydmg.mmu", ["pydmg/mmu.pyx"], include_dirs=[np.get_include()],
              extra_compile_args=COMPILER_FLAGS, extra_link_args=LINK_FLAGS,
              define_macros=[("NPY_NO_DEPRECATED_API", "NPY_1_7_API_VERSION")]),
    Extension("pydmg.gameboy", ["pydmg/gameboy.pyx"], include_dirs=[np.get_include()],
              extra_compile_args=COMPILER_FLAGS, extra_link_args=LINK_FLAGS,
              define_macros=[("NPY_NO_DEPRECATED_API", "NPY_1_7_API_VERSION")]),
]

# ===== SETUP FINAL =====
setup(
    name="pydmg",
    version="1.0.0",
    description="Game Boy Emulator Core (Auto-optimizado)",
    packages=find_packages(),
    ext_modules=cythonize(
        extensions,
        compiler_directives={
            'language_level': 3,
            'boundscheck': False,
            'wraparound': False,
            'cdivision': True,
            'initializedcheck': False,
            'profile': False,
            'always_allow_keywords': False,  # 🔥 +3% rendimiento
        },
        annotate=False,  # Desactivar para builds release
    ),
    cmdclass={'build_ext': PostBuildClean},
    install_requires=[
        "numpy>=1.19.0",
        "PySDL2>=0.9.14",
    ],
    python_requires=">=3.7",
)