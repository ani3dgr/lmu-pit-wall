# -*- coding: utf-8 -*-
"""
El panel de clasificacion: los tiempos de todos los coches, encima del juego.

Una fila por coche, en orden de posicion. Las columnas las elige cada uno en
Opciones -> Tiempos -> Clasificacion, y tambien su orden: hay muchas (puesto,
marca, dorsal, piloto, mejor vuelta del coche y del piloto, sectores,
distancias, combustible...) y cada uno quiere ver unas. Nuestro coche va
resaltado, y la mejor vuelta de cada clase sale en morado, como en la tele.

Los datos los trae clasificacion.py de la API del juego. Va en su propia
ventana, como el clima y los frenos: se arrastra con el raton mientras las
opciones estan abiertas.
"""
import time
import tkinter as tk

import clasificacion
import idiomas

T = idiomas.t

CHROMA = "#010203"          # el color que Windows vuelve transparente
MARGEN = 8
ALTO_FILA = 20
MORADO = "#bf5af2"
GRIS_CLARO = "#9aa3ad"
AMARILLO = "#ffd60a"
ROJO = "#ff453a"
RESALTE = "#1f3b57"
FILAS_RUEDA = 3             # filas que mueve cada golpe de rueda del raton
MANUAL_S = 30.0
ASA = 16                    # pixeles de la esquina que sirven para estirar             # tras usar la rueda, lo que tarda en volver solo
CLASES = (("hyper", "#e8102a"), ("lmp2", "#2f7de1"), ("lmp3", "#a855f7"),
          ("gt3", "#25b84c"), ("gte", "#f59e0b"))

# Todas las columnas que se pueden poner: (clave, ancho, a la derecha).
# El nombre corto de la cabecera es "cla.col.<clave>" en los idiomas, y el
# largo, el de la lista de Opciones, "cla.nom.<clave>".
COLUMNAS = [
    ("puesto", 30, True),
    ("puesto_general", 34, True),
    ("clase", 58, False),
    ("marca", 40, False),
    ("dorsal", 42, False),
    ("piloto", 160, False),
    ("equipo", 170, False),
    ("mejor", 72, True),
    ("mejor_piloto", 72, True),
    ("ultima", 72, True),
    ("media", 100, True),
    ("en_curso", 66, True),
    ("s1", 54, True),
    ("s2", 54, True),
    ("s3", 54, True),
    ("mejor_s1", 54, True),
    ("mejor_s2", 54, True),
    ("mejor_s3", 54, True),
    ("dif_lider", 64, True),
    ("dif_clase", 64, True),
    ("dif_delante", 60, True),
    ("dif_delante_clase", 60, True),
    ("vueltas", 40, True),
    ("paradas", 40, True),
    ("penas", 40, True),
    ("anuladas", 50, True),
    ("sanciones_piloto", 44, True),
    ("neumatico", 56, False),
    ("neum_vueltas", 44, True),
    ("juegos", 56, True),
    ("gasolina", 48, True),
    ("energia", 48, True),
    ("gasto_gasolina", 54, True),
    ("gasto_energia", 54, True),
    ("vueltas_quedan", 50, True),
    ("parar_en", 50, True),
    ("salida", 40, True),
]
_POR_CLAVE = {c[0]: c for c in COLUMNAS}
DE_SALIDA = ("puesto", "marca", "dorsal", "piloto", "mejor", "mejor_piloto",
             "ultima", "media", "en_curso", "neumatico", "gasolina",
             "energia", "gasto_energia", "vueltas_quedan", "parar_en")


def columnas(cfg):
    """
    [[clave, se_ve], ...] en el orden elegido, siempre con TODAS las columnas.

    Lo guardado se respeta; lo que falte (columnas nuevas de una version
    posterior) se anade al final.
    """
    guardadas = cfg.get("tabla_columnas")
    salida, vistas = [], set()
    if isinstance(guardadas, list):
        for par in guardadas:
            try:
                clave, ver = par[0], bool(par[1])
            except (TypeError, IndexError):
                continue
            if clave in _POR_CLAVE and clave not in vistas:
                salida.append([clave, ver])
                vistas.add(clave)
        # Una columna que no estaba cuando se guardo sale como en una
        # instalacion nueva: encendida si es de las de salida.
        for clave, _, _ in COLUMNAS:
            if clave not in vistas:
                salida.append([clave, clave in DE_SALIDA])
        return salida
    return [[clave, clave in DE_SALIDA] for clave, _, _ in COLUMNAS]


def _color_clase(clase):
    plano = (clase or "").lower().replace(" ", "")
    for trozo, color in CLASES:
        if trozo in plano:
            return color
    return GRIS_CLARO


def _corta_clase(clase):
    plano = (clase or "").lower()
    if "hyper" in plano:
        return "HY"
    if "gt3" in plano:
        return "GT3"
    return (clase or "")[:5].upper()


def _por_ciento(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "", None
    if v < 0:
        return "", None
    return "%.0f%%" % (v * 100.0), (ROJO if v < 0.1 else None)


# Los compuestos, como los pinta la tele: (letra, color). La letra sale de los
# idiomas ("cla.neu.<compuesto>") para que en espanol la blanda sea B y no S.
COMPUESTOS = {"soft": "#ff3b30", "medium": "#ffd60a", "hard": "#f2f2f2",
              "wet": "#2f8cff", "inter": "#30d158", "intermediate": "#30d158"}


def _compuesto(nombre):
    plano = (nombre or "").strip().lower()
    if plano not in COMPUESTOS:
        return "?", GRIS_CLARO
    return T("cla.neu." + plano), COMPUESTOS[plano]


def _neumatico(n):
    """Una letra si van las cuatro iguales; delante/detras si no."""
    if not n:
        return "", None, False
    if n.get("desconocido"):
        return "?", GRIS_CLARO, False
    p = n["puestos"]
    delante = {p.get("fl"), p.get("fr")} - {None}
    detras = {p.get("rl"), p.get("rr")} - {None}
    if len(delante | detras) == 1:
        letra, color = _compuesto(next(iter(delante | detras)))
        return letra, color, True
    d = "".join(_compuesto(x)[0] for x in sorted(delante))
    t = "".join(_compuesto(x)[0] for x in sorted(detras))
    color = _compuesto(sorted(delante)[0])[1] if delante else None
    return "%s/%s" % (d, t), color, True


def _calculando():
    """
    Lo que sale mientras faltan vueltas para sacar una media: despues de parar
    en boxes hacen falta un par sin repostar. Un hueco vacio parecia un fallo.
    """
    return T("cla.p.calculando"), GRIS_CLARO, False


def _celda(f, clave):
    """(texto, color o None para el normal, en negrita)"""
    reloj = clasificacion.reloj
    # El puesto que importa es el de la clase: en una carrera con Hypercar y
    # GT3 juntos, el primer GT3 va 15o de la general y eso no dice nada.
    if clave == "puesto":
        return str(f.get("puesto_clase") or f["puesto"]), None, True
    if clave == "puesto_general":
        return str(f["puesto"]), None, True
    if clave == "clase":
        return _corta_clase(f["clase"]), _color_clase(f["clase"]), True
    if clave == "dorsal":
        return ("#" + f["dorsal"]) if f["dorsal"] else "", None, False
    if clave in ("piloto", "equipo"):
        return f[clave], None, False
    if clave == "mejor":
        if f["la_mejor"]:
            return reloj(f["mejor"]), MORADO, True
        return reloj(f["mejor"]), None, False
    if clave in ("mejor_piloto", "ultima"):
        return reloj(f[clave]), None, False
    if clave == "media":
        # con cuantas vueltas esta hecha: va subiendo hasta el cambio de piloto
        if not f["media"]:
            return _calculando()
        return "%s (%d)" % (reloj(f["media"]), f["media_vueltas"]), None, False
    if clave == "en_curso":
        if f["en_boxes"]:
            return T("cla.p.boxes"), AMARILLO, True
        return reloj(f["en_curso"])[:-2], None, False     # en decimas
    if clave in ("s1", "s2", "s3", "mejor_s1", "mejor_s2", "mejor_s3"):
        v = f[clave]
        return ("%.3f" % v) if v else "-", None, False
    if clave in ("dif_lider", "dif_clase", "dif_delante", "dif_delante_clase"):
        return clasificacion.distancia(f[clave]), None, False
    if clave in ("vueltas", "paradas", "salida"):
        return str(f[clave]), None, False
    if clave == "penas":
        n = f["penas"]
        return (str(n), ROJO, True) if n else ("", None, False)
    if clave == "anuladas":
        # anuladas / dadas, del piloto que conduce, en toda la sesion
        malas, todas = f["anuladas"]
        if not todas:
            return "", None, False
        return "%d/%d" % (malas, todas), (ROJO if malas else None), bool(malas)
    if clave == "sanciones_piloto":
        n = f["sanciones_piloto"]
        return (str(n), ROJO, True) if n else ("", None, False)
    if clave == "neumatico":
        return _neumatico(f.get("neumaticos"))
    if clave == "neum_vueltas":
        n = f.get("neumaticos")
        if n and n.get("desconocido"):
            return "?", GRIS_CLARO, False
        return (str(n["vueltas"]), None, False) if n else ("", None, False)
    if clave == "juegos":
        # juegos nuevos montados; y si el servidor dice cuantas ruedas da,
        # los que le quedan (una estimacion: ver la ayuda)
        n = f.get("neumaticos")
        if not n:
            return "", None, False
        if n.get("desconocido") or n.get("juegos") is None:
            return "?", GRIS_CLARO, False
        usados = n["juegos"]
        texto = ("%.1f" % usados).rstrip("0").rstrip(".")
        garaje = clasificacion.tabla.ruedas_garaje
        if garaje:
            quedan = max(0.0, garaje / 4.0 - usados)
            texto += " (%s)" % ("%.1f" % quedan).rstrip("0").rstrip(".")
            return texto, (ROJO if quedan < 1 else None), False
        return texto, None, False
    if clave in ("gasto_gasolina", "gasto_energia"):
        que = clave[6:]
        g = ((f.get("combustible") or {}).get(que) or {}).get("gasto")
        if g:
            return "%.1f%%" % (g * 100.0), None, False
        # solo "calculando" si el juego da ese dato de este coche
        queda = f.get(que)
        if isinstance(queda, (int, float)) and queda > 0:
            return _calculando()
        return "", None, False
    if clave == "vueltas_quedan":
        q = (f.get("combustible") or {}).get("quedan")
        if q is None:
            return _calculando() if f.get("combustible") else ("", None, False)
        return "%.1f" % q, (ROJO if q < 2 else (AMARILLO if q < 4 else None)), q < 4
    if clave == "parar_en":
        v = (f.get("combustible") or {}).get("parar_en")
        if v is not None:
            return str(v), None, False
        return _calculando() if f.get("combustible") else ("", None, False)
    if clave in ("gasolina", "energia"):
        texto, color = _por_ciento(f[clave])
        return texto, color, False
    return "", None, False


class Panel:
    # Las claves de la configuracion van con este prefijo ("tabla_x",
    # "tabla_tam"...). El panel de estrategia aprovecha todo esto (arrastrar,
    # fondo, rueda del raton) con el suyo.
    PRE = "tabla"

    def __init__(self, raiz, cfg, guardar):
        self.cfg = cfg
        self.guardar = guardar
        self.arrastre = None
        self.estirando = None
        self.modo_mover = False
        self._ultimo = None         # lo ultimo pintado, para no repintar igual
        self._cuando = 0.0
        # Desplazamiento con la rueda del raton. None = solo, centrado en el
        # nuestro; un numero = la primera fila que se ensena, elegida a mano.
        self._desde = None
        self._manual_hasta = 0.0
        self._inicio = 0            # lo ultimo ensenado, para la rueda y la barra
        self._total = 0

        v = tk.Toplevel(raiz)
        self.v = v
        v.overrideredirect(True)
        v.attributes("-topmost", True)
        v.attributes("-transparentcolor", CHROMA)
        v.attributes("-alpha", float(cfg.get(self.PRE + "_opacidad", 0.95)))
        v.configure(bg=CHROMA)
        v.withdraw()

        self.lienzo = tk.Canvas(v, bg=CHROMA, highlightthickness=0)
        self.lienzo.pack()
        self.lienzo.bind("<Button-1>", self._empezar_arrastre)
        self.lienzo.bind("<B1-Motion>", self._arrastrar)
        self.lienzo.bind("<ButtonRelease-1>", self._soltar)
        self.lienzo.bind("<Motion>", self._cursor)
        self.lienzo.bind("<MouseWheel>", self._rueda)
        self.v.bind("<MouseWheel>", self._rueda)
        self.lienzo.bind("<Double-Button-1>", self._volver_al_nuestro)

    # ------------------------------------------------------------ rueda
    def _rueda(self, e):
        """
        Subir y bajar por la parrilla cuando no cabe entera, para tenerlo en
        grande en una segunda pantalla. Pasado un rato sin tocarla vuelve sola
        a centrarse en nuestro coche, y con doble clic al momento.
        """
        paso = -FILAS_RUEDA if e.delta > 0 else FILAS_RUEDA
        self._desde = max(0, self._inicio + paso)
        self._manual_hasta = time.monotonic() + MANUAL_S
        self._cuando = 0.0          # que se vea ya, sin esperar al repintado

    def _volver_al_nuestro(self, _=None):
        self._desde = None
        self._cuando = 0.0

    # ------------------------------------------------------------ arrastre
    def _empezar_arrastre(self, e):
        # La esquina de abajo a la derecha es el asa para estirar la ventana.
        self.estirando = None
        try:
            ancho, alto = int(self.lienzo["width"]), int(self.lienzo["height"])
        except (tk.TclError, ValueError):
            ancho = alto = 0
        if ancho and e.x >= ancho - ASA and e.y >= alto - ASA:
            self.estirando = (e.x_root, e.y_root, ancho,
                              float(self.cfg.get(self.PRE + "_tam", 100)),
                              getattr(self, "_mostradas", 0) or 1,
                              getattr(self, "_fila_h", ALTO_FILA) or ALTO_FILA)
            self.arrastre = None
            return
        # Un clic en la barra de la derecha pasa una pagina arriba o abajo,
        # por si la rueda no llega (con el juego delante, Windows se la puede
        # dar al juego).
        barra = getattr(self, "_barra", None)
        if barra and e.x >= barra[0]:
            n = max(1, int(self.cfg.get(self.PRE + "_filas", 60)) - 2)
            paso = -n if e.y < barra[1] else n
            self._desde = max(0, self._inicio + paso)
            self._manual_hasta = time.monotonic() + MANUAL_S
            self._cuando = 0.0
            self.arrastre = None
            return
        self.arrastre = (e.x, e.y)

    def _arrastrar(self, e):
        if self.estirando:
            self._estirar(e)
            return
        if not self.arrastre:
            return
        self.cfg[self.PRE + "_x"] += e.x - self.arrastre[0]
        self.cfg[self.PRE + "_y"] += e.y - self.arrastre[1]
        self.v.geometry("+%d+%d" % (self.cfg[self.PRE + "_x"], self.cfg[self.PRE + "_y"]))
        self.guardar(self.cfg)

    def _estirar(self, e):
        """
        Estirar con el asa de la esquina, para encajar las ventanas a mano (una
        debajo de otra en una segunda pantalla, por ejemplo):
          - de lado cambia el ANCHO, sin tocar las letras (Manuel lo queria
            asi para que quepan los textos largos de la parada en boxes; el
            tamano de las letras va aparte, en Opciones). Nunca mas estrecha
            que la tabla;
          - de arriba abajo cambia el ALTO: cuantas filas se ven (las "filas"
            de Opciones). Si hay menos coches que filas, no crece mas.
        """
        x0, y0, ancho0, tam0, filas0, fila_h = self.estirando
        ancho = max(120, ancho0 + e.x_root - x0)
        filas = max(3, min(80, filas0 + int(round((e.y_root - y0) / float(fila_h)))))
        if (ancho, filas) != (self.cfg.get(self.PRE + "_ancho"),
                              self.cfg.get(self.PRE + "_filas")):
            self.cfg[self.PRE + "_ancho"] = ancho
            self.cfg[self.PRE + "_filas"] = filas
            self._cuando = 0.0          # que se vea ya

    def _cursor(self, e):
        """
        Encima del asa, el cursor de estirar en diagonal: si no, nadie se
        entera de que la ventana se puede cambiar de tamano.
        """
        try:
            ancho, alto = int(self.lienzo["width"]), int(self.lienzo["height"])
            en_asa = e.x >= ancho - ASA and e.y >= alto - ASA
            querido = "size_nw_se" if en_asa else ""
            if self.lienzo["cursor"] != querido:
                self.lienzo.configure(cursor=querido)
        except (tk.TclError, ValueError):
            pass

    def _soltar(self, _=None):
        if self.estirando:
            self.estirando = None
            self.guardar(self.cfg)

    def _asa(self, c, ancho, alto, esc):
        """Tres rayitas en la esquina: por ahi se estira."""
        for i in (4, 8, 12):
            d = int(i * esc * 0.8)
            c.create_line(ancho - d, alto - 2, ancho - 2, alto - d,
                          fill="#ffffff", width=max(1, int(round(1.5 * esc))))

    def colocar(self, moviendo):
        """
        Con las opciones abiertas se ensena siempre, para poder colocarlo: con
        la carrera de verdad si la hay, y si no con datos de muestra.
        """
        self.modo_mover = moviendo
        self._ultimo = None
        if moviendo:
            self.pintar([], forzar=True)
        elif not self.cfg.get(self.PRE + "_ver", False):
            self.esconder()

    def esconder(self):
        if self.modo_mover:
            return
        self._ultimo = None
        self.v.withdraw()

    # -------------------------------------------------------------- pintar
    def pintar(self, filas, forzar=False):
        """`filas`: las de clasificacion.Tabla.filas()."""
        if not self.cfg.get(self.PRE + "_ver", False) and not self.modo_mover:
            self.esconder()
            return
        # El reloj de la vuelta en curso cambia sin parar: diez veces por
        # segundo basta para verlo correr y no se repinta en cada vuelta del
        # bucle del mapa (veinte por segundo).
        ahora = time.monotonic()
        if not forzar and ahora - self._cuando < 0.1:
            return
        if not filas and self.modo_mover:
            filas = _muestra()
        filas = self._recortar(filas)
        cols = [_POR_CLAVE[k] for k, ver in columnas(self.cfg) if ver]
        celdas = [[_celda(f, col[0]) if col[0] != "marca" else None for col in cols]
                  for f in filas]
        firma = (tuple(tuple(map(tuple, (x for x in fila if x))) for fila in celdas),
                 tuple(f["es_yo"] for f in filas),
                 tuple(c[0] for c in cols),
                 self.cfg.get(self.PRE + "_tam"), self.cfg.get(self.PRE + "_fondo"),
                 self.cfg.get(self.PRE + "_opacidad"), self.cfg.get(self.PRE + "_color_fondo"),
                 self.cfg.get(self.PRE + "_color_texto"), self.modo_mover)
        if firma == self._ultimo:
            return
        self._ultimo = firma
        self._cuando = ahora

        esc = max(0.5, float(self.cfg.get(self.PRE + "_tam", 100)) / 100.0)
        c = self.lienzo
        c.delete("all")
        anchos = [int(col[1] * esc) for col in cols]
        x0 = int(MARGEN * esc)
        ancho = max(int(160 * esc), sum(anchos) + x0 * 2,
                    int(self.cfg.get(self.PRE + "_ancho") or 0))
        fila_h = int(ALTO_FILA * esc)
        alto = int((MARGEN * 2 + 22) * esc) + fila_h * max(1, len(filas))
        con_barra = self._total > len(filas)
        if con_barra:
            ancho += int(8 * esc)   # sitio para la barra de desplazamiento

        c.configure(width=ancho, height=alto)
        if self.cfg.get(self.PRE + "_fondo", True):
            self._caja(c, 0, 0, ancho, alto,
                       self.cfg.get(self.PRE + "_color_fondo", "#0d1116"), esc)
        texto = self.cfg.get(self.PRE + "_color_texto", "#ffffff")
        self._asa(c, ancho, alto, esc)
        self._mostradas, self._fila_h = len(filas), fila_h

        xs = []
        x = x0 + int(4 * esc)        # deja sitio a la raya de la clase
        for a in anchos:
            xs.append(x)
            x += a

        # cabecera
        y = int((MARGEN + 9) * esc)
        for i, col in enumerate(cols):
            derecha = col[2]
            self._texto(c, xs[i] + anchos[i] - 4 if derecha else xs[i] + 4, y,
                        T("cla.col." + col[0]), GRIS_CLARO, int(8 * esc), "bold",
                        "e" if derecha else "w")
        y = int((MARGEN + 22) * esc)

        if not filas:
            self._texto(c, ancho / 2, y + fila_h / 2, T("cla.p.sin_datos"),
                        GRIS_CLARO, int(9 * esc))

        letra = int(9 * esc)
        for f, fila in zip(filas, celdas):
            medio = y + fila_h / 2
            if f["es_yo"]:
                c.create_rectangle(x0, y, ancho - x0, y + fila_h,
                                   fill=RESALTE, outline="")
            # la raya de color de la clase, a la izquierda
            c.create_rectangle(x0, y + 3, x0 + max(2, int(3 * esc)), y + fila_h - 3,
                               fill=_color_clase(f["clase"]), outline="")
            for i, col in enumerate(cols):
                if col[0] == "marca":
                    self._placa(c, xs[i] + 4, medio, f["marca"], esc)
                    continue
                valor, color, negrita = fila[i]
                if col[0] in ("piloto", "equipo"):
                    valor = self._corta(valor, anchos[i] - 8, letra,
                                        "bold" if f["es_yo"] else "normal")
                peso = "bold" if (negrita or f["es_yo"]) else "normal"
                self._texto(c, xs[i] + anchos[i] - 4 if col[2] else xs[i] + 4,
                            medio, valor, color or texto, letra, peso,
                            "e" if col[2] else "w")
            y += fila_h

        if con_barra:
            # La barra de la derecha: donde esta lo que se ve dentro de toda
            # la parrilla. Se mueve con la rueda del raton.
            arriba = int((MARGEN + 22) * esc)
            largo = fila_h * len(filas)
            bx = ancho - x0 - int(4 * esc)
            c.create_rectangle(bx, arriba, bx + int(4 * esc), arriba + largo,
                               fill="#2a3038", outline="")
            y0 = arriba + largo * self._inicio / self._total
            y1 = arriba + largo * (self._inicio + len(filas)) / self._total
            c.create_rectangle(bx, y0, bx + int(4 * esc), y1,
                               fill=GRIS_CLARO, outline="")
            self._barra = (bx - int(6 * esc), (y0 + y1) / 2)
        else:
            self._barra = None

        self.v.attributes("-alpha", float(self.cfg.get(self.PRE + "_opacidad", 0.95)))
        self.v.geometry("%dx%d+%d+%d" % (ancho, alto, self.cfg.get(self.PRE + "_x", 60),
                                         self.cfg.get(self.PRE + "_y", 200)))
        self.v.deiconify()
        self.v.lift()

    def _recortar(self, filas):
        """
        Si hay mas coches que filas, las que se ensenan van CENTRADAS en el
        nuestro: lo que interesa en carrera es quien va delante y detras.
        """
        n = max(1, int(self.cfg.get(self.PRE + "_filas", 60)))
        self._total = len(filas)
        if len(filas) <= n:
            self._inicio = 0
            return filas
        if self._desde is not None and time.monotonic() > self._manual_hasta:
            self._desde = None
        if self._desde is not None:
            desde = self._desde
        else:
            # Desde arriba, y solo se baja lo justo para que el nuestro se vea
            # con tres coches por detras. Centrarlo escondia a los de cabeza
            # aunque solo sobrasen dos filas (visto el 30/10/2026: 27 GT3 en
            # 25 filas y la tabla empezaba en el 3o).
            mio = next((i for i, f in enumerate(filas) if f["es_yo"]), None)
            desde = 0 if mio is None else mio - (n - 4)
        desde = max(0, min(desde, len(filas) - n))
        if self._desde is not None:
            self._desde = desde
        self._inicio = desde
        return filas[desde:desde + n]

    # ------------------------------------------------------------- ayudas
    def _placa(self, c, x, y, marca, esc):
        """La marca: una placa con sus siglas en los colores de la casa."""
        _, siglas, fondo, letras = marca
        w, h = int(32 * esc), int(14 * esc)
        oscuro = fondo.lower() in ("#000000", "#1a1a1a", "#1e1e1e")
        c.create_rectangle(x, y - h / 2, x + w, y + h / 2, fill=fondo,
                           outline="#4a525c" if oscuro else fondo)
        c.create_text(x + w / 2, y, text=siglas, fill=letras,
                      font=("Segoe UI", max(6, int(7 * esc)), "bold"))

    def _corta(self, texto, ancho, tam, peso):
        """Recorta un nombre si no cabe en su columna."""
        if self._ancho(texto, tam, peso) <= ancho:
            return texto
        while texto and self._ancho(texto + "...", tam, peso) > ancho:
            texto = texto[:-1]
        return texto + "..."

    def _caja(self, c, x, y, ancho, alto, color, esc):
        """El fondo, con las esquinas redondeadas a mano."""
        r = int(7 * esc)
        c.create_rectangle(x + r, y, x + ancho - r, y + alto, fill=color,
                           outline=color)
        c.create_rectangle(x, y + r, x + ancho, y + alto - r, fill=color,
                           outline=color)
        for ex, ey in ((x, y), (x + ancho - 2 * r, y),
                       (x, y + alto - 2 * r), (x + ancho - 2 * r, y + alto - 2 * r)):
            c.create_oval(ex, ey, ex + 2 * r, ey + 2 * r, fill=color,
                          outline=color)

    def _texto(self, c, x, y, texto, color, tam, peso="normal", anclaje="center"):
        letra = ("Segoe UI", max(6, int(tam)), peso)
        if not self.cfg.get(self.PRE + "_fondo", True):
            # sin fondo, el texto va sobre el juego y necesita sombra
            for ox, oy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
                c.create_text(x + ox, y + oy, text=texto, font=letra,
                              fill="#000000", anchor=anclaje)
        c.create_text(x, y, text=texto, font=letra, fill=color, anchor=anclaje)

    def _ancho(self, texto, tam, peso="normal"):
        import tkinter.font as tkfont
        try:
            return tkfont.Font(family="Segoe UI", size=max(6, int(tam)),
                               weight=peso).measure(texto)
        except tk.TclError:
            return int(len(texto) * tam * 0.6)


def _muestra():
    """Lo que se ensena con las opciones abiertas si no hay carrera."""
    m = clasificacion.marca_de
    datos = [
        (1, "Hypercar", "50", "(muestra) A", m("Ferrari 499P"), 106.071, 41.3),
        (2, "Hypercar", "7", "(muestra) B", m("Toyota GR010"), 106.233, 39.8),
        (3, "LMGT3", "92", "(muestra) C", m("Porsche 911 GT3 R"), 115.654, 52.1),
        (4, "LMGT3", "399", "(muestra) D", m("Z06GT3R"), 117.186, 48.7),
        (5, "LMGT3", "21", "(muestra) E", m("McLaren 720S"), 117.207, None),
    ]
    filas = []
    for puesto, clase, dorsal, piloto, marca, mejor, en_curso in datos:
        filas.append({
            "puesto": puesto, "puesto_clase": puesto if puesto < 3 else puesto - 2,
            "clase": clase, "dorsal": dorsal, "piloto": piloto,
            "equipo": "", "marca": marca, "mejor": mejor,
            "mejor_piloto": mejor + 0.4, "ultima": mejor + 0.8,
            "media": mejor + 1.1, "media_vueltas": 7,
            "en_curso": en_curso, "s1": 31.2, "s2": 42.1, "s3": 33.0,
            "mejor_s1": 30.9, "mejor_s2": 41.8, "mejor_s3": 32.7,
            "dif_lider": (puesto * 2.1 - 2.1, 0), "dif_clase": (0.0, 0),
            "dif_delante": (2.1 if puesto > 1 else None, 0),
            "dif_delante_clase": (2.1 if puesto not in (1, 3) else None, 0),
            "vueltas": 26, "paradas": 1, "penas": 0, "gasolina": 0.42,
            "energia": 0.38, "salida": puesto, "anuladas": (1, 12),
            "sanciones_piloto": 0,
            "combustible": {"gasolina": {"gasto": 0.021}, "energia": {"gasto": 0.031},
                            "quedan": 12.3, "parar_en": 38, "manda": "energia"},
            "neumaticos": {"puestos": {"fl": "Medium", "fr": "Medium",
                                       "rl": "Medium", "rr": "Medium"},
                           "vueltas": 12, "juegos": 2.0}, "en_boxes": en_curso is None,
            "es_yo": dorsal == "399", "la_mejor": puesto in (1, 3)})
    return filas
