# -*- coding: utf-8 -*-
"""
El panel de los frenos: como va cada disco, encima del juego.

PARA QUE. El juego no ensena en ningun sitio cuanto le queda a un disco, y
cuando se acaba ese freno deja de frenar de golpe (ver frenos.py). Esto pone a
la vista lo que la API del juego si sabe: el grosor de cada disco, cuanto le
queda hasta romperse -en tiempo y en vueltas- y lo que tiene que ver con los
frenos en el menu de boxes.

No ensena temperaturas a proposito: esas ya salen en el propio juego.

Va en su propia ventana, como el clima y la bola de fuerzas G: se arrastra con
el raton mientras las opciones estan abiertas.
"""
import tkinter as tk

import idiomas

T = idiomas.t

CHROMA = "#010203"          # el color que Windows vuelve transparente
MARGEN = 8
ANCHO_CELDA = 124
ALTO_CELDA = 60
VERDE = "#34c759"
AMARILLO = "#ffd60a"
ROJO = "#ff453a"
GRIS = "#6b747e"
GRIS_CLARO = "#9aa3ad"


def _tiempo(minutos):
    """142.5 -> '2 h 22'; 35 -> '35 min'."""
    m = int(round(minutos))
    if m >= 60:
        return "%d h %02d" % (m // 60, m % 60)
    return "%d min" % m


class Panel:
    def __init__(self, raiz, cfg, guardar):
        self.cfg = cfg
        self.guardar = guardar
        self.arrastre = None
        self.modo_mover = False
        self._ultimo = None         # lo ultimo pintado, para no repintar igual

        v = tk.Toplevel(raiz)
        self.v = v
        v.overrideredirect(True)
        v.attributes("-topmost", True)
        v.attributes("-transparentcolor", CHROMA)
        v.attributes("-alpha", float(cfg.get("frenos_opacidad", 0.95)))
        v.configure(bg=CHROMA)
        v.withdraw()

        self.lienzo = tk.Canvas(v, bg=CHROMA, highlightthickness=0)
        self.lienzo.pack()
        self.lienzo.bind("<Button-1>", self._empezar_arrastre)
        self.lienzo.bind("<B1-Motion>", self._arrastrar)

    # ------------------------------------------------------------ arrastre
    def _empezar_arrastre(self, e):
        self.arrastre = (e.x, e.y)

    def _arrastrar(self, e):
        if not self.arrastre:
            return
        self.cfg["frenos_panel_x"] += e.x - self.arrastre[0]
        self.cfg["frenos_panel_y"] += e.y - self.arrastre[1]
        self.v.geometry("+%d+%d" % (self.cfg["frenos_panel_x"],
                                    self.cfg["frenos_panel_y"]))
        self.guardar(self.cfg)

    def colocar(self, moviendo):
        """Con las opciones abiertas sale con datos de muestra, para colocarlo."""
        self.modo_mover = moviendo
        self._ultimo = None
        if moviendo:
            self.pintar(*_MUESTRA)
        elif not self.cfg.get("frenos_ver", False):
            self.esconder()

    def esconder(self):
        if self.modo_mover:
            return
        self._ultimo = None
        self.v.withdraw()

    # -------------------------------------------------------------- pintar
    def pintar(self, fichas, extra, reparto_del):
        """
        `fichas`: las cuatro de frenos.Vigia.fichas() (o None cada una).
        `extra`: frenos.discos.extra() (cambio_s, pedido, conductos).
        `reparto_del`: tanto por uno de la frenada que va delante, o None.
        """
        if not self.cfg.get("frenos_ver", False) and not self.modo_mover:
            self.esconder()
            return
        # Se redondea lo que se ve: si no ha cambiado nada visible, no se
        # repinta. A veinte lecturas por segundo, repintar igual es tirar CPU.
        firma = (self._firma(fichas), tuple(sorted((extra or {}).items())),
                 None if reparto_del is None else round(reparto_del, 3),
                 self.cfg.get("frenos_tam"), self.cfg.get("frenos_fondo"),
                 self.cfg.get("frenos_opacidad"), self.modo_mover)
        if firma == self._ultimo:
            return
        self._ultimo = firma

        esc = max(0.5, float(self.cfg.get("frenos_tam", 100)) / 100.0)
        c = self.lienzo
        c.delete("all")
        hay = any(f is not None for f in fichas)
        lineas = self._lineas(extra, reparto_del)

        ancho = int((ANCHO_CELDA * 2 + MARGEN * 3) * esc)
        alto = int((MARGEN + 20) * esc)
        if hay:
            alto += int((ALTO_CELDA * 2 + MARGEN) * esc)
        else:
            alto += int(24 * esc)
        alto += int((len(lineas) * 17 + MARGEN) * esc)

        c.configure(width=ancho, height=alto)
        fondo = self.cfg.get("frenos_color_fondo", "#0d1116")
        if self.cfg.get("frenos_fondo", True):
            self._caja(c, 0, 0, ancho, alto, fondo, esc)
        texto = self.cfg.get("frenos_color_texto", "#ffffff")

        y = int(MARGEN * esc)
        self._texto(c, int(MARGEN * esc), y + int(9 * esc), T("frn.p.titulo"),
                    texto, int(10 * esc), "bold", "w")
        if extra.get("cambio_s"):
            self._texto(c, ancho - int(MARGEN * esc), y + int(9 * esc),
                        T("frn.p.cambio") % extra["cambio_s"],
                        GRIS_CLARO, int(8 * esc), anclaje="e")
        y += int(20 * esc)

        if hay:
            nombres = T("frn.p.ruedas").split("|")
            for r in range(4):
                fila, col = divmod(r, 2)
                x0 = int((MARGEN + col * (ANCHO_CELDA + MARGEN)) * esc)
                y0 = y + int(fila * (ALTO_CELDA + MARGEN) * esc)
                self._celda(c, x0, y0, esc, fichas[r],
                            nombres[r] if len(nombres) == 4 else "", texto)
            y += int((ALTO_CELDA * 2 + MARGEN) * esc)
        else:
            self._texto(c, ancho / 2, y + int(12 * esc), T("frn.p.sin_datos"),
                        GRIS_CLARO, int(9 * esc))
            y += int(24 * esc)

        for linea, color in lineas:
            y += int(17 * esc)
            self._texto(c, int(MARGEN * esc), y - int(6 * esc), linea,
                        color or texto, int(9 * esc), anclaje="w")

        self.v.attributes("-alpha", float(self.cfg.get("frenos_opacidad", 0.95)))
        self.v.geometry("%dx%d+%d+%d" % (ancho, alto,
                                         self.cfg.get("frenos_panel_x", 60),
                                         self.cfg.get("frenos_panel_y", 480)))
        self.v.deiconify()
        self.v.lift()

    def _firma(self, fichas):
        salida = []
        for f in fichas:
            if f is None:
                salida.append(None)
                continue
            salida.append((round(f["mm"], 2), f["roto"],
                           None if f["fraccion"] is None else round(f["fraccion"], 2),
                           None if f["minutos"] is None else int(f["minutos"]),
                           None if f["vueltas"] is None else int(f["vueltas"]),
                           None if f["ritmo_h"] is None else round(f["ritmo_h"], 2)))
        return tuple(salida)

    def _lineas(self, extra, reparto_del):
        lineas = []
        if reparto_del is not None and 0.0 < reparto_del < 1.0:
            lineas.append((T("frn.p.reparto") % (reparto_del * 100.0), None))
        if extra.get("conducto_del") or extra.get("conducto_tras"):
            lineas.append((T("frn.p.conductos") % (extra.get("conducto_del") or "-",
                                                   extra.get("conducto_tras") or "-"),
                           None))
        if "pedido" in extra:
            if extra["pedido"]:
                lineas.append((T("frn.p.pedido_si"), VERDE))
            else:
                lineas.append((T("frn.p.pedido_no"), GRIS_CLARO))
        return lineas

    def _celda(self, c, x0, y0, esc, f, nombre, texto):
        w, h = int(ANCHO_CELDA * esc), int(ALTO_CELDA * esc)
        borde = "#2a3038"
        if f is not None and f["roto"]:
            borde = ROJO
        c.create_rectangle(x0, y0, x0 + w, y0 + h, outline=borde,
                           width=max(1, int(1.5 * esc)))
        pad = int(6 * esc)
        self._texto(c, x0 + pad, y0 + int(9 * esc), nombre, GRIS_CLARO,
                    int(8 * esc), anclaje="w")
        if f is None:
            return
        if f["roto"]:
            self._texto(c, x0 + w / 2, y0 + h / 2 + int(4 * esc), T("frn.p.roto"),
                        ROJO, int(15 * esc), "bold")
            return

        # el grosor, grande
        # Dos decimales: el disco de un Hypercar baja unas centesimas por
        # hora, y con uno solo el numero no se movia en toda una tanda y
        # parecia que el panel no funcionaba.
        grande = "%.2f" % f["mm"]
        self._texto(c, x0 + pad, y0 + int(26 * esc), grande, texto,
                    int(15 * esc), "bold", "w")
        ancho_num = self._ancho(grande, int(15 * esc), "bold")
        self._texto(c, x0 + pad + ancho_num + int(3 * esc), y0 + int(29 * esc),
                    "mm", GRIS_CLARO, int(8 * esc), anclaje="w")
        if f["ritmo_h"]:
            self._texto(c, x0 + w - pad, y0 + int(9 * esc),
                        T("frn.p.ritmo") % f["ritmo_h"], GRIS_CLARO,
                        int(8 * esc), anclaje="e")

        # la barra: de nuevo (llena) a punto de romperse (vacia)
        by = y0 + int(39 * esc)
        bh = max(3, int(5 * esc))
        c.create_rectangle(x0 + pad, by, x0 + w - pad, by + bh,
                           fill="#2a3038", outline="")
        fr = f["fraccion"]
        if fr is not None:
            color = VERDE if fr > 0.5 else (AMARILLO if fr > 0.2 else ROJO)
            largo = int((w - 2 * pad) * fr)
            if largo > 0:
                c.create_rectangle(x0 + pad, by, x0 + pad + largo, by + bh,
                                   fill=color, outline="")

        # lo que queda
        if f["minutos"] is not None:
            queda = T("frn.p.queda") % _tiempo(f["minutos"])
            if f["vueltas"] is not None:
                queda += "  " + T("frn.p.vueltas") % f["vueltas"]
            color = ROJO if fr is not None and fr <= 0.2 else texto
        elif f["ritmo_h"] == 0.0:
            queda, color = T("frn.p.sin_desgaste"), GRIS_CLARO
        elif f["limite"] is None:
            queda, color = T("frn.p.sin_limite"), GRIS
        else:
            queda, color = T("frn.p.midiendo"), GRIS
        self._texto(c, x0 + pad, y0 + int(52 * esc), queda, color,
                    int(8 * esc), anclaje="w")

    # ------------------------------------------------------------- ayudas
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
        if not self.cfg.get("frenos_fondo", True):
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


def _ficha_muestra(mm, nuevo, limite, ritmo_h, vuelta_s=215.0):
    margen = mm - limite - 0.5
    minutos = margen / ritmo_h * 60.0
    return {"mm": mm, "nuevo": nuevo, "limite": limite, "margen": margen,
            "fraccion": max(0.0, min(1.0, margen / (nuevo - limite - 0.5))),
            "minutos": minutos, "vueltas": minutos * 60.0 / vuelta_s,
            "ritmo_h": ritmo_h, "roto": False}


# Lo que se ensena con las opciones abiertas, para colocarlo.
_MUESTRA = (
    [_ficha_muestra(31.2, 34.0, 25.0, 0.62), _ficha_muestra(32.0, 34.0, 25.0, 0.48),
     _ficha_muestra(31.1, 32.0, 25.0, 0.21), _ficha_muestra(31.2, 32.0, 25.0, 0.19)],
    {"cambio_s": 120.0, "pedido": False, "conducto_del": "20%",
     "conducto_tras": "Abierto"},
    0.545,
)
