# -*- coding: utf-8 -*-
"""
Las direcciones de internet del programa, todas juntas en un sitio.

Estan aqui y no repartidas por el codigo para poder cambiarlas sin buscar:
si manana cambia la cuenta de donaciones, se toca esta linea y ya esta.

Los botones que tengan la direccion vacia no se dibujan, asi que se puede
publicar el programa sin tener todavia la cuenta abierta.
"""

# La pagina del programa (donde se descarga y se lee como va)
PROYECTO = "https://github.com/ani3dgr/lmu-pit-wall"

# Donaciones. Ko-fi no cobra comision por las donaciones sueltas; PayPal es el
# que todo el mundo tiene ya. Con poner una de las dos sobra.
KOFI = ""                # p.ej. "https://ko-fi.com/tuusuario"
PAYPAL = "https://paypal.me/ani3dgr"

# El patrocinador
CICLOTRACKER = "https://ciclotracker.com"
CICLOTRACKER_ANDROID = ""    # enlace de Google Play, cuando lo haya


def abrir(direccion):
    """Abre una direccion en el navegador. No revienta si no hay ninguna."""
    if not direccion:
        return False
    import webbrowser
    try:
        webbrowser.open(direccion)
        return True
    except Exception:
        return False
