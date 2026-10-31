# -*- coding: utf-8 -*-
"""
El panel de estrategia: la prediccion de carrera, encima del juego.

Arriba, en tres lineas, lo que se mira en el muro:
  - NOSOTROS: puesto, ritmo, en que vuelta toca repostar, paradas que faltan
    y lo que cuesta una parada;
  - SI PARAMOS AHORA: en que puesto salimos, quien queda delante y detras, y
    si salimos metidos en trafico o con la pista libre;
  - PREVISION: el puesto dentro de X minutos y al final, con cuantos
    adelantamos y cuantos nos adelantan.
Debajo, los coches de nuestra clase con la distancia de ahora, el ritmo
comparado con el nuestro, las paradas que le tocan, la distancia NETA
(contando paradas) y la prevision: si le pasamos o nos pasa, y en que vuelta.

Las cuentas las hace estrategia.py. Va en su propia ventana porque es otra
cosa que la clasificacion: aquella dice como va la carrera, esta lo que va a
pasar. Lo comun (arrastrar, fondo, rueda del raton) es el panel de
clasificacion, del que hereda.
"""
import time

import clasificacion
import clasificacion_gui as base
import idiomas

T = idiomas.t

VERDE = "#30d158"
ROJO = base.ROJO
GRIS = base.GRIS_CLARO
AMARILLO = base.AMARILLO

# (clave, ancho, a la derecha)
COLUMNAS = [
    ("puesto", 30, True),
    ("marca", 40, False),
    ("dorsal", 42, False),
    ("piloto", 140, False),
    ("distancia", 62, True),
    ("ritmo", 54, True),
    ("pillar_v", 52, True),
    ("pillar_t", 58, True),
    ("para_en", 50, True),
    ("coste", 50, True),
    ("paradas", 50, True),
    ("neta", 62, True),
    ("prevision", 130, False),
]


def _reloj_largo(segundos):
    if segundos is None:
        return "--:--"
    segundos = int(segundos)
    return "%d:%02d:%02d" % (segundos // 3600, segundos % 3600 // 60, segundos % 60)


def _signo(v, decimales=1):
    """-7.46 -> '-7.5'; 8.6 -> '+8.6'. Negativo = por delante de nosotros."""
    if v is None:
        return "?"
    return ("%+." + str(decimales) + "f") % v


class Panel(base.Panel):
    PRE = "estr"

    def colocar(self, moviendo):
        self.modo_mover = moviendo
        self._ultimo = None
        if moviendo:
            self.pintar(None, forzar=True)
        elif not self.cfg.get("estr_ver", False):
            self.esconder()

    def pintar(self, datos, forzar=False):
        """`datos`: lo de estrategia.calcular(), o None."""
        if not self.cfg.get("estr_ver", False) and not self.modo_mover:
            self.esconder()
            return
        ahora = time.monotonic()
        # Esto cambia despacio: dos veces por segundo sobra (salvo estirando).
        if not forzar and not self.estirando and ahora - self._cuando < 0.5:
            return
        self._cuando = ahora

        if self.modo_mover and (not datos or datos.get("falta")):
            datos = _muestra()     # opciones abiertas sin carrera: para colocarlo
        lineas = self._lineas(datos)
        esc = max(0.5, float(self.cfg.get("estr_tam", 100)) / 100.0)
        lineas = self._partir(lineas, esc)
        rivales = self._filas(datos)
        filas = self._recortar(rivales)
        celdas = [[self._celda(r, col[0]) for col in COLUMNAS] for r in filas]
        firma = (tuple(lineas), tuple(tuple(map(str, x)) for x in celdas),
                 self.cfg.get("estr_tam"), self.cfg.get("estr_fondo"),
                 self.cfg.get("estr_opacidad"), self.cfg.get("estr_color_fondo"),
                 self.cfg.get("estr_color_texto"), self.modo_mover)
        if firma == self._ultimo:
            return
        self._ultimo = firma

        esc = max(0.5, float(self.cfg.get("estr_tam", 100)) / 100.0)
        c = self.lienzo
        c.delete("all")
        anchos = [int(col[1] * esc) for col in COLUMNAS]
        x0 = int(base.MARGEN * esc)
        ancho = self._ancho_total(lineas, esc)
        fila_h = int(base.ALTO_FILA * esc)
        alto_lineas = int(18 * esc) * len(lineas)
        alto = (int((base.MARGEN * 2 + 22) * esc) + alto_lineas
                + fila_h * max(1, len(filas)) + int(8 * esc))
        con_barra = self._total > len(filas)

        c.configure(width=ancho, height=alto)
        if self.cfg.get("estr_fondo", True):
            self._caja(c, 0, 0, ancho, alto,
                       self.cfg.get("estr_color_fondo", "#0d1116"), esc)
        texto = self.cfg.get("estr_color_texto", "#ffffff")
        self._asa(c, ancho, alto, esc)
        self._mostradas, self._fila_h = len(filas), fila_h

        # las lineas de arriba
        y = int((base.MARGEN + 9) * esc)
        for i, (linea, color, negrita) in enumerate(lineas):
            self._texto(c, x0 + int(4 * esc), y, linea, color or texto,
                        int((10 if i == 0 else 9) * esc),
                        "bold" if negrita else "normal", "w")
            y += int(18 * esc)
        y += int(4 * esc)

        xs = []
        x = x0 + int(4 * esc)
        for a in anchos:
            xs.append(x)
            x += a
        for i, col in enumerate(COLUMNAS):
            self._texto(c, xs[i] + anchos[i] - 4 if col[2] else xs[i] + 4, y,
                        T("est.col." + col[0]), GRIS, int(8 * esc), "bold",
                        "e" if col[2] else "w")
        y += int(13 * esc)
        arriba_tabla = y

        letra = int(9 * esc)
        for r, fila in zip(filas, celdas):
            medio = y + fila_h / 2
            if r["es_yo"]:
                c.create_rectangle(x0, y, ancho - x0, y + fila_h,
                                   fill=base.RESALTE, outline="")
            for i, col in enumerate(COLUMNAS):
                if col[0] == "marca":
                    self._placa(c, xs[i] + 4, medio, r["fila"]["marca"], esc)
                    continue
                valor, color, negrita = fila[i]
                if col[0] == "piloto":
                    valor = self._corta(valor, anchos[i] - 8, letra, "normal")
                peso = "bold" if (negrita or r["es_yo"]) else "normal"
                self._texto(c, xs[i] + anchos[i] - 4 if col[2] else xs[i] + 4,
                            medio, valor, color or texto, letra, peso,
                            "e" if col[2] else "w")
            y += fila_h

        if con_barra:
            largo = fila_h * len(filas)
            bx = ancho - x0 - int(4 * esc)
            c.create_rectangle(bx, arriba_tabla, bx + int(4 * esc),
                               arriba_tabla + largo, fill="#2a3038", outline="")
            y0 = arriba_tabla + largo * self._inicio / self._total
            y1 = arriba_tabla + largo * (self._inicio + len(filas)) / self._total
            c.create_rectangle(bx, y0, bx + int(4 * esc), y1, fill=GRIS, outline="")
            self._barra = (bx - int(6 * esc), (y0 + y1) / 2)
        else:
            self._barra = None

        self.v.attributes("-alpha", float(self.cfg.get("estr_opacidad", 0.95)))
        self.v.geometry("%dx%d+%d+%d" % (ancho, alto, self.cfg.get("estr_x", 60),
                                         self.cfg.get("estr_y", 300)))
        self.v.deiconify()
        self.v.lift()

    # ------------------------------------------------------------ lo de arriba
    def _lineas(self, d):
        """[(texto, color o None, negrita)]"""
        titulo = T("est.titulo")
        if not d or d.get("falta"):
            espera = T("est.esperando") if not d else T("est.falta_ritmo")
            return [(titulo, None, True), (espera, GRIS, False)]
        titulo += "   " + T("est.queda") % _reloj_largo(d["restante"])
        salida = [(titulo, None, True)]

        # nosotros
        comb = d["yo"].get("combustible") or {}
        nosotros = T("est.nosotros") % (d["puesto"] or 0, d["yo"]["clase"],
                                        clasificacion.reloj(d["ritmo"]))
        if d.get("paradas_final") == 0:
            pass                    # no hay que repostar: no se dice cuando
        elif comb.get("parar_en") is not None:
            nosotros += "  ·  " + T("est.repostar") % (comb["parar_en"], comb["quedan"])
        else:
            nosotros += "  ·  " + T("est.repostar_calc")
        salida.append((nosotros, None, False))

        # Sin mas paradas hasta la bandera: lo de parar sobra, y lo que se
        # pregunta en el muro es donde llegamos y con cuanto margen
        # (Manuel, 31/10/2026, en el ultimo relevo de Imola).
        final = d.get("final")
        if d.get("paradas_final") == 0 and final:
            linea = T("est.sin_paradas") % final["puesto_final"]
            if final.get("llegada_delante"):
                s, f = final["llegada_delante"]
                linea += "  ·  " + T("est.sp_delante") % (f["dorsal"], -s)
            if final.get("llegada_detras"):
                s, f = final["llegada_detras"]
                linea += "  ·  " + T("est.sp_detras") % (f["dorsal"], s)
            salida.append((linea, AMARILLO, True))
            cambio = (final["puesto"] or 0) - final["puesto_final"]
            texto = T("est.prev_final") % (final["puesto_final"],
                                           "%+d" % cambio if cambio else "=",
                                           final["pasamos"], final["nos_pasan"])
            color = VERDE if cambio > 0 else (ROJO if cambio < 0 else None)
            salida.append((texto, color, True))
            return salida

        mas = T("est.paradas_final") % (
            "?" if d["paradas_final"] is None else d["paradas_final"])
        # El total de la proxima parada, en su linea y bien visible: es lo
        # primero que se pregunta en el muro antes de llamar al coche.
        p = d.get("parada")
        total = p["total"] if p and p.get("total") else d["perdida"]
        de_menu = bool(p and p.get("total"))
        salida.append((T("est.parada_total") % (total, T("est.segun_menu") if de_menu
                                                 else T("est.segun_media")), AMARILLO, True))
        salida.append((mas + "  ·  " + self._parada(d), GRIS, False))

        # donde salimos: si paramos ahora y cuando toque
        salida.append(self._salida(T("est.si_paramos"), d["si_paramos"]))
        if d.get("al_parar"):
            ap = d["al_parar"]
            salida.append(self._salida(T("est.al_parar") % ap["vuelta"], ap))

        # prevision
        for clave, p in (("est.prev_horizonte", d), ("est.prev_final", d.get("final"))):
            if not p:
                continue
            cambio = (p["puesto"] or 0) - p["puesto_final"]
            texto = T(clave) % (p["puesto_final"], "%+d" % cambio if cambio else "=",
                                p["pasamos"], p["nos_pasan"])
            if clave == "est.prev_horizonte":
                if d.get("es_ciclo"):
                    texto = texto.replace(T("est.en_min_cab"), T("est.tras_paradas"))
                texto = texto.replace("{min}", str(int((d["horizonte"] or 0) // 60)))
            color = VERDE if cambio > 0 else (ROJO if cambio < 0 else None)
            salida.append((texto, color, True))
        return salida

    def _ancho_total(self, lineas, esc):
        """
        La tabla manda como minimo. Si se ha estirado a mano, ese ancho; si
        no, lo que pidan las lineas de arriba para caber enteras.
        """
        x0 = int(base.MARGEN * esc)
        ancho = sum(int(col[1] * esc) for col in COLUMNAS) + x0 * 2 + int(12 * esc)
        elegido = int(self.cfg.get("estr_ancho") or 0)
        if elegido:
            return max(ancho, elegido)
        for i, (linea, _, negrita) in enumerate(lineas):
            ancho = max(ancho, self._ancho(linea, int((10 if i == 0 else 9) * esc),
                                           "bold" if negrita else "normal")
                        + x0 * 2 + int(12 * esc))
        return ancho

    def _partir(self, lineas, esc):
        """
        Con un ancho elegido a mano, las lineas que no caben se parten por sus
        trozos ("  ·  " y " + ") en varias, en vez de salirse de la ventana.
        """
        elegido = int(self.cfg.get("estr_ancho") or 0)
        if not elegido:
            return lineas
        ancho = self._ancho_total([], esc) - int(base.MARGEN * esc) * 2 - int(12 * esc)
        salida = []
        for i, (linea, color, negrita) in enumerate(lineas):
            tam = int((10 if i == 0 else 9) * esc)
            peso = "bold" if negrita else "normal"
            if self._ancho(linea, tam, peso) <= ancho:
                salida.append((linea, color, negrita))
                continue
            trozos = linea.replace(" + ", "  +  ").split("  ")
            actual = ""
            for t in trozos:
                if not t.strip():
                    continue
                prueba = (actual + "  " + t) if actual else t
                if actual and self._ancho(prueba, tam, peso) > ancho:
                    salida.append((actual, color, negrita))
                    actual = "    " + t
                else:
                    actual = prueba
            if actual:
                salida.append((actual, color, negrita))
        return salida

    def _parada(self, d):
        """
        'parada ~72 s: parado 36.5 (energia 24.5 + 4 ruedas 12) + carril 35'.
        Con el menu de boxes del juego; si no lo hay, la media de la clase.
        """
        p = d.get("parada")
        if not p or not p.get("total"):
            texto = T("est.parada_media") % d["perdida"]
            if not d["paradas_vistas"]:
                texto += " " + T("est.perdida_supuesta")
            return texto
        partes = []
        if p["energia_s"]:
            partes.append(T("est.p_energia") % p["energia_s"])
        if p["ruedas"]:
            partes.append(T("est.p_ruedas") % (p["ruedas"], p["ruedas_s"]))
        if p["piloto"]:
            partes.append(T("est.p_piloto") % (p["piloto_s"]))
        if p["reparar"]:
            partes.append(T("est.p_reparar") % p["reparar_s"])
        if p["frenos"]:
            partes.append(T("est.p_frenos") % p["frenos_s"])
        texto = T("est.parada_menu") % p["parado"]
        if partes:
            texto += " (" + " + ".join(partes) + ")"
        texto += " + " + T("est.p_carril") % p["carril"]
        if p.get("extra_piloto"):
            texto += " + " + T("est.p_extra_piloto") % p["extra_piloto"]
        # el total, al final de la suma
        return texto + " = " + T("est.p_total") % p["total"]

    def _salida(self, cabeza, sp):
        """Una linea: puesto al salir, quien queda delante y detras, trafico."""
        linea = cabeza + " " + T("est.salimos") % sp["puesto"]
        if sp["delante"]:
            linea += "  ·  " + T("est.sp_delante") % (sp["delante"][1]["dorsal"],
                                                      -sp["delante"][0])
        if sp["detras"]:
            linea += "  ·  " + T("est.sp_detras") % (sp["detras"][1]["dorsal"],
                                                     sp["detras"][0])
        if sp["trafico"]:
            quien = ", ".join("#%s" % f["dorsal"] for f in sp["trafico"][:3])
            return linea + "  ·  " + T("est.trafico") % quien, AMARILLO, True
        return linea + "  ·  " + T("est.libre"), None, True

    # ------------------------------------------------------------ la tabla
    def _filas(self, d):
        if not d or d.get("falta"):
            return []
        filas = [{"fila": r["fila"], "r": r, "es_yo": False} for r in d["rivales"]]
        filas.append({"fila": d["yo"], "r": None, "es_yo": True})
        filas.sort(key=lambda x: x["fila"].get("puesto_clase") or 999)
        self._paradas_yo = d["paradas"]
        self._ritmo_yo = d["ritmo"]
        self._para_yo = (d["yo"].get("combustible") or {}).get("parar_en")
        self._perdidas = d.get("perdidas") or {}
        self._perdida_yo = d.get("perdida")
        return filas

    def _pillar(self, r, clave):
        """
        En cuantas vueltas y en cuanto tiempo lo pillamos (si va delante y
        vamos mas rapido) o nos pilla (si va detras y va mas rapido). Es en
        PISTA, con la distancia de ahora y la diferencia de ritmo, sin contar
        paradas. Verde si es bueno para nosotros, rojo si no. Si la distancia
        no se cierra, no sale nada.
        """
        dist, dr = r["distancia"], r["dif_ritmo"]
        if dist is None or dr is None or abs(dr) < 0.05:
            return "", None, False
        if dist < 0 < dr:                   # delante y mas lento: lo pillamos
            vueltas, color = -dist / dr, VERDE
        elif dr < 0 < dist:                 # detras y mas rapido: nos pilla
            vueltas, color = dist / -dr, ROJO
        else:
            return "", None, False
        if clave == "pillar_v":
            return ("%d v" % max(1, round(vueltas))), color, True
        segundos = vueltas * (self._ritmo_yo or 0)
        if segundos >= 3600:
            texto = "%d:%02d h" % (segundos // 3600, segundos % 3600 // 60)
        else:
            texto = "%d:%02d" % (segundos // 60, segundos % 60)
        return texto, color, True

    def _celda(self, x, clave):
        f, r = x["fila"], x["r"]
        if clave == "puesto":
            return str(f.get("puesto_clase") or ""), None, True
        if clave == "marca":
            return "", None, False
        if clave == "dorsal":
            return "#" + f["dorsal"], None, False
        if clave == "piloto":
            return f["piloto"], None, False
        if r is None:                       # nuestra fila
            if clave == "para_en":
                v = self._para_yo
                return ("v.%d" % v) if v is not None else "", None, True
            if clave == "coste":
                return ("%.0f s" % self._perdida_yo) if self._perdida_yo else "", None, True
            if clave == "paradas":
                p = self._paradas_yo
                return ("?" if p is None else str(p)), None, True
            return "", None, False
        if clave == "distancia":
            return _signo(r["distancia"]), None, False
        if clave == "ritmo":
            dr = r["dif_ritmo"]
            if dr is None:
                return base._calculando()
            # mas rapido que nosotros = malo para nosotros
            color = ROJO if dr < -0.2 else (VERDE if dr > 0.2 else None)
            return _signo(dr), color, False
        if clave in ("pillar_v", "pillar_t"):
            return self._pillar(r, clave)
        if clave == "para_en":
            # en que vuelta tiene que parar a repostar; en amarillo si para
            # antes que nosotros (nos puede pasar o le pasamos en boxes)
            v = (f.get("combustible") or {}).get("parar_en")
            if v is None:
                return base._calculando()
            antes = self._para_yo is not None and v < self._para_yo
            return "v.%d" % v, AMARILLO if antes else None, antes
        if clave == "coste":
            c = self._perdidas.get(f["clave"])
            return ("%.0f s" % c) if c else "", None, False
        if clave == "paradas":
            p = r["paradas"]
            if p is None:
                return base._calculando()
            color = AMARILLO if p != self._paradas_yo else None
            return str(p), color, p != self._paradas_yo
        if clave == "neta":
            n = r["neta"]
            if n is None:
                return "?", GRIS, False
            cambia = r["distancia"] is not None and (n < 0) != (r["distancia"] < 0)
            color = (VERDE if n > 0 else ROJO) if cambia else None
            return _signo(n), color, cambia
        if clave == "prevision":
            if r["prevision"] == "pasamos":
                cuando = (T("est.en_boxes") if r["vuelta"] == "boxes"
                          else T("est.en_vuelta") % r["vuelta"] if r["vuelta"] else "")
                return T("est.pasamos") + cuando, VERDE, True
            if r["prevision"] == "nos_pasa":
                cuando = (T("est.en_boxes") if r["vuelta"] == "boxes"
                          else T("est.en_vuelta") % r["vuelta"] if r["vuelta"] else "")
                return T("est.nos_pasa") + cuando, ROJO, True
            return "", None, False
        return "", None, False


def _muestra():
    """
    Lo que se ensena con las opciones abiertas si no hay carrera, para poder
    colocar el panel y ver como queda (y para las capturas de la ficha).
    """
    m = clasificacion.marca_de

    def coche(puesto, dorsal, piloto, marca, parar_en):
        return {"puesto_clase": puesto, "dorsal": dorsal, "piloto": piloto,
                "marca": m(marca), "clave": dorsal, "clase": "LMGT3",
                "combustible": {"parar_en": parar_en, "quedan": parar_en - 52.0}}

    yo = coche(3, "399", "(muestra) Nosotros", "Porsche 911 GT3 R", 58)
    a = coche(1, "92", "(muestra) A", "Ferrari 296 GT3", 55)
    b = coche(2, "21", "(muestra) B", "McLaren 720S", 59)
    c = coche(4, "77", "(muestra) C", "BMW M4 GT3", 54)
    d = coche(5, "54", "(muestra) D", "Lexus RC F GT3", 60)

    def rival(f, dist, dr, paradas, neta, prev=None, vuelta=None):
        return {"fila": f, "distancia": dist, "dif_ritmo": dr, "paradas": paradas,
                "neta": neta, "prevision": prev, "vuelta": vuelta}

    parada = {"total": 76.4, "parado": 39.1, "energia_s": 39.1, "ruedas": 0,
              "ruedas_s": 0.0, "piloto": True, "piloto_s": 25.0, "reparar": "",
              "frenos": False, "carril": 35.3, "extra_piloto": 2.0}
    sp = {"puesto": 4, "delante": (-6.2, b), "detras": (2.1, c), "trafico": [c]}
    ap = {"puesto": 3, "delante": (-3.4, b), "detras": (12.8, c), "trafico": [],
          "vuelta": 58}
    final = {"puesto": 3, "puesto_final": 2, "pasamos": 1, "nos_pasan": 0}
    return {
        "yo": yo, "falta": None, "restante": 7920.0, "horizonte": 1500.0,
        "es_ciclo": True, "puesto": 3, "ritmo": 107.3, "paradas": 1,
        "paradas_final": 3, "perdida": 76.4, "paradas_vistas": 12,
        "parada": parada, "si_paramos": sp, "al_parar": ap, "final": final,
        "puesto_final": 3, "pasamos": 1, "nos_pasan": 1,
        "perdidas": {"92": 77.0, "21": 74.5, "77": 78.1, "54": 76.0},
        "rivales": [
            rival(a, -21.4, -0.3, 1, -19.0),
            rival(b, -8.7, 0.6, 1, 2.6, "pasamos", "boxes"),
            rival(c, 4.1, -0.4, 1, 6.3),
            rival(d, 15.9, -0.9, 0, -0.5, "nos_pasa", 71),
        ],
    }

