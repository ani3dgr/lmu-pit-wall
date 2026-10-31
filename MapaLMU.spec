# -*- mode: python ; coding: utf-8 -*-
"""
Receta para compilar el mapa con PyInstaller.

Salen DOS ejecutables del mismo codigo, compartiendo una sola copia de las
librerias:

  MapaLMU.exe          sin ventana negra: es el mapa
  MapaLMU-consola.exe  con ventana negra: los escaneos y el diagnostico

Lo que NO se mete dentro del ejecutable, a proposito, para que se pueda tocar
sin recompilar: circuitos/, idiomas/, coches.json y las instrucciones. Eso lo
copia compilar.py al lado del .exe.
"""

# Modulos que se cargan por su nombre, en marcha. PyInstaller no los ve
# siguiendo los imports, asi que hay que nombrarlos aqui o no entrarian.
OCULTOS = [
    "escanear_circuito",
    "escanear_bordes",
    "escanear_boxes",
    "buscar_aviso",
    "construir_circuitos",
    "opciones",
    "visor",
    "grabador",
    "comparador",
    "catalogo",
    "coches",
    "resultados",
    "circuitos",
    "idiomas",
    "reglajes",
    "biblioteca",
    "biblioteca_gui",
    "ingenieria",
    "ingeniero_gui",
    "editor_gui",
    "manual",
    "manual_gui",
    "fov_gui",
    "paginas",
    "historial",
    "fichas",
    "fichas_gui",
    "avisos",
    "aviso_gui",
    "enlaces",
    "juego",
    "rutas",
    "lector_lmu",
    "elegir_coche",
    "bola_gui",
    "clima",
    "clima_gui",
    "registrar_clima",
    "pantalla",
    "clasificacion",
    "clasificacion_gui",
    "estrategia",
    "estrategia_gui",
    "boxes",
]

a = Analysis(
    ["mapa_pista.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=OCULTOS,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["numpy", "PIL", "matplotlib", "pytest", "setuptools", "pip"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe_mapa = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MapaLMU",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # el mapa no arrastra ventana negra
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

exe_consola = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MapaLMU-consola",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,           # los escaneos van guiando por escrito
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe_mapa,
    exe_consola,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="MapaLMU",
)
