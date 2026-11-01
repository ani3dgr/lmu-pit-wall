# -*- coding: utf-8 -*-
"""
Mapa de pista para Le Mans Ultimate.

Ventana sin bordes, fondo transparente y siempre encima, que dibuja el circuito
y la posicion de todos los coches leyendo la memoria compartida del juego.

    F9   mostrar / ocultar el mapa
    F10  abrir / cerrar las opciones
    Con las opciones abiertas se puede arrastrar el mapa con el raton,
    y ahi abajo esta el boton CERRAR EL MAPA para salir del programa.

Requiere el juego en modo BORDERLESS (Config_DX11.ini -> Borderless=1).
En pantalla completa exclusiva Windows no deja poner nada encima.

    python mapa_pista.py          normal
    python mapa_pista.py --demo   simulacion sin el juego, para ajustar colores
"""
import ctypes
import json
import math
import os
import random
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, colorchooser

import clima
import comparador as comp
import grabador as grab
import lector_lmu as lmu
import rutas
import idiomas
import opciones

CARPETA = rutas.carpeta()
CONFIG = os.path.join(CARPETA, "mapa_config.json")
CHROMA = "#010203"          # este color se vuelve transparente

# Cuanto puede diferir el largo del trazado guardado del que dice el juego
# antes de dar por hecho que son dos trazados distintos.
#
# Se pone bajo, en 10 m, porque el largo no se mide ni se estima: es el
# numero que publica el juego, y para un mismo trazado sale siempre igual.
# Dos variantes del mismo circuito se llevan poco (Silverstone WEC y ELMS,
# veintidos metros), asi que un margen generoso no las distinguiria, que es
# justo lo que hace falta cazar.
MARGEN_LARGO = 10.0
REFRESCO_MS = 50            # 20 veces por segundo
SEGUNDOS_SIN_DATOS = 3.0    # sin novedades del juego, se da la sesion por salida
SALTO_SESION = 5.0          # s de desfase del reloj de sesion contra el reloj
                            # real a partir de los cuales ya no es la misma
                            # sesion, sino otra
ESPERA_AVISO_YO = 3.0       # s dudando de cual es tu coche antes de sacar el
                            # cartel: al entrar en una sesion el juego tarda un
                            # momento en decirlo y no hay que asustar por eso


def reparto_de(cargas):
    """
    De las cuatro cargas al reparto en tanto por ciento (delante, izquierda).

    Se acota entre 0 y 100 porque en un piano o en un salto una rueda puede
    quedarse en el aire y dar fuerza negativa, y entonces salen porcentajes
    imposibles (medido: hasta -60 % y 110 %). None si no hay peso que repartir.
    """
    total = sum(cargas)
    if total < 500:                  # el coche en el aire o sin datos
        return None
    delante = 100.0 * (cargas[0] + cargas[1]) / total
    izquierda = 100.0 * (cargas[0] + cargas[2]) / total
    return (max(0.0, min(100.0, delante)), max(0.0, min(100.0, izquierda)))


def nombre_sesion(codigo):
    """1-4 practicas, 5-8 clasificacion, 9 warmup, 10-13 carrera."""
    if codigo is None or codigo == 0:
        return ""
    if codigo <= 4:
        return idiomas.t("ses.practica")
    if codigo <= 8:
        return idiomas.t("ses.clasificacion")
    if codigo == 9:
        return idiomas.t("ses.warmup")
    return idiomas.t("ses.carrera")

# Los nombres que puede dar el juego para cada categoria. La tabla esta en
# lector_lmu porque el comparador tambien la necesita, y con dos copias una se
# quedaria atras el dia que aparezca una clase nueva.
ALIAS_CLASE = lmu.ALIAS_CLASE

POR_DEFECTO = {
    "x": 40, "y": 40, "tamano": 394,
    "mostrar_oponentes": True,
    "mostrar_numeros": True,
    "ver_numero_curva": True,
    "ver_nombre_curva": False,
    "usar_colores_clase": True,
    "radio_yo": 9, "radio_rival": 7,
    "color_yo": "#00ff00",
    "color_rival": "#9aa0a6",
    "color_pista": "#b0b0b0",
    "grosor_pista": 5,
    "opacidad": 0.9,
    # Veces por segundo que se REDIBUJA el mapa. Leer y grabar van siempre a 20,
    # asi que bajar esto no cuesta ni una vuelta guardada: solo hace que los
    # coches se muevan con menos suavidad. Sirve para ordenadores justos, porque
    # cada redibujado obliga a Windows a mezclar la ventana con el juego.
    "dibujos_por_segundo": 20,
    "tam_numero": 7,
    "tam_curva": 8,
    "color_curva": "#ffd24a",
    "comparar": True,
    "ver_texto_estado": True,
    "ver_sesion": True,
    "tam_estado": 11,
    "ver_patrocinador": True,
    "tam_patrocinador": 10,
    "color_referencia": "#b06cff",
    "color_lento": "#ff3b30",
    "color_igual": "#ffd60a",
    "color_rapido": "#32d74b",
    "ver_parados": True,
    "color_parado": "#ffd60a",
    # El aviso grande de coche parado. Va aparte del mapa porque el mapa
    # se mira cuando se puede y esto tiene que verte a ti.
    "aviso_parados": True,
    "aviso_segundos": 8,
    "aviso_color": "#ff2d2d",
    "aviso_tam": 26,
    "aviso_x": 700,
    "aviso_y": 120,
    "aviso_sonar": True,
    # Al 60 y no al maximo a proposito: un pitido a todo volumen que no
    # esperas, conduciendo, da un susto de verdad. Que suba quien quiera.
    "aviso_volumen": 60,
    "aviso_sonido": "doble.wav",
    "aviso_texto": "",
    # El aviso de los frenos (frenos.py): roto, o que toca cambiarlos.
    "frenos_aviso": True,
    "frenos_aviso_min": 60,
    "frenos_cartel_x": 700,
    "frenos_cartel_y": 190,
    # El panel de los frenos (frenos_gui.py). Apagado de salida, como el clima.
    "frenos_ver": False,
    "frenos_panel_x": 60,
    "frenos_panel_y": 480,
    "frenos_tam": 100,
    "frenos_opacidad": 0.95,
    "frenos_fondo": True,
    "frenos_color_fondo": "#0d1116",
    "frenos_color_texto": "#ffffff",
    # El panel de clasificacion (clasificacion_gui.py): los tiempos de todos.
    "tabla_ver": False,
    "tabla_x": 60,
    "tabla_y": 200,
    "tabla_tam": 100,
    "tabla_filas": 60,
    "tabla_ancho": 0,               # 0 = el de la tabla; si no, estirado a mano
    "tabla_columnas": None,         # None: las de salida (clasificacion_gui)
    "tabla_solo_clase": False,
    "tabla_opacidad": 0.95,
    "tabla_fondo": True,
    "tabla_color_fondo": "#0d1116",
    "tabla_color_texto": "#ffffff",
    # El panel de estrategia (estrategia_gui.py): la prediccion de carrera.
    "estr_ver": False,
    "estr_x": 60,
    "estr_y": 300,
    "estr_tam": 100,
    "estr_filas": 15,
    "estr_ancho": 0,
    "estr_minutos": 0,              # 0 = tras el ciclo de paradas
    "estr_opacidad": 0.95,
    "estr_fondo": True,
    "estr_color_fondo": "#0d1116",
    "estr_color_texto": "#ffffff",
    "yo_anillo": True,
    # La bola de reparto de carga (el circulo con el punto que se mueve)
    "bola_ver": False,
    "bola_x": 60,
    "bola_y": 60,
    "bola_tam": 130,
    "bola_circulo": True,
    "bola_numeros": False,
    # 2,5 G llena el circulo. Medido en Daytona con el LMP2: con esa escala el
    # punto toca el borde el 1,5 % del tiempo -o sea, en lo mas fuerte de la
    # frenada y de las curvas rapidas- y el resto del rato se mueve por dentro.
    # Con 3 G no llegaba al borde casi nunca y el dibujo se quedaba soso.
    "bola_escala": 2.5,
    # Cuanto se frena el punto. 0 = tal cual llega del juego, que es como
    # estaba y bailaba demasiado para poder leerlo conduciendo.
    "bola_suavidad": 75,
    "bola_color_punto": "#00ff00",
    "bola_color_circulo": "#b0b0b0",
    "bola_color_numeros": "#ffffff",
    # El panel del clima. Va apagado de salida como los demas instrumentos:
    # quien lo quiera lo enciende, y quien no, ni se enteraba de que existe.
    "clima_ver": False,
    "clima_x": 60,
    "clima_y": 260,
    "clima_tam": 100,
    "clima_opacidad": 1.0,
    # Con fondo por defecto: los numeros pequenos encima de un cielo claro o
    # de un muro blanco no se leen, y este panel se mira de reojo. Sin fondo
    # el texto se pinta con sombra, que ayuda pero no tanto.
    "clima_fondo": True,
    "clima_color_fondo": "#0d1116",
    "clima_color_texto": "#ffffff",
    "clima_color_aviso": "#ff9f0a",
    "clima_ahora": True,
    "clima_pronostico": True,
    "clima_temps": True,
    "clima_pista": True,
    "clima_hora": True,
    "clima_viento": False,
    "clima_humedad": False,
    "clima_aviso_lluvia": True,
    # Que sesion ensena el pronostico: "auto" la que se este corriendo, o una
    # fija. Ponerlo en "race" en los libres es lo que da la ventaja: se ve lo
    # que va a caer en la carrera antes de decidir la estrategia.
    "clima_que_sesion": "auto",
    # Que se rotula encima de cada punto del pronostico: "circuito" la hora
    # del circuito (la del sol que se ve por el parabrisas, que es la que
    # manda para el clima y los faros) o "falta" lo que queda de carrera.
    #
    # Por defecto la del circuito, porque es la misma que ensenan las
    # pantallas del juego y asi los dos numeros cuadran. OJO: no es la hora
    # real. El juego mete la carrera en la franja de tarde del circuito -una
    # de 6 h empezada a las 17:23 reales salia a las 14:00 del circuito- asi
    # que las dos van desfasadas, y si la escala de tiempo no es 1 el desfase
    # ademas crece.
    "clima_reloj": "circuito",
    "ver_salidas": True,
    # Por defecto NO: en carrera el juego solo publica la salida cuando llega
    # a sancionar, y los avisos de limites de pista no salen en la memoria
    # compartida. Fiandolo solo al juego se pierden casi todas las salidas.
    "salidas_segun_juego": False,
    "margen_salida": 0.8,
    "color_salida": "#ff9f0a",
    "tam_salida": 10,
    "colores_clase": {
        "hypercar": "#ff4a3d",
        "lmp2": "#3ddc84",
        "lmgt3": "#4aa8ff",
    },
}


def cargar_config():
    cfg = dict(POR_DEFECTO)
    cfg["colores_clase"] = dict(POR_DEFECTO["colores_clase"])
    try:
        # utf-8-sig y no utf-8: el Bloc de notas y PowerShell anaden un BOM
        # invisible al guardar, y con utf-8 eso tumba toda la configuracion
        with open(CONFIG, encoding="utf-8-sig") as f:
            guardado = json.load(f)
        cfg.update({k: v for k, v in guardado.items() if k != "colores_clase"})
        cfg["colores_clase"].update(guardado.get("colores_clase", {}))
    except (OSError, ValueError):
        pass
    return cfg


def guardar_config(cfg):
    try:
        with open(CONFIG, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


# ---------------- suavizado del movimiento ----------------
class Suavizado:
    """
    El buffer de scoring solo se refresca 5 veces por segundo (medido), pero el
    mapa dibuja 20, asi que los coches irian a saltos. Entre dato y dato se
    estima donde estan prolongando su ultimo desplazamiento conocido.
    """
    ADELANTO_MAX = 0.35     # s que se predice como mucho antes de quedarse quieto
    VELOCIDAD_MAX = 120.0   # m/s; evita que un coche teletransportado salga disparado

    def __init__(self):
        self.hist = {}

    def reinicia(self):
        self.hist.clear()

    def posicion(self, clave, x, z, ahora):
        h = self.hist.get(clave)
        if h is None:
            self.hist[clave] = {"pos": (x, z), "t": ahora, "v": (0.0, 0.0)}
            return x, z

        if (x, z) != h["pos"]:                     # ha llegado dato nuevo
            dt = ahora - h["t"]
            if 0.02 < dt < 1.0:
                vx, vz = (x - h["pos"][0]) / dt, (z - h["pos"][1]) / dt
                if math.hypot(vx, vz) <= self.VELOCIDAD_MAX:
                    h["v"] = (vx, vz)
                else:
                    h["v"] = (0.0, 0.0)            # salto imposible: no predecir
            h["pos"], h["t"] = (x, z), ahora

        adelanto = min(ahora - h["t"], self.ADELANTO_MAX)
        return h["pos"][0] + h["v"][0] * adelanto, h["pos"][1] + h["v"][1] * adelanto


# ---------------- teclas globales ----------------
_user32 = ctypes.windll.user32
VK = {"F9": 0x78, "F10": 0x79, "F11": 0x7A}


class Teclas:
    """Detecta pulsaciones aunque el foco lo tenga el juego."""

    def __init__(self):
        self.antes = {k: False for k in VK}

    def pulsada(self, nombre):
        # bit 0x8000 = la tecla esta pulsada ahora mismo
        # bit 0x0001 = se pulso en algun momento desde la consulta anterior,
        #              lo que rescata los toques cortos entre sondeo y sondeo
        estado = _user32.GetAsyncKeyState(VK[nombre])
        ahora = bool(estado & 0x8000)
        desde_antes = bool(estado & 0x0001)
        nueva = (ahora and not self.antes[nombre]) or (desde_antes and not ahora)
        self.antes[nombre] = ahora
        return nueva


def click_atraviesa(hwnd, activar):
    """Que los clicks pasen al juego y la ventana nunca robe el foco."""
    GWL_EXSTYLE = -20
    WS_EX_LAYERED = 0x80000
    WS_EX_TRANSPARENT = 0x20
    WS_EX_NOACTIVATE = 0x8000000
    try:
        estilo = _user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        if activar:
            estilo |= WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE
        else:
            estilo &= ~(WS_EX_TRANSPARENT | WS_EX_NOACTIVATE)
        _user32.SetWindowLongW(hwnd, GWL_EXSTYLE, estilo)
    except Exception:
        pass


# ---------------- fuente de datos simulada ----------------
class Demo:
    """Reproduce un escaneo como si fuera el juego, para ajustar sin conducir."""

    def __init__(self):
        circuitos = lmu.cargar_circuitos()
        clave = "circuitdespafrancorchamps"
        if clave not in circuitos:
            clave = sorted(circuitos)[0]
        self.datos = circuitos[clave]
        self.aviso = ""
        pts = self.datos["puntos"]
        self.largo = sum(math.hypot(pts[(i + 1) % len(pts)][0] - pts[i][0],
                                    pts[(i + 1) % len(pts)][1] - pts[i][1])
                         for i in range(len(pts)))
        clases = ["Hypercar", "LMP2", "LMGT3"]
        self.lista = [{
            "nombre": "Piloto %d" % (i + 1),
            "i": random.randrange(len(pts)),
            "paso": random.uniform(0.20, 0.30),
            "clase": clases[i % 3],
            "es_yo": i == 0,
            "puesto": i + 1,
            "vueltas": 0,
            "ultima": 0.0,
        } for i in range(14)]
        self.lista[0]["nombre"] = "Manuel"

    def leer(self):
        pts = self.datos["puntos"]
        salida = []
        for c in self.lista:
            antes = c["i"]
            c["i"] = (c["i"] + c["paso"]) % len(pts)
            if c["i"] < antes:                       # ha cruzado la meta
                c["vueltas"] += 1
                # a mayor paso, vuelta mas rapida: da tiempos coherentes
                c["ultima"] = round(len(pts) / c["paso"] * (REFRESCO_MS / 1000.0), 3)
            x, z = pts[int(c["i"])]
            salida.append({"nombre": c["nombre"], "x": x, "z": z,
                           "clase": c["clase"], "es_yo": c["es_yo"],
                           "puesto": c["puesto"],
                           "dist": c["i"] / float(len(pts)) * self.largo,
                           "vueltas": c["vueltas"], "mejor": c["ultima"],
                           "ultima": c["ultima"]})
        return salida


# ---------------- fuente de datos real ----------------
class Juego:
    def __init__(self):
        self.sco = None
        self.circuitos = lmu.cargar_circuitos()
        self.clave = None
        self.datos = None
        self.aviso = idiomas.t("map.esperando_juego")
        self.off_puesto = None
        self.largo = 0.0
        self.sesion = None
        self.fase_juego = 0
        self.estado = ""
        self.tele = None               # G y cargas de TU coche
        self.yo_origen = None          # de donde ha salido "mi coche"
        self.yo_fiable = False         # y si esa via lo SABE o lo supone
        self.nueva_sesion = False      # obliga a empezar de cero
        self.congelado = False         # el juego no publica: pausa o menu
        self.publicando = False        # si AHORA MISMO llegan datos frescos.
                                       # El panel del clima lo necesita: la
                                       # memoria compartida se queda con lo
                                       # ultimo cuando el juego se cierra, y
                                       # sin esto seguia ensenando la
                                       # temperatura y la hora de la ultima
                                       # sesion como si nada
        self._version = None
        self._version_desde = 0.0
        self._et = None
        self._et_real = None   # reloj real, para saber si el de sesion salta
        self._ultimos = []

    def leer(self):
        """Devuelve la lista de coches, o [] si aun no hay datos utilizables."""
        try:
            if self.sco is None:
                self.sco = lmu.Scoring()
            sco = self.sco
        except OSError:
            self.sco = None
            self.datos = None
            self.publicando = False
            self.aviso = idiomas.t("map.esperando_juego")
            return []

        # Al salir al menu principal el juego DEJA DE PUBLICAR pero la memoria
        # se queda con lo ultimo: mismo circuito, mismos coches. Sin esto el
        # mapa seguiria pintando una sesion que ya no existe. El contador de
        # version de la cabecera es lo que delata que ya no llegan datos.
        #
        # OJO: NO sirve `mOptionsLocation` de la memoria propia de LMU, que en
        # la documentacion promete 0=menu 1=cargando 2=monitor 3=en pista.
        # Medido el 28/08/2026: **LMU lo deja clavado en 0 siempre**, tambien
        # dentro de una sesion con coches en pista. Es un campo heredado de
        # rFactor que el juego no rellena. Se probo y dejaba el mapa en blanco.
        version = sco.version()
        ahora = time.monotonic()
        if version != self._version:
            self._version, self._version_desde = version, ahora
        if ahora - self._version_desde > SEGUNDOS_SIN_DATOS:
            # Ha dejado de publicar. Puede ser que hayas SALIDO de la sesion o
            # que la tengas en PAUSA, y desde fuera se ven igual. Se le
            # pregunta al juego si ha descargado el circuito: si lo ha hecho,
            # la sesion se acabo y no hay nada que pintar.
            if sco.circuito_descargado():
                self.datos = None
                self.congelado = False
                self.publicando = False
                self.estado = ""
                self._ultimos = []
                sco.fijar_coche(None)  # fuera de sesion, el coche elegido
                                       # ya no vale: los mID cambian
                self.aviso = idiomas.t("map.entra_circuito")
                return []
            # El circuito sigue cargado, asi que la sesion sigue viva: es una
            # pausa, una carga o una repeticion, y no se borra nada. Se
            # deja la ultima imagen y se avisa de que esta congelada, para
            # poder seguir ajustando colores y grosores con el juego en pausa,
            # que es cuando hace falta.
            self.congelado = True
            self.publicando = False
            if self.datos:
                self.estado = idiomas.t("map.pausa")
                return self._ultimos
            self.aviso = idiomas.t("map.entra_circuito")
            return []

        self.congelado = False
        self.publicando = True

        n = sco.n_coches()
        if n == 0:
            self.datos = None
            self.estado = ""
            self.aviso = idiomas.t("map.esperando_pista")
            return []

        nombre_pista = sco.circuito()
        # Se le pasa el largo para que pueda elegir entre dos trazados que se
        # llaman igual. Portimao publica "Algarve International Circuit" tanto
        # en su version normal como en la de ELMS, y por el nombre no hay
        # manera de saber cual es.
        clave, datos = lmu.buscar_circuito(self.circuitos, nombre_pista,
                                           sco.largo_pista())
        if not datos:
            self.datos = None
            self.aviso = idiomas.t("map.sin_escanear") % (nombre_pista or "?")
            return []

        if clave != self.clave:                    # circuito nuevo -> recalibrar
            self.clave = clave
            sco.off_pos = None

        if sco.off_pos is None:
            off, informe = lmu.calibrar(sco.sco, datos, n, verboso=True)
            print("[calibracion] %s -> %s" % (datos["nombre"], informe))
            lmu.apuntar("calibracion en %s: %s" % (datos["nombre"], informe))
            if off is None:
                self.datos = None
                self.aviso = "Calibrando..."
                return []
            sco.off_pos = off
            sco.off_jugador = lmu.buscar_jugador(sco.sco, n)
            sco.off_clase = lmu.calibrar_clase(sco.sco, n) or lmu.OFF_CLASE
            self.off_puesto = lmu.calibrar_puesto(sco.sco, n) or lmu.OFF_PUESTO
            print("[calibracion] jugador=%s clase=%s puesto=%s"
                  % (sco.off_jugador, sco.off_clase, self.off_puesto))
            lmu.apuntar("calibracion: jugador=%s clase=%s puesto=%s"
                        % (sco.off_jugador, sco.off_clase, self.off_puesto))

        self.datos = datos
        self.largo = sco.largo_pista()
        # El reloj de sesion es lo unico que distingue una practica de la
        # practica siguiente: el codigo de sesion vale 1 en las dos. Ya no se
        # usa el "dejar de publicar" para esto, porque eso tambien ocurre al
        # pausar y borraria los datos por una simple pausa.
        et = sco.tiempo_sesion()
        real = time.monotonic()
        if self._et is not None and self._et_real is not None:
            salto = et - self._et
            paso = real - self._et_real
            # El reloj de sesion avanza un segundo por cada segundo real. Si
            # pega un salto que no cuadra con el tiempo que ha pasado de
            # verdad, es que estas en OTRA sesion, no en la de antes.
            #
            # Mirar solo si RETROCEDE no basta, y costo una manana verlo: al
            # salir de una practica propia y entrar en una SALA DE PRACTICAS
            # ONLINE que llevaba rato abierta, el reloj no retrocede, pega un
            # salto hacia ADELANTE (medido: de unos cientos de segundos a
            # 4991). Circuito, medida y codigo de sesion son los mismos -las
            # dos son "practica"- asi que el mapa creia que seguias donde
            # estabas y se traia las salidas de pista de la sesion anterior:
            # al entrar al garaje el mapa aparecia lleno de triangulos sin
            # haber rodado.
            #
            # Una pausa no dispara esto: ahi el reloj se para, no salta.
            if salto < -SALTO_SESION or salto > paso + SALTO_SESION:
                self.nueva_sesion = True
                # Otra sesion, otro coche: se suelta el que estuviera fijado
                # -incluso el elegido a mano- para que el lector vuelva a
                # buscar cual eres tu. Los mID no sobreviven a un cambio de
                # sesion, asi que conservarlo apuntaria a un coche cualquiera.
                sco.fijar_coche(None)
        self._et = et
        self._et_real = real

        self.sesion = sco.sesion()
        self.fase_juego = sco.fase_juego()
        self.estado = nombre_sesion(self.sesion)
        coches = sco.coches()
        # OJO: mInRealtime habla de TI, no del coche. En una carrera por
        # equipos, mientras conduce el companero tu figuras "en el garaje"
        # pero el coche esta rodando y el mapa lo sigue perfectamente. Poner
        # "(garaje)" a secas asustaba, porque parecia que no se estaba
        # grabando nada, y si se graba (con el nombre de quien va al volante
        # pegado a cada vuelta). Se mira si TU coche esta en boxes para
        # separar las dos situaciones.
        self.conduzco = sco.en_pista()
        if not self.conduzco:
            yo = next((c for c in coches if c.get("es_yo")), None)
            quien = (yo or {}).get("nombre") or ""
            if yo is not None and not yo.get("en_boxes") and quien:
                self.estado += idiomas.t("ses.conduce_otro") % quien
            else:
                self.estado += idiomas.t("ses.garaje")
        self.tele = sco.telemetria()
        self.yo_origen = sco.origen_yo
        self.yo_fiable = sco.yo_fiable
        if self.off_puesto is not None:
            # OJO con el indice: es el de la FICHA en el buffer, no el de la
            # fila en esta lista. La lista se salta los coches cuya posicion no
            # se puede leer, asi que en cuanto falta uno las dos numeraciones
            # dejan de cuadrar y cada coche se quedaba con el puesto de otro.
            for c in coches:
                c["puesto"] = lmu.u1(sco.sco,
                                     lmu.SCO_BASE + c["ficha"] * lmu.SCO_STRIDE
                                     + self.off_puesto)
            self._puesto_de_clase(coches)
        self.aviso = ""
        self._ultimos = coches
        return coches

    def _puesto_de_clase(self, coches):
        """
        Cambia el puesto general por el puesto DENTRO DE TU CLASE.

        El juego publica `mPlace`, que es el puesto general contando todas las
        categorias juntas. Pero en una carrera multiclase eso no es lo que
        nadie mira: la pantalla de tiempos del propio juego, y los pilotos,
        cuentan por clase.

        Medido en carrera el 28/08/2026: 20 coches, 5 Hypercar y 15 GT3. Los
        Hypercar ocupan del 1 al 5, asi que los GT3 van del 6 al 20 y el coche
        que iba **19 general** era en realidad el **14 de GT3**. El mapa ponia
        19 y en la pantalla del juego se veia 14.

        Se hace ordenando por el puesto general dentro de cada clase, que asi
        no hay que saber cuantos coches lleva cada categoria ni si alguna se ha
        quedado sin ninguno.
        """
        por_clase = {}
        for c in coches:
            if not c.get("puesto"):
                continue
            familia = lmu.familia(c.get("clase") or "")
            if not familia:
                # Coche sin categoria: los que estan a medio conectar o que no
                # han llegado a salir. Antes se metian todos en un mismo saco y
                # se les repartia un 1, un 2, un 3... que no significaban nada
                # y confundian con los puestos de verdad. Se quedan con el
                # puesto general, que es lo unico que se sabe de ellos.
                continue
            por_clase.setdefault(familia, []).append(c)
        for iguales in por_clase.values():
            for sitio, c in enumerate(sorted(iguales, key=lambda x: x["puesto"]), 1):
                c["puesto"] = sitio


# ---------------- ventana del mapa ----------------

ERRORES = "errores.txt"
ERRORES_MAX = 200 * 1024        # medio megabyte de errores ya es de sobra


def apuntar_fallo():
    """
    Deja constancia de un fallo, con su hora, en errores.txt.

    No basta con imprimirlo: el mapa se abre sin ventana negra para no molestar
    mientras juegas, asi que un mensaje por pantalla no lo lee nadie. Sin esto,
    el programa puede quedarse a medias -por ejemplo dejar de grabar vueltas- y
    parecer que va bien.
    """
    import traceback
    traceback.print_exc()
    try:
        ruta = rutas.datos(ERRORES)
        if os.path.isfile(ruta) and os.path.getsize(ruta) > ERRORES_MAX:
            os.remove(ruta)
        with open(ruta, "a", encoding="utf-8") as f:
            f.write("\n===== %s =====\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
            traceback.print_exc(file=f)
    except Exception:
        pass


class Mapa:
    def __init__(self, fuente):
        self.cfg = cargar_config()
        self.fuente = fuente
        self.teclas = Teclas()
        self.opciones = None
        self.eleccion = None            # ventana de "cual es tu coche" (F11)
        self._dudando_desde = None      # desde cuando no se sabe cual eres
        self._elegido_restaurado = False
        self.visible = True
        self.arrastre = None
        self.modo_mover = False     # con las opciones abiertas se puede arrastrar
        self.suave = Suavizado()
        self._fuentes = {}
        self.comparador = None
        self.avisador = None
        self.avisa_frenos = None
        self.panel_frenos = None
        self.tabla = None
        self.estrategia = None
        self.bola = None
        self._bola_pos = [0.0, 0.0]     # el punto ya suavizado
        self.clima = None
        self.grabador = None

        self.root = tk.Tk()
        self.root.title(idiomas.t("map.titulo"))
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-transparentcolor", CHROMA)
        self.root.attributes("-alpha", self.cfg["opacidad"])
        self.root.config(bg=CHROMA)

        t = self.cfg["tamano"]
        self.root.geometry("%dx%d+%d+%d" % (t, t, self.cfg["x"], self.cfg["y"]))
        self.lienzo = tk.Canvas(self.root, bg=CHROMA, highlightthickness=0,
                                width=t, height=t)
        self.lienzo.pack(fill="both", expand=True)

        self.lienzo.bind("<Button-1>", self._empezar_arrastre)
        self.lienzo.bind("<B1-Motion>", self._arrastrar)

        self.root.update_idletasks()
        self.hwnd = _user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
        click_atraviesa(self.hwnd, True)

        self.root.after(REFRESCO_MS, self.tick)

    # ---- arrastre (solo con las opciones abiertas) ----
    def _empezar_arrastre(self, e):
        self.arrastre = (e.x, e.y)

    def _arrastrar(self, e):
        if not self.arrastre:
            return
        self.cfg["x"] += e.x - self.arrastre[0]
        self.cfg["y"] += e.y - self.arrastre[1]
        self.root.geometry("+%d+%d" % (self.cfg["x"], self.cfg["y"]))

    # ---- dibujo ----
    def color_de(self, coche):
        if coche.get("es_yo"):
            return self.cfg["color_yo"]
        if self.cfg["usar_colores_clase"]:
            clase = (coche.get("clase") or "").lower().replace(" ", "")
            for cl, color in self.cfg["colores_clase"].items():
                if any(a in clase for a in ALIAS_CLASE.get(cl, (cl,))):
                    return color
        return self.cfg["color_rival"]

    def dibujar(self, coches):
        c = self.lienzo
        c.delete("all")
        t = self.cfg["tamano"]

        if self.modo_mover:
            # Superficie opaca para poder agarrar el mapa: sobre el fondo
            # transparente el raton pasa de largo y no hay nada que arrastrar.
            c.create_rectangle(0, 0, t - 1, t - 1, fill="#202020", outline="#ffcc00",
                               width=2, dash=(6, 4))
            c.create_text(t // 2, 14, text=idiomas.t("map.arrastra"),
                          fill="#ffcc00", font=("Segoe UI", 9, "bold"))

        datos = getattr(self.fuente, "datos", None)
        if not datos:
            self.suave.reinicia()      # cambio de sesion: el historial ya no vale
            aviso = getattr(self.fuente, "aviso", "")
            if aviso:
                c.create_text(t // 2, t // 2, text=aviso, fill=self.cfg["color_pista"],
                              font=("Segoe UI", 10), justify="center")
            return

        x0, z0, x1, z1 = datos["limites"]
        margen = max(self.cfg["radio_yo"], self.cfg["radio_rival"]) + 6
        ancho, alto = max(x1 - x0, 1), max(z1 - z0, 1)
        # Banda libre arriba para el rotulo de la comparacion: si no, el texto
        # queda pegado al trazado y se lee mal en marcha.
        cuantas = len(self._lineas_rotulo())
        banda = 8 + cuantas * (self.cfg["tam_estado"] + 5) if cuantas else 0
        util = t - banda
        escala = min((t - 2 * margen) / ancho, (util - 2 * margen) / alto)
        despx = (t - ancho * escala) / 2
        despy = (util - alto * escala) / 2

        def a_pantalla(x, z):
            return (despx + (x - x0) * escala,
                    banda + util - (despy + (z - z0) * escala))  # Z crece hacia arriba

        pantalla = [a_pantalla(x, z) for x, z in datos["puntos"]]
        puntos = []
        for px, py in pantalla:
            puntos.extend((px, py))
        puntos.extend(puntos[:2])                       # cerrar el circuito

        comparando = (self.cfg["comparar"] and self.comparador is not None
                      and self.comparador.referencia)
        base = self.cfg["color_referencia"] if comparando else self.cfg["color_pista"]
        c.create_line(*puntos, fill=base, width=self.cfg["grosor_pista"],
                      capstyle="round", joinstyle="round")
        if comparando:
            self._pintar_comparacion(c, pantalla)

        self._dibujar_salidas(c, a_pantalla, pantalla)
        self._dibujar_curvas(c, datos, a_pantalla, t)
        self._dibujar_textos(c, t)

        ahora = time.monotonic()
        accidentados = set()
        if self.cfg["ver_parados"] and self.comparador is not None:
            accidentados = self.comparador.parados(coches)
        self._avisar_de_parados(coches, accidentados)
        # medio segundo encendido, medio apagado
        destello = int(ahora * 2) % 2 == 0

        yo = yo_pos = None
        for i, coche in enumerate(coches):
            x, z = self.suave.posicion(i, coche["x"], coche["z"], ahora)
            if coche.get("es_yo"):
                yo, yo_pos = coche, (x, z)
                continue
            if self.cfg["mostrar_oponentes"]:
                accidentado = coche.get("nombre") in accidentados
                color = self.color_de(coche)
                radio = self.cfg["radio_rival"]
                if accidentado:
                    # parpadea y se agranda: la gracia es verlo de un vistazo
                    # sin apartar la vista de la carretera
                    color = self.cfg["color_parado"] if destello else color
                    radio = radio + 3
                self._punto(c, a_pantalla(x, z), radio, color, coche,
                            resaltar=accidentado and destello)
        if yo:                                           # el jugador, siempre el ultimo
            self._punto(c, a_pantalla(*yo_pos),
                        self.cfg["radio_yo"], self.color_de(yo), yo, resaltar=True,
                        hueco=self.cfg["yo_anillo"])

    def _texto_con_sombra(self, c, x, y, texto, color, tam, anclaje="center"):
        """El mapa va sobre la imagen del juego: sin sombra el texto se pierde."""
        for ox, oy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
            c.create_text(x + ox, y + oy, text=texto, fill="#000000",
                          font=("Segoe UI", tam, "bold"), anchor=anclaje)
        c.create_text(x, y, text=texto, fill=color,
                      font=("Segoe UI", tam, "bold"), anchor=anclaje)

    def _ancho(self, texto, tam):
        """Cuanto ocupa un texto en pixeles con ese tamano de letra."""
        try:
            import tkinter.font as tkfont
            clave = ("Segoe UI", tam)
            if clave not in self._fuentes:
                self._fuentes[clave] = tkfont.Font(family=clave[0], size=tam,
                                                   weight="bold")
            return self._fuentes[clave].measure(texto)
        except Exception:
            return len(texto) * tam * 0.62      # estimacion de respaldo

    def _lineas_rotulo(self):
        """
        Lo que va escrito arriba del mapa: una linea por cosa, con su color.

        La primera es el aviso de que el mapa no sabe cual eres tu, y va la
        primera y en rojo a proposito: es lo unico que puede dejar todo lo
        demas sin valor. En Silverstone el mapa siguio a otro coche seis horas
        sin decir ni pio.
        """
        lineas = []
        aviso = self._aviso_de_quien_soy()
        if aviso:
            lineas.append((aviso, self.cfg["aviso_color"]))
        if self.cfg["ver_sesion"]:
            sesion = getattr(self.fuente, "estado", "")
            if sesion:
                lineas.append((sesion, self.cfg["color_referencia"]))
        if (self.cfg["comparar"] and self.comparador is not None
                and self.cfg["ver_texto_estado"]):
            lineas.append((self.comparador.texto_estado(),
                           self.cfg["color_referencia"]))
        return lineas

    def _aviso_de_quien_soy(self):
        """
        Cartel de "ojo, que igual no eres tu ese coche". "" cuando no hay duda.

        Solo se calla si la eleccion viene de una via que SABE la respuesta: el
        propio juego o el usuario. Si el mapa ha tenido que deducirlo por el
        nombre del piloto, lo dice; y si no lo sabe nadie, lo dice mas alto.
        """
        origen = getattr(self.fuente, "yo_origen", "juego")
        fiable = getattr(self.fuente, "yo_fiable", True)
        if origen is not None and fiable:
            self._dudando_desde = None
            return ""
        ahora = time.monotonic()
        if self._dudando_desde is None:
            self._dudando_desde = ahora
        if ahora - self._dudando_desde < ESPERA_AVISO_YO:
            return ""                    # dale un momento al juego
        return idiomas.t("map.yo_desconocido" if origen is None
                         else "map.yo_sin_confirmar")

    def _dibujar_textos(self, c, t):
        # Una linea por cosa: juntas se salian del mapa por los dos lados,
        # porque el ancho del mapa es pequeno y los textos largos.
        tam = self.cfg["tam_estado"]
        for n, (texto, color) in enumerate(self._lineas_rotulo()):
            # si el mapa es pequeno el texto no cabe y se sale por los lados,
            # asi que se encoge la letra hasta que entre
            propio = tam
            while propio > 6 and self._ancho(texto, propio) > t - 10:
                propio -= 1
            self._texto_con_sombra(c, t / 2, 4 + tam + n * (tam + 5), texto,
                                   color, propio)

    def _pintar_comparacion(self, c, pantalla):
        """
        Encima del trazado de la referencia se superponen los tramos que ya has
        pasado en esta vuelta: rojo si vas mas lento, amarillo si igual, verde
        si le has ganado. Solo se pintan los tramos ya medidos.
        """
        colores = {
            "lento": self.cfg["color_lento"],
            "igual": self.cfg["color_igual"],
            "rapido": self.cfg["color_rapido"],
        }
        n = len(pantalla)
        por_tramo = n / float(comp.TRAMOS)
        grosor = self.cfg["grosor_pista"] + 2

        for k, veredicto in enumerate(self.comparador.colores()):
            if not veredicto:
                continue
            ini = int(k * por_tramo)
            fin = int((k + 1) * por_tramo)
            trozo = []
            for i in range(ini, fin + 1):
                px, py = pantalla[i % n]
                trozo.extend((px, py))
            if len(trozo) >= 4:
                c.create_line(*trozo, fill=colores[veredicto], width=grosor,
                              capstyle="round", joinstyle="round")

    def _dibujar_salidas(self, c, a_pantalla, pantalla):
        """
        Triangulo de aviso donde te saliste la ultima vez que pasaste por ahi.

        Se guarda la posicion real que tenia el coche al salirse, asi que basta
        con apartar el simbolo en esa misma direccion respecto al trazado para
        que caiga siempre del lado correcto y sin taparlo.
        """
        if not (self.cfg["ver_salidas"] and self.comparador is not None):
            return
        r = self.cfg["tam_salida"]
        separacion = self.cfg["grosor_pista"] + r + 4

        for datos_salida in self.comparador.salidas.values():
            px, py = a_pantalla(datos_salida["x"], datos_salida["z"])
            # punto del trazado mas cercano, para saber hacia donde apartarlo
            cx, cy = min(pantalla, key=lambda q: (q[0] - px) ** 2 + (q[1] - py) ** 2)
            dx, dy = px - cx, py - cy
            largo = math.hypot(dx, dy)
            if largo < 1.0:                     # justo encima de la linea
                dx, dy, largo = px - self.cfg["tamano"] / 2, py - self.cfg["tamano"] / 2, None
                largo = math.hypot(dx, dy) or 1.0
            ex = cx + dx / largo * separacion
            ey = cy + dy / largo * separacion

            c.create_polygon(ex, ey - r, ex - r, ey + r * 0.8, ex + r, ey + r * 0.8,
                             fill=self.cfg["color_salida"], outline="#000000", width=1)
            c.create_text(ex, ey + r * 0.15, text="!", fill="#000000",
                          font=("Segoe UI", max(6, int(r * 1.1)), "bold"))

    def _dibujar_curvas(self, c, datos, a_pantalla, t):
        """Numero y/o nombre junto a cada curva, apartados hacia afuera del
        trazado para que no tapen la linea ni a los coches."""
        if not (self.cfg["ver_numero_curva"] or self.cfg["ver_nombre_curva"]):
            return
        curvas = datos.get("curvas") or []
        if not curvas:
            return

        centro = t / 2.0
        for cur in curvas:
            partes = []
            if self.cfg["ver_numero_curva"]:
                partes.append(str(cur["n"]))
            if self.cfg["ver_nombre_curva"] and cur.get("nombre"):
                partes.append(cur["nombre"])
            if not partes:
                continue

            px, py = a_pantalla(cur["x"], cur["z"])
            # apartar la etiqueta alejandola del centro del mapa
            dx, dy = px - centro, py - centro
            dist = math.hypot(dx, dy) or 1.0
            sep = 6 + self.cfg["tam_curva"]
            ex, ey = px + dx / dist * sep, py + dy / dist * sep

            texto = " ".join(partes)
            # sombra oscura debajo: el mapa va sobre imagen del juego y si no
            # el texto claro se pierde en las zonas claras
            for ox, oy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
                c.create_text(ex + ox, ey + oy, text=texto, fill="#000000",
                              font=("Segoe UI", self.cfg["tam_curva"], "bold"))
            c.create_text(ex, ey, text=texto, fill=self.cfg["color_curva"],
                          font=("Segoe UI", self.cfg["tam_curva"], "bold"))

    def _punto(self, c, pos, r, color, coche, resaltar=False, hueco=False):
        px, py = pos
        if resaltar:
            # anillo de contraste: tu coche se distingue aunque coincida de color
            # con el trazado o con un rival justo debajo
            c.create_oval(px - r - 3, py - r - 3, px + r + 3, py + r + 3,
                          outline="#000000", width=3)
        if hueco:
            # Dibujado como anillo, no relleno: a la escala del mapa un metro
            # son centimetros de pantalla, asi que un coche pegado a ti quedaba
            # completamente tapado por tu punto. Con el centro vacio se ve.
            c.create_oval(px - r, py - r, px + r, py + r,
                          outline=color, width=max(2, r // 3))
        else:
            c.create_oval(px - r, py - r, px + r, py + r,
                          fill=color, outline="#000000", width=1)
        if self.cfg["mostrar_numeros"] and coche.get("puesto"):
            c.create_text(px, py, text=str(coche["puesto"]), fill="#000000",
                          font=("Segoe UI", self.cfg["tam_numero"], "bold"))

    # ---- bucle ----
    def tick(self):
        try:
            if self.teclas.pulsada("F9"):
                self.visible = not self.visible
                (self.root.deiconify if self.visible else self.root.withdraw)()
            if self.teclas.pulsada("F10"):
                self.alternar_opciones()
            if self.teclas.pulsada("F11"):
                self.alternar_eleccion()
        except Exception:
            # Protegido por lo mismo que el resto del ciclo: si abrir una
            # ventana fallara, la excepcion saldria del temporizador de tkinter
            # y el mapa se quedaria congelado con la ultima imagen.
            apuntar_fallo()

        # Leer y grabar se hacen SIEMPRE, este el mapa a la vista o escondido.
        #
        # Antes todo esto colgaba de "si el mapa esta visible", asi que esconder
        # el mapa con F9 dejaba de grabar las vueltas y de medir la comparacion.
        # Quien lo escondiera para conducir mas limpio se encontraba luego con
        # la sesion vacia, y sin ninguna pista de por que. F9 solo decide si se
        # DIBUJA.
        #
        # Todo el ciclo va protegido, no solo la lectura: si algo falla en el
        # comparador o al dibujar, la excepcion se llevaba por delante el
        # temporizador y el mapa se quedaba CONGELADO con la ultima imagen,
        # coches incluidos, sin volver a refrescarse jamas.
        try:
            coches = self.fuente.leer()
            self._llevar_bola()
            self._llevar_clima()
            self._llevar_frenos(coches)
            self._llevar_tabla(coches)
            self._llevar_estrategia(coches)
            self._restaurar_elegido(coches)
            self._llevar_comparador(coches)
            if self.visible and self._toca_dibujar():
                self.dibujar(coches)
        except Exception:
            apuntar_fallo()

        self.root.after(REFRESCO_MS, self.tick)

    def _toca_dibujar(self):
        """
        Si en esta vuelta del bucle toca repintar.

        Leer y grabar van siempre a 20 por segundo; el dibujo puede ir mas
        despacio si el usuario lo baja. Se cuentan vueltas del bucle en vez de
        mirar el reloj para que el reparto salga parejo y no a tirones.
        """
        por_segundo = self.cfg.get("dibujos_por_segundo", 20)
        try:
            por_segundo = max(4, min(20, int(por_segundo)))
        except (TypeError, ValueError):
            por_segundo = 20
        cada = max(1, round(1000.0 / REFRESCO_MS / por_segundo))
        self._cuenta_dibujo = getattr(self, "_cuenta_dibujo", 0) + 1
        if self._cuenta_dibujo >= cada:
            self._cuenta_dibujo = 0
            return True
        return False

    def _llevar_comparador(self, coches):
        """
        Mide a todos los coches SIEMPRE, este o no activado el modo comparacion.

        Registrar no cuesta nada (ya estamos leyendo las posiciones para pintar
        el mapa) y asi, cuando se activa el modo, lo normal es que ya haya una
        vuelta rival medida y la comparacion arranque al instante en vez de
        tener que esperar a que alguien complete una vuelta desde cero.
        El interruptor solo decide si se MUESTRA.
        """
        largo = getattr(self.fuente, "largo", 0.0)
        if not largo:
            return                                  # aun no sabemos el circuito
        # Al cambiar de circuito O de sesion (practica -> clasificacion ->
        # carrera) se empieza de cero: los tramos y la referencia de la sesion
        # anterior ya no valen, y dejarlos puestos enganaria.
        sesion = getattr(self.fuente, "sesion", None)
        nueva = getattr(self.fuente, "nueva_sesion", False)
        if nueva:
            self.fuente.nueva_sesion = False
            # Otra sesion: los mID se reparten de nuevo, asi que el coche que
            # se hubiera elegido a mano ya no significa nada.
            self.cfg["coche_fijado"] = None
            self._elegido_restaurado = True
        # Se compara tambien el NOMBRE del circuito, no solo su largo: dos
        # variantes del mismo sitio (Silverstone WEC y ELMS) se diferencian
        # en menos de los cincuenta metros que se miraban, y pasaban por el
        # mismo circuito.
        # Se usa la clave del circuito escaneado y no el nombre a secas:
        # es la que ya distingue una variante de otra
        # (silverstonegrandprixcircuitwec de ...elms) y la fuente la calcula
        # de todas formas para saber que trazado pintar.
        nombre_circuito = getattr(self.fuente, "clave", "") or ""
        if (self.comparador is None or nueva
                or abs(self.comparador.largo - largo) > 50
                or self.comparador.sesion != sesion
                or self.comparador.circuito != nombre_circuito):
            self.comparador = comp.Comparador(largo, sesion, nombre_circuito)
            if self.grabador is not None:
                self.grabador.guardar()          # cierra la sesion anterior
            self.grabador = None

        # El grabador se crea aparte, y se REINTENTA mientras falte.
        #
        # Antes nacia dentro del 'if' de arriba, o sea una sola vez por sesion.
        # Si en ese preciso instante el circuito aun no estaba identificado -lo
        # normal al abrir el mapa con la sesion ya empezada- se quedaba sin
        # grabador para siempre: el mapa se veia, la comparacion funcionaba, y
        # no se guardaba ni una vuelta. Costaba de ver justamente porque todo
        # lo demas iba bien.
        if self.grabador is None:
            clave = getattr(self.fuente, "clave", None)
            datos = getattr(self.fuente, "datos", None)
            if clave and datos:
                self.grabador = grab.Grabador(
                    clave, datos["nombre"], sesion, largo,
                    time.strftime("%Y%m%d_%H%M"))
                print("[grabador] grabando %s (%s)"
                      % (datos["nombre"], os.path.basename(self.grabador.archivo)))
        self.comparador.usar_flag_juego = self.cfg["salidas_segun_juego"]
        self.comparador.margen_salida = self.cfg["margen_salida"]
        if coches and not getattr(self.fuente, "congelado", False):
            ahora = time.monotonic()
            self.comparador.actualiza(coches, ahora)
            if self.grabador is not None:
                self.grabador.actualiza(coches, ahora)

    # ---- opciones ----
    def alternar_opciones(self):
        if self.opciones and self.opciones.winfo_exists():
            self.cerrar_opciones()
        else:
            self.abrir_opciones()

    def _avisar_de_parados(self, coches, accidentados):
        """
        Ensena el cartel cuando hay un coche parado por delante.

        La cuenta de a cuantos segundos esta la hace avisos.py; aqui solo se
        le pasa lo que ya tenemos en la mano y se le deja decidir.
        """
        if self.comparador is None:
            return
        if self.avisador is None:
            import aviso_gui
            self.avisador = aviso_gui.Motor(self.root, self.cfg, guardar_config)
            self.avisador.colocar(self.modo_mover)
        yo = next((c for c in coches if c.get("es_yo")), None)
        mi_kmh = None
        if yo:
            mi_kmh = (self.comparador.coches.get(yo.get("nombre") or "")
                      or {}).get("kmh")
        self.avisador.latido(coches, accidentados,
                             getattr(self.fuente, "largo", 0.0), mi_kmh)

    def cerrar_opciones(self):
        self.modo_mover = False
        if self.avisador is not None:
            self.avisador.colocar(False)
        if self.avisa_frenos is not None:
            self.avisa_frenos.colocar(False)
        if self.panel_frenos is not None:
            self.panel_frenos.colocar(False)
        if self.tabla is not None:
            self.tabla.colocar(False)
        if self.estrategia is not None:
            self.estrategia.colocar(False)
        if self.bola is not None:
            self.bola.colocar(False)
        if self.clima is not None:
            self.clima.colocar(False)
        guardar_config(self.cfg)
        click_atraviesa(self.hwnd, True)
        if self.opciones:
            self.opciones.destroy()
        self.opciones = None

    def _llevar_bola(self):
        """
        Mueve el punto de la bola de reparto de carga.

        El punto va con las **G**, no con el reparto de carga, y es a
        proposito: asi esta en el centro cuando el coche va recto y quieto,
        que es lo que uno espera de este dibujo. El reparto de carga real no
        sirve para eso, porque un LMP2 rodando lleva SIEMPRE mas peso detras
        (medido en Daytona: 37 % delante en paso por curva, contra 48 % parado,
        por la carga aerodinamica), asi que el punto viviria pegado abajo.

        Donde si se ensena el reparto de verdad es en los numeros, que salen
        del peso medido en cada rueda.
        """
        if not self.cfg.get("bola_ver", False) and self.bola is None:
            return
        if self.bola is None:
            import bola_gui
            self.bola = bola_gui.Bola(self.root, self.cfg, guardar_config)
            self.bola.colocar(self.modo_mover)
        if not self.cfg.get("bola_ver", False):
            self.bola.esconder()
            return
        tele = getattr(self.fuente, "tele", None)
        # La telemetria es siempre la de TU coche mientras lo llevas tu. En
        # cuanto se lo pasas a un companero el juego deja de refrescarla, y
        # la bola se quedaba clavada en la ultima G que hubo antes de entrar
        # a boxes: parecia un coche frenando eternamente. Al centro, que es
        # lo que ya se hace cuando no hay datos.
        if (not tele or getattr(self.fuente, "congelado", False)
                or not getattr(self.fuente, "conduzco", True)):
            self._bola_pos[0] = self._bola_pos[1] = 0.0
            self.bola.pintar(0.0, 0.0, None)
            return
        escala = max(0.5, float(self.cfg.get("bola_escala", 2.5)))
        # +x del juego sale por tu lado izquierdo y +z por detras del coche:
        # frenando, el punto sube; girando a izquierdas, el peso -y el punto-
        # se van a la derecha. Comprobado con los datos de Daytona.
        x, y = self._suavizar(tele["g_lateral"] / escala, tele["g_larga"] / escala)
        self.bola.pintar(x, y, reparto_de(tele["cargas"]))

    def _llevar_frenos(self, coches):
        """
        El aviso de freno roto o gastado (ver frenos.py).

        Va aunque el mapa este escondido con F9, como el de coche parado: un
        freno que se rompe no espera a que mires el mapa.
        """
        ver_panel = self.cfg.get("frenos_ver", False)
        if self.avisa_frenos is None:
            if not self.cfg.get("frenos_aviso", True) and not ver_panel:
                return
            import aviso_gui
            self.avisa_frenos = aviso_gui.MotorFrenos(self.root, self.cfg,
                                                      guardar_config)
            self.avisa_frenos.colocar(self.modo_mover)
        yo = next((c for c in (coches or []) if c.get("es_yo")), None)
        tele = None
        if not getattr(self.fuente, "congelado", False):
            tele = getattr(self.fuente, "tele", None)
        self.avisa_frenos.latido(tele, yo, getattr(self.fuente, "conduzco", True))

        if self.panel_frenos is None:
            if not ver_panel:
                return
            import frenos_gui
            self.panel_frenos = frenos_gui.Panel(self.root, self.cfg, guardar_config)
            self.panel_frenos.colocar(self.modo_mover)
        if self.modo_mover:
            return                      # con opciones abiertas, la muestra
        if not ver_panel:
            self.panel_frenos.esconder()
            return
        import frenos
        # Lo que dura una vuelta, para pasar los minutos que quedan a vueltas:
        # la ultima, y si aun no hay, la mejor.
        vuelta = 0.0
        if yo:
            vuelta = yo.get("ultima") or 0.0
            if not vuelta or vuelta <= 0:
                vuelta = yo.get("mejor") or 0.0
        vigia = self.avisa_frenos.vigia
        fichas = vigia.fichas(frenos.discos.mm(), frenos.familia_de(yo), vuelta)
        reparto = None
        if tele and tele.get("reparto_tras") is not None:
            reparto = 1.0 - tele["reparto_tras"]
        self.panel_frenos.pintar(fichas, frenos.discos.extra(), reparto)

    def _llevar_tabla(self, coches):
        """
        Refresca el panel de clasificacion (ver clasificacion.py).

        Los tiempos los trae de la API del juego un hilo aparte; aqui solo se
        recogen. Nuestro coche se reconoce por el que lleva el mapa, que en
        carreras por equipos sigue siendo el nuestro aunque conduzca otro.
        """
        if not self.cfg.get("tabla_ver", False) and self.tabla is None:
            return
        if self.tabla is None:
            import clasificacion_gui
            self.tabla = clasificacion_gui.Panel(self.root, self.cfg, guardar_config)
            self.tabla.colocar(self.modo_mover)
        # Con las opciones abiertas se sigue pintando: la carrera de verdad si
        # la hay, para ver como quedan las columnas que se van eligiendo.
        if not self.cfg.get("tabla_ver", False) and not self.modo_mover:
            self.tabla.esconder()
            return
        import clasificacion
        yo = next((c for c in (coches or []) if c.get("es_yo")), None)
        self.tabla.pintar(clasificacion.tabla.filas(
            yo, self.cfg.get("tabla_solo_clase", False)))

    def _llevar_estrategia(self, coches):
        """
        Refresca el panel de estrategia (ver estrategia.py).

        Saca sus cuentas de lo mismo que la clasificacion (clasificacion.tabla)
        y solo dos veces por segundo: no cambia mas deprisa.
        """
        if not self.cfg.get("estr_ver", False) and self.estrategia is None:
            return
        if self.estrategia is None:
            import estrategia_gui
            self.estrategia = estrategia_gui.Panel(self.root, self.cfg, guardar_config)
            self.estrategia.colocar(self.modo_mover)
        if not self.cfg.get("estr_ver", False) and not self.modo_mover:
            self.estrategia.esconder()
            return
        ahora = time.monotonic()
        if (ahora - getattr(self, "_estr_cuando", 0.0) < 0.5
                and not self.estrategia.estirando):
            return
        self._estr_cuando = ahora
        import clasificacion
        import estrategia
        yo = next((c for c in (coches or []) if c.get("es_yo")), None)
        filas = clasificacion.tabla.filas(yo, False)
        datos = estrategia.calcular_todo(clasificacion.tabla, filas,
                                         int(self.cfg.get("estr_minutos", 0)))
        estrategia.apuntar(datos)
        estrategia.vigilar_paradas(clasificacion.tabla, datos)
        self.estrategia.pintar(datos, forzar=True)

    def _llevar_clima(self):
        """
        Refresca el panel del clima.

        Son dos fuentes que van a ritmos muy distintos: lo que hace AHORA sale
        de la memoria compartida y se lee aqui mismo, y el PRONOSTICO lo trae
        clima.py de la API web del juego en su propio hilo, cada veinte
        segundos. Aqui solo se recoge lo ultimo que haya llegado, sin esperar
        a nadie: una peticion HTTP en este bucle congelaria el mapa.

        El panel se pinta aunque no haya coches en pista -en el garaje, sin
        salir- porque es justo ahi donde se mira el pronostico para decidir la
        estrategia.
        """
        if not self.cfg.get("clima_ver", False) and self.clima is None:
            return
        if self.clima is None:
            import clima_gui
            self.clima = clima_gui.Panel(self.root, self.cfg, guardar_config)
            self.clima.colocar(self.modo_mover)
        if not self.cfg.get("clima_ver", False):
            self.clima.esconder()
            return
        # Solo se ensena el tiempo si el juego lo esta publicando AHORA. La
        # memoria compartida se queda con lo ultimo al cerrar el juego, asi
        # que sin esta condicion el panel seguia ensenando la temperatura y la
        # hora de la sesion de hace un rato, tan convencido. Visto el
        # 12/09/2026: LMU cerrado y el panel marcando 20 grados y las 15:26
        # del circuito.
        sco = getattr(self.fuente, "sco", None)
        ahora = None
        if (sco is not None and hasattr(sco, "clima")
                and getattr(self.fuente, "publicando", True)):
            ahora = sco.clima()
        # Que pronostico se ensena, y -esto es lo importante- si es el de la
        # sesion que se esta corriendo. Solo entonces el panel puede poner
        # horas y cuenta atras; con el de la carrera puesto desde los libres
        # no se sabe ni cuando empieza ni cuanto dura, y una hora inventada
        # ahi seria peor que no poner ninguna.
        de_ahora = clima.bloque_de_sesion(getattr(self.fuente, "sesion", None))
        elegida = self.cfg.get("clima_que_sesion", "auto")
        cual = elegida.upper() if elegida in ("practice", "qualify", "race") \
            else de_ahora
        # El cielo de AHORA se saca interpolando el pronostico de la sesion en
        # curso (ver clima.cielo_ahora), que da el mismo estado que ensena la
        # pantalla del juego. Ojo: el de la sesion EN CURSO, que no tiene que
        # ser el que se este ensenando abajo -se puede estar mirando el de la
        # carrera desde los libres-.
        if ahora:
            ahora["cielo"] = clima.cielo_ahora(
                clima.pronostico.sesion(de_ahora), ahora)
        self.clima.pintar(ahora, clima.pronostico.sesion(cual), cual,
                          cual == de_ahora)

    def _suavizar(self, x, y):
        """
        Frena el punto para que se pueda leer conduciendo.

        El juego publica las G tal cual las calcula, con todo el temblor del
        piano y del bordillo dentro, y a veinte dibujos por segundo el punto
        vibra tanto que no da tiempo a leerlo. Lo que se hace NO es mirar el
        dato menos veces -eso lo dejaria dando saltos, que es peor- sino
        dejar que el punto persiga al dato: cada vuelta del bucle avanza solo
        una parte del camino que le falta. Con 0 va tal cual llega; cuanto mas
        alto, mas tarda en llegar y mas quieto se ve.
        """
        try:
            suavidad = float(self.cfg.get("bola_suavidad", 75))
        except (TypeError, ValueError):
            suavidad = 75.0
        paso = 1.0 - max(0.0, min(95.0, suavidad)) / 100.0
        self._bola_pos[0] += (x - self._bola_pos[0]) * paso
        self._bola_pos[1] += (y - self._bola_pos[1]) * paso
        return self._bola_pos[0], self._bola_pos[1]

    # ---- cual es tu coche (F11) ----
    def alternar_eleccion(self):
        if self.eleccion and self.eleccion.winfo_exists():
            self.cerrar_eleccion()
        else:
            self.abrir_eleccion()

    def abrir_eleccion(self):
        import elegir_coche
        self.eleccion = elegir_coche.abrir(self)

    def cerrar_eleccion(self):
        if self.eleccion:
            self.eleccion.destroy()
        self.eleccion = None

    def fijar_mi_coche(self, mid):
        """
        El usuario dice cual es su coche (o `None` para volver a automatico).

        Se guarda tambien en la configuracion para que un reinicio del mapa en
        mitad de una carrera no lo pierda: en resistencia el mapa se abre y se
        cierra a media carrera mas de lo que parece.
        """
        sco = getattr(self.fuente, "sco", None)
        if sco is None:
            return
        sco.fijar_coche(mid)
        guardado = None
        if mid is not None:
            elegido = next((c for c in getattr(self.fuente, "_ultimos", [])
                            if c["id"] == mid), None)
            if elegido is not None:
                guardado = {"id": mid,
                            "piloto": elegido.get("nombre", ""),
                            "vehiculo": elegido.get("vehiculo", ""),
                            "clave": getattr(self.fuente, "clave", None),
                            "sesion": getattr(self.fuente, "sesion", None)}
        self.cfg["coche_fijado"] = guardado
        self._elegido_restaurado = True
        guardar_config(self.cfg)

    def _restaurar_elegido(self, coches):
        """
        Recupera el coche elegido a mano si el mapa se ha reiniciado.

        Solo vale para la MISMA sesion del MISMO circuito, y ademas el coche
        tiene que seguir siendo el mismo (mismo mID y mismo equipo). Los mID se
        reparten de nuevo en cada sesion, asi que sin esas comprobaciones se
        estaria fijando un coche al azar -que es exactamente el fallo que se
        esta arreglando-.
        """
        if self._elegido_restaurado or not coches:
            return
        sco = getattr(self.fuente, "sco", None)
        guardado = self.cfg.get("coche_fijado") or {}
        if sco is None:
            return
        self._elegido_restaurado = True
        if not guardado:
            return
        if (guardado.get("clave") != getattr(self.fuente, "clave", None)
                or guardado.get("sesion") != getattr(self.fuente, "sesion", None)):
            self.cfg["coche_fijado"] = None       # es de otra sesion
            return
        for c in coches:
            if (c["id"] == guardado.get("id")
                    and c.get("vehiculo") == guardado.get("vehiculo")):
                sco.fijar_coche(c["id"])
                return
        self.cfg["coche_fijado"] = None           # ese coche ya no esta

    def abrir_opciones(self):
        click_atraviesa(self.hwnd, False)      # para poder arrastrar el mapa
        self.modo_mover = True
        if self.avisador is not None:
            self.avisador.colocar(True)
        if self.avisa_frenos is not None:
            self.avisa_frenos.colocar(True)
        if self.panel_frenos is not None:
            self.panel_frenos.colocar(True)
        if self.tabla is not None:
            self.tabla.colocar(True)
        if self.estrategia is not None:
            self.estrategia.colocar(True)
        if self.bola is not None:
            self.bola.colocar(True)
        if self.clima is not None:
            self.clima.colocar(True)
        self.opciones = opciones.abrir(self, guardar_config)

    def cerrar_programa(self):
        self.cerrar_eleccion()
        if self.grabador is not None:
            self.grabador.guardar()          # no perder la sesion al salir
        """Cierra el mapa del todo. El programa corre sin consola ni barra de
        titulo, asi que este boton es la unica salida que no pasa por el
        Administrador de tareas."""
        guardar_config(self.cfg)
        self.root.quit()
        self.root.destroy()

    def ejecutar(self):
        self.root.mainloop()


def leer_catalogo_de_coches():
    """
    Pone al dia la tabla de que coche lleva cada uno, leyendo los resultados
    que el juego escribe al terminar cada sesion.

    Va en un hilo aparte para no retrasar el arranque: la primera vez hay que
    leerse el historial entero (con 828 sesiones, un segundo), y a partir de
    ahi solo se miran los archivos nuevos. Si falla no pasa nada, el mapa
    funciona igual: los coches saldrian con el nombre del equipo.
    """
    try:
        import resultados
        archivos, codigos = resultados.actualizar()
        if archivos:
            print("Coches: %d sesiones nuevas leidas, %d coches nuevos."
                  % (archivos, codigos))
    except Exception:
        pass


def main():
    demo = "--demo" in sys.argv
    fuente = Demo() if demo else Juego()
    threading.Thread(target=leer_catalogo_de_coches, daemon=True).start()
    print("LMU Pit Wall %s. F9 = ocultar/mostrar, F10 = opciones."
          % ("(DEMO)" if demo else ""))
    Mapa(fuente).ejecutar()




def comprobar():
    """
    Revision rapida sin necesidad del juego: donde esta cada cosa y si se lee.

    Se pide con   LMUPitWall-consola.exe comprobar
    """
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    import circuitos
    import coches
    import juego
    import rutas

    print("=" * 68)
    print("  REVISION DEL MAPA DE PISTA")
    print("=" * 68)
    print("  compilado          : %s" % ("si" if rutas.compilado() else "no"))
    print("  carpeta del programa: %s" % rutas.carpeta())
    print()

    fallos = []

    pistas = circuitos.cargar(recargar=True)
    con_bordes = sum(1 for v in pistas.values() if v.get("bordes"))
    con_curvas = sum(1 for v in pistas.values() if v.get("curvas"))
    print("  circuitos medidos  : %d  (%d con bordes, %d con curvas)"
          % (len(pistas), con_bordes, con_curvas))
    if not pistas:
        fallos.append("no hay ningun circuito: falta la carpeta circuitos/")

    disponibles = idiomas.disponibles()
    print("  idiomas            : %d  (%s)"
          % (len(disponibles), ", ".join(c for c, _ in disponibles)))
    print("  idioma elegido     : %s" % idiomas.actual())
    if len(idiomas.textos_es()) < 100:
        fallos.append("faltan traducciones: falta la carpeta idiomas/")

    print("  coches a mano      : %d" % len(coches.cargar()["coches"]))

    # El catalogo que sale de los resultados del juego. Se lee aqui a proposito,
    # que asi la revision tambien sirve para ponerlo al dia.
    import resultados
    leidos, nuevos = resultados.actualizar()
    if leidos is None:
        print("  coches del juego   : no encuentro UserData/Log/Results")
        fallos.append("no encuentro los resultados del juego: los coches "
                      "saldran con el nombre del equipo en vez de su modelo")
    else:
        modelos, decoraciones, sesiones = resultados.resumen()
        print("  coches del juego   : %d modelos, %d decoraciones "
              "(de %d sesiones)" % (modelos, decoraciones, sesiones))
        if not modelos:
            fallos.append("el juego no ha dejado ningun resultado todavia: "
                          "termina una sesion y vuelve a pasar esta revision")

    carpeta_juego = juego.carpeta()
    print("  Le Mans Ultimate   : %s" % (carpeta_juego or "NO LO ENCUENTRO"))
    if not carpeta_juego:
        fallos.append("no encuentro el juego; ponlo a mano en ruta_juego.txt")

    try:
        import catalogo
        print("  trazados instalados: %d" % len(catalogo.inventario()))
    except Exception as e:
        print("  trazados instalados: no se han podido leer (%s)" % e)

    # El manual va suelto al lado del .exe, asi que puede faltar: si alguien
    # descomprime a medias o borra el archivo, el boton abriria una ventana
    # vacia y no se sabria por que.
    try:
        import manual
        puestos = manual.tomos()
        if puestos:
            cuenta = ", ".join("%s: %d apartados" % (t, len(manual.todos(t)))
                               for t in puestos)
            print("  manual             : %s" % cuenta)
        else:
            print("  manual             : NO ESTA")
            fallos.append("falta manual_reglajes.json: el manual saldra vacio")
    except Exception as e:
        print("  manual             : no se ha podido leer (%s)" % e)
        fallos.append("el manual no se puede leer: %s" % e)

    # Las dos razones por las que alguien abre el mapa y no ve nada, y que no
    # se ven a simple vista: el modo de pantalla del juego y una casilla de
    # Windows escondida en las propiedades del ejecutable.
    try:
        import pantalla
        d = pantalla.diagnostico(juego.carpeta())
        modos = {"exclusiva": "pantalla completa", "sin_bordes": "sin bordes",
                 "ventana": "en ventana"}
        print("  modo de pantalla    : %s" % modos.get(d["modo"], "no se sabe"))
        if d["optimizaciones"] is False:
            print("  optimizaciones win  : DESACTIVADAS  <-- por esto no se ve "
                  "el mapa en pantalla completa")
            fallos.append("alguien marco 'Deshabilitar las optimizaciones de "
                          "pantalla completa' en el .exe del juego: quitalo "
                          "desde F10 -> EL MAPA -> Pantalla y fluidez")
        elif d["optimizaciones"]:
            print("  optimizaciones win  : activadas (bien)")
        if d["se_vera"] is False:
            print("  el mapa se vera     : NO con lo que hay puesto")
        elif d["se_vera"]:
            print("  el mapa se vera     : si")
    except Exception as e:
        print("  modo de pantalla    : no se ha podido mirar (%s)" % e)

    # El clima llega por dos caminos distintos, asi que se comprueban los dos:
    # la memoria compartida (lo que hace ahora) y la API web del juego (el
    # pronostico). Uno puede funcionar sin el otro, y saber cual falla ahorra
    # media hora de buscar a ciegas.
    # Que la memoria compartida se pueda ABRIR no quiere decir que el juego
    # este vivo: al cerrarse, el mapa la mantiene abierta y ahi se queda, con
    # los ultimos valores o a ceros. Lo unico que lo delata es el contador de
    # version, que solo se mueve mientras el juego publica.
    publicando = False
    try:
        _sco = lmu.Scoring()
        _v = _sco.version()
        time.sleep(1.2)
        publicando = _sco.version() != _v
    except OSError:
        _sco = None

    if _sco is None:
        print("  el juego            : cerrado (normal si no estas jugando)")
    elif publicando:
        print("  el juego            : abierto y publicando datos")
    else:
        print("  el juego            : la memoria esta ahi pero NO llegan "
              "datos (cerrado, en el menu o en pausa)")

    if _sco is not None and publicando:
        sco_clima = _sco.clima()
        if sco_clima:
            print("  clima ahora         : aire %.0f, asfalto %.0f, %s"
                  % (sco_clima["aire"], sco_clima["asfalto"],
                     clima.nombre_cielo(sco_clima["cielo"])))
        else:
            print("  clima ahora         : no se puede leer")
    else:
        print("  clima ahora         : sin datos del juego")
    clima.pronostico.arrancar()
    espera = time.monotonic() + 5.0
    while clima.pronostico.datos() is None and time.monotonic() < espera:
        time.sleep(0.2)
    nodos = clima.pronostico.sesion("RACE")
    if nodos:
        print("  pronostico          : %d puntos de la carrera, hasta %d%% de "
              "lluvia" % (len(nodos), max(n["lluvia"] for n in nodos)))
    else:
        print("  pronostico          : la interfaz del juego no contesta "
              "(normal con el juego cerrado)")



    # Se monta la ventana de opciones sin ensenarla. Es la parte con mas
    # codigo de todo el programa, asi que si se dibuja entera es que no falta
    # nada; compilado, una libreria que se hubiera quedado fuera saltaria aqui.
    try:
        import tkinter as tk
        import tkinter.ttk as ttk
        import opciones
        raiz = tk.Tk()
        raiz.withdraw()

        class Falsa(object):
            pass

        falsa = Falsa()
        falsa.root = raiz
        falsa.cfg = cargar_config()
        falsa.lienzo = tk.Canvas(raiz)
        falsa.cerrar_opciones = falsa.cerrar_programa = lambda *a: None
        ventana = opciones.Opciones(falsa, lambda c: None)
        cuaderno = [w for w in ventana.v.winfo_children()
                    if isinstance(w, ttk.Notebook)][0]
        for i in range(len(cuaderno.tabs())):
            cuaderno.select(i)
            raiz.update()
        print("  ventana de opciones : %d pestanas, todas se dibujan"
              % len(cuaderno.tabs()))

        # Y la del manual, por lo mismo: compilado, si el modulo se hubiera
        # quedado fuera del ejecutable, se veria aqui y no al pulsar el boton.
        try:
            import manual_gui
            m = manual_gui.Manual(raiz)
            raiz.update()
            m.v.destroy()
            print("  ventana del manual  : se abre")
            import fov_gui
            c = fov_gui.Calculadora(raiz)
            raiz.update()
            c.v.destroy()
            print("  calculadora de FOV  : se abre")
        except Exception as e:
            print("  ventana del manual  : FALLA (%s)" % e)
            fallos.append("el manual no se abre: %s" % e)

        raiz.destroy()
    except Exception as e:
        print("  ventana de opciones : FALLA (%s)" % e)
        fallos.append("la ventana de opciones no se abre: %s" % e)

    print()
    if fallos:
        print("  HAY %d COSAS QUE REVISAR:" % len(fallos))
        for f in fallos:
            print("    - %s" % f)
    else:
        print("  Todo en orden.")
    print("=" * 68)
    print()
    try:
        input(idiomas.t("sc.cerrar"))
    except Exception:
        pass
    return 1 if fallos else 0

# ---------------------------------------------------------------- arranque
def arranque():
    """
    Por donde entra el programa.

    Compilado, el mismo ejecutable sirve para el mapa y para los escaneos: si
    le llega un argumento, se ejecuta ese escaneo en vez del mapa. Asi no hay
    que compilar cinco programas ni repartir cinco iconos.
    """
    tareas = {
        "escanear_circuito": "escanear_circuito",
        "escanear_bordes": "escanear_bordes",
        "escanear_boxes": "escanear_boxes",
        "buscar_aviso": "buscar_aviso",
        # Herramienta de taller: apunta el clima en un archivo para poder
        # calibrar luego con calma. Va aqui para que tambien funcione desde
        # el ejecutable con consola.
        "registrar_clima": "registrar_clima",
    }
    if len(sys.argv) > 1 and sys.argv[1] == "comprobar":
        return comprobar()
    if len(sys.argv) > 1 and sys.argv[1] in tareas:
        import importlib
        modulo = importlib.import_module(tareas[sys.argv[1]])
        try:
            codigo = modulo.main()
        except KeyboardInterrupt:
            codigo = 1
        except Exception:
            apuntar_fallo()
            codigo = 2
        print()
        try:
            input(idiomas.t("sc.cerrar"))
        except Exception:
            pass
        return codigo
    main()
    return 0


if __name__ == "__main__":
    sys.exit(arranque())
