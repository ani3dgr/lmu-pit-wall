# -*- coding: utf-8 -*-
"""
Ventana de opciones del mapa, organizada en pestanas.

Se saco del archivo del mapa porque habia crecido tanto que la ventana no
cabia de alto en la pantalla. Cada pestana lleva su boton de ayuda (i) con la
explicacion de para que sirve lo que hay dentro.
"""
import os
import subprocess
import sys
import tkinter as tk
from tkinter import ttk, colorchooser, messagebox

import catalogo
import coches
import enlaces
import rutas
import idiomas
import reglajes

T = idiomas.t
import grabador as grab
import visor

CARPETA = rutas.carpeta()



def ayuda(padre, clave, titulo):
    """La explicacion del boton (i). El texto vive en la carpeta idiomas."""
    messagebox.showinfo(titulo, T("ayuda." + clave), parent=padre)


class Opciones:
    """Construye la ventana. `mapa` es la instancia de Mapa que la abre."""

    def __init__(self, mapa, guardar):
        self.mapa = mapa
        self.cfg = mapa.cfg
        self.guardar = guardar

        v = tk.Toplevel(mapa.root)
        self.v = v
        v.title(T("win.titulo"))
        v.attributes("-topmost", True)
        v.resizable(False, False)
        v.protocol("WM_DELETE_WINDOW", mapa.cerrar_opciones)

        # Dos alturas de pestanas: arriba el grupo, dentro la hoja.
        #
        # Eran nueve pestanas seguidas y ya no cabian de ancho, y encima se
        # anaden funciones cada poco. Agrupadas se busca por donde se usa:
        # lo que se VE en el mapa, lo que te ayuda EN PISTA, los TIEMPOS y lo
        # que el programa tiene GUARDADO.
        cuaderno = ttk.Notebook(v)
        cuaderno.pack(fill="both", expand=True, padx=8, pady=(8, 0))

        mapa_ = self._grupo(cuaderno, T("grupo.mapa"))
        self._pestana_ver(mapa_)
        self._pestana_aspecto(mapa_)
        self._pestana_pantalla(mapa_)

        pista = self._grupo(cuaderno, T("grupo.pista"))
        self._pestana_fuerzas(pista)
        self._pestana_clima(pista)
        self._pestana_frenos(pista)
        self._pestana_avisos(pista)

        tiempos = self._grupo(cuaderno, T("grupo.tiempos"))
        self._pestana_tiempos(tiempos)
        self._pestana_clasificacion(tiempos)
        self._pestana_estrategia(tiempos)
        self._pestana_trazadas(tiempos)

        biblioteca = self._grupo(cuaderno, T("grupo.biblioteca"))
        self._pestana_coches(biblioteca)
        self._pestana_reglajes(biblioteca)
        self._pestana_escaneo(biblioteca)

        self._pestana_acerca(cuaderno)

        pie = ttk.Frame(v, padding=(10, 6))
        pie.pack(fill="x")
        ttk.Label(pie, foreground="#666",
                  text=T("pie.teclas")).pack(side="left")

    # ---------- utilidades de construccion ----------
    def _grupo(self, cuaderno, titulo):
        """Una pestana de arriba, que por dentro lleva sus propias hojas."""
        marco = ttk.Frame(cuaderno)
        cuaderno.add(marco, text=titulo)
        dentro = ttk.Notebook(marco)
        dentro.pack(fill="both", expand=True, padx=6, pady=6)
        return dentro

    def _hoja(self, cuaderno, titulo, clave_ayuda):
        marco = ttk.Frame(cuaderno, padding=12)
        cuaderno.add(marco, text=titulo)
        cabecera = ttk.Frame(marco)
        cabecera.grid(row=0, column=0, columnspan=3, sticky="we", pady=(0, 6))
        ttk.Label(cabecera, text=titulo, font=("Segoe UI", 10, "bold")).pack(side="left")
        tk.Button(cabecera, text=" i ", font=("Segoe UI", 8, "bold"),
                  fg="white", bg="#3a7bd5", relief="groove",
                  command=lambda: ayuda(self.v, clave_ayuda, titulo)).pack(side="right")
        return marco, [1]

    def _interruptor(self, m, fila, texto, clave, sangria=0):
        var = tk.BooleanVar(value=self.cfg[clave])

        def cambio():
            self.cfg[clave] = var.get()
            self.guardar(self.cfg)
        ttk.Checkbutton(m, text=texto, variable=var, command=cambio).grid(
            row=fila[0], column=0, columnspan=3, sticky="w", padx=(sangria, 0))
        fila[0] += 1

    def _deslizador(self, m, fila, texto, clave, desde, hasta, decimales=0):
        ttk.Label(m, text=texto).grid(row=fila[0], column=0, sticky="w")
        var = tk.DoubleVar(value=self.cfg[clave])
        formato = "%." + str(decimales) + "f"
        etiqueta = ttk.Label(m, width=5, text=formato % self.cfg[clave])

        def cambio(_=None):
            val = round(var.get(), decimales) if decimales else int(var.get())
            self.cfg[clave] = val
            etiqueta.config(text=formato % val)
            if clave == "opacidad":
                self.mapa.root.attributes("-alpha", val)
            elif clave == "tamano":
                self.mapa.root.geometry("%dx%d" % (val, val))
                self.mapa.lienzo.config(width=val, height=val)
            self.guardar(self.cfg)
        ttk.Scale(m, from_=desde, to=hasta, variable=var, command=cambio,
                  length=190).grid(row=fila[0], column=1, sticky="we", padx=6)
        etiqueta.grid(row=fila[0], column=2)
        fila[0] += 1

    def _color(self, m, fila, texto, clave, sub=None):
        ttk.Label(m, text=texto).grid(row=fila[0], column=0, sticky="w")
        actual = self.cfg["colores_clase"][sub] if sub else self.cfg[clave]
        boton = tk.Button(m, bg=actual, width=12, relief="groove")

        def elegir():
            nuevo = colorchooser.askcolor(color=boton["bg"], parent=self.v)[1]
            if nuevo:
                boton.config(bg=nuevo)
                if sub:
                    self.cfg["colores_clase"][sub] = nuevo
                else:
                    self.cfg[clave] = nuevo
                self.guardar(self.cfg)
        boton.config(command=elegir)
        boton.grid(row=fila[0], column=1, columnspan=2, sticky="w", padx=6, pady=1)
        fila[0] += 1

    def _titulo(self, m, fila, texto):
        ttk.Label(m, text=texto, font=("Segoe UI", 9, "bold")).grid(
            row=fila[0], column=0, columnspan=3, sticky="w", pady=(10, 2))
        fila[0] += 1

    # ---------- pestanas ----------
    def _pestana_ver(self, cuaderno):
        m, fila = self._hoja(cuaderno, T("tab.ver"), "ver")
        self._titulo(m, fila, T("tab.coches"))
        self._interruptor(m, fila, T("ver.mostrar_rivales"), "mostrar_oponentes")
        self._interruptor(m, fila, T("ver.numeros"), "mostrar_numeros")
        self._interruptor(m, fila, T("ver.colores_clase"), "usar_colores_clase")
        self._interruptor(m, fila, T("ver.anillo"),
                          "yo_anillo")
        self._titulo(m, fila, T("com.circuito"))
        self._interruptor(m, fila, T("ver.num_curva"), "ver_numero_curva")
        self._interruptor(m, fila, T("ver.nom_curva"), "ver_nombre_curva")
        self._titulo(m, fila, T("ver.tit_textos"))
        self._interruptor(m, fila, T("ver.sesion"), "ver_sesion")
        self._interruptor(m, fila, T("ver.rotulo"), "ver_texto_estado")


    def _pestana_aspecto(self, cuaderno):
        m, fila = self._hoja(cuaderno, T("tab.aspecto"), "aspecto")
        self._titulo(m, fila, T("asp.tit_tamanos"))
        self._deslizador(m, fila, T("com.mi_coche"), "radio_yo", 3, 20)
        self._deslizador(m, fila, T("com.los_demas"), "radio_rival", 2, 20)
        self._deslizador(m, fila, T("asp.num_posicion"), "tam_numero", 6, 16)
        self._deslizador(m, fila, T("asp.texto_curvas"), "tam_curva", 6, 16)
        self._deslizador(m, fila, T("asp.rotulo"), "tam_estado", 7, 20)
        self._deslizador(m, fila, T("asp.aviso_salida"), "tam_salida", 5, 16)
        self._titulo(m, fila, T("asp.tit_mapa"))
        self._deslizador(m, fila, T("asp.tam_mapa"), "tamano", 200, 800)
        self._deslizador(m, fila, T("asp.grosor"), "grosor_pista", 1, 8)
        self._deslizador(m, fila, T("asp.opacidad"), "opacidad", 0.2, 1.0, 2)
        self._fluidez(m, fila)
        ttk.Label(m, foreground="#666", justify="left",
                  text=T("asp.fluidez.nota")).grid(
            row=fila[0], column=0, columnspan=3, sticky="w", padx=(20, 0))
        fila[0] += 1
        self._titulo(m, fila, T("asp.tit_colores"))
        self._color(m, fila, T("com.mi_coche"), "color_yo")
        self._color(m, fila, T("com.los_demas"), "color_rival")
        self._color(m, fila, T("com.trazado"), "color_pista")
        self._color(m, fila, T("com.curvas"), "color_curva")
        self._color(m, fila, "Hypercar", None, "hypercar")
        self._color(m, fila, "LMP2", None, "lmp2")
        self._color(m, fila, "LMGT3", None, "lmgt3")
        self._titulo(m, fila, T("asp.colocar"))
        marco = ttk.Frame(m)
        marco.grid(row=fila[0], column=0, columnspan=3, sticky="w")
        fila[0] += 1
        for texto, derecha, abajo in ((T("asp.arr_izq"), False, False),
                                      (T("asp.arr_der"), True, False),
                                      (T("asp.aba_izq"), False, True),
                                      (T("asp.aba_der"), True, True)):
            ttk.Button(marco, text=texto, width=11,
                       command=self._ir_esquina(derecha, abajo)).pack(side="left", padx=2)

    # Solo estos tres valores. El bucle va a 20 por segundo, asi que los
    # dibujos solo se pueden repartir en 20, 10 o 5; cualquier otro numero
    # acabaria redondeado a uno de estos y el ajuste mentiria.
    FLUIDEZ = [20, 10, 5]

    def _fluidez(self, m, fila):
        """Cuantas veces por segundo se repinta el mapa."""
        nombres = [T("asp.fluidez.alta"), T("asp.fluidez.media"),
                   T("asp.fluidez.baja")]
        ttk.Label(m, text=T("asp.fluidez")).grid(row=fila[0], column=0, sticky="w")
        actual = self.cfg.get("dibujos_por_segundo", 20)
        try:
            i = self.FLUIDEZ.index(int(actual))
        except (ValueError, TypeError):
            i = 0
        var = tk.StringVar(value=nombres[i])

        def cambio(_=None):
            self.cfg["dibujos_por_segundo"] = self.FLUIDEZ[nombres.index(var.get())]
            self.guardar(self.cfg)

        combo = ttk.Combobox(m, textvariable=var, values=nombres,
                             state="readonly", width=22)
        combo.grid(row=fila[0], column=1, sticky="w", padx=4, pady=1)
        combo.bind("<<ComboboxSelected>>", cambio)
        fila[0] += 1

    def _ir_esquina(self, derecha, abajo):
        def ir():
            t = self.cfg["tamano"]
            margen = 30
            ancho = self.mapa.root.winfo_screenwidth()
            alto = self.mapa.root.winfo_screenheight()
            self.cfg["x"] = (ancho - t - margen) if derecha else margen
            self.cfg["y"] = (alto - t - margen) if abajo else margen
            self.mapa.root.geometry("+%d+%d" % (self.cfg["x"], self.cfg["y"]))
            self.guardar(self.cfg)
        return ir

    def _pestana_fuerzas(self, cuaderno):
        """
        La bola de fuerzas G.

        Tiene hoja propia porque no es "algo que se ve en el mapa": es un
        instrumento aparte, con su ventana, su sitio en la pantalla y sus
        ajustes.
        """
        m, fila = self._hoja(cuaderno, T("tab.fuerzas"), "fuerzas")
        self._interruptor(m, fila, T("bola.ver"), "bola_ver")
        self._interruptor(m, fila, T("bola.circulo"), "bola_circulo")
        self._interruptor(m, fila, T("bola.numeros"), "bola_numeros")
        self._titulo(m, fila, T("bola.tit_ajustes"))
        self._deslizador(m, fila, T("bola.tam"), "bola_tam", 70, 260)
        self._deslizador(m, fila, T("bola.escala"), "bola_escala", 1.5, 4.0, 1)
        self._deslizador(m, fila, T("bola.suavidad"), "bola_suavidad", 0, 95)
        ttk.Label(m, foreground="#666", justify="left",
                  text=T("bola.nota_suavidad")).grid(
            row=fila[0], column=0, columnspan=3, sticky="w", padx=(20, 0))
        fila[0] += 1
        self._titulo(m, fila, T("asp.tit_colores"))
        self._color(m, fila, T("bola.color_punto"), "bola_color_punto")
        self._color(m, fila, T("bola.color_circulo"), "bola_color_circulo")
        self._color(m, fila, T("bola.color_numeros"), "bola_color_numeros")
        ttk.Label(m, foreground="#666", justify="left",
                  text=T("bola.nota")).grid(
            row=fila[0], column=0, columnspan=3, sticky="w", pady=(10, 0))
        fila[0] += 1

    def _pestana_tiempos(self, cuaderno):
        m, fila = self._hoja(cuaderno, T("tab.tiempos"), "tiempos")
        boton = tk.Button(m, relief="groove", font=("Segoe UI", 9, "bold"))

        estado = ttk.Label(m, justify="left")

        def pinta():
            activo = self.cfg["comparar"]
            boton.config(
                text=T("tie.salir") if activo else T("tie.entrar"),
                bg="#8e44ad" if activo else "#2d6a4f", fg="white")
            # El texto del boton es la ACCION, no el estado, y eso se lee mal:
            # con la comparacion apagada pone "COMPARAR TIEMPOS CON OPONENTES"
            # y parece que ya esta comparando. Debajo va el estado, sin dudas.
            estado.config(text=T("tie.activado") if activo else T("tie.apagado"),
                          foreground="#2d6a4f" if activo else "#b03a2e")

        def alterna():
            self.cfg["comparar"] = not self.cfg["comparar"]
            self.guardar(self.cfg)
            pinta()
        boton.config(command=alterna)
        pinta()
        boton.grid(row=fila[0], column=0, columnspan=3, sticky="we", pady=2)
        fila[0] += 1
        estado.grid(row=fila[0], column=0, columnspan=3, sticky="w", pady=(0, 4))
        fila[0] += 1
        pinta()

        self._titulo(m, fila, T("tie.tit_colores"))
        self._color(m, fila, T("tie.referencia"), "color_referencia")
        self._color(m, fila, T("tie.lento"), "color_lento")
        self._color(m, fila, T("tie.igual"), "color_igual")
        self._color(m, fila, T("tie.rapido"), "color_rapido")

        cab = ttk.Frame(m)
        cab.grid(row=fila[0], column=0, columnspan=3, sticky="we", pady=(12, 2))
        fila[0] += 1
        ttk.Label(cab, text=T("tie.tit_salidas"),
                  font=("Segoe UI", 9, "bold")).pack(side="left")
        tk.Button(cab, text=" i ", font=("Segoe UI", 8, "bold"), fg="white",
                  bg="#3a7bd5", relief="groove",
                  command=lambda: ayuda(self.v, "salidas", T("tie.tit_salidas"))
                  ).pack(side="right")
        self._interruptor(m, fila, T("tie.avisar_salidas"), "ver_salidas")
        self._interruptor(m, fila, T("tie.solo_juego"), "salidas_segun_juego", 20)
        self._deslizador(m, fila, T("tie.sensibilidad"), "margen_salida", 0.2, 3.0, 1)
        self._color(m, fila, T("tie.color_aviso"), "color_salida")

        cab2 = ttk.Frame(m)
        cab2.grid(row=fila[0], column=0, columnspan=3, sticky="we", pady=(12, 2))
        fila[0] += 1
        ttk.Label(cab2, text=T("tie.tit_parados"),
                  font=("Segoe UI", 9, "bold")).pack(side="left")
        tk.Button(cab2, text=" i ", font=("Segoe UI", 8, "bold"), fg="white",
                  bg="#3a7bd5", relief="groove",
                  command=lambda: ayuda(self.v, "parados", T("tie.tit_parados"))
                  ).pack(side="right")
        self._interruptor(m, fila, T("tie.avisar_parados"), "ver_parados")
        ttk.Label(m, foreground="#666", justify="left",
                  text=T("tie.nota_banderas")).grid(row=fila[0], column=0, columnspan=3, sticky="w", padx=(20, 0))
        fila[0] += 1
        self._color(m, fila, T("tie.color_parpadeo"), "color_parado")
        ttk.Button(m, text=T("tie.buscar_avisos"),
                   command=self._lanzar("buscar_aviso.py")).grid(
            row=fila[0], column=0, columnspan=3, sticky="we", pady=(10, 0))
        fila[0] += 1

    def _pestana_trazadas(self, cuaderno):
        m, fila = self._hoja(cuaderno, T("tab.trazadas"), "trazadas")
        ttk.Label(m, foreground="#666", justify="left",
                  text=T("tra.intro")).grid(row=fila[0], column=0, columnspan=3, sticky="w", pady=(0, 8))
        fila[0] += 1

        self.resumen = ttk.Label(m, justify="left", text="")
        self.resumen.grid(row=fila[0], column=0, columnspan=3, sticky="w", pady=(0, 8))
        fila[0] += 1
        self._refrescar_resumen()

        tk.Button(m, text=T("tra.abrir"),
                  command=self._abrir_visor, bg="#2d6a4f", fg="white",
                  relief="groove", font=("Segoe UI", 9, "bold")).grid(
            row=fila[0], column=0, columnspan=3, sticky="we", pady=2)
        fila[0] += 1
        ttk.Button(m, text=T("tra.actualizar"),
                   command=self._refrescar_resumen).grid(
            row=fila[0], column=0, columnspan=3, sticky="we", pady=2)
        fila[0] += 1

    def _refrescar_resumen(self):
        sesiones = grab.listar_sesiones()
        if not sesiones:
            self.resumen.config(text=T("tra.sin_sesiones"))
            return
        sitio = sum(s["tamano"] for s in sesiones) / 1024.0
        ultima = sesiones[0]
        self.resumen.config(
            text=T("tra.resumen")
                 % (len(sesiones), sitio, ultima["circuito"],
                    grab.nombre_sesion(ultima["sesion"]), ultima["vueltas"]))

    def _abrir_visor(self):
        visor.abrir(self.v, self.cfg)

    def _pestana_pantalla(self, cuaderno):
        """
        Por que se ve (o no) el mapa encima del juego, y que cuesta.

        Es la unica hoja que mira COSAS DE FUERA del programa: el modo de
        pantalla que tiene puesto el juego y una casilla de Windows. Estan
        aqui porque son las dos unicas razones por las que alguien abre el
        mapa y no ve nada, y ninguna de las dos se ve a simple vista.
        """
        m, fila = self._hoja(cuaderno, T("tab.pantalla"), "pantalla")
        self.marco_pantalla = ttk.Frame(m)
        self.marco_pantalla.grid(row=fila[0], column=0, columnspan=3,
                                 sticky="we")
        fila[0] += 1
        self._pintar_pantalla()

        self._titulo(m, fila, T("pan.tit_fluidez"))
        self._fluidez(m, fila)
        ttk.Label(m, foreground="#666", justify="left",
                  text=T("pan.fluidez_nota")).grid(
            row=fila[0], column=0, columnspan=3, sticky="w", padx=(20, 0))
        fila[0] += 1

    def _pintar_pantalla(self):
        """El diagnostico, que se vuelve a pintar despues de arreglar nada."""
        import juego
        import pantalla
        for hijo in self.marco_pantalla.winfo_children():
            hijo.destroy()
        d = pantalla.diagnostico(juego.carpeta())
        f = [0]

        def linea(texto, valor, color=None):
            ttk.Label(self.marco_pantalla, text=texto).grid(
                row=f[0], column=0, sticky="w", pady=1)
            et = tk.Label(self.marco_pantalla, text=valor, anchor="w")
            if color:
                et.config(fg=color)
            et.grid(row=f[0], column=1, sticky="w", padx=6)
            f[0] += 1

        modos = {"exclusiva": T("pan.modo_exclusiva"),
                 "sin_bordes": T("pan.modo_sin_bordes"),
                 "ventana": T("pan.modo_ventana")}
        linea(T("pan.modo"), modos.get(d["modo"], T("pan.no_se_sabe")))

        if d["optimizaciones"] is None:
            linea(T("pan.optimizaciones"), T("pan.no_se_sabe"))
        elif d["optimizaciones"]:
            linea(T("pan.optimizaciones"), T("pan.opt_si"), "#1a7f37")
        else:
            linea(T("pan.optimizaciones"), T("pan.opt_no"), "#b3261e")

        if d["se_vera"] is True:
            linea(T("pan.conclusion"), T("pan.si_se_ve"), "#1a7f37")
        elif d["se_vera"] is False:
            linea(T("pan.conclusion"), T("pan.no_se_ve"), "#b3261e")
        else:
            linea(T("pan.conclusion"), T("pan.no_se_sabe"))

        # El boton solo aparece cuando hay algo que arreglar DE VERDAD: la
        # casilla marcada Y el juego pidiendo pantalla completa.
        #
        # Medido el 13/09/2026 con PresentMon, en sin bordes y con la casilla
        # en los dos estados: el camino que da Windows es el mismo
        # ("Hardware Composed: Independent Flip") con ella marcada y sin
        # marcar. O sea que **en ventana o sin bordes la casilla no hace
        # nada**, y ofrecer ahi un boton seria invitar a tocar lo que no
        # estorba. Solo actua cuando el juego pide la exclusiva, que es lo
        # unico que esa casilla impide que Windows convierta.
        if (d["optimizaciones"] is False and d["exe"]
                and d["modo"] == "exclusiva"):
            ttk.Label(self.marco_pantalla, foreground="#666", justify="left",
                      text=T("pan.aviso_arreglo")).grid(
                row=f[0], column=0, columnspan=3, sticky="w", pady=(8, 2))
            f[0] += 1
            ttk.Button(self.marco_pantalla, text=T("pan.arreglar"),
                       command=lambda: self._arreglar_pantalla(d["exe"])).grid(
                row=f[0], column=0, columnspan=2, sticky="w")
            f[0] += 1

    def _arreglar_pantalla(self, exe):
        """
        Quita la casilla que impide ver el mapa en pantalla completa.

        Es lo unico que el programa escribe fuera de su carpeta, asi que se
        pregunta antes, se dice exactamente que se toca, y se conservan las
        demas marcas de compatibilidad que hubiera en esa linea.
        """
        import pantalla
        if not messagebox.askyesno(T("pan.arreglar"),
                                   T("pan.confirmar") % exe, parent=self.v):
            return
        bien, motivo = pantalla.activar_optimizaciones(exe)
        if bien:
            messagebox.showinfo(T("pan.arreglar"), T("pan.arreglado"),
                                parent=self.v)
        else:
            messagebox.showerror(T("pan.arreglar"),
                                 T("pan.no_arreglado") % motivo, parent=self.v)
        self._pintar_pantalla()

    def _pestana_clima(self, cuaderno):
        """
        El panel del clima.

        Hoja propia, como la bola de fuerzas G: es otro instrumento con su
        ventana, su sitio en la pantalla y sus ajustes, no algo que se dibuje
        dentro del mapa.
        """
        m, fila = self._hoja(cuaderno, T("tab.clima"), "clima")
        self._interruptor(m, fila, T("clima.opt.ver"), "clima_ver")
        self._titulo(m, fila, T("clima.opt.tit_que_sale"))
        self._interruptor(m, fila, T("clima.opt.ahora"), "clima_ahora")
        self._interruptor(m, fila, T("clima.opt.pronostico"), "clima_pronostico")
        self._interruptor(m, fila, T("clima.opt.temps"), "clima_temps", 20)
        self._interruptor(m, fila, T("clima.opt.pista"), "clima_pista", 20)
        self._interruptor(m, fila, T("clima.opt.hora"), "clima_hora", 20)
        self._interruptor(m, fila, T("clima.opt.viento"), "clima_viento", 20)
        self._interruptor(m, fila, T("clima.opt.humedad"), "clima_humedad", 20)
        self._interruptor(m, fila, T("clima.opt.aviso"), "clima_aviso_lluvia")

        self._titulo(m, fila, T("clima.opt.tit_sesion"))
        self._sesion_del_clima(m, fila)
        ttk.Label(m, foreground="#666", justify="left",
                  text=T("clima.opt.sesion_nota")).grid(
            row=fila[0], column=0, columnspan=3, sticky="w", padx=(20, 0))
        fila[0] += 1

        self._reloj_del_clima(m, fila)
        ttk.Label(m, foreground="#666", justify="left",
                  text=T("clima.opt.reloj_nota")).grid(
            row=fila[0], column=0, columnspan=3, sticky="w", padx=(20, 0))
        fila[0] += 1

        self._titulo(m, fila, T("clima.opt.tit_aspecto"))
        self._deslizador(m, fila, T("clima.opt.tam"), "clima_tam", 60, 220)
        self._deslizador(m, fila, T("asp.opacidad"), "clima_opacidad", 0.2, 1.0, 2)
        self._interruptor(m, fila, T("clima.opt.fondo"), "clima_fondo")
        self._color(m, fila, T("clima.opt.color_fondo"), "clima_color_fondo")
        self._color(m, fila, T("clima.opt.color_texto"), "clima_color_texto")
        self._color(m, fila, T("clima.opt.color_aviso"), "clima_color_aviso")
        ttk.Label(m, foreground="#666", justify="left",
                  text=T("clima.opt.mover")).grid(
            row=fila[0], column=0, columnspan=3, sticky="w", pady=(8, 0))
        fila[0] += 1

    # Las cuatro opciones de que pronostico se ensena. El valor que se guarda
    # no es el texto traducido, que cambia con el idioma, sino el codigo.
    SESIONES_CLIMA = ["auto", "practice", "qualify", "race"]

    RELOJES_CLIMA = ["circuito", "ambas", "falta"]

    def _reloj_del_clima(self, m, fila):
        nombres = [T("clima.opt.reloj_" + c) for c in self.RELOJES_CLIMA]
        actual = self.cfg.get("clima_reloj", "circuito")
        if actual not in self.RELOJES_CLIMA:
            actual = "circuito"
        ttk.Label(m, text=T("clima.opt.reloj")).grid(
            row=fila[0], column=0, sticky="w")
        var = tk.StringVar(value=nombres[self.RELOJES_CLIMA.index(actual)])

        def cambio(_=None):
            self.cfg["clima_reloj"] = \
                self.RELOJES_CLIMA[nombres.index(var.get())]
            self.guardar(self.cfg)
        combo = ttk.Combobox(m, textvariable=var, values=nombres,
                             state="readonly", width=22)
        combo.grid(row=fila[0], column=1, sticky="w", padx=4, pady=1)
        combo.bind("<<ComboboxSelected>>", cambio)
        fila[0] += 1

    def _sesion_del_clima(self, m, fila):
        nombres = [T("clima.opt.ses_" + c) for c in self.SESIONES_CLIMA]
        actual = self.cfg.get("clima_que_sesion", "auto")
        if actual not in self.SESIONES_CLIMA:
            actual = "auto"
        ttk.Label(m, text=T("clima.opt.que_sesion")).grid(
            row=fila[0], column=0, sticky="w")
        var = tk.StringVar(value=nombres[self.SESIONES_CLIMA.index(actual)])

        def cambio(_=None):
            self.cfg["clima_que_sesion"] =                 self.SESIONES_CLIMA[nombres.index(var.get())]
            self.guardar(self.cfg)
        combo = ttk.Combobox(m, textvariable=var, values=nombres,
                             state="readonly", width=22)
        combo.grid(row=fila[0], column=1, sticky="w", padx=4, pady=1)
        combo.bind("<<ComboboxSelected>>", cambio)
        fila[0] += 1

    def _pestana_frenos(self, cuaderno):
        """
        El panel de los frenos y sus avisos, juntos.

        Los avisos van aqui y no en la hoja de Avisos porque salen del mismo
        dato que el panel (el grosor de los discos) y quien los configure
        quiere ver las dos cosas a la vez.
        """
        m, fila = self._hoja(cuaderno, T("tab.frenos"), "frenos")
        ttk.Label(m, justify="left", foreground="#555", wraplength=430,
                  text=T("frn.nota")).grid(row=fila[0], column=0, columnspan=3,
                                           sticky="w", pady=(0, 8))
        fila[0] += 1

        self._titulo(m, fila, T("frn.tit_panel"))
        self._interruptor(m, fila, T("frn.opt.ver"), "frenos_ver")
        self._deslizador(m, fila, T("clima.opt.tam"), "frenos_tam", 60, 220)
        self._deslizador(m, fila, T("asp.opacidad"), "frenos_opacidad", 0.2, 1.0, 2)
        self._interruptor(m, fila, T("clima.opt.fondo"), "frenos_fondo")
        self._color(m, fila, T("clima.opt.color_fondo"), "frenos_color_fondo")
        self._color(m, fila, T("clima.opt.color_texto"), "frenos_color_texto")

        self._titulo(m, fila, T("frn.titulo"))
        self._interruptor(m, fila, T("frn.activado"), "frenos_aviso")
        self._deslizador(m, fila, T("frn.minutos"), "frenos_aviso_min", 15, 180)
        ttk.Label(m, foreground="#666", justify="left", wraplength=430,
                  text=T("frn.nota_sonido")).grid(
            row=fila[0], column=0, columnspan=3, sticky="w", padx=(20, 0))
        fila[0] += 1

        ttk.Label(m, foreground="#b03a2e", justify="left", wraplength=430,
                  font=("Segoe UI", 9, "bold"),
                  text=T("frn.colocar")).grid(
            row=fila[0], column=0, columnspan=3, sticky="w", pady=(12, 0))
        fila[0] += 1

    def _pestana_clasificacion(self, cuaderno):
        """El panel con los tiempos de todos los coches (clasificacion_gui.py)."""
        m, fila = self._hoja(cuaderno, T("tab.clasificacion"), "clasificacion")
        ttk.Label(m, justify="left", foreground="#555", wraplength=430,
                  text=T("cla.nota")).grid(row=fila[0], column=0, columnspan=3,
                                           sticky="w", pady=(0, 8))
        fila[0] += 1

        self._titulo(m, fila, T("cla.tit_panel"))
        self._interruptor(m, fila, T("cla.opt.ver"), "tabla_ver")
        self._interruptor(m, fila, T("cla.opt.solo_clase"), "tabla_solo_clase")
        self._deslizador(m, fila, T("cla.opt.filas"), "tabla_filas", 5, 80)
        self._deslizador(m, fila, T("clima.opt.tam"), "tabla_tam", 60, 220)
        self._deslizador(m, fila, T("asp.opacidad"), "tabla_opacidad", 0.2, 1.0, 2)
        self._interruptor(m, fila, T("clima.opt.fondo"), "tabla_fondo")
        self._color(m, fila, T("clima.opt.color_fondo"), "tabla_color_fondo")
        self._color(m, fila, T("clima.opt.color_texto"), "tabla_color_texto")

        self._titulo(m, fila, T("cla.tit_columnas"))
        self._elegir_columnas(m, fila)

        ttk.Label(m, foreground="#b03a2e", justify="left", wraplength=430,
                  font=("Segoe UI", 9, "bold"),
                  text=T("cla.colocar")).grid(
            row=fila[0], column=0, columnspan=3, sticky="w", pady=(12, 0))
        fila[0] += 1

    def _pestana_estrategia(self, cuaderno):
        """El panel de prediccion de carrera (estrategia_gui.py)."""
        m, fila = self._hoja(cuaderno, T("tab.estrategia"), "estrategia")
        ttk.Label(m, justify="left", foreground="#555", wraplength=430,
                  text=T("est.nota")).grid(row=fila[0], column=0, columnspan=3,
                                           sticky="w", pady=(0, 8))
        fila[0] += 1
        self._titulo(m, fila, T("est.tit_panel"))
        self._interruptor(m, fila, T("est.opt.ver"), "estr_ver")
        self._deslizador(m, fila, T("est.opt.minutos"), "estr_minutos", 0, 120)
        self._deslizador(m, fila, T("cla.opt.filas"), "estr_filas", 5, 40)
        self._deslizador(m, fila, T("clima.opt.tam"), "estr_tam", 60, 220)
        self._deslizador(m, fila, T("asp.opacidad"), "estr_opacidad", 0.2, 1.0, 2)
        self._interruptor(m, fila, T("clima.opt.fondo"), "estr_fondo")
        self._color(m, fila, T("clima.opt.color_fondo"), "estr_color_fondo")
        self._color(m, fila, T("clima.opt.color_texto"), "estr_color_texto")
        ttk.Label(m, foreground="#b03a2e", justify="left", wraplength=430,
                  font=("Segoe UI", 9, "bold"),
                  text=T("est.colocar")).grid(
            row=fila[0], column=0, columnspan=3, sticky="w", pady=(12, 0))
        fila[0] += 1

    def _elegir_columnas(self, m, fila):
        """
        Que columnas lleva el panel de clasificacion y en que orden.

        Una lista con todas: la marca de la izquierda dice si se ve, y con los
        botones se pone o se quita y se sube o se baja. El panel cambia en el
        momento, asi que se ve como queda mientras se elige.
        """
        import clasificacion_gui
        cols = clasificacion_gui.columnas(self.cfg)

        ttk.Label(m, foreground="#666", justify="left", wraplength=430,
                  text=T("cla.nota_columnas")).grid(
            row=fila[0], column=0, columnspan=3, sticky="w")
        fila[0] += 1

        marco = ttk.Frame(m)
        marco.grid(row=fila[0], column=0, columnspan=3, sticky="w", pady=(4, 0))
        fila[0] += 1
        lista = tk.Listbox(marco, height=12, width=38, activestyle="none",
                           exportselection=False, font=("Segoe UI", 9))
        barra = ttk.Scrollbar(marco, orient="vertical", command=lista.yview)
        lista.configure(yscrollcommand=barra.set)
        lista.grid(row=0, column=0, rowspan=4, sticky="ns")
        barra.grid(row=0, column=1, rowspan=4, sticky="ns")

        def rellenar(elegida=None):
            lista.delete(0, "end")
            for clave, ver in cols:
                lista.insert("end", ("☑  " if ver else "☐  ")
                             + T("cla.nom." + clave))
            if elegida is not None:
                lista.selection_set(elegida)
                lista.see(elegida)

        def guardar(elegida):
            self.cfg["tabla_columnas"] = [list(par) for par in cols]
            self.guardar(self.cfg)
            rellenar(elegida)

        def cual():
            sel = lista.curselection()
            return sel[0] if sel else None

        def poner_quitar(_=None):
            i = cual()
            if i is not None:
                cols[i][1] = not cols[i][1]
                guardar(i)

        def mover(paso):
            i = cual()
            if i is None or not 0 <= i + paso < len(cols):
                return
            cols[i], cols[i + paso] = cols[i + paso], cols[i]
            guardar(i + paso)

        lista.bind("<Double-Button-1>", poner_quitar)
        ttk.Button(marco, text=T("cla.btn.ver"), command=poner_quitar).grid(
            row=0, column=2, sticky="we", padx=(8, 0))
        ttk.Button(marco, text=T("cla.btn.subir"), command=lambda: mover(-1)).grid(
            row=1, column=2, sticky="we", padx=(8, 0))
        ttk.Button(marco, text=T("cla.btn.bajar"), command=lambda: mover(1)).grid(
            row=2, column=2, sticky="we", padx=(8, 0))
        rellenar()

    def _pestana_avisos(self, cuaderno):
        """
        El cartel que salta cuando hay un coche parado por delante.

        Va en pestana propia y no junto a los colores del mapa porque no es
        cosa de aspecto: es lo unico del programa que te interrumpe mientras
        conduces, y quien lo configure tiene que verlo todo junto para
        decidir cuanto quiere que le moleste.
        """
        import aviso_gui
        m, fila = self._hoja(cuaderno, T("tab.avisos"), "avisos")

        ttk.Label(m, justify="left", foreground="#555", wraplength=430,
                  text=T("avi.intro")).grid(row=fila[0], column=0, columnspan=3,
                                            sticky="w", pady=(0, 8))
        fila[0] += 1

        self._interruptor(m, fila, T("avi.activado"), "aviso_parados")

        self._titulo(m, fila, T("avi.tit_cuando"))
        self._deslizador(m, fila, T("avi.antelacion"), "aviso_segundos", 3, 20)
        ttk.Label(m, foreground="#666", justify="left", wraplength=430,
                  text=T("avi.antelacion_nota")).grid(
            row=fila[0], column=0, columnspan=3, sticky="w", padx=(20, 0))
        fila[0] += 1

        self._titulo(m, fila, T("avi.tit_como"))
        self._deslizador(m, fila, T("avi.tamano"), "aviso_tam", 12, 60)
        self._color(m, fila, T("avi.color"), "aviso_color")

        ttk.Label(m, text=T("avi.texto_etiqueta")).grid(
            row=fila[0], column=0, sticky="w")
        var_texto = tk.StringVar(value=self.cfg.get("aviso_texto", ""))

        def texto_cambia(*_):
            self.cfg["aviso_texto"] = var_texto.get()
            self.guardar(self.cfg)
        var_texto.trace_add("write", texto_cambia)
        ttk.Entry(m, textvariable=var_texto, width=30).grid(
            row=fila[0], column=1, columnspan=2, sticky="w", padx=6)
        fila[0] += 1
        ttk.Label(m, foreground="#666", justify="left", wraplength=430,
                  text=T("avi.texto_nota")).grid(
            row=fila[0], column=0, columnspan=3, sticky="w", padx=(20, 0))
        fila[0] += 1

        self._titulo(m, fila, T("avi.tit_sonido"))
        self._interruptor(m, fila, T("avi.sonar"), "aviso_sonar")
        self._deslizador(m, fila, T("avi.volumen"), "aviso_volumen", 0, 100)
        ttk.Label(m, text=T("avi.sonido")).grid(row=fila[0], column=0, sticky="w")
        var_son = tk.StringVar(value=self.cfg.get("aviso_sonido", "doble.wav"))
        lista = [T("avi.sin_sonido")] + aviso_gui.sonidos_disponibles()

        def son_cambia(_=None):
            elegido = var_son.get()
            self.cfg["aviso_sonido"] = "" if elegido == T("avi.sin_sonido") else elegido
            self.guardar(self.cfg)
        combo = ttk.Combobox(m, textvariable=var_son, values=lista, width=18,
                             state="readonly")
        combo.grid(row=fila[0], column=1, sticky="w", padx=6)
        combo.bind("<<ComboboxSelected>>", son_cambia)
        ttk.Button(m, text=T("avi.probar"),
                   command=lambda: aviso_gui.tocar(
                       self.cfg.get("aviso_sonido"),
                       self.cfg.get("aviso_volumen", 60), True)
                   ).grid(row=fila[0], column=2, sticky="w")
        fila[0] += 1
        # Va justo debajo del boton de probar, que es donde mira uno cuando
        # le da y no suena nada. Ahi es donde hace falta la explicacion, no
        # enterrada en la ayuda.
        ttk.Label(m, foreground="#b03a2e", font=("Segoe UI", 8),
                  text=T("avi.suena_por")).grid(
            row=fila[0], column=1, columnspan=2, sticky="w", padx=6)
        fila[0] += 1
        ttk.Label(m, foreground="#666", justify="left", wraplength=430,
                  text=T("avi.sonido_nota")).grid(
            row=fila[0], column=0, columnspan=3, sticky="w", padx=(20, 0))
        fila[0] += 1

        ttk.Label(m, foreground="#b03a2e", justify="left", wraplength=430,
                  font=("Segoe UI", 9, "bold"),
                  text=T("avi.colocar")).grid(
            row=fila[0], column=0, columnspan=3, sticky="w", pady=(12, 0))
        fila[0] += 1

    def _pestana_escaneo(self, cuaderno):
        m, fila = self._hoja(cuaderno, T("tab.escaneo"), "escaneo")
        ttk.Label(m, foreground="#666", justify="left",
                  text=T("esc.intro")).grid(row=fila[0], column=0, columnspan=3, sticky="w", pady=(0, 6))
        fila[0] += 1

        marco = ttk.Frame(m)
        marco.grid(row=fila[0], column=0, columnspan=3, sticky="nsew")
        fila[0] += 1
        self.tabla = ttk.Treeview(
            marco, columns=("pista", "trazada", "boxes"), height=14,
            selectmode="browse")
        self.tabla.heading("#0", text=T("esc.col_circuito"))
        self.tabla.column("#0", width=260)
        for col, titulo in (("pista", T("esc.col_pista")),
                            ("trazada", T("esc.col_trazada")),
                            ("boxes", T("esc.col_boxes"))):
            self.tabla.heading(col, text=titulo)
            self.tabla.column(col, width=62, anchor="center")
        barra = ttk.Scrollbar(marco, orient="vertical", command=self.tabla.yview)
        self.tabla.configure(yscrollcommand=barra.set)
        self.tabla.pack(side="left")
        barra.pack(side="left", fill="y")
        self.tabla.bind("<Double-1>", lambda e: self._ver_escaneo())
        self.tabla.tag_configure("completo", foreground="#1f6b2f")
        self.tabla.tag_configure("vacio", foreground="#999")

        self.resumen_pistas = ttk.Label(m, foreground="#666", text="")
        self.resumen_pistas.grid(row=fila[0], column=0, columnspan=3,
                                 sticky="w", pady=(4, 6))
        fila[0] += 1
        self._refrescar_tabla()

        acciones = ttk.Frame(m)
        acciones.grid(row=fila[0], column=0, columnspan=3, sticky="we")
        fila[0] += 1
        ttk.Button(acciones, text=T("esc.ver"),
                   command=self._ver_escaneo).pack(side="left")
        ttk.Button(acciones, text=T("com.actualizar"),
                   command=self._refrescar_tabla).pack(side="left", padx=4)
        ttk.Button(acciones, text=T("esc.borrar"),
                   command=self._borrar_escaneo).pack(side="right")
        ttk.Label(m, foreground="#666", justify="left",
                  text=T("esc.nota_botones")).grid(
            row=fila[0], column=0, columnspan=3, sticky="w", pady=(4, 0))
        fila[0] += 1

        self._titulo(m, fila, T("esc.tit_escanear"))
        ttk.Label(m, foreground="#666", justify="left",
                  text=T("esc.nota_orden")).grid(
            row=fila[0], column=0, columnspan=3, sticky="w", pady=(0, 4))
        fila[0] += 1
        for texto, guion in (
                (T("esc.paso2"), "escanear_bordes.py"),
                (T("esc.paso3"), "escanear_boxes.py"),
                (T("esc.paso1"), "escanear_circuito.py")):
            ttk.Button(m, text=texto, width=42,
                       command=self._lanzar(guion)).grid(
                row=fila[0], column=0, columnspan=3, sticky="we", pady=2)
            fila[0] += 1

    def _refrescar_tabla(self):
        for i in self.tabla.get_children():
            self.tabla.delete(i)
        self.inventario = catalogo.inventario()
        marca = lambda b: T("com.si") if b else "-"
        for e in self.inventario:
            completo = e["pista"] and e["trazada"] and e["boxes"]
            etiqueta = "completo" if completo else ("vacio" if not e["trazada"] else "")
            self.tabla.insert(
                "", "end",
                text="%s  -  %s" % (e["circuito"], e["layout"]),
                values=(marca(e["pista"]), marca(e["trazada"]), marca(e["boxes"])),
                tags=(etiqueta,) if etiqueta else ())
        total = len(self.inventario)
        con = sum(1 for e in self.inventario if e["trazada"])
        self.resumen_pistas.config(
            text=T("esc.resumen")
                 % (total, con, sum(1 for e in self.inventario if e["pista"]),
                    sum(1 for e in self.inventario if e["boxes"])))

    def _fila_elegida(self):
        sel = self.tabla.selection()
        if not sel:
            return None
        return self.inventario[self.tabla.index(sel[0])]

    def _ver_escaneo(self):
        e = self._fila_elegida()
        if not e:
            messagebox.showinfo(T("esc.tit_ver"), T("esc.elige"),
                                parent=self.v)
            return
        if not e["clave"]:
            messagebox.showinfo(
                T("esc.tit_ver"), T("esc.sin_escanear"),
                parent=self.v)
            return
        visor.abrir_escaneo(self.v, e["clave"])

    def _borrar_escaneo(self):
        e = self._fila_elegida()
        if not e or not e["clave"]:
            messagebox.showinfo(T("com.borrar"), T("esc.elige_escaneado"),
                                parent=self.v)
            return
        if messagebox.askyesno(
                T("esc.tit_borrar"),
                T("esc.confirmar_borrar") % (e["circuito"], e["layout"])
                + T("com.seguro"), parent=self.v):
            catalogo.borrar_escaneo(e["clave"])
            self._refrescar_tabla()


    # ---------- pestana de coches ----------
    def _pestana_coches(self, cuaderno):
        m, fila = self._hoja(cuaderno, T("tab.coches"), "coches")
        ttk.Label(m, foreground="#666", justify="left",
                  text=T("coc.intro")).grid(row=fila[0], column=0, columnspan=3, sticky="w", pady=(0, 6))
        fila[0] += 1

        self.aviso_catalogo = ttk.Label(m, foreground="#2d6a4f", justify="left")
        self.aviso_catalogo.grid(row=fila[0], column=0, columnspan=3,
                                 sticky="w", pady=(0, 6))
        fila[0] += 1

        marco = ttk.Frame(m)
        marco.grid(row=fila[0], column=0, columnspan=3, sticky="nsew")
        fila[0] += 1
        self.arbol_coches = ttk.Treeview(marco, columns=("marca", "modelo"),
                                         height=13, selectmode="browse")
        self.arbol_coches.heading("#0", text=T("coc.col_arbol"))
        self.arbol_coches.column("#0", width=250)
        self.arbol_coches.heading("marca", text=T("coc.col_marca"))
        self.arbol_coches.column("marca", width=110, stretch=False)
        self.arbol_coches.heading("modelo", text=T("coc.col_modelo"))
        self.arbol_coches.column("modelo", width=150, stretch=False)
        barra = ttk.Scrollbar(marco, orient="vertical",
                              command=self.arbol_coches.yview)
        self.arbol_coches.configure(yscrollcommand=barra.set)
        self.arbol_coches.pack(side="left", fill="both", expand=True)
        barra.pack(side="left", fill="y")
        self.arbol_coches.tag_configure("pendiente", foreground="#b06000")
        self.arbol_coches.bind("<<TreeviewSelect>>", self._coche_elegido)

        # formulario
        form = ttk.Frame(m)
        form.grid(row=fila[0], column=0, columnspan=3, sticky="we", pady=(8, 0))
        fila[0] += 1
        self.v_equipo = tk.StringVar()
        self.v_marca = tk.StringVar()
        self.v_modelo = tk.StringVar()
        self.v_categoria = tk.StringVar(value=coches.CATEGORIAS[3])

        ttk.Label(form, text=T("coc.equipo")).grid(row=0, column=0, sticky="w")
        ttk.Entry(form, textvariable=self.v_equipo, width=34).grid(
            row=0, column=1, columnspan=3, sticky="we", padx=4, pady=1)
        ttk.Label(form, text=T("coc.col_marca")).grid(row=1, column=0, sticky="w")
        ttk.Entry(form, textvariable=self.v_marca, width=16).grid(
            row=1, column=1, sticky="we", padx=4, pady=1)
        ttk.Label(form, text=T("coc.col_modelo")).grid(row=1, column=2, sticky="e")
        combo_modelo = ttk.Combobox(form, textvariable=self.v_modelo, width=18,
                                    values=coches.modelos_instalados())
        combo_modelo.grid(row=1, column=3, sticky="we", padx=4, pady=1)
        # al elegir un modelo de los instalados, la marca se rellena sola
        combo_modelo.bind("<<ComboboxSelected>>", self._partir_modelo)
        ttk.Label(form, text=T("coc.categoria")).grid(row=2, column=0, sticky="w")
        ttk.Combobox(form, textvariable=self.v_categoria, values=coches.CATEGORIAS,
                     state="readonly", width=14).grid(row=2, column=1, sticky="w",
                                                      padx=4, pady=1)

        acciones = ttk.Frame(m)
        acciones.grid(row=fila[0], column=0, columnspan=3, sticky="we", pady=(6, 0))
        fila[0] += 1
        tk.Button(acciones, text=T("coc.guardar"), command=self._guardar_coche,
                  bg="#2d6a4f", fg="white", relief="groove",
                  font=("Segoe UI", 9, "bold")).pack(side="left")
        ttk.Button(acciones, text=T("com.borrar"),
                   command=self._borrar_coche).pack(side="right")
        ttk.Button(acciones, text=T("com.actualizar"),
                   command=self._refrescar_coches).pack(side="right", padx=4)
        ttk.Button(acciones, text=T("coc.traer"),
                   command=self._traer_parrilla).pack(side="left", padx=8)
        ttk.Button(acciones, text=T("coc.leer_juego"),
                   command=self._leer_del_juego).pack(side="left", padx=4)
        self._refrescar_coches()

    def _leer_del_juego(self):
        """Relee los resultados del juego por si hay sesiones nuevas."""
        import resultados
        archivos, nuevos = resultados.actualizar()
        if archivos is None:
            messagebox.showinfo(T("tab.coches"), T("coc.sin_resultados"),
                                parent=self.v)
            return
        self._refrescar_coches()
        modelos, decoraciones, sesiones = resultados.resumen()
        messagebox.showinfo(
            T("tab.coches"),
            T("coc.leido") % (archivos, nuevos, modelos, decoraciones, sesiones),
            parent=self.v)

    def _refrescar_coches(self):
        import resultados
        for i in self.arbol_coches.get_children():
            self.arbol_coches.delete(i)
        self.fichas_coches = {}

        modelos, decoraciones, sesiones = resultados.resumen()
        self.aviso_catalogo.configure(
            text=T("coc.del_juego") % (modelos, decoraciones, sesiones)
            if sesiones else T("coc.sin_leer"))

        pendientes = coches.pendientes()
        if pendientes:
            rama = self.arbol_coches.insert(
                "", "end", open=True, values=("", ""),
                text=T("coc.sin_identificar") % len(pendientes), tags=("pendiente",))
            for f in pendientes:
                visto = f.get("visto_en") or ""
                hijo = self.arbol_coches.insert(
                    rama, "end", tags=("pendiente",),
                    text="   %s" % f["equipo"],
                    values=(f.get("clase", ""), T("coc.visto_en") % visto if visto else ""))
                self.fichas_coches[hijo] = dict(f, pendiente=True)

        for categoria, lista in coches.por_categoria().items():
            if not lista:
                continue
            rama = self.arbol_coches.insert("", "end", text=categoria, open=False,
                                            values=("", ""))
            for f in lista:
                hijo = self.arbol_coches.insert(
                    rama, "end", text="   %s" % f.get("equipo", ""),
                    values=(f.get("marca", ""), f.get("modelo", "")))
                self.fichas_coches[hijo] = f

        # Los modelos que el juego ha dicho que tiene. No son equipos, son la
        # lista de coches del juego: sirve para ver de un vistazo que hay y es
        # de donde saldran los reglajes.
        del_juego = resultados.modelos_por_categoria()
        if del_juego:
            raiz = self.arbol_coches.insert(
                "", "end", open=False, values=("", ""),
                text=T("coc.modelos_juego") % sum(len(v) for v in del_juego.values()))
            for categoria in sorted(del_juego):
                rama = self.arbol_coches.insert(raiz, "end", open=False,
                                                text="   %s" % categoria,
                                                values=("", ""))
                for nombre in del_juego[categoria]:
                    marca, modelo = coches.partir_modelo(nombre)
                    self.arbol_coches.insert(rama, "end", text="      %s" % nombre,
                                             values=(marca, modelo))

    def _coche_elegido(self, _=None):
        sel = self.arbol_coches.selection()
        f = self.fichas_coches.get(sel[0]) if sel else None
        if not f:
            return
        self.v_equipo.set(f.get("equipo", ""))
        self.v_marca.set(f.get("marca", ""))
        self.v_modelo.set(f.get("modelo", ""))
        cat = f.get("categoria")
        if not cat:
            clase = (f.get("clase") or "").upper()
            cat = next((c for c in coches.CATEGORIAS if c.upper() in clase), "GT3")
        self.v_categoria.set(cat)

    def _partir_modelo(self, _=None):
        marca, modelo = coches.partir_modelo(self.v_modelo.get().strip())
        if marca:
            self.v_marca.set(marca)
            self.v_modelo.set(modelo)

    def _traer_parrilla(self):
        anadidos, total = coches.traer_de_la_sesion()
        if anadidos is None:
            messagebox.showinfo(
                T("tab.coches"), T("coc.sin_juego"),
                parent=self.v)
            return
        self._refrescar_coches()
        messagebox.showinfo(
            T("tab.coches"), T("coc.traidos") % (total, anadidos),
            parent=self.v)

    def _guardar_coche(self):
        equipo = self.v_equipo.get().strip()
        if not equipo:
            messagebox.showinfo(T("tab.coches"), T("coc.elige_equipo"),
                                parent=self.v)
            return
        if not self.v_marca.get().strip() and not self.v_modelo.get().strip():
            messagebox.showinfo(T("tab.coches"), T("coc.falta_marca"),
                                parent=self.v)
            return
        coches.definir(equipo, self.v_categoria.get(),
                       self.v_marca.get().strip(), self.v_modelo.get().strip())
        self._refrescar_coches()

    def _borrar_coche(self):
        equipo = self.v_equipo.get().strip()
        if not equipo:
            return
        if messagebox.askyesno(T("com.borrar"), T("coc.quitar") % equipo,
                               parent=self.v):
            coches.borrar(equipo)
            self._refrescar_coches()

    def _interprete(self):
        """
        Python CON consola.

        El mapa se arranca con pythonw.exe, que no tiene consola. Si se lanzara
        el escaneo con ese mismo interprete se abriria la ventana negra pero
        vacia: los mensajes que van guiando paso a paso no saldrian por ningun
        lado y pareceria que el boton no hace nada.
        """
        exe = sys.executable or ""
        if os.path.basename(exe).lower() == "pythonw.exe":
            con_consola = os.path.join(os.path.dirname(exe), "python.exe")
            if os.path.isfile(con_consola):
                return con_consola
        return exe

    def _orden(self, guion):
        """
        Que hay que ejecutar para abrir ese escaneo.

        Sin compilar: el interprete de Python con el .py.
        Compilado: el ejecutable hermano con consola, al que se le pasa el
        nombre del escaneo como argumento (ver arranque() en mapa_pista).
        """
        if rutas.compilado():
            consola = rutas.datos("MapaLMU-consola.exe")
            if not os.path.isfile(consola):
                raise IOError("falta MapaLMU-consola.exe al lado del programa")
            return [consola, os.path.splitext(guion)[0]]
        return [self._interprete(), os.path.join(CARPETA, guion)]

    def _lanzar(self, guion):
        def ir():
            try:
                # ventana propia: el escaneo va guiando paso a paso y hay que
                # poder leerlo mientras se conduce
                subprocess.Popen(self._orden(guion), cwd=CARPETA,
                                 creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
            except Exception as e:
                messagebox.showerror(T("err.no_abre"), str(e), parent=self.v)
        return ir


    # ---------------- pestana de reglajes (vista previa) ----------------
    GRIS = "#8d8d8d"
    GRIS_FLOJO = "#bdbdbd"
    GRIS_FUERTE = "#5a5a5a"

    def _pestana_reglajes(self, cuaderno):
        m, fila = self._hoja(cuaderno, T("tab.reglajes"), "reglajes")

        # La primera parte que ya funciona de verdad. Lo de abajo (las
        # fichas de coche y la hoja de reglaje) sigue siendo la maqueta.
        arriba = ttk.Frame(m)
        arriba.grid(row=fila[0], column=0, columnspan=3, sticky="we", pady=(0, 6))
        fila[0] += 1
        ttk.Button(arriba, text=T("reg.biblioteca"),
                   command=self._abrir_biblioteca).pack(side="left")
        ttk.Button(arriba, text=T("man.abrir"),
                   command=self._abrir_manual).pack(side="left", padx=(6, 0))
        ttk.Button(arriba, text=T("fov.abrir"),
                   command=self._abrir_fov).pack(side="left", padx=(6, 0))
        self.rotulo_reglaje = ttk.Label(arriba, foreground="#555",
                                        justify="left", font=("Segoe UI", 9))
        self.rotulo_reglaje.pack(side="left", padx=(12, 0))

        cuerpo = ttk.Frame(m)
        cuerpo.grid(row=fila[0], column=0, columnspan=3, sticky="nsew")
        fila[0] += 1

        # ---- izquierda: categorias y coches
        izq = ttk.Frame(cuerpo)
        izq.pack(side="left", fill="y")
        self.arbol_reglajes = ttk.Treeview(izq, height=21, selectmode="browse",
                                           show="tree")
        self.arbol_reglajes.column("#0", width=225, stretch=False)
        barra = ttk.Scrollbar(izq, orient="vertical",
                              command=self.arbol_reglajes.yview)
        self.arbol_reglajes.configure(yscrollcommand=barra.set)
        self.arbol_reglajes.pack(side="left", fill="y")
        barra.pack(side="left", fill="y")
        self.arbol_reglajes.tag_configure("grupo", foreground="#444")
        self.arbol_reglajes.bind("<<TreeviewSelect>>", self._coche_reglaje_elegido)

        # ---- derecha: las dos sub-pestanas
        der = ttk.Frame(cuerpo)
        der.pack(side="left", fill="both", expand=True, padx=(10, 0))
        sub = ttk.Notebook(der)
        sub.pack(fill="both", expand=True)

        hoja_car = ttk.Frame(sub, padding=6)
        sub.add(hoja_car, text=T("reg.sub.caracteristicas"))
        self.lienzo_car = tk.Canvas(hoja_car, width=640, height=372,
                                    bg="white", highlightthickness=1,
                                    highlightbackground="#d5d5d5")
        self.lienzo_car.pack(fill="both", expand=True)
        bajo = ttk.Frame(hoja_car)
        bajo.pack(fill="x", pady=(6, 0))
        self.b_ficha = ttk.Button(bajo, text=T("fic.escribir"),
                                  command=self._editar_ficha)
        self.b_ficha.pack(side="left")
        ttk.Label(bajo, foreground="#777", text=T("fic.nota")).pack(
            side="left", padx=(10, 0))

        # ---- la hoja de reglaje, que ahora se toca de verdad
        hoja_reg = ttk.Frame(sub, padding=6)
        sub.add(hoja_reg, text=T("reg.sub.reglaje"))
        elegir = ttk.Frame(hoja_reg)
        elegir.pack(fill="x", pady=(0, 4))
        ttk.Label(elegir, text=T("bib.circuito")).pack(side="left")
        self.ed_circuito = tk.StringVar()
        self.combo_ed_circuito = ttk.Combobox(elegir, width=18, state="readonly",
                                              textvariable=self.ed_circuito)
        self.combo_ed_circuito.pack(side="left", padx=(4, 10))
        self.combo_ed_circuito.bind("<<ComboboxSelected>>",
                                    lambda _: self._llenar_reglajes_editor())
        self.ed_reglaje = tk.StringVar()
        self.combo_ed_reglaje = ttk.Combobox(elegir, width=42, state="readonly",
                                             textvariable=self.ed_reglaje)
        self.combo_ed_reglaje.pack(side="left")
        self.combo_ed_reglaje.bind("<<ComboboxSelected>>",
                                   lambda _: self._cargar_en_editor())

        import editor_gui
        self.editor = editor_gui.Editor(hoja_reg,
                                        al_guardar=self._llenar_reglajes_editor)

        self._llenar_arbol_reglajes()
        self._llenar_circuitos_editor()

    def _abrir_biblioteca(self):
        """
        La biblioteca va en ventana aparte porque necesita ancho: son
        ochenta reglajes con siete columnas y aqui no caben.
        """
        import biblioteca_gui
        biblioteca_gui.abrir(self.v)

    def _abrir_manual(self):
        """
        El manual, en ventana aparte y sin cerrar las opciones: la gracia es
        poder leer lo que hace un ajuste con la pantalla del reglaje delante.
        """
        import manual_gui
        manual_gui.abrir(self.v)

    def _abrir_fov(self):
        """
        La calculadora de campo de vision. No es un reglaje del coche, pero
        se abre desde aqui porque es el ajuste que mas cambia como conduces
        y el manual empieza hablando de el.
        """
        import fov_gui
        fov_gui.abrir(self.v)

    def _llenar_arbol_reglajes(self):
        arbol = self.arbol_reglajes
        for i in arbol.get_children():
            arbol.delete(i)
        self.modelo_reglaje = ""
        primero = None
        import fichas
        por_cat = fichas.por_categoria()
        for categoria in reglajes.CATEGORIAS:
            lista = por_cat.get(categoria) or []
            if not lista:
                continue
            grupo = arbol.insert("", "end", text="%s  (%d)" % (categoria, len(lista)),
                                 open=True, tags=("grupo",))
            for modelo in lista:
                hijo = arbol.insert(grupo, "end", text="   " + reglajes.bonito(modelo),
                                    values=(modelo,))
                if primero is None:
                    primero = hijo
        if primero:
            arbol.selection_set(primero)
            arbol.see(primero)

    def _coche_reglaje_elegido(self, _=None):
        sel = self.arbol_reglajes.selection()
        if not sel:
            return
        valores = self.arbol_reglajes.item(sel[0], "values")
        if not valores:
            return                       # es una categoria, no un coche
        self.modelo_reglaje = valores[0]
        self._pintar_caracteristicas()

    # ---- caracteristicas del coche
    def _editar_ficha(self):
        """Escribir o corregir la ficha del coche que este elegido."""
        if not getattr(self, "modelo_reglaje", ""):
            return
        import fichas_gui
        fichas_gui.Editar(self.v, self.modelo_reglaje,
                          self._pintar_caracteristicas)

    def _pintar_caracteristicas(self):
        import fichas
        c = self.lienzo_car
        c.delete("all")
        ficha = fichas.de(self.modelo_reglaje)
        self.b_ficha.configure(
            text=T("fic.corregir") if ficha else T("fic.escribir"))

        if not ficha:
            # Un coche que el juego ha sacado despues de hacerse el
            # programa. No se deja en blanco y ya: se dice que pasa y como
            # arreglarlo, que es lo unico que hace falta para que esto no
            # se quede muerto el dia que nadie lo mantenga.
            c.create_text(16, 20, anchor="w",
                          text=reglajes.bonito(self.modelo_reglaje),
                          fill=self.GRIS_FUERTE, font=("Segoe UI", 13, "bold"))
            c.create_text(16, 60, anchor="nw", text=T("fic.no_hay"),
                          fill=self.GRIS, font=("Segoe UI", 9), width=600)
            return
        # Si la ficha viene con el programa se ensena traducida; si la
        # escribio alguien a mano, tal cual la escribio.
        ficha = dict(fichas.traducida(self.modelo_reglaje) or ficha)
        y = 18
        c.create_text(16, y, anchor="w", text=reglajes.bonito(self.modelo_reglaje),
                      fill=self.GRIS_FUERTE, font=("Segoe UI", 13, "bold"))
        y += 30
        for etiqueta, dato in ((T("reg.motor"), "motor"),
                               (T("reg.cilindrada"), "cilindrada"),
                               (T("reg.potencia"), "potencia"),
                               (T("reg.posicion"), "posicion"),
                               (T("reg.traccion"), "traccion")):
            c.create_line(16, y + 13, 624, y + 13, fill="#ededed")
            c.create_text(16, y, anchor="w", text=etiqueta, fill=self.GRIS,
                          font=("Segoe UI", 9))
            c.create_text(624, y, anchor="e", text=ficha[dato], fill=self.GRIS_FUERTE,
                          font=("Segoe UI", 9, "bold"))
            y += 27
        y += 14
        c.create_text(16, y, anchor="w", text=T("reg.comportamiento"), fill=self.GRIS,
                      font=("Segoe UI", 9, "bold"))
        y += 22
        c.create_text(16, y, anchor="nw", text=ficha["resumen"], fill=self.GRIS,
                      font=("Segoe UI", 9), width=608)

    # ---- el editor de reglajes
    def _llenar_circuitos_editor(self):
        import biblioteca
        import biblioteca_gui
        base = biblioteca_gui.settings()
        circuitos = biblioteca.circuitos_del_juego(base) if base else []
        self.combo_ed_circuito.configure(values=circuitos)
        if circuitos and not self.ed_circuito.get():
            self.ed_circuito.set(circuitos[0])
        self._llenar_reglajes_editor()

    def _llenar_reglajes_editor(self):
        """Los reglajes del circuito elegido, para el desplegable."""
        import biblioteca_gui
        base = biblioteca_gui.settings()
        circuito = self.ed_circuito.get()
        nombres = []
        if base and circuito:
            carpeta = os.path.join(base, circuito)
            try:
                nombres = sorted(f[:-4] for f in os.listdir(carpeta)
                                 if f.lower().endswith(".svm"))
            except OSError:
                nombres = []
        self.combo_ed_reglaje.configure(values=nombres)
        if self.ed_reglaje.get() not in nombres:
            self.ed_reglaje.set(nombres[0] if nombres else "")
        self._cargar_en_editor()

    def _cargar_en_editor(self):
        import biblioteca
        import biblioteca_gui
        base = biblioteca_gui.settings()
        circuito, nombre = self.ed_circuito.get(), self.ed_reglaje.get()
        if not base or not circuito or not nombre:
            return
        ficha = biblioteca.leer(os.path.join(base, circuito, nombre + ".svm"))
        if ficha:
            self.editor.cargar(ficha)

    def _pestana_acerca(self, cuaderno):
        m, fila = self._hoja(cuaderno, T("tab.acerca"), "acerca")

        def linea(color="#dcdcdc"):
            tk.Frame(m, height=1, bg=color).grid(
                row=fila[0], column=0, columnspan=3, sticky="we", pady=9)
            fila[0] += 1

        # ---- que es esto
        tk.Label(m, text=T("acerca.titulo"), font=("Segoe UI", 11, "bold"),
                 fg="#2c3e50").grid(row=fila[0], column=0, columnspan=3, sticky="w")
        fila[0] += 1
        ttk.Label(m, foreground="#666", justify="left",
                  text=T("acerca.descripcion")).grid(
            row=fila[0], column=0, columnspan=3, sticky="w", pady=(2, 0))
        fila[0] += 1
        if enlaces.PROYECTO:
            self._enlace(m, fila, T("acerca.proyecto"), enlaces.PROYECTO)

        # ---- idioma
        linea()
        caja = ttk.Frame(m)
        caja.grid(row=fila[0], column=0, columnspan=3, sticky="w")
        fila[0] += 1
        ttk.Label(caja, text=T("acerca.idioma"),
                  font=("Segoe UI", 9, "bold")).pack(side="left")
        lista = idiomas.disponibles()
        self.v_idioma = tk.StringVar(value=dict(lista).get(idiomas.actual(), ""))
        combo = ttk.Combobox(caja, textvariable=self.v_idioma, state="readonly",
                             width=18, values=[n for _, n in lista])
        combo.pack(side="left", padx=8)
        combo.bind("<<ComboboxSelected>>", self._cambiar_idioma)
        self.aviso_idioma = ttk.Label(m, foreground="#888", text="")
        self.aviso_idioma.grid(row=fila[0], column=0, columnspan=3, sticky="w",
                               pady=(2, 0))
        fila[0] += 1

        # ---- donaciones
        linea()
        tk.Label(m, text=T("acerca.donar.titulo"), font=("Segoe UI", 10, "bold"),
                 fg="#8a6d3b").grid(row=fila[0], column=0, columnspan=3, sticky="w")
        fila[0] += 1
        ttk.Label(m, foreground="#666", justify="left",
                  text=T("acerca.donar.texto")).grid(
            row=fila[0], column=0, columnspan=3, sticky="w", pady=(2, 6))
        fila[0] += 1
        botones = ttk.Frame(m)
        botones.grid(row=fila[0], column=0, columnspan=3, sticky="w")
        fila[0] += 1
        hay = False
        for texto, url, color in ((T("acerca.donar.kofi"), enlaces.KOFI, "#ff5e5b"),
                                  (T("acerca.donar.paypal"), enlaces.PAYPAL, "#0070ba")):
            if url:
                hay = True
                tk.Button(botones, text=texto, bg=color, fg="white", relief="groove",
                          font=("Segoe UI", 9, "bold"),
                          command=lambda u=url: enlaces.abrir(u)).pack(side="left",
                                                                      padx=(0, 6))
        if not hay:
            # sin cuenta abierta todavia: se avisa aqui y no en un boton muerto
            ttk.Label(botones, foreground="#aaa",
                      text=T("acerca.sin_enlace")).pack(side="left")

        # ---- CicloTracker: ya no "patrocinado por", sino apoyarlo para que sigamos
        # haciendo proyectos (lo pidio Manuel el 08/10/2026, igual que en LMU Chat Radio)
        linea()
        tk.Label(m, text=T("acerca.patrocinio"), font=("Segoe UI", 10, "bold"),
                 fg="#2e9e4f").grid(row=fila[0], column=0, columnspan=3, sticky="w")
        fila[0] += 1
        ttk.Label(m, foreground="#666", justify="left",
                  text=T("acerca.patrocinio.texto")).grid(
            row=fila[0], column=0, columnspan=3, sticky="w", pady=(2, 6))
        fila[0] += 1
        patro = ttk.Frame(m)
        patro.grid(row=fila[0], column=0, columnspan=3, sticky="w")
        fila[0] += 1
        tk.Button(patro, text=T("acerca.patrocinio.web"), bg="#2e9e4f", fg="white",
                  relief="groove", font=("Segoe UI", 9, "bold"),
                  command=lambda: enlaces.abrir(enlaces.CICLOTRACKER)).pack(side="left")
        if enlaces.CICLOTRACKER_ANDROID:
            ttk.Button(patro, text=T("acerca.patrocinio.android"),
                       command=lambda: enlaces.abrir(
                           enlaces.CICLOTRACKER_ANDROID)).pack(side="left", padx=6)

        # ---- cerrar
        linea()
        tk.Button(m, text=T("acerca.cerrar"), command=self.mapa.cerrar_programa,
                  bg="#c0392b", fg="white", relief="groove",
                  font=("Segoe UI", 9, "bold")).grid(
            row=fila[0], column=0, columnspan=3, sticky="we", pady=2)
        fila[0] += 1

    def _enlace(self, m, fila, texto, url):
        """Un texto azul subrayado que abre una direccion."""
        et = tk.Label(m, text=texto, fg="#1a5fb4", cursor="hand2",
                      font=("Segoe UI", 9, "underline"))
        et.grid(row=fila[0], column=0, columnspan=3, sticky="w", pady=(4, 0))
        et.bind("<Button-1>", lambda _e: enlaces.abrir(url))
        fila[0] += 1

    def _cambiar_idioma(self, _=None):
        for codigo, nombre in idiomas.disponibles():
            if nombre == self.v_idioma.get():
                idiomas.elegir(codigo)
                self.aviso_idioma.configure(text=T("acerca.reiniciar"))
                return


def abrir(mapa, guardar):
    return Opciones(mapa, guardar).v
