# -*- coding: utf-8 -*-
"""
Los tiempos de todos los coches de la sesion, para el panel de clasificacion.

DE DONDE SALE
La API web del propio juego (puerto 6397, la misma del clima y los frenos), en
`/rest/watch/standings`: una ficha por coche con la posicion, el dorsal, el
piloto, la mejor vuelta, la ultima, los sectores, lo que lleva de la vuelta en
curso, las distancias y si esta en boxes. Comprobado el 30/10/2026 en una
carrera por equipos, con Manuel de espectador: llegan los 44 coches y el reloj
de la vuelta en curso avanza.

Se usa la API y no la memoria compartida porque la memoria no trae el dorsal y
la API si, y porque lo que lleva de vuelta ya viene calculado.

Como el reloj de la vuelta en curso solo llega una vez por segundo, el panel lo
hace avanzar el solo entre una respuesta y la siguiente (ver `filas`).
"""
import csv
import datetime
import json
import os
import re
import threading
import time
import urllib.request

import rutas

URL = "http://127.0.0.1:6397/rest/watch/standings"
# Las vueltas de TODA la sesion de cada coche, con quien las dio. Pesa (400 KB
# en una carrera de 44 coches), asi que se pide de vez en cuando: sirve para
# rellenar lo que paso antes de abrir el mapa.
URL_HISTORIA = "http://127.0.0.1:6397/rest/watch/standings/history"
CADA_HISTORIA = 30.0
# Las paradas de cada equipo: piloto, si hubo cambio y QUE NEUMATICO se puso
# en cada rueda, nuevo o usado.
URL_PARADAS = "http://127.0.0.1:6397/rest/strategy/overall"
CADA_PARADAS = 5.0
# Los neumaticos que da el servidor para el garaje (ruedas sueltas, no juegos).
URL_SESION = "http://127.0.0.1:6397/rest/sessions"
# La energia virtual de cada piloto vuelta a vuelta, desde el principio. Con
# esto el gasto sale bien aunque el mapa se abra a media carrera.
URL_ENERGIA = "http://127.0.0.1:6397/rest/strategy/usage"
# Lo que queda de sesion, el largo de la pista y en que vuelta va: lo que hace
# falta para predecir (ver estrategia.py). Es pequeno y se pide a menudo.
URL_INFO = "http://127.0.0.1:6397/rest/watch/sessionInfo"
CADA_INFO = 2.0
# Con cuantas vueltas (las ultimas, sin repostar por medio) se hace la media
# del gasto: pocas, para que siga al ritmo de ahora (lluvia, coche de
# seguridad, ahorro), pero no tan pocas que una vuelta rara la tuerza.
VUELTAS_GASTO = 5
CADA_SESION = 60.0
# Cada vuelta de cada coche, tambien las anuladas, en un CSV por sesion. Para
# estudiar despues la fiabilidad de cada piloto y para predecir tiempos.
CARPETA_VUELTAS = "vueltas_carreras"
CADA = 1.0                  # segundos entre preguntas a la API
ESPERA = 2.0                # lo que se espera a que conteste
CADUCA = 6.0                # sin respuesta en este rato, no hay datos


# La marca de cada coche, por palabras que salen en su nombre o en su archivo.
#
# Hace falta porque los coches de equipo propio ("Custom Team") no dicen la
# marca en ninguna parte: se llaman "BMWMH Custom Team", "296GT3 Custom Team",
# "9x8 Wing Custom Team"... y el catalogo del juego no los tiene. Por eso se
# busca por trozos del nombre. Va en orden: lo mas concreto primero.
#
# (marca, siglas, color de la placa, color de las letras)
MARCAS = [
    (("alpine", "a424"), ("Alpine", "ALP", "#0055ff", "#ffffff")),
    (("aston", "vantage", "valkyrie", "amr"), ("Aston Martin", "AST", "#00594f", "#ffffff")),
    (("bmw", "m4", "mhybrid"), ("BMW", "BMW", "#1c69d4", "#ffffff")),
    (("cadillac", "vlmdh", "v-series", "vseries"), ("Cadillac", "CAD", "#b8a36a", "#000000")),
    (("corvette", "z06", "chevrolet"), ("Corvette", "COR", "#ffd400", "#000000")),
    (("ferrari", "499p", "296"), ("Ferrari", "FER", "#d40000", "#ffe600")),
    (("mustang", "ford"), ("Ford", "FOR", "#003478", "#ffffff")),
    (("genesis",), ("Genesis", "GEN", "#000000", "#ffffff")),
    (("glickenhaus", "glick", "scg"), ("Glickenhaus", "SCG", "#1a1a1a", "#e0e0e0")),
    (("isotta", "tipo6"), ("Isotta Fraschini", "ISO", "#0b2d5b", "#ffffff")),
    (("lamborghini", "sc63", "huracan"), ("Lamborghini", "LAM", "#d4af37", "#000000")),
    (("lexus", "rcf"), ("Lexus", "LEX", "#6e7378", "#ffffff")),
    (("mclaren", "720s"), ("McLaren", "MCL", "#ff8000", "#000000")),
    (("mercedes", "amg"), ("Mercedes-AMG", "MER", "#00a19c", "#000000")),
    (("oreca", "lmp2"), ("Oreca", "ORE", "#0a3c8c", "#ffffff")),
    (("peugeot", "9x8"), ("Peugeot", "PEU", "#1e1e1e", "#c9ff00")),
    (("porsche", "963", "911gt3", "911"), ("Porsche", "POR", "#c4001a", "#ffffff")),
    (("toyota", "gr010"), ("Toyota", "TOY", "#eb0a1e", "#ffffff")),
    (("vanwall", "vandervell"), ("Vanwall", "VAN", "#0d4d2e", "#ffffff")),
]
SIN_MARCA = ("", "?", "#3a424c", "#ffffff")

_marcas_vistas = {}


def marca_de(nombre_vehiculo, archivo="", clase=""):
    """
    ('Ferrari', 'FER', color placa, color letras) para un coche.

    Primero se pregunta al catalogo (coches.texto), que conoce los coches
    oficiales por su codigo; si no lo sabe, se busca en el nombre y el archivo.
    """
    clave = (nombre_vehiculo, archivo, clase)
    if clave in _marcas_vistas:
        return _marcas_vistas[clave]
    textos = [nombre_vehiculo or "", archivo or ""]
    try:
        import coches
        textos.insert(0, coches.texto(nombre_vehiculo, clase, ""))
    except Exception:
        pass
    hallada = SIN_MARCA
    for texto in textos:
        plano = re.sub(r"[^0-9a-z-]", "", texto.lower())
        for palabras, marca in MARCAS:
            if any(p in plano for p in palabras):
                hallada = marca
                break
        if hallada is not SIN_MARCA:
            break
    if hallada is SIN_MARCA and "lmp2" in (clase or "").lower():
        hallada = dict(MARCAS)[("oreca", "lmp2")]
    _marcas_vistas[clave] = hallada
    return hallada


def _num(v):
    """Un tiempo de la API: los que aun no existen llegan como -1 o 0."""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


class Tabla:
    """
    Pregunta a la API en su hilo; el mapa solo recoge lo ultimo que haya.

    Ademas APUNTA cada vuelta que cierra cada coche, con quien la dio. Hace
    falta por las carreras por equipos: el juego da UNA mejor vuelta por coche,
    pero interesa tambien la de cada piloto, y eso solo se sabe mirando quien
    iba al volante cuando se cerro cada vuelta. Esa historia es tambien la base
    para predecir tiempos.

    Lo apuntado vive mientras el mapa este abierto: las vueltas de antes de
    abrirlo no se conocen (la mejor del coche si, porque la da el juego).
    """

    def __init__(self):
        self._coches = []
        self._sello = 0.0
        self._hilo = None
        self._fallos = 0
        self._antes = {}            # clave del coche -> ficha anterior de la API
        self.historia = {}          # clave del coche -> [vueltas cerradas]
        self._mejor_piloto = {}     # (clave del coche, piloto) -> mejor vuelta
        self._mejor_coche = {}      # clave del coche -> mejor vuelta vista
        self._sesion = None
        self._sanciones = {}        # (clave del coche, piloto) -> sanciones
        self._archivo = None        # el CSV de esta sesion
        self._pit_en_vuelta = {}    # clave -> paso por boxes en esta vuelta
        self._paradas = []          # [[equipo, [paradas]], ...] de la API
        self._pilotos = {}          # clave del coche -> nombres (con su #)
        self.ruedas_garaje = None   # neumaticos sueltos que da el servidor
        self.info = {}              # /rest/watch/sessionInfo
        # Al pasar de una sesion a otra (clasificacion -> carrera) la historia
        # del juego SIGUE trayendo las vueltas de la anterior un buen rato
        # (visto en Barcelona el 01/11/2026: en la vuelta de formacion habia
        # 151 vueltas de la clasificacion) y se colaban como ritmo de carrera.
        # Las que habia al cambiar se apuntan aqui y no se vuelven a meter.
        self._nombre_sesion = None
        self._viejas = set()        # (slot, vehiculo, vuelta, tiempo) de antes
        self._marcar_viejas = False
        self.info_sello = 0.0

    def arrancar(self):
        if self._hilo is None:
            self._hilo = threading.Thread(target=self._bucle, daemon=True)
            self._hilo.start()

    # ---------------------------------------------------------- apuntar
    def _vaciar(self):
        """Lo de la sesion anterior ya no vale."""
        self._antes, self.historia = {}, {}
        self._mejor_piloto, self._mejor_coche = {}, {}
        self._sanciones, self._archivo = {}, None
        self._pit_en_vuelta = {}

    def _apuntar(self, coches):
        """Mira que coches han cerrado vuelta desde la ultima respuesta."""
        # Sesion nueva (los tiempos de la anterior no valen): han cambiado los
        # coches o, entre todos, llevan menos vueltas que antes.
        firma = tuple(sorted((c.get("slotID"), c.get("vehicleName") or "") for c in coches))
        vueltas = sum(int(c.get("lapsCompleted") or 0) for c in coches)
        if self._sesion is not None and (firma != self._sesion[0]
                                         or vueltas < self._sesion[1] - 3):
            self._vaciar()
        self._sesion = (firma, vueltas)

        for c in coches:
            k = _clave(c)
            antes = self._antes.get(k)
            self._antes[k] = c
            # Si paso por boxes en algun momento de la vuelta: al cerrarla ya
            # puede ir por la pista (la de salida) o aun no haber entrado del
            # todo, y mirar solo ese instante dejaba colarse esas vueltas en
            # la media.
            if c.get("pitting") or c.get("inGarageStall"):
                self._pit_en_vuelta[k] = True
            if antes is None:
                continue
            # Las sanciones se apuntan al que conducia cuando le cayeron. En
            # CARRERA el juego no anula vueltas por salirse: sanciona (ver
            # OFF_PENAS en lector_lmu), asi que la fiabilidad de un piloto en
            # carrera sale de aqui. Solo se cuentan las que llegan; cumplirlas
            # baja el numero del juego pero no borra lo que hizo.
            nuevas = int(c.get("penalties") or 0) - int(antes.get("penalties") or 0)
            if nuevas > 0:
                kp = (k, _limpio(antes.get("driverName")))
                self._sanciones[kp] = self._sanciones.get(kp, 0) + nuevas
            if int(c.get("lapsCompleted") or 0) <= int(antes.get("lapsCompleted") or 0):
                continue
            tiempo = _num(c.get("lastLapTime"))
            if tiempo is None:
                continue
            # La vuelta la dio quien iba conduciendo JUSTO ANTES de cerrarla,
            # y si contaba o no lo dice la marca de esa misma lectura (en la
            # nueva ya es la de la vuelta siguiente).
            piloto = _limpio(antes.get("driverName"))
            valida = antes.get("countLapFlag") == "COUNT_LAP_AND_TIME"
            # Si con esta vuelta el juego ha bajado la mejor del coche, es que
            # contaba seguro.
            if _num(c.get("bestLapTime")) == tiempo:
                valida = True
            s1 = _num(c.get("lastSectorTime1"))
            s12 = _num(c.get("lastSectorTime2"))
            self.historia.setdefault(k, []).append({
                "vuelta": int(c.get("lapsCompleted") or 0),
                "tiempo": tiempo,
                "piloto": piloto,
                "valida": valida,
                "s1": s1,
                "s2": s12 - s1 if s1 and s12 else None,
                "s3": tiempo - s12 if s12 else None,
                "boxes": bool(self._pit_en_vuelta.get(k)),
                "gasolina": c.get("fuelFraction"),
                "energia": c.get("veFraction"),
                "hora": time.time(),
            })
            # la de salida tambien es de boxes: sigue marcada si aun esta dentro
            self._pit_en_vuelta[k] = bool(c.get("pitting") or c.get("inGarageStall"))
            self._guardar(c, self.historia[k][-1])
            if valida:
                kp = (k, piloto)
                if kp not in self._mejor_piloto or tiempo < self._mejor_piloto[kp]:
                    self._mejor_piloto[kp] = tiempo
                if k not in self._mejor_coche or tiempo < self._mejor_coche[k]:
                    self._mejor_coche[k] = tiempo

    # ------------------------------------------------------------ filas
    def filas(self, yo=None, solo_mi_clase=False):
        """
        Los coches en orden de posicion, listos para pintar, o [] sin datos.

        `yo` es nuestro coche tal y como lo lleva el mapa (con su "vehiculo" y
        su "nombre"). Se busca por el nombre del vehiculo, que en una carrera
        por equipos sigue siendo el nuestro aunque conduzca el companero. Los
        coches de equipo propio comparten nombre ("BMW GT3 Custom Team #397"
        lo llevan varios), asi que si hay mas de uno se desempata por el
        piloto. Si el mapa aun no lo sabe, vale la marca de jugador de la API.
        """
        self.arrancar()
        ahora = time.monotonic()
        coches = self._coches
        if not coches or ahora - self._sello > CADUCA:
            return []
        pasado = ahora - self._sello

        mi_vehiculo = (yo or {}).get("vehiculo") or ""
        mi_piloto = (yo or {}).get("nombre") or ""
        candidatos = [c for c in coches
                      if mi_vehiculo and c.get("vehicleName") == mi_vehiculo]
        if len(candidatos) > 1:
            candidatos = ([c for c in candidatos if c.get("driverName") == mi_piloto]
                          or candidatos[:1])
        if not candidatos:
            candidatos = [c for c in coches if c.get("player")]
        mio = _clave(candidatos[0]) if candidatos else None

        salida = []
        for c in coches:
            k = _clave(c)
            nombre = c.get("vehicleName") or ""
            piloto = _limpio(c.get("driverName"))
            en_boxes = bool(c.get("pitting") or c.get("inGarageStall"))
            en_curso = _num(c.get("timeIntoLap"))
            if en_curso is not None and not en_boxes:
                en_curso += pasado
            del_juego = _num(c.get("bestLapTime"))
            mejor = del_juego
            visto = self._mejor_coche.get(k)
            if visto and (mejor is None or visto < mejor):
                mejor = visto
            ultima = _num(c.get("lastLapTime"))
            s1, s12 = _num(c.get("lastSectorTime1")), _num(c.get("lastSectorTime2"))
            b1, b12 = _num(c.get("bestSectorTime1")), _num(c.get("bestSectorTime2"))
            bl12 = _num(c.get("bestLapSectorTime2"))
            media, cuantas = self._media_del_relevo(k, piloto)
            salida.append({
                "clave": k,
                "puesto": int(c.get("position") or 0),
                "clase": c.get("carClass") or "",
                "dorsal": str(c.get("carNumber") or ""),
                "piloto": piloto,
                "equipo": c.get("fullTeamName") or "",
                "marca": marca_de(nombre, c.get("vehicleFilename") or "",
                                  c.get("carClass") or ""),
                "mejor": mejor,
                "mejor_piloto": self._mejor_piloto.get((k, piloto)),
                "ultima": ultima,
                "media": media,
                "media_vueltas": cuantas,
                "anuladas": self.anuladas(k, piloto),
                "sanciones_piloto": self._sanciones.get((k, piloto), 0),
                "neumaticos": self.neumaticos(c),
                "api": c,                   # la ficha tal cual, para las cuentas
                "combustible": self._combustible(k, c),
                "en_curso": en_curso,
                # sectores de la ultima vuelta
                "s1": s1,
                "s2": s12 - s1 if s1 and s12 else None,
                "s3": ultima - s12 if ultima and s12 else None,
                # los mejores sectores sueltos (el juego da el S1+S2 acumulado,
                # como en rFactor) y el S3 de la mejor vuelta
                "mejor_s1": b1,
                "mejor_s2": b12 - b1 if b1 and b12 else None,
                "mejor_s3": del_juego - bl12 if del_juego and bl12 else None,
                "dif_lider": (_num(c.get("timeBehindLeader")),
                              int(c.get("lapsBehindLeader") or 0)),
                "dif_clase": (_num(c.get("timeBehindClassLeader")),
                              int(c.get("lapsBehindClassLeader") or 0)),
                "dif_delante": (_num(c.get("timeBehindNext")),
                                int(c.get("lapsBehindNext") or 0)),
                "vueltas": int(c.get("lapsCompleted") or 0),
                "paradas": int(c.get("pitstops") or 0),
                "penas": int(c.get("penalties") or 0),
                "gasolina": c.get("fuelFraction"),
                "energia": c.get("veFraction"),
                "salida": int(c.get("qualification") or 0),
                "en_boxes": en_boxes,
                "es_yo": k == mio,
                "empieza_vuelta": _num(c.get("lapStartET")),
                "metros": c.get("lapDistance"),
                "boxes_ya": bool(c.get("pitting") or c.get("inGarageStall")),
            })
        salida.sort(key=lambda f: f["puesto"] or 999)

        # Puesto dentro de la clase, distancia al de delante DE SU CLASE (la
        # que importa en una carrera con varias clases) y la mejor vuelta de
        # cada clase, para pintarla en morado como en la tele.
        por_clase = {}
        for f in salida:
            por_clase.setdefault(f["clase"], []).append(f)
        for lista in por_clase.values():
            mejor_clase = min((f["mejor"] for f in lista if f["mejor"]), default=None)
            delante = None
            for puesto, f in enumerate(lista, 1):
                f["puesto_clase"] = puesto
                f["la_mejor"] = bool(f["mejor"]) and f["mejor"] == mejor_clase
                if delante is None:
                    f["dif_delante_clase"] = (None, 0)
                else:
                    t1, v1 = f["dif_clase"]
                    t0, v0 = delante["dif_clase"]
                    if v1 != v0:
                        f["dif_delante_clase"] = (None, v1 - v0)
                    else:
                        f["dif_delante_clase"] = ((t1 or 0.0) - (t0 or 0.0), 0)
                delante = f

        if solo_mi_clase:
            mia = next((f["clase"] for f in salida if f["es_yo"]), None)
            if mia:
                salida = [f for f in salida if f["clase"] == mia]
        return salida

    def _rellenar(self, historia):
        """
        Mete las vueltas de antes de abrir el mapa, de la historia del juego.

        El juego no dice si cada vuelta conto, asi que se deduce: una vuelta
        MAS RAPIDA que la mejor del coche es que no conto (si hubiera contado,
        seria la mejor). Las demas se dan por buenas. Las de entrada y salida
        de boxes se marcan para que no entren en la media.
        """
        if self._marcar_viejas:
            self._marcar_viejas = False
            for lista in historia.values():
                for h in lista if isinstance(lista, list) else []:
                    self._viejas.add((h.get("slotID"), h.get("vehicleName") or "",
                                      h.get("totalLaps"), h.get("lapTime")))
            return
        mejores = {_clave(c): _num(c.get("bestLapTime")) for c in self._coches}
        completadas = {_clave(c): int(c.get("lapsCompleted") or 0) for c in self._coches}
        for lista in historia.values():
            if not isinstance(lista, list):
                continue
            # La historia va en orden y la sesion anterior va DELANTE: la
            # clasificacion llega hasta su vuelta 10 y la carrera vuelve a
            # empezar desde 0. Lo de antes del ultimo salto atras no es de esta
            # sesion, y si ya se habia metido (el mapa se abrio en la vuelta de
            # formacion, por ejemplo) se saca.
            corte = 0
            for i in range(1, len(lista)):
                if int(lista[i].get("totalLaps") or 0) < int(lista[i - 1].get("totalLaps") or 0):
                    corte = i
            # Y si trae vueltas que el coche aun no ha dado, la lista entera es
            # de la sesion anterior: en Barcelona, ya en la vuelta 3 de la
            # carrera, la historia seguia siendo la de la clasificacion (hasta
            # la vuelta 10) sin una sola vuelta de carrera.
            if lista:
                k0 = (lista[0].get("slotID"), lista[0].get("vehicleName") or "")
                dadas = completadas.get(k0)
                if dadas is not None and any(int(h.get("totalLaps") or 0) > dadas + 1
                                             for h in lista):
                    corte = len(lista)
            if corte:
                for h in lista[:corte]:
                    k = (h.get("slotID"), h.get("vehicleName") or "")
                    fuera = (int(h.get("totalLaps") or 0), _num(h.get("lapTime")))
                    if k in self.historia:
                        self.historia[k] = [v for v in self.historia[k]
                                            if not (v.get("de_la_historia")
                                                    and (v["vuelta"], v["tiempo"]) == fuera)]
                lista = lista[corte:]
            previa = None
            tocadas = set()
            for h in lista:
                k = (h.get("slotID"), h.get("vehicleName") or "")
                if (k[0], k[1], h.get("totalLaps"), h.get("lapTime")) in self._viejas:
                    continue
                tiempo = _num(h.get("lapTime"))
                boxes = bool(h.get("pitting")) or bool(previa and previa.get("pitting"))
                previa = h
                vuelta = int(h.get("totalLaps") or 0)
                if tiempo is None or not vuelta:
                    continue
                mias = self.historia.setdefault(k, [])
                if any(v["vuelta"] == vuelta for v in mias):
                    continue
                piloto = _limpio(h.get("driverName"))
                self._pilotos.setdefault(k, set()).add(h.get("driverName") or "")
                mejor = mejores.get(k)
                valida = not (mejor and tiempo < mejor - 0.0005)
                s1 = _num(h.get("sectorTime1"))
                s12 = _num(h.get("sectorTime2"))
                mias.append({
                    "vuelta": vuelta, "tiempo": tiempo, "piloto": piloto,
                    "valida": valida, "s1": s1,
                    "s2": s12 - s1 if s1 and s12 else None,
                    "s3": tiempo - s12 if s12 else None,
                    "boxes": boxes, "gasolina": None, "energia": None,
                    "hora": None, "de_la_historia": True,
                })
                tocadas.add(k)
                if valida:
                    kp = (k, piloto)
                    if kp not in self._mejor_piloto or tiempo < self._mejor_piloto[kp]:
                        self._mejor_piloto[kp] = tiempo
                    if k not in self._mejor_coche or tiempo < self._mejor_coche[k]:
                        self._mejor_coche[k] = tiempo
            for k in tocadas:
                self.historia[k].sort(key=lambda v: v["vuelta"])

    def _poner_energia(self, uso):
        """
        Mete la energia virtual de cada vuelta (de /rest/strategy/usage, que
        va por piloto) en las vueltas de cada coche que no la tengan. El valor
        de la vuelta N es el que quedaba al cerrarla, igual que el apuntado en
        directo (comprobado el 30/10/2026).
        """
        for c in self._coches:
            self._pilotos.setdefault(_clave(c), set()).add(c.get("driverName") or "")
        for k, nombres in self._pilotos.items():
            por_vuelta = {}
            for nombre in nombres:
                for e in uso.get(nombre) or []:
                    if isinstance(e, dict) and e.get("lap"):
                        por_vuelta[int(e["lap"])] = e.get("ve")
            if not por_vuelta:
                continue
            for v in self.historia.get(k, []):
                if v.get("energia") is None and v["vuelta"] in por_vuelta:
                    v["energia"] = por_vuelta[v["vuelta"]]

    def gasto(self, k, que):
        """
        Lo que gasta por vuelta, en tanto por uno, de "gasolina" o "energia":
        la media de las ultimas vueltas seguidas sin repostar. None si aun no
        hay con que.

        Se cuenta de vuelta cerrada a vuelta cerrada. Si entre dos sube, ahi
        se reposto y se corta. Las vueltas de boxes no entran: la de entrada
        gasta menos (el limitador) y la de salida empieza con el deposito
        recien lleno.
        """
        vueltas = [v for v in self.historia.get(k, []) if v.get(que) is not None]
        gastos = []
        for antes, ahora in zip(reversed(vueltas[:-1]), reversed(vueltas)):
            if ahora["vuelta"] - antes["vuelta"] != 1:
                break
            bajada = antes[que] - ahora[que]
            if bajada <= 0:
                break                   # repostaje: lo de antes es otro stint
            if ahora["boxes"]:
                continue
            gastos.append(bajada)
            if len(gastos) >= VUELTAS_GASTO:
                break
        if not gastos:
            return None
        return sum(gastos) / len(gastos)

    def ritmo(self, k, cuantas=5):
        """
        A que ritmo va AHORA: la mediana de sus ultimas vueltas limpias (sin
        boxes). Mediana y no media para que una vuelta con un trompo o
        doblando a alguien no la tuerza. Cuentan aunque cambie el piloto: lo
        que interesa es a que va el coche.
        """
        limpias = [v["tiempo"] for v in self.historia.get(k, []) if not v["boxes"]]
        limpias = limpias[-cuantas:]
        if len(limpias) < 2:
            return None
        limpias.sort()
        mitad = len(limpias) // 2
        if len(limpias) % 2:
            return limpias[mitad]
        return (limpias[mitad - 1] + limpias[mitad]) / 2.0

    def perdidas(self, k):
        """
        Lo que le ha costado cada parada, en segundos: lo que tardaron las
        vueltas de boxes (entrada y salida) menos lo que habrian tardado a su
        ritmo de antes. Medido el 30/10/2026 en Barcelona: unos 76 s en GT3 y
        96 en Hypercar, y de 46 a 120 segun lo que se haga en la parada.
        """
        vs = self.historia.get(k, [])
        salida = []
        i = 0
        while i < len(vs):
            if not vs[i]["boxes"] or vs[i]["vuelta"] <= 2:
                i += 1
                continue
            j = i
            while j < len(vs) and vs[j]["boxes"]:
                j += 1
            evento = vs[i:j]
            antes = [v["tiempo"] for v in vs[max(0, i - 5):i] if not v["boxes"]]
            seguidas = all(e["vuelta"] == evento[0]["vuelta"] + n
                           for n, e in enumerate(evento))
            if len(antes) >= 3 and seguidas and len(evento) <= 3:
                antes.sort()
                ref = antes[len(antes) // 2]
                perdida = sum(e["tiempo"] for e in evento) - len(evento) * ref
                if 15.0 < perdida < 400.0:
                    salida.append(perdida)
            i = j
        return salida

    def cruce(self, k, vuelta, empieza, completadas):
        """
        A que hora de sesion cruzo la meta al cerrar la vuelta `vuelta`, o None.

        Se cuenta hacia atras desde la hora a la que empezo la vuelta en curso
        (`empieza`, que da el juego; es cuando cerro la vuelta `completadas`)
        restando los tiempos de las vueltas. Es
        como se miden de verdad las distancias entre coches: cada uno contra el
        otro en la MISMA vuelta, aunque uno vaya doblado.
        """
        if empieza is None:
            return None
        por_vuelta = {v["vuelta"]: v["tiempo"] for v in self.historia.get(k, [])}
        hora = empieza
        n = completadas
        while n > vuelta:
            if n not in por_vuelta:
                return None
            hora -= por_vuelta[n]
            n -= 1
        return hora if n == vuelta else None

    def _paradas_de(self, coche):
        """Las paradas de ese coche segun el juego (/rest/strategy/overall)."""
        equipo = coche.get("fullTeamName") or ""
        piloto = coche.get("driverName") or ""
        candidatas = [p for e, p in self._paradas if e == equipo and p]
        if len(candidatas) > 1:
            candidatas = ([p for p in candidatas
                           if any(x.get("driver") == piloto for x in p)]
                          or candidatas[:1])
        return candidatas[0] if candidatas else []

    def paradas_medidas(self, coche):
        """
        Cada parada hecha, partida en dos: lo que estuvo PARADO (lo apunta el
        juego en `time`) y lo que perdio en el CARRIL de boxes (lo que perdio
        en total menos lo parado). [{"vuelta", "parado", "perdida", "carril",
        "cambio_piloto", "ruedas"}]

        Visto el 30/10/2026 en Barcelona: el carril son unos 27 s, igual para
        todos; con cambio de piloto salen unos 14 s mas de los que el juego
        apunta como parado.
        """
        k = _clave(coche)
        vs = self.historia.get(k, [])
        salida = []
        for p in self._paradas_de(coche):
            vuelta = int(p.get("lap") or 0)
            parado = p.get("time")
            if not vuelta or not isinstance(parado, (int, float)) or parado <= 0:
                continue
            evento = [v for v in vs if v["boxes"] and vuelta - 1 <= v["vuelta"] <= vuelta + 2]
            antes = sorted(v["tiempo"] for v in vs
                           if not v["boxes"] and vuelta - 6 <= v["vuelta"] < vuelta - 1)
            perdida = carril = None
            if evento and len(antes) >= 3:
                ref = antes[len(antes) // 2]
                perdida = sum(v["tiempo"] for v in evento) - len(evento) * ref
                carril = perdida - parado
            salida.append({
                "vuelta": vuelta, "parado": parado, "perdida": perdida,
                "carril": carril, "cambio_piloto": bool(p.get("driverSwap")),
                "ruedas": sum(1 for r in (p.get("tyres") or {}).values() if r.get("changed")),
            })
        return salida

    def carril(self, clase):
        """
        (carril de boxes, lo que se pierde de mas con cambio de piloto) en
        segundos, medidos con las paradas de todos los de esa clase, o
        (None, None). Las raras (reparaciones, sanciones, un trompo a la
        salida) se quitan por no caer entre 10 y 80 s.
        """
        sin, con = [], []
        for c in self._coches:
            if (c.get("carClass") or "") != clase:
                continue
            for p in self.paradas_medidas(c):
                if p["carril"] is None or not 10.0 < p["carril"] < 80.0:
                    continue
                (con if p["cambio_piloto"] else sin).append(p["carril"])
        mediana = lambda xs: sorted(xs)[len(xs) // 2] if xs else None
        base = mediana(sin)
        extra = None
        if base is not None and con:
            extra = max(0.0, mediana(con) - base)
        return base, extra

    def neumaticos(self, coche):
        """
        Lo de los neumaticos de un coche, sacado de sus paradas:
        {"puestos": {"fl": "Wet", ...}, "vueltas": las que llevan,
         "juegos": juegos nuevos montados, contando los de salida}.
        None si no se sabe.

        Las paradas van por nombre de equipo. Si dos coches comparten nombre,
        se desempata por los pilotos que han subido a cada uno.
        """
        paradas = self._paradas_de(coche)
        if not paradas:
            return None
        puestos, cambiada = {}, {}
        nuevas = 0
        for i, p in enumerate(paradas):
            for rueda, r in (p.get("tyres") or {}).items():
                if i == 0 or r.get("changed"):
                    puestos[rueda] = r.get("compound") or ""
                    cambiada[rueda] = int(p.get("lap") or 0)
                    if r.get("new"):
                        nuevas += 1
        if not puestos:
            return None
        hechas = int(coche.get("lapsCompleted") or 0)
        vueltas = max(0, hechas - min(cambiada.values()))

        # OJO: si el juego se reinicia a media carrera, al volver solo
        # recuerda las paradas de NUESTRO equipo; de los demas solo queda la
        # salida. Visto el 30/10/2026: tras reiniciar el ordenador todo el
        # mundo salia con lluvia (la carrera empezo mojada) y todos llevaban
        # secos. Si un coche lleva mas vueltas sin parar de las que le da un
        # deposito, es que ha parado y no lo sabemos: mejor "?" que mentir.
        stint = self._stint_maximo(coche)
        if vueltas > stint:
            return {"desconocido": True}
        # Lo mismo con los que entraron (o volvieron a entrar) a media
        # carrera: solo queda la salida, que no es lo que llevan.
        if len(paradas) == 1:
            lider = max((int(c.get("lapsCompleted") or 0) for c in self._coches
                         if c.get("carClass") == coche.get("carClass")), default=0)
            if lider and hechas < lider * 0.5:
                return {"desconocido": True}
        # Los juegos solo si no falta ninguna parada por medio.
        vueltas_paradas = [0] + sorted(int(p.get("lap") or 0) for p in paradas[1:]) + [hechas]
        completo = all(b - a <= stint for a, b in zip(vueltas_paradas, vueltas_paradas[1:]))
        return {"puestos": puestos, "vueltas": vueltas,
                "juegos": nuevas / 4.0 if completo else None}

    def _stint_maximo(self, coche):
        """
        Las vueltas que como mucho se pueden dar con un deposito (con margen),
        de lo que gasta ese coche; si aun no se sabe, 45.
        """
        k = _clave(coche)
        gastos = [g for g in (self.gasto(k, "energia"), self.gasto(k, "gasolina")) if g]
        if not gastos:
            return 45
        return int(1.0 / max(gastos) * 1.15) + 3

    def _guardar(self, c, v):
        """Apunta la vuelta en el CSV de la sesion. Si no se puede, se sigue."""
        try:
            if self._archivo is None:
                carpeta = rutas.datos(CARPETA_VUELTAS)
                os.makedirs(carpeta, exist_ok=True)
                self._archivo = os.path.join(carpeta, datetime.datetime.now()
                                             .strftime("%Y-%m-%d_%H%M%S.csv"))
            nuevo = not os.path.exists(self._archivo)
            with open(self._archivo, "a", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f, delimiter=";")
                if nuevo:
                    w.writerow(["hora", "dorsal", "clase", "coche", "equipo",
                                "piloto", "vuelta", "tiempo", "valida", "s1",
                                "s2", "s3", "boxes", "gasolina", "energia",
                                "puesto"])
                num = lambda x: "" if x is None else ("%.3f" % x).replace(".", ",")
                w.writerow([datetime.datetime.now().strftime("%H:%M:%S"),
                            c.get("carNumber"), c.get("carClass"),
                            c.get("vehicleName"), c.get("fullTeamName"),
                            v["piloto"], v["vuelta"], num(v["tiempo"]),
                            "si" if v["valida"] else "NO", num(v["s1"]),
                            num(v["s2"]), num(v["s3"]),
                            "si" if v["boxes"] else "",
                            num(v["gasolina"]), num(v["energia"]),
                            c.get("position")])
        except Exception:
            pass

    def anuladas(self, k, piloto):
        """(vueltas anuladas, vueltas dadas) de ese piloto en ese coche, en la sesion."""
        suyas = [v for v in self.historia.get(k, []) if v["piloto"] == piloto]
        return sum(1 for v in suyas if not v["valida"]), len(suyas)

    def _media_del_relevo(self, k, piloto):
        """
        (media, cuantas vueltas) del piloto que lleva el coche AHORA, desde que
        se subio: al cambiar de piloto vuelve a empezar de cero.

        Se cuentan las vueltas seguidas de ese piloto desde la ultima del
        anterior. Las de entrada y salida de boxes no entran: van 20 o 30
        segundos mas lentas y la media dejaria de decir a que ritmo va. Las
        que no cuentan por limites de pista si entran: el ritmo es ese.
        """
        tiempos = []
        for v in reversed(self.historia.get(k, [])):
            if v["piloto"] != piloto:
                break
            if not v["boxes"]:
                tiempos.append(v["tiempo"])
        if not tiempos:
            return None, 0
        return sum(tiempos) / len(tiempos), len(tiempos)

    def _combustible(self, k, c):
        """
        Gasto por vuelta, vueltas que le quedan y la vuelta en la que tiene
        que parar, de gasolina y de energia virtual. Manda lo que se acabe
        antes: en Hypercar y GT3 casi siempre es la energia.
        """
        vueltas = int(c.get("lapsCompleted") or 0)
        salida = {}
        for que, campo in (("gasolina", "fuelFraction"), ("energia", "veFraction")):
            queda = c.get(campo)
            gasto = self.gasto(k, que)
            if not isinstance(queda, (int, float)) or queda < 0 or not gasto:
                salida[que] = {"gasto": gasto, "quedan": None}
                continue
            salida[que] = {"gasto": gasto, "quedan": queda / gasto}
        cuales = [x for x in salida.values() if x["quedan"] is not None]
        manda = min(cuales, key=lambda x: x["quedan"]) if cuales else None
        salida["manda"] = ("energia" if manda is salida["energia"] else "gasolina") if manda else None
        salida["quedan"] = manda["quedan"] if manda else None
        # Lo que queda se mide desde la ultima vuelta cerrada, asi que la
        # vuelta en la que ya no llega es la de ahora mas las que quedan.
        salida["parar_en"] = vueltas + int(manda["quedan"]) if manda else None
        return salida

    def _pedir(self, url):
        pet = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(pet, timeout=ESPERA * 2) as r:
            crudo = r.read()
        # utf-8-sig: la API cuela el BOM delante del JSON
        return json.loads(crudo.decode("utf-8-sig", "replace"))

    def _lo_lento(self, cuando):
        """Lo que no hace falta cada segundo: paradas, historia y sesion."""
        ahora = time.monotonic()
        if ahora - cuando.get("paradas", -999) > CADA_PARADAS:
            cuando["paradas"] = ahora
            d = self._pedir(URL_PARADAS)
            if isinstance(d, list):
                self._paradas = [x for x in d if isinstance(x, list) and len(x) == 2]
        if ahora - cuando.get("historia", -999) > CADA_HISTORIA:
            cuando["historia"] = ahora
            d = self._pedir(URL_HISTORIA)
            if isinstance(d, dict):
                self._rellenar(d)
            d = self._pedir(URL_ENERGIA)
            if isinstance(d, dict):
                self._poner_energia(d)
        if ahora - cuando.get("info", -999) > CADA_INFO:
            cuando["info"] = ahora
            d = self._pedir(URL_INFO)
            if isinstance(d, dict):
                self.info, self.info_sello = d, time.monotonic()
                nombre = d.get("session")
                if nombre and nombre != self._nombre_sesion:
                    if self._nombre_sesion is not None:
                        # sesion nueva con el mapa abierto: fuera lo de antes,
                        # y lo que traiga ahora la historia es de la vieja
                        self._vaciar()
                        self._marcar_viejas = True
                        cuando["historia"] = -999   # pedirla ya
                    self._nombre_sesion = nombre
        if ahora - cuando.get("sesion", -999) > CADA_SESION:
            cuando["sesion"] = ahora
            d = self._pedir(URL_SESION)
            ajuste = (d or {}).get("SESSSET_tires_available_in_garage") or {}
            valor = ajuste.get("currentValue")
            self.ruedas_garaje = int(valor) if isinstance(valor, (int, float)) else None

    def _bucle(self):
        cuando = {}
        while True:
            try:
                pet = urllib.request.Request(URL, headers={"Accept": "application/json"})
                with urllib.request.urlopen(pet, timeout=ESPERA) as r:
                    crudo = r.read()
                # utf-8-sig: la API cuela el BOM delante del JSON
                d = json.loads(crudo.decode("utf-8-sig", "replace"))
                if isinstance(d, list):
                    coches = [c for c in d if isinstance(c, dict)]
                    try:
                        self._apuntar(coches)
                    except Exception:
                        pass        # que un fallo apuntando no deje sin tabla
                    self._coches = coches
                    self._sello = time.monotonic()
                    self._fallos = 0
                    try:
                        self._lo_lento(cuando)
                    except Exception:
                        pass        # sin historia o paradas, la tabla sigue
                else:
                    self._fallos += 1
            except Exception:
                # Juego cerrado o cargando: volver a preguntar. Este hilo no
                # puede morirse.
                self._fallos += 1
            time.sleep(CADA if self._fallos < 5 else CADA * 3)


def _clave(c):
    """Lo que identifica un coche durante la sesion, cambie quien lo conduzca."""
    return (c.get("slotID"), c.get("vehicleName") or "")


def _limpio(nombre):
    """'Alberto Martos#4037' -> 'Alberto Martos' (el # es su etiqueta de Discord)."""
    return re.sub(r"#\d+$", "", nombre or "").strip()


tabla = Tabla()


def reloj(segundos):
    """106.409 -> '1:46.409'; 31.2 -> '31.200'; None -> '-:--.---'."""
    if not segundos:
        return "-:--.---"
    m, s = divmod(segundos, 60.0)
    if m:
        return "%d:%06.3f" % (m, s)
    return "%.3f" % s


def distancia(par):
    """(12.34, 0) -> '+12.3'; (None, 2) -> '+2 V'; (None, 0) -> ''."""
    tiempo, vueltas = par
    if vueltas:
        return "+%d V" % vueltas
    if tiempo is None or tiempo <= 0:
        return ""
    if tiempo >= 60:
        return "+" + reloj(tiempo)[:-2]
    return "+%.1f" % tiempo
