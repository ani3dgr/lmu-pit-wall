# -*- coding: utf-8 -*-
"""
Vigila los discos de freno y avisa ANTES de que se rompan.

POR QUE EXISTE
En las 24 h de Le Mans del 24/10/2026 (BMW M4 GT3) el freno delantero
izquierdo dejo de frenar a las 14 h 20 de carrera. El coche se iba a la derecha
en cada frenada, se estrello dos veces, y el juego no dijo nada: ni un aviso ni
un color. Lo descubrio el companero viendo el disco a 21,9 grados con los
demas a 350. Esa misma noche les paso lo mismo a un Lexus (a las 14 h 30) y a
otro BMW (a las 15 h): es DESGASTE, no mala suerte. El servidor tenia las
averias mecanicas puestas, y con eso un disco gastado del todo deja de frenar.

DE DONDE SALE EL DATO
La memoria compartida no trae el desgaste de los frenos, solo la temperatura.
Pero la API web del propio juego (puerto 6397, la misma del clima) si lo da,
en `/rest/garage/UIScreen/RepairAndRefuel` -> `wearables.brakes`: el GROSOR
de cada disco en metros (del izq, del der, tras izq, tras der). Lo usa asi
TinyPedal, y de alli salen tambien los grosores a los que se rompen:

  - el disco se va gastando POCO A POCO, y el grosor baja vuelta a vuelta;
  - pero la rotura es DE GOLPE: al llegar al grosor de rotura el juego lo
    pone a CERO y ese freno deja de frenar. Ni se nota antes ni se va
    apagando: hasta ese momento frena bien;
  - el disco roto se va enfriando despues, poco a poco, hasta la temperatura
    del aire. Por eso el companero lo vio a 21,9 grados un buen rato despues.

  Grosores de rotura (los de TinyPedal, que salen de verlos romperse):
  GT3 / GTE unos 30 mm, Hypercar y LMP2 unos 25 mm. No es un numero fijo: cada
  marca tiene el suyo, y por eso aqui se APRENDE. Cada vez que un disco se
  rompe se apunta a que grosor lo hizo, y la proxima vez se usa ese.

LO QUE AVISA
  1. FRENO ROTO: el grosor de un disco cae a cero, o -si la API no contesta-
     un disco se queda frio frenando mientras el de su mismo eje quema.
  2. CAMBIAR FRENOS: con lo que se gasta por minuto de conduccion, cuando a
     algun disco le quedan menos minutos de los que se elijan en Opciones.

Con el disco nuevo no se puede predecir nada hasta llevar unos minutos
rodando: hace falta ver cuanto baja para saber a que ritmo.
"""
import json
import os
import threading
import time
import urllib.request

import lector_lmu as lmu
import rutas

URL = "http://127.0.0.1:6397/rest/garage/UIScreen/RepairAndRefuel"
CADA = 2.0                  # segundos entre preguntas a la API
ESPERA = 2.0                # lo que se espera a que conteste
APRENDIDOS = rutas.datos("frenos_rotura.json")
# Historia del grosor: una linea cada 30 s de conduccion. Para poder estudiar
# despues como se gasta cada coche (y a que grosor se rompio) sin haber tenido
# que estar grabando aparte.
REGISTRO = rutas.datos("frenos_registro.csv")
REGISTRO_MAX = 5 * 1024 * 1024

RUEDAS = ("del_izq", "del_der", "tras_izq", "tras_der")

# Grosor al que se rompe el disco, en milimetros, por categoria. Solo sirve
# para PREDECIR; el aviso de roto va aparte y no depende de esto.
ROTURA_MM = {"lmgt3": 30.0, "hypercar": 25.0, "lmp2": 25.0}
# El grosor de rotura no es exacto ni para la misma marca (el motor del juego
# le pone una variacion a cada disco), asi que la cuenta de minutos se hace
# contra medio milimetro por encima.
SEGURIDAD_MM = 0.5

VENTANA = 40 * 60           # minutos de conduccion con los que se mide el ritmo
MINIMO = 5 * 60             # sin esto rodado no se predice nada
CADA_MUESTRA = 30           # segundos de conduccion entre muestra y muestra

# Respaldo por temperatura: un disco frenando a menos del 40 % de la
# temperatura del de su mismo eje, con ese otro por encima de 150 grados.
FRIO_PROPORCION = 0.4
FRIO_MINIMO_C = 150.0
FRIO_SEGUNDOS = 3.0         # segundos de frenada fuerte asi para darlo por roto


# ------------------------------------------------------------------ la API
class Discos:
    """
    Pregunta a la API del juego por el grosor de los discos, en su hilo.

    Igual que el pronostico del clima: una peticion HTTP en el bucle del mapa
    lo congelaria, asi que va aparte y el mapa solo recoge lo ultimo que haya.
    Si el juego esta cerrado falla en silencio y lo vuelve a intentar.
    """

    def __init__(self):
        self._mm = None
        self._extra = {}
        self._sello = 0.0
        self._hilo = None
        self._fallos = 0

    def arrancar(self):
        if self._hilo is None:
            self._hilo = threading.Thread(target=self._bucle, daemon=True)
            self._hilo.start()

    def mm(self):
        """Grosor de los cuatro discos en mm, o None si no hay dato reciente."""
        self.arrancar()
        if self._mm is None or time.monotonic() - self._sello > 10.0:
            return None
        return list(self._mm)

    def extra(self):
        """
        Lo demas que trae la misma respuesta y tiene que ver con los frenos:
        lo que cuesta cambiarlos en boxes, si esta pedido el cambio en el menu
        de boxes y como estan los conductos. Vacio si no hay dato reciente.
        """
        if time.monotonic() - self._sello > 10.0:
            return {}
        return dict(self._extra)

    def _bucle(self):
        while True:
            try:
                pet = urllib.request.Request(URL, headers={"Accept": "application/json"})
                with urllib.request.urlopen(pet, timeout=ESPERA) as r:
                    crudo = r.read()
                # utf-8-sig: la API cuela el BOM delante del JSON
                d = json.loads(crudo.decode("utf-8-sig", "replace"))
                discos = leer_grosores(d)
                if discos is not None:
                    self._mm = discos
                    self._extra = leer_extra(d)
                    self._sello = time.monotonic()
                    self._fallos = 0
                else:
                    self._fallos += 1
            except Exception:
                # Juego cerrado, cargando o sin coche: nada que hacer salvo
                # volver a preguntar. Este hilo no puede morirse.
                self._fallos += 1
            time.sleep(CADA if self._fallos < 5 else CADA * 3)


def leer_grosores(d):
    """Los cuatro grosores en mm a partir de la respuesta de la API, o None."""
    try:
        valores = d["wearables"]["brakes"]
    except (KeyError, TypeError):
        return None
    if not isinstance(valores, list) or len(valores) < 4:
        return None
    try:
        return [float(v) * 1000.0 for v in valores[:4]]      # metros -> mm
    except (TypeError, ValueError):
        return None


def leer_extra(d):
    """
    Del menu de boxes y de los tiempos de parada, lo que toca a los frenos.

    Medido el 24/10/2026 con el Toyota en Le Mans, offline: el menu trae
    "REPLACE BRAKES" (No / Si), "F BRAKE DUCT" y "R BRAKE DUCT" (Abierto, 10 %,
    20 %...), y los tiempos de parada dicen BrakeChange = 120 s. Dos minutos
    parado: por eso cambiar frenos se piensa, no se pide por si acaso.
    """
    salida = {}
    try:
        salida["cambio_s"] = float(d["pitStopTimes"]["times"]["BrakeChange"])
    except (KeyError, TypeError, ValueError):
        pass
    try:
        menu = d["pitMenu"]["pitMenu"]
    except (KeyError, TypeError):
        menu = []
    for linea in menu if isinstance(menu, list) else []:
        if not isinstance(linea, dict):
            continue
        nombre = (linea.get("name") or "").strip().upper()
        actual = linea.get("currentSetting")
        opciones = linea.get("settings") or []
        texto = None
        if isinstance(actual, int) and 0 <= actual < len(opciones):
            texto = (opciones[actual] or {}).get("text")
        if nombre.startswith("REPLACE BRAKES"):
            salida["pedido"] = bool(actual)
        elif nombre.startswith("F BRAKE DUCT"):
            salida["conducto_del"] = texto
        elif nombre.startswith("R BRAKE DUCT"):
            salida["conducto_tras"] = texto
    return salida


discos = Discos()


# ------------------------------------------------------- lo aprendido
def _cargar_aprendidos():
    try:
        with open(APRENDIDOS, encoding="utf-8-sig") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _guardar_aprendido(clave, mm, coche):
    d = _cargar_aprendidos()
    d[clave] = {"mm": round(mm, 2), "coche": coche,
                "cuando": time.strftime("%Y-%m-%d %H:%M")}
    try:
        with open(APRENDIDOS, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def _apuntar(coche, conducido, mm, tele):
    try:
        nuevo = not os.path.isfile(REGISTRO)
        if not nuevo and os.path.getsize(REGISTRO) > REGISTRO_MAX:
            os.replace(REGISTRO, REGISTRO + ".viejo")
            nuevo = True
        temps = (tele or {}).get("frenos_c") or [0, 0, 0, 0]
        with open(REGISTRO, "a", encoding="utf-8") as f:
            if nuevo:
                f.write("fecha;coche;min_conducidos;mm_di;mm_dd;mm_ti;mm_td;"
                        "C_di;C_dd;C_ti;C_td\n")
            f.write("%s;%s;%.1f;%s;%s\n" % (
                time.strftime("%Y-%m-%d %H:%M:%S"), coche, conducido / 60.0,
                ";".join("%.4f" % v for v in mm),
                ";".join("%.0f" % v for v in temps)))
    except OSError:
        pass


def _clave(cual, rueda):
    """'Toyota GR010|del'. `cual` es el modelo del coche o, si no, la categoria."""
    return "%s|%s" % (cual or "?", "del" if rueda < 2 else "tras")


# ----------------------------------------------------------- el vigia
class Vigia:
    """
    Decide si hay que avisar. No pinta nada: devuelve que pasa y aviso_gui
    se encarga del cartel.

    `mirar` devuelve None (todo bien) o un dict:
        {"nivel": "roto", "rueda": 0}            freno roto
        {"nivel": "cambiar", "rueda": 0, "minutos": 42.0}
    """

    def __init__(self):
        self._reinicia()
        self.aprendidos = _cargar_aprendidos()

    def _reinicia(self):
        self.ultimo_mm = None          # lo que se leyo la vez anterior
        self.muestras = []             # (segundos conduciendo, [mm x4])
        self.conducido = 0.0           # segundos con el coche rodando
        self.ultima_muestra = -CADA_MUESTRA
        self.rotos = set()             # ruedas dadas por rotas
        self.rotos_temp = set()        # las que se dieron solo por temperatura
        self.frio = [0.0] * 4          # segundos de frenada con el disco frio
        self.ritmo = [None] * 4        # mm por segundo de conduccion
        self.nuevo = [0.0] * 4         # el grosor mas alto visto: el de nuevo
        self.reloj = None

    def rotura_mm(self, familia, rueda, coche=""):
        """
        A que grosor se rompe. Primero lo aprendido con ESTE modelo de coche
        (cada marca tiene el suyo); luego lo aprendido con otro de su categoria;
        y si no, la tabla de TinyPedal.
        """
        for cual in (coche, familia):
            if not cual:
                continue
            dato = self.aprendidos.get(_clave(cual, rueda))
            if isinstance(dato, dict) and isinstance(dato.get("mm"), (int, float)):
                return float(dato["mm"])
        return ROTURA_MM.get(familia)

    def mirar(self, mm, tele, familia, coche, en_boxes, conduzco, aviso_min):
        ahora = time.monotonic()
        dt = 0.0 if self.reloj is None else min(1.0, ahora - self.reloj)
        self.reloj = ahora
        rodando = bool(tele) and conduzco and not en_boxes and tele.get("kmh", 0) > 30

        if mm is not None:
            self._con_api(mm, familia, coche, en_boxes)
        if tele and conduzco:
            self._por_temperatura(tele, dt)

        if rodando:
            self.conducido += dt
        if mm is not None and rodando and self.conducido - self.ultima_muestra >= CADA_MUESTRA:
            self.ultima_muestra = self.conducido
            self.muestras.append((self.conducido, list(mm)))
            _apuntar(coche, self.conducido, mm, tele)
            while self.muestras and self.conducido - self.muestras[0][0] > VENTANA:
                self.muestras.pop(0)
            self._calcula_ritmo()

        self.coche = coche
        if self.rotos:
            return {"nivel": "roto", "rueda": min(self.rotos)}
        if mm is None:
            return None
        peor = None
        for r, f in enumerate(self.fichas(mm, familia)):
            if f is None or f["roto"] or f["limite"] is None:
                continue
            minutos = f["minutos"]
            # Poco margen es aviso aunque no haya ritmo medido todavia: con
            # el disco asi no se sale de boxes.
            if (minutos is not None and minutos < aviso_min) or f["margen"] < 0.5:
                if peor is None or (minutos or 0) < (peor["minutos"] or 0):
                    peor = {"nivel": "cambiar", "rueda": r, "minutos": minutos}
        return peor

    def fichas(self, mm, familia, vuelta_s=0.0):
        """
        Como esta cada disco, para el panel. Una ficha por rueda:
            mm        grosor ahora
            nuevo     el grosor mas alto visto (el de discos nuevos)
            limite    grosor al que se rompe (None si no se sabe)
            margen    mm que quedan hasta el limite, con la seguridad quitada
            fraccion  de 1 (nuevo) a 0 (en el limite), para la barra
            ritmo_h   mm que se gastan por hora de conduccion
            minutos   lo que le queda, o None si aun no hay ritmo
            vueltas   lo mismo en vueltas, si se sabe lo que dura una
            roto      si esta roto
        """
        if mm is None:
            return [None] * 4
        salida = []
        for r in range(4):
            limite = self.rotura_mm(familia, r, getattr(self, "coche", ""))
            roto = r in self.rotos or (mm[r] <= 0 and any(v > 0 for v in mm))
            margen = fraccion = minutos = vueltas = None
            if limite is not None and mm[r] > 0:
                margen = mm[r] - limite - SEGURIDAD_MM
                total = max(0.1, self.nuevo[r] - limite - SEGURIDAD_MM)
                fraccion = max(0.0, min(1.0, margen / total))
                if self.ritmo[r]:          # ni None ni cero
                    minutos = max(0.0, margen) / self.ritmo[r] / 60.0
                    if vuelta_s and vuelta_s > 0:
                        vueltas = minutos * 60.0 / vuelta_s
            salida.append({
                "mm": mm[r], "nuevo": self.nuevo[r], "limite": limite,
                "margen": margen if margen is not None else 99.0,
                "fraccion": fraccion, "minutos": minutos, "vueltas": vueltas,
                "ritmo_h": None if self.ritmo[r] is None else self.ritmo[r] * 3600.0,
                "roto": roto,
            })
        return salida

    def _con_api(self, mm, familia, coche, en_boxes):
        antes = self.ultimo_mm
        self.ultimo_mm = list(mm)
        self.nuevo = [max(a, b) for a, b in zip(self.nuevo, mm)]
        if antes is None:
            return
        # Discos nuevos: el grosor SUBE. Se empieza de cero.
        if any(mm[r] > antes[r] + 1.0 for r in range(4) if antes[r] > 0):
            print("[frenos] discos cambiados: %s mm"
                  % " / ".join("%.1f" % v for v in mm))
            self._reinicia()
            self.ultimo_mm = list(mm)
            self.nuevo = list(mm)
            return
        # Si los cuatro estan a cero no es una rotura, es que no hay coche.
        if not any(v > 0 for v in mm):
            return
        for r in range(4):
            if antes[r] > 0 and mm[r] <= 0 and r not in self.rotos:
                self.rotos.add(r)
                print("[frenos] ROTO %s a %.2f mm (%s %s)"
                      % (RUEDAS[r], antes[r], familia, coche))
                # Se apunta el grosor al que se rompio para predecir la
                # proxima vez con el de esta marca y no con el de la tabla.
                # Se guarda con el MODELO del coche, y tambien con la
                # categoria para que sirva de referencia a los demas coches de
                # esa categoria que aun no se hayan roto nunca.
                if not en_boxes:
                    if coche:
                        _guardar_aprendido(_clave(coche, r), antes[r], coche)
                    clave_cat = _clave(familia, r)
                    if clave_cat not in self.aprendidos:
                        _guardar_aprendido(clave_cat, antes[r], coche)
                    self.aprendidos = _cargar_aprendidos()

    def _por_temperatura(self, tele, dt):
        """
        El respaldo: un disco que no calienta frenando fuerte esta roto.

        Se compara con el de SU MISMO EJE y en proporcion, no con un numero
        fijo: con lluvia o de noche todos los discos van mas frios, pero van
        frios todos a la vez.
        """
        temps = tele.get("frenos_c")
        if not temps or len(temps) < 4:
            return
        frenando = tele.get("pedal_freno", 0) > 0.4 and tele.get("kmh", 0) > 80
        if not frenando:
            return
        for r in range(4):
            pareja = r ^ 1                  # 0<->1 delante, 2<->3 detras
            otro, este = temps[pareja], temps[r]
            if otro > FRIO_MINIMO_C and este < otro * FRIO_PROPORCION:
                self.frio[r] += dt
                if self.frio[r] >= FRIO_SEGUNDOS and r not in self.rotos:
                    self.rotos.add(r)
                    self.rotos_temp.add(r)
                    print("[frenos] ROTO %s por temperatura (%.0f C contra %.0f C)"
                          % (RUEDAS[r], este, otro))
            elif este > otro * 0.7:
                self.frio[r] = max(0.0, self.frio[r] - dt)
                # Si se dio por roto SOLO por la temperatura y vuelve a
                # calentar como su pareja, era una falsa alarma: se retira.
                # Lo que dijo la API (grosor a cero) no se retira asi.
                if self.frio[r] == 0.0 and r in self.rotos_temp:
                    self.rotos.discard(r)
                    self.rotos_temp.discard(r)

    def _calcula_ritmo(self):
        if len(self.muestras) < 2:
            return
        (t0, mm0), (t1, mm1) = self.muestras[0], self.muestras[-1]
        if t1 - t0 < MINIMO:
            return
        # Ritmo CERO no es lo mismo que no saberlo: con las averias mecanicas
        # apagadas en el servidor los discos NO SE GASTAN (medido el
        # 24/10/2026: 34,0000 mm clavados toda una clasificacion con
        # MechFailRate=0, y bajando en unos libres con MechFailRate=1).
        for r in range(4):
            gastado = mm0[r] - mm1[r]
            self.ritmo[r] = gastado / (t1 - t0) if gastado > 0 else 0.0


def familia_de(coche):
    return lmu.familia((coche or {}).get("clase") or "")
