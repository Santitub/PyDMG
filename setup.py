from setuptools import setup, Extension, find_packages
from Cython.Build import cythonize
import numpy as np

extensions = [
    Extension(
        "pydmg.cpu",
        ["pydmg/cpu.pyx"],
        include_dirs=[np.get_include()],
        extra_compile_args=["-O3", "-ffast-math"],
    ),
    Extension(
        "pydmg.ppu",
        ["pydmg/ppu.pyx"],
        include_dirs=[np.get_include()],
        extra_compile_args=["-O3", "-ffast-math"],
    ),
    Extension(
        "pydmg.apu",
        ["pydmg/apu.pyx"],
        include_dirs=[np.get_include()],
        extra_compile_args=["-O3", "-ffast-math"],
    ),
    Extension(
        "pydmg.timer",
        ["pydmg/timer.pyx"],
        include_dirs=[np.get_include()],
        extra_compile_args=["-O3", "-ffast-math"],
    )
]

setup(
    name="pydmg",
    version="1.0.0",
    description="Game Boy Emulator Core",
    packages=find_packages(),
    ext_modules=cythonize(
        extensions,
        compiler_directives={
            'language_level': 3,
            'boundscheck': False,
            'wraparound': False,
            'cdivision': True,
        },
        annotate=True,
    ),
    install_requires=[
        "numpy>=1.19.0",
        "PySDL2>=0.9.14",
    ],
    python_requires=">=3.7",
)