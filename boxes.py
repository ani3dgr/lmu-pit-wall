# -*- coding: utf-8 -*-
"""
Lo que va a costar NUESTRA proxima parada, con lo que esta marcado en el menu
de boxes del juego.

DE DONDE SALE (visto el 30/10/2026, carrera de 6 h en Barcelona)
La misma API que los frenos, `/rest/garage/UIScreen/RepairAndRefuel`, trae:
  - `pitMenu`: el menu de boxes tal cual, con lo que hay marcado: piloto,
    energia virtual, ruedas, reparar, frenos... Lo marca el companero que
    observa antes de que el coche entre.
  - `pitStopLength.timeInSeconds`: lo que el PROPIO JUEGO calcula que va a
    estar el coche parado con ese menu. Es el dato bueno.
  - `pitStopTimes.times`: la tabla de tiempos de cada operacion: cuatro ruedas
    12 s, dos ruedas 4,5, cambio de piloto 25, reparar carroceria 30, frenos
    120, energia al 2,5 % por segundo (el deposito entero en 40 s), y si cada
    cosa va A LA VEZ que las demas o detras ("...Concurrent").
Con el menu de entonces (energia del 43 al 100 % y cuatro ruedas) el juego
decia 34,7 s: 22,8 de energia + 12 de ruedas. O sea, ruedas y energia van una
DETRAS de otra, no a la vez.

LO QUE NO DICE EL JUEGO
Lo que se pierde en el carril de boxes (entrar a 60, salir): se mide en
clasificacion.Tabla con las paradas de todos (unos 27 s alli). Y en las
paradas con CAMBIO DE PILOTO se pierden unos 14 s mas de lo que el juego
apunta como parado: tambien se mide de las paradas de todos.

Para salir de dudas (por ejemplo si el cambio de piloto se suma a las ruedas
o va a la vez), cada vez que cambia el menu se apunta en un CSV lo marcado y
lo que dice el juego, y cada parada nuestra lo previsto contra lo real.
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

URL = "http://127.0.0.1:6397/rest/garage/UIScreen/RepairAndRefuel"
CADA = 2.0
CADUCA = 10.0


def _pct(texto):
    """'100% 33 Vueltas' -> 1.0"""
    hallado = re.match(r"\s*(\d+(?:[.,]\d+)?)\s*%", texto or "")
    return float(hallado.group(1).replace(",", ".")) / 100.0 if hallado else None


class Boxes:
    def __init__(self):
        self._d = None
        self._sello = 0.0
        self._hilo = None
        self._ultimo_menu = None
        self._archivo = None

    def arrancar(self):
        if self._hilo is None:
            self._hilo = threading.Thread(target=self._bucle, daemon=True)
            self._hilo.start()

    def _bucle(self):
        while True:
            try:
                pet = urllib.request.Request(URL, headers={"Accept": "application/json"})
                with urllib.request.urlopen(pet, timeout=3) as r:
                    d = json.loads(r.read().decode("utf-8-sig", "replace"))
                if isinstance(d, dict) and d.get("pitMenu"):
                    self._d, self._sello = d, time.monotonic()
                    try:
                        self._apuntar_menu()
                    except Exception:
                        pass
            except Exception:
                pass
            time.sleep(CADA)

    # ------------------------------------------------------------ lectura
    def menu(self):
        """{nombre: texto marcado} del menu de boxes, o {}."""
        self.arrancar()
        if not self._d or time.monotonic() - self._sello > CADUCA:
            return {}
        salida = {}
        for m in (self._d.get("pitMenu") or {}).get("pitMenu") or []:
            opciones = [s.get("text") for s in m.get("settings") or []]
            i = m.get("currentSetting")
            nombre = (m.get("name") or "").strip().rstrip(":")
            if isinstance(i, int) and 0 <= i < len(opciones):
                salida[nombre] = (opciones[i] or "").strip()
        return salida

    def prevision(self, piloto_ahora=""):
        """
        Lo de la proxima parada segun el menu, o None:
        {"parado": s que dice el juego, "piloto": si cambia, "energia_s",
         "ruedas": cuantas, "ruedas_s", "piloto_s", "reparar", "reparar_s",
         "frenos", "frenos_s"}.
        """
        self.arrancar()
        if not self._d or time.monotonic() - self._sello > CADUCA:
            return None
        menu = self.menu()
        tiempos = ((self._d.get("pitStopTimes") or {}).get("times")) or {}
        parado = (self._d.get("pitStopLength") or {}).get("timeInSeconds")

        # energia: de lo que hay a lo marcado, a su ritmo de llenado
        info = self._d.get("fuelInfo") or {}
        energia_s = 0.0
        objetivo = _pct(menu.get("VIRTUAL ENERGY"))
        maximo = info.get("maxVirtualEnergy") or 0
        if objetivo is not None and maximo:
            hay = (info.get("currentVirtualEnergy") or 0) / maximo
            ritmo = tiempos.get("virtualEnergyFillRate") or 0
            if ritmo > 0:
                energia_s = max(0.0, objetivo - hay) / ritmo

        ruedas = sum(1 for r in ("FL TIRE", "FR TIRE", "RL TIRE", "RR TIRE")
                     if menu.get(r) and not menu[r].lower().startswith("sin"))
        ruedas_s = (tiempos.get("FourTireChange") if ruedas > 2
                    else tiempos.get("TwoTireChange") if ruedas else 0) or 0

        nuevo_piloto = menu.get("DRIVER", "")
        cambia = bool(nuevo_piloto) and not _mismo_piloto(nuevo_piloto, piloto_ahora)
        reparar = menu.get("DAMAGE", "")
        repara = bool(reparar) and not reparar.lower().startswith("no")
        frenos = (menu.get("REPLACE BRAKES", "").lower() in ("si", "sí", "yes"))
        return {
            "parado": parado if isinstance(parado, (int, float)) else None,
            "piloto": cambia, "nuevo_piloto": nuevo_piloto,
            "piloto_s": tiempos.get("DriverChange", 0) if cambia else 0,
            "energia_s": energia_s,
            "energia_hasta": objetivo,
            "ruedas": ruedas, "ruedas_s": ruedas_s,
            "reparar": reparar if repara else "", "reparar_s":
                (tiempos.get("FixAllDamage", 0) if repara else 0),
            "frenos": frenos, "frenos_s": tiempos.get("BrakeChange", 0) if frenos else 0,
        }

    # --------------------------------------------------------- registro
    def _apuntar_menu(self):
        """
        Una linea cada vez que cambia lo marcado: asi se ve que tiempo da el
        juego para cada combinacion (cambio de piloto con y sin ruedas...).
        """
        menu = self.menu()
        parado = (self._d.get("pitStopLength") or {}).get("timeInSeconds")
        clave = (tuple(sorted((k, v) for k, v in menu.items()
                              if k in ("DRIVER", "VIRTUAL ENERGY", "TIRES", "FL TIRE",
                                       "FR TIRE", "RL TIRE", "RR TIRE", "DAMAGE",
                                       "REPLACE BRAKES"))),
                 # en segundos enteros: con decimas apuntaba una linea cada
                 # dos segundos solo porque la energia iba bajando
                 None if parado is None else int(round(parado)))
        if clave == self._ultimo_menu:
            return
        self._ultimo_menu = clave
        info = self._d.get("fuelInfo") or {}
        maximo = info.get("maxVirtualEnergy") or 0
        hay = (info.get("currentVirtualEnergy") or 0) / maximo if maximo else None
        self._escribir("boxes_menu", ["hora", "piloto", "energia_hay",
                                      "energia_hasta", "ruedas", "reparar",
                                      "frenos", "parado_segun_juego"],
                       [datetime.datetime.now().strftime("%H:%M:%S"),
                        menu.get("DRIVER", ""), _num(hay),
                        menu.get("VIRTUAL ENERGY", ""),
                        " ".join(menu.get(r, "") for r in ("FL TIRE", "FR TIRE",
                                                           "RL TIRE", "RR TIRE")),
                        menu.get("DAMAGE", ""), menu.get("REPLACE BRAKES", ""),
                        _num(parado)])

    def apuntar_parada(self, fila):
        """Una parada nuestra ya hecha: lo previsto contra lo real."""
        self._escribir("boxes_paradas", ["hora", "vuelta", "piloto", "cambio_piloto",
                                         "ruedas", "parado_previsto",
                                         "parado_real", "perdida_total"], fila)

    def _escribir(self, nombre, cabecera, fila):
        try:
            carpeta = rutas.datos("vueltas_carreras")
            os.makedirs(carpeta, exist_ok=True)
            archivo = os.path.join(carpeta, "%s_%s.csv" % (
                nombre, datetime.date.today().isoformat()))
            nuevo = not os.path.exists(archivo)
            with open(archivo, "a", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f, delimiter=";")
                if nuevo:
                    w.writerow(cabecera)
                w.writerow(fila)
        except Exception:
            pass


def _mismo_piloto(a, b):
    """'A Martos#4037' y 'Alberto Martos#4037' son el mismo: por la etiqueta o el apellido."""
    a, b = (a or "").strip(), (b or "").strip()
    if not a or not b:
        return True
    ea, eb = re.search(r"#\d+", a), re.search(r"#\d+", b)
    if ea and eb:
        return ea.group(0) == eb.group(0)
    apellido = lambda x: re.sub(r"#\d+$", "", x).split()[-1].lower() if x.split() else ""
    return apellido(a) == apellido(b)


def _num(x):
    return "" if x is None else ("%.2f" % x).replace(".", ",")


boxes = Boxes()
