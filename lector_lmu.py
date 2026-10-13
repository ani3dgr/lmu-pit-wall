# -*- coding: utf-8 -*-
"""
Lectura del buffer de scoring de LMU (posiciones de todos los coches en pista).

Reutiliza la base ya calibrada en ingeniero_ia.py:
    SCO_BASE = 560, SCO_STRIDE = 584, numVehicles en offset 116, trackName en 12.

Lo que NO estaba calibrado (posicion X/Z, quien es el jugador, clase del coche)
se autodetecta comparando contra el trazado real del circuito: solo hay un sitio
del buffer que coloca a TODOS los coches encima de la pista.
"""
import ctypes
import json
import math
import os
import re
import struct
import time

import rutas

CARPETA = rutas.carpeta()

SCO_MAP = "$rFactor2SMMP_Scoring$"
SCO_BASE = 560          # primer coche
SCO_STRIDE = 584        # bytes por coche

# LMU publica ADEMAS su propia memoria compartida, aparte de la del plugin de
# rFactor, documentada en Support/SharedMemoryInterface/. Trae una cosa que la
# otra no: el juego dice EL MISMO cual de los coches es el del jugador, sin que
# haya que deducirlo de la marca ni del nombre del piloto.
LMU_MAP = "LMU_Data"
LMU_AVISOS = 0                              # lista de los ultimos avisos del
LMU_AVISOS_N = 16                           # juego; 16 = hueco vacio
AVISO_UNLOAD = 5                            # ha descargado el circuito
LMU_SCORING = 1632                          # el bloque de scoring (mTrackName)
LMU_VEHICULOS = LMU_SCORING + 560           # la lista de coches
LMU_MAX_VEH = 104                           # plazas que reserva el juego
LMU_STREAM = 65536                          # el texto de resultados que va detras
# SharedMemoryTelemetryData: activeVehicles, playerVehicleIdx, playerHasVehicle
LMU_TELE = LMU_VEHICULOS + LMU_MAX_VEH * SCO_STRIDE + LMU_STREAM
LMU_TELE_FICHAS = LMU_TELE + 4              # telemInfo[0], que empieza por su mID
LMU_TELE_STRIDE = 1888                      # bytes por coche en la telemetria
# Dentro de la ficha de TELEMETRIA (la de 1888 bytes de LMU_Data), calculados
# del InternalsPlugin.hpp con pack(4). Comprobados: la struct suma 1888 justos
# y mRearBrakeBias cae en 664, que ya estaba verificado en pista.
TEL_ET = 12             # mElapsedTime
TEL_VEL = 184           # mLocalVel (3 dobles)
TEL_ACC = 208           # mLocalAccel: +x al lado izquierdo, +y arriba, +z atras
TEL_FUEL = 524          # litros
TEL_RUEDA0 = 848        # primera rueda; orden del/izq, del/der, tras/izq, tras/der
TEL_RUEDA_STRIDE = 260
TEL_SUSPF = 16          # mSuspForce, en newtons: la carga de esa esquina
TEL_CARGA = 104         # mTireLoad. NO USAR: LMU lo deja a cero casi siempre

OFF_TRACK = 12          # nombre del circuito (64 bytes)
OFF_NUMVEH = 116        # numero de coches (int)
OFF_JUGADOR = 128       # mPlayerName en la cabecera: tu nombre de piloto
OFF_SESION = 76         # mSession: 0 = sin empezar, 1-4 practicas,
                        # 5-8 clasificacion, 9 warmup, 10-13 carrera
OFF_ID = 0              # mID: numero propio de cada coche en esta sesion. Va
                        # con el COCHE, no con el piloto ni con la decoracion,
                        # asi que aguanta un cambio de piloto en un relevo.
                        # OJO: no es el dorsal. El dorsal de verdad (el de la
                        # pantalla de tiempos) NO esta en este buffer: el
                        # '#397' de mVehicleName es el numero de la plantilla
                        # 'Custom Team' y lo llevan todos los coches iguales.
OFF_NOMBRE = 4          # driverName dentro de la ficha del coche (32 bytes)
OFF_VEHICULO = 36       # mVehicleName: "Heart of Racing Team 2026 #23:WEC"
OFF_CODIGO = 544        # mVehFilename: codigo interno del coche, "91_26_MANT..."
                        # Lleva el ano dentro, asi que cambia cada temporada:
                        # sirve de referencia, no como identificador estable.

# Verificados en pista el 23/08/2026 (Silverstone, 18 coches). Coinciden con el
# header oficial de Studio 397 salvo la posicion, que en el buffer del plugin
# cae 8 bytes antes de lo que dice el struct (por eso el stride es 584 y no 592).
OFF_POS = 264           # posicion en el mundo: 3 dobles X, Y, Z
OFF_YO = 196            # mIsPlayer: vale 1 solo en el coche del jugador
OFF_PUESTO = 199        # mPlace: puesto en carrera, 1..N
OFF_CLASE = 200         # mVehicleClass: texto (Hypercar / LMP2 / LMGT3)
OFF_VUELTAS = 100       # mTotalLaps: vueltas completadas (short)
OFF_DIST = 104          # mLapDist: metros recorridos en la vuelta actual
OFF_LATERAL = 112       # mPathLateral: separacion del centro de la pista (m)
OFF_BORDE = 120         # mTrackEdge: donde queda el borde POR ESE LADO. Viene
                        # con signo, del mismo lado que el coche, asi que para
                        # saber si esta fuera hay que comparar valores absolutos
OFF_MEJOR = 144         # mBestLapTime: mejor vuelta en segundos
OFF_ULTIMA = 168        # mLastLapTime: ultima vuelta cerrada, en segundos
OFF_SEC1 = 152          # mLastSector1: sector 1 de la ultima vuelta
OFF_SEC2 = 160          # mLastSector2: sectores 1+2 de la ultima vuelta
OFF_BOXES = 198         # mInPits: 1 si esta en la calle de boxes
OFF_FASE = 459          # mIndividualPhase: 5 = verde, 10 = bajo amarilla,
                        # 11 = bajo azul. Es lo que avisa de que hay amarilla.
OFF_BANDERA = 504       # mFlag: 0 = verde, 6 = azul (le estan doblando)
OFF_PENAS = 194         # mNumPenalties: sanciones pendientes (short). En
                        # CARRERA el juego no anula la vuelta, sanciona, asi
                        # que este es el aviso que cuenta ahi.
OFF_VALIDA = 506        # mCountLapFlag: veredicto del JUEGO sobre la vuelta.
                        # 2 = cuenta vuelta y tiempo (todo en orden)
                        # 1 = cuenta la vuelta pero no el tiempo
                        # 0 = no cuenta ninguna de las dos
                        # Baja de 2 en cuanto el juego invalida por salirse.

# ---------------- el clima, en la cabecera del buffer ----------------
#
# Calculados del `InternalsPlugin.hpp` del propio juego con pack(4), contando
# desde el principio de ScoringInfoV01 (que empieza en el byte 12) y
# COMPROBADOS en pista el 12/09/2026 en Barcelona: la temperatura del aire
# (20,02) y la del asfalto (37,55) salieron clavadas a lo que decia en ese
# mismo instante la API web del juego, y el reloj del dia dio la hora real de
# la sesion. Que el ultimo campo del bloque (mVehicle) caiga justo en el byte
# 560, donde empieza el primer coche, confirma que toda la cuenta cuadra.
#
# Los cinco ultimos son ANADIDOS DE LMU: no estan en el rFactor 2 original, el
# juego los mete donde aquel dejaba sitio de reserva. Y son justo los mas
# utiles: el estado del cielo con un numero y la hora del dia.
OFF_T_AIRE = 240        # mAmbientTemp: grados del aire
OFF_T_ASFALTO = 248     # mTrackTemp: grados del asfalto
OFF_LLUVIA = 232        # mRaining: cuanto llueve AHORA, de 0 a 1
OFF_NUBES = 224         # mDarkCloud: lo oscuro que esta el cielo, de 0 a 1
OFF_VIENTO = 256        # mWind: 3 dobles, metros por segundo
OFF_MOJADO_MIN = 280    # mMinPathWetness: lo menos mojado de la trazada
OFF_MOJADO_MAX = 288    # mMaxPathWetness: lo mas mojado de la trazada
OFF_MOJADO_MED = 344    # mAvgPathWetness: la media (anadido de LMU)
OFF_HORA_DIA = 356      # mTimeOfDay: segundos desde medianoche (float). Con
                        # esto se sabe si es de noche sin adivinar nada
OFF_AGARRE = 361        # mTrackGripLevel: 0 baja, 1 media, 2 alta, 3 optima
OFF_CIELO = 362         # mCloudCoverage: el estado del cielo, 0..10, con los
                        # mismos numeros que el pronostico de la API web
OFF_ET = 80             # mCurrentET: segundos de sesion transcurridos
OFF_FIN_ET = 88         # mEndET: segundos de sesion en los que se acaba

MAX_COCHES = 128

# ---------------- acceso a memoria compartida ----------------
_k32 = ctypes.windll.kernel32
_k32.OpenFileMappingW.restype = ctypes.c_void_p
_k32.OpenFileMappingW.argtypes = (ctypes.c_uint32, ctypes.c_int, ctypes.c_wchar_p)
_k32.MapViewOfFile.restype = ctypes.c_void_p
_k32.MapViewOfFile.argtypes = (ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32,
                               ctypes.c_uint32, ctypes.c_size_t)
_FILE_MAP_READ = 0x0004


def abrir(nombre):
    """Abre el mapa del juego SOLO si existe (nunca crea uno falso)."""
    h = _k32.OpenFileMappingW(_FILE_MAP_READ, False, nombre)
    if not h:
        raise OSError("no existe el mapa %s (juego cerrado o plugin desactivado)" % nombre)
    ptr = _k32.MapViewOfFile(h, _FILE_MAP_READ, 0, 0, 0)
    if not ptr:
        _k32.CloseHandle(h)
        raise OSError("no se pudo mapear %s" % nombre)
    return ptr


def d(base, off):
    return struct.unpack("<d", ctypes.string_at(base + off, 8))[0]


def i4(base, off):
    return struct.unpack("<i", ctypes.string_at(base + off, 4))[0]


def i2(base, off):
    return struct.unpack("<h", ctypes.string_at(base + off, 2))[0]


def u1(base, off):
    return ctypes.string_at(base + off, 1)[0]


def f4(base, off):
    """Un float de 4 bytes. LMU usa estos para la hora del dia y el reloj."""
    return struct.unpack("<f", ctypes.string_at(base + off, 4))[0]


def txt(base, off, n):
    """
    Texto del buffer. Los nombres de piloto llevan acentos (Francois Heriau,
    Jose Maria Lopez): se prueba UTF-8 y se cae a latin-1 si no cuadra.
    """
    crudo = ctypes.string_at(base + off, n).split(b"\x00")[0]
    try:
        return crudo.decode("utf-8")
    except UnicodeDecodeError:
        return crudo.decode("latin-1", "replace")


def normaliza(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


# LMU no siempre llama a las clases igual que nosotros: en Silverstone reporta
# "GT3" a secas, no "LMGT3". Por eso cada categoria acepta varios nombres. La
# tabla vive aqui porque la usan el mapa (para el color), el comparador y el
# grabador (para no medirte contra una categoria que no es la tuya).
ALIAS_CLASE = {
    "hypercar": ("hypercar", "hyper", "lmh", "lmdh", "gtp"),
    "lmp2": ("lmp2", "p2"),
    "lmgt3": ("lmgt3", "gt3", "gte"),
}


def familia(clase):
    """
    La categoria de un coche con el nombre unificado.

    Devuelve "" si el juego no da la clase; entonces quien llame tiene que
    seguir como antes, sin distinguir categorias, en vez de quedarse sin
    referencia.
    """
    n = normaliza(clase or "")
    if not n:
        return ""
    for familia_, alias in ALIAS_CLASE.items():
        if any(a in n for a in alias):
            return familia_
    return n


# ---------------- circuitos ----------------
def cargar_circuitos(recargar=False):
    """Los circuitos medidos. Cada uno vive en su propio archivo, dentro de
    la carpeta 'circuitos', para poder compartirlos sueltos."""
    import circuitos
    return circuitos.cargar(recargar)


def base_de(clave):
    """
    'algarveinternationalcircuit__4635' -> 'algarveinternationalcircuit'.

    Cuando dos trazados se llaman igual, el segundo se guarda con su largo
    pegado detras para poder tener los dos a la vez. Esto quita ese sufijo
    para poder compararlos por el nombre.
    """
    return (clave or "").split("__")[0]


def buscar_circuito(circuitos, nombre_juego, largo_juego=None):
    """
    Empareja el circuito del juego con uno de los trazados guardados.

    POR QUE HACE FALTA EL LARGO
    Hay circuitos con dos trazados a los que el juego llama IGUAL. Portimao
    publica "Algarve International Circuit" tanto en su version normal como
    en la de ELMS, asi que por el nombre es imposible saber cual se esta
    corriendo. Silverstone si lo dice ("- WEC", "- ELMS"), pero no se puede
    contar con ello.

    La solucion no es avisar de que algo no cuadra y dejar que se apane
    quien lo use: es tener los dos medidos y coger el que toca. Cuando hay
    varios candidatos con el mismo nombre, gana el que mida lo mismo que el
    circuito de ahora.
    """
    n = normaliza(nombre_juego)
    if not n:
        return None, None

    # todos los que casan por nombre, sin mirar el sufijo del largo
    candidatos = [c for c in circuitos
                  if base_de(c) == n or n in base_de(c) or base_de(c) in n]
    if not candidatos:
        return None, None
    if len(candidatos) == 1:
        return candidatos[0], circuitos[candidatos[0]]

    # Varios. Si sabemos cuanto mide el de ahora, gana el que mas se le
    # parezca: eso es lo que separa una variante de otra.
    if largo_juego:
        medidos = sorted((abs(circuitos[c]["largo"] - largo_juego), c)
                         for c in candidatos if circuitos[c].get("largo"))
        if medidos:
            return medidos[0][1], circuitos[medidos[0][1]]

    # Sin largos con los que comparar se hace como siempre: gana el nombre
    # mas largo, que es el mas concreto.
    mejor = max(candidatos, key=len)
    return mejor, circuitos[mejor]


# ---------------- autocalibracion ----------------
MARGEN_XZ = 150.0     # m que un coche puede estar fuera del trazado (boxes, escapatorias)
MARGEN_Y = 30.0       # m fuera del rango de altura conocido del circuito
SALTO_MAX = 250.0     # m maximos que puede recorrer un coche entre dos lecturas
DISPERSION_MIN = 25.0  # m que como minimo separan al primer coche del ultimo
FUERA_MAX = 0.20      # proporcion de coches a los que se les permite estar fuera
                      # del trazado: los del garaje y los que se desconectan


def _dist_al_trazado(x, z, puntos):
    return min(math.hypot(x - px, z - pz) for px, pz in puntos)


def muestra(sco, off, n_coches):
    """Lee la terna (X,Y,Z) de ese offset para todos los coches."""
    salida = []
    for v in range(n_coches):
        b = SCO_BASE + v * SCO_STRIDE
        salida.append((d(sco, b + off), d(sco, b + off + 8), d(sco, b + off + 16)))
    return salida


def _evaluar(ternas, puntos, altura):
    """
    Devuelve (desvio maximo al trazado, dispersion entre coches) si la muestra
    puede ser posiciones de coches, o None si no lo es.

    **No se exige que TODOS los coches esten sobre el trazado, y es a
    proposito.** Antes bastaba con uno fuera para tumbar el offset entero, y
    siempre hay alguno: el garaje de Daytona queda a 165 m de la pista, y ahi
    hay coches parados toda la sesion; los que se desconectan tambien se
    quedan tirados en cualquier parte.

    Medido el 30/08/2026 en Daytona, 62 coches: dos en el garaje (151 y 165 m)
    hacian que el offset bueno -el 264 de siempre- se descartara, y la busqueda
    a ciegas se quedaba entonces con otro que no eran posiciones. El mapa
    dibujaba la carrera entera mal y no habia forma de enterarse.

    Asi que se pide que la GRAN MAYORIA encaje y se mide el desvio solo con
    esos. Los coches sueltos ya no pueden con la calibracion, pero una zona de
    ceros o de velocidades sigue sin colar: para eso estan la altura, la
    distancia al trazado y, sobre todo, la dispersion.
    """
    ymin, ymax = altura
    dentro = []
    fuera = 0
    permitidos = max(1, int(len(ternas) * FUERA_MAX))
    for x, y, z in ternas:
        if (not (math.isfinite(x) and math.isfinite(y) and math.isfinite(z))
                or not (ymin - MARGEN_Y <= y <= ymax + MARGEN_Y)
                or _dist_al_trazado(x, z, puntos) > MARGEN_XZ):
            fuera += 1
            if fuera > permitidos:
                return None
            continue
        dentro.append((x, y, z))

    if not dentro:
        return None
    peor = max(_dist_al_trazado(x, z, puntos) for x, y, z in dentro)
    xs = [t[0] for t in dentro]
    zs = [t[2] for t in dentro]
    return peor, math.hypot(max(xs) - min(xs), max(zs) - min(zs))


def calibrar(sco, datos, n_coches, verboso=False):
    """
    Encuentra el offset de la posicion (X,Y,Z) dentro de la ficha de cada coche.

    No basta con que los valores caigan sobre el trazado: hay huecos del buffer
    (velocidades, aceleraciones) que valen casi cero, y el punto (0,0) del mundo
    suele quedar pegado al circuito, asi que colarian con todos los coches
    amontonados en el centro del mapa. Por eso se exige ademas altura coherente,
    que siga siendo valido en una segunda lectura y que nadie se teletransporte.

    Devuelve (offset_pos, informe) u (None, informe).
    """
    puntos, altura = datos["puntos"], datos["altura"]

    # Camino rapido: el offset ya verificado en pista. Se comprueba igualmente,
    # por si una actualizacion del juego moviera el campo de sitio.
    try:
        r = _evaluar(muestra(sco, OFF_POS, n_coches), puntos, altura)
    except (struct.error, OSError):
        r = None
    if r is not None:
        return OFF_POS, "offset posicion = %d (el conocido; desvio max %.1f m, coches separados %.0f m)" % (
            OFF_POS, r[0], r[1])

    # Busqueda completa solo si el conocido ya no vale.
    candidatos = []
    for off in range(0, SCO_STRIDE - 24, 8):
        try:
            r = _evaluar(muestra(sco, off, n_coches), puntos, altura)
        except (struct.error, OSError):
            continue
        if r is None:
            continue
        peor, dispersion = r
        if n_coches >= 3 and dispersion < DISPERSION_MIN:
            continue          # coches amontonados: es una zona de ceros, no posiciones
        candidatos.append((dispersion, off, peor))

    if not candidatos:
        # Si el trazado guardado esta mal (un escaneo torcido, por ejemplo) la
        # comprobacion falla aunque el offset sea correcto. Antes se devolvia
        # None y el mapa se quedaba en "Calibrando..." para siempre. Es mejor
        # tirar con el offset verificado: como mucho se vera el circuito raro,
        # pero los coches saldran en su sitio relativo.
        return OFF_POS, ("el trazado guardado no cuadra con las posiciones; "
                         "se usa el offset conocido (%d). Merece la pena "
                         "reescanear este circuito." % OFF_POS)

    # El criterio que de verdad separa el grano de la paja es la DISPERSION:
    # los coches de verdad estan repartidos por el circuito (cientos de metros),
    # mientras que las zonas de ceros y los tiempos de vuelta se quedan en unas
    # pocas decenas. En pista la diferencia es de un orden de magnitud.
    # Si el de siempre esta entre los que encajan, es el de siempre: entre dos
    # candidatos parecidos, el verificado en pista gana a uno que ha salido de
    # una busqueda. Asi la calibracion no baila de una sesion a otra.
    candidatos.sort(reverse=True)
    conocido = [c for c in candidatos if c[1] == OFF_POS]
    dispersion, off, peor = conocido[0] if conocido else candidatos[0]
    informe = "offset posicion = %d (desvio max %.1f m, coches separados %.0f m, %d candidatos)" % (
        off, peor, dispersion, len(candidatos))
    if verboso:
        informe += "\n  descartados: " + ", ".join(
            "%d (%.0fm)" % (o, disp) for disp, o, _ in candidatos[1:6])
    return off, informe


def _solo_uno(sco, off, n_coches):
    """Cierto si en ese byte exactamente un coche vale 1 y el resto 0."""
    try:
        vals = [u1(sco, SCO_BASE + v * SCO_STRIDE + off) for v in range(n_coches)]
    except OSError:
        return False
    return sorted(vals) == [0] * (n_coches - 1) + [1]


def buscar_jugador(sco, n_coches):
    """
    Offset del byte que marca al coche del jugador: SIEMPRE el verificado, 196.

    Antes, si el 196 no cumplia -exactamente un coche a 1-, se buscaba a ciegas
    el primer byte de la ficha que tuviera esa pinta. **Eso costo la carrera de
    6 h de Silverstone del 29/08/2026.** Manuel entro de ESPECTADOR: ahi no hay
    ningun coche marcado, asi que la busqueda a ciegas se quedo con un byte
    cualquiera de los muchos que valen 1 en un solo coche a ratos (mInPits, por
    ejemplo), el mapa se engancho a un BMW M4 de otro equipo y siguio con el
    las seis horas, grabando sus vueltas como si fueran las de Manuel.

    Y no se corregia nunca, porque el offset malo se calibra UNA vez al entrar
    al circuito y ya se queda.

    Adivinar en silencio sale mucho mas caro que no saberlo. Si el 196 no marca
    a nadie -espectador, relevo, sala online rara- ahora simplemente no hay
    marca: el mapa lo dice en pantalla y el coche se elige a mano.
    """
    return OFF_YO


def calibrar_jugador(sco, n_coches):
    """Todos los offsets que cumplen la condicion. Solo para diagnostico."""
    validos = []
    for off in range(0, SCO_STRIDE):
        try:
            vals = [u1(sco, SCO_BASE + v * SCO_STRIDE + off) for v in range(n_coches)]
        except OSError:
            continue
        if sorted(vals) == [0] * (n_coches - 1) + [1]:
            validos.append(off)
    return validos


def calibrar_clase(sco, n_coches):
    """Busca el campo de texto con la clase del coche (Hypercar / LMP2 / LMGT3...)."""
    CLASES = ("hyper", "lmp", "lmgt", "gte", "gt3", "gtp")

    def vale(off):
        try:
            vals = [txt(sco, SCO_BASE + v * SCO_STRIDE + off, 32) for v in range(n_coches)]
        except OSError:
            return False
        # el texto tiene que EMPEZAR donde empieza el campo: un offset una
        # posicion antes tambien contendria la palabra, precedida de basura
        if not all(v[:1].isalpha() for v in vals):
            return False
        # mVehicleName (36) tambien puede cumplirlo ("BMW GT3 Custom Team
        # 2026 #397") y entonces cada modelo era una "clase": el 13/10/2026 en
        # Paul Ricard el mapa daba a Manuel el puesto contando solo los coches
        # con "GT3" en el modelo (11) en vez del de su clase (17). Una clase de
        # verdad no lleva dorsal.
        if any("#" in v for v in vals):
            return False
        return all(any(c in v.lower() for c in CLASES) for v in vals)

    # primero el verificado en pista; buscar solo si el juego lo hubiera movido
    if vale(OFF_CLASE):
        return OFF_CLASE
    for off in range(0, SCO_STRIDE - 8):
        if vale(off):
            return off
    return None


REGISTRO = "registro.txt"
REGISTRO_MAX = 200 * 1024


def apuntar(texto):
    """
    Deja por escrito, con su hora, algo que el mapa ha decidido solo.

    El mapa corre sin consola: cuando algo sale raro no queda ni rastro de por
    que eligio lo que eligio. Despues de las 6 h de Silverstone (29/08/2026)
    hubo que deducir a que coche habia estado siguiendo a partir de los
    resultados del juego. Aqui van las dos decisiones que pueden estropear una
    sesion entera sin que se note: que coche eres tu y donde estan las
    posiciones dentro del buffer.
    """
    try:
        ruta = os.path.join(CARPETA, REGISTRO)
        if os.path.isfile(ruta) and os.path.getsize(ruta) > REGISTRO_MAX:
            os.remove(ruta)
        with open(ruta, "a", encoding="utf-8") as f:
            f.write("%s  %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), texto))
    except OSError:
        pass


# ---------------- lectura en vivo ----------------
class Scoring:
    def __init__(self):
        self.sco = abrir(SCO_MAP)
        # Si no estuviera -otra version del juego- el mapa sigue funcionando
        # como antes: es una ayuda, no un requisito. Se abre en `_lmu()`, que
        # lo reintenta, y NO aqui de una vez: ver el porque alli.
        self.lmu = None
        self._reintento_lmu = 0.0
        self._lmu()
        self.off_pos = None            # se confirma contra el trazado al entrar
        self.off_jugador = OFF_YO      # verificados en pista; la autodeteccion
        self.off_clase = OFF_CLASE     # solo hace falta si el juego los mueve
        self.id_yo = None              # tu coche, una vez fijado. Lo borra el
                                       # mapa al empezar otra sesion.
        self.fijado = None             # mID elegido A MANO por el usuario.
                                       # Manda por encima de todo lo demas.
        self.origen_yo = None          # de donde salio la eleccion: "manual",
                                       # "juego", "marca", "nombre" o None
        self.yo_fiable = False         # si la eleccion viene de una fuente que
                                       # NO adivina. Con False el mapa avisa y
                                       # no graba vueltas como tuyas.
        self._apunte = None            # ultimo apunte escrito, para no repetir

    def _lmu(self):
        """
        La memoria propia del juego (`LMU_Data`), abriendola cuando aparezca.

        NO se abre una sola vez al arrancar, y esto es un arreglo, no un
        capricho. El juego publica DOS memorias: el scoring, que es la de
        rFactor 2 y aparece pronto, y `LMU_Data`, que es suya y aparece
        despues. El mapa se engancha en cuanto ve el scoring, y si en ese
        instante `LMU_Data` todavia no estaba, antes se quedaba a None PARA
        SIEMPRE: la bola de fuerzas G no se movia del centro y el reparto de
        peso salia vacio durante toda la sesion, aunque el juego llevara
        media hora abierto. Habia que cerrar el mapa y volver a abrirlo.

        Se reintenta cada dos segundos, que es de sobra: abrir un mapa que no
        existe cuesta muy poco, pero hacerlo veinte veces por segundo seria
        tirar tiempo en el bucle del mapa.
        """
        if self.lmu is None and time.monotonic() >= self._reintento_lmu:
            self._reintento_lmu = time.monotonic() + 2.0
            try:
                self.lmu = abrir(LMU_MAP)
            except OSError:
                self.lmu = None
        return self.lmu

    def telemetria(self):
        """
        Lo que le esta pasando a TU coche ahora mismo: las G y el peso que
        lleva cada rueda. None si el juego no dice cual es tu coche.

        Sale de la ficha de telemetria de `LMU_Data` (1888 bytes por coche).
        Los offsets estan calculados del `InternalsPlugin.hpp` del propio
        juego con `pack(4)`, y cuadran por dos sitios: la ficha entera suma
        exactamente 1888 bytes y el reparto de frenada cae en el 664, que ya
        estaba verificado en pista.

        **Las cargas salen de `mSuspForce` y no de `mTireLoad`.** Medido el
        30/08/2026 en Daytona (24 minutos de sesion, 16.081 muestras):
        `mTireLoad` vale cero el 97 % del tiempo -solo se rellena unos
        segundos al cargar el coche- y en esos pocos instantes vale EXACTAMENTE
        lo mismo que `mSuspForce`. Asi que `mSuspForce` es la carga vertical de
        la esquina, comparable entre el eje delantero y el trasero, y ademas es
        la que esta siempre.
        """
        if self._lmu() is None:
            return None
        try:
            if not u1(self.lmu, LMU_TELE + 2):        # playerHasVehicle
                return None
            cual = u1(self.lmu, LMU_TELE + 1)
            activos = u1(self.lmu, LMU_TELE)
            if not 0 <= cual < min(activos, LMU_MAX_VEH):
                return None
            b = LMU_TELE_FICHAS + cual * LMU_TELE_STRIDE
            cargas = [d(self.lmu, b + TEL_RUEDA0 + r * TEL_RUEDA_STRIDE + TEL_SUSPF)
                      for r in range(4)]
            return {
                "id": i4(self.lmu, b),
                "reloj": d(self.lmu, b + TEL_ET),
                # +x sale por el lado IZQUIERDO del coche y +z por DETRAS (lo
                # dice el header y se confirmo con los datos: frenando a tope
                # el eje z se va a +3 G, y girando a izquierdas el peso se
                # marcha a la derecha).
                "g_lateral": d(self.lmu, b + TEL_ACC) / 9.81,
                "g_larga": d(self.lmu, b + TEL_ACC + 16) / 9.81,
                "kmh": math.sqrt(sum(d(self.lmu, b + TEL_VEL + 8 * i) ** 2
                                     for i in range(3))) * 3.6,
                "cargas": cargas,          # del izq, del der, tras izq, tras der
                "combustible": d(self.lmu, b + TEL_FUEL),
            }
        except (OSError, struct.error, ValueError):
            return None

    def fijar_coche(self, mid):
        """
        El usuario dice cual es su coche. `None` vuelve a automatico.

        Existe porque hay salas donde el juego no dice de quien eres -entrar de
        espectador a una carrera por equipos, sobre todo- y ahi antes el mapa
        se lo inventaba. Ahora, si no lo sabe, lo pregunta.
        """
        self.fijado = mid
        self.id_yo = mid
        self.origen_yo = "manual" if mid is not None else None
        self.yo_fiable = mid is not None
        self._apunte = None            # que el cambio quede apuntado

    def clima(self):
        """
        El tiempo que hace AHORA MISMO, tal cual lo publica el juego.

        Todo sale de la cabecera del buffer de scoring, asi que no cuesta
        nada: ya estaba abierto para leer las posiciones de los coches. Se
        refresca a la vez que el resto, o sea 5 veces por segundo, que para el
        clima es una exageracion pero sale gratis.

        Lo que NO esta aqui es el pronostico: eso hay que pedirselo a la API
        web del juego y lo hace `clima.py` en su propio hilo.
        """
        try:
            sco = self.sco
            return {
                "aire": d(sco, OFF_T_AIRE),
                "asfalto": d(sco, OFF_T_ASFALTO),
                "lluvia": d(sco, OFF_LLUVIA),
                "nubes": d(sco, OFF_NUBES),
                "cielo": u1(sco, OFF_CIELO),
                "agarre": u1(sco, OFF_AGARRE),
                "mojado": d(sco, OFF_MOJADO_MED),
                "mojado_min": d(sco, OFF_MOJADO_MIN),
                "mojado_max": d(sco, OFF_MOJADO_MAX),
                # El viento viene en 3 ejes y en metros por segundo; lo que
                # interesa es cuanto sopla, asi que se da el modulo en km/h.
                "viento": math.sqrt(sum(d(sco, OFF_VIENTO + 8 * i) ** 2
                                        for i in range(3))) * 3.6,
                "hora_dia": f4(sco, OFF_HORA_DIA),
                "reloj_sesion": d(sco, OFF_ET),
                "fin_sesion": d(sco, OFF_FIN_ET),
            }
        except (OSError, struct.error, ValueError):
            return None

    def circuito(self):
        return txt(self.sco, OFF_TRACK, 64)

    def nombre_jugador(self):
        """Tu nombre de piloto, tal cual lo publica la cabecera."""
        return txt(self.sco, OFF_JUGADOR, 32)

    def sesion(self):
        """Que sesion se esta corriendo. Al cambiar hay que empezar de cero."""
        return i4(self.sco, OFF_SESION)

    def version(self):
        """
        Contador que el plugin sube en cada actualizacion.

        Es la forma de saber si el juego esta publicando: al salir al menu
        principal la memoria se queda con los ultimos datos (mismo circuito,
        mismos coches) y sin esto el mapa seguiria pintando una sesion que ya
        no existe.
        """
        return i4(self.sco, 0)

    def tiempo_sesion(self):
        """
        mCurrentET: segundos transcurridos de la sesion.

        Vuelve a empezar en cada sesion nueva, asi que si retrocede es que se
        ha empezado otra. Hace falta porque el codigo de sesion no distingue
        una practica de la practica siguiente: las dos valen 1.
        """
        return d(self.sco, 80)

    def en_pista(self):
        """mInRealtime: 1 conduciendo, 0 en el garaje o en la reproduccion."""
        return bool(u1(self.sco, 127))

    def fase_juego(self):
        """mGamePhase de la cabecera: 5 = verde, 6 = amarilla a todo el trazado."""
        return u1(self.sco, 120)

    def largo_pista(self):
        """Longitud del circuito en metros (cabecera del buffer)."""
        return d(self.sco, 100)

    def n_coches(self):
        n = i4(self.sco, OFF_NUMVEH)
        return n if 0 < n <= MAX_COCHES else 0

    def coches(self):
        """Lista de dicts: nombre, x, z, clase, es_yo."""
        salida = []
        if self.off_pos is None:
            return salida
        mi_nombre = self.nombre_jugador()
        con_marca = []      # los que llevan la marca del juego
        con_mi_nombre = []  # los que conduce alguien que se llama como tu
        for v in range(self.n_coches()):
            b = SCO_BASE + v * SCO_STRIDE
            try:
                x = d(self.sco, b + self.off_pos)
                z = d(self.sco, b + self.off_pos + 16)
            except (OSError, struct.error):
                continue
            if not (math.isfinite(x) and math.isfinite(z)):
                continue
            piloto = txt(self.sco, b + OFF_NOMBRE, 32)
            if self.off_jugador is not None and u1(self.sco, b + self.off_jugador):
                con_marca.append(len(salida))
            if mi_nombre and piloto == mi_nombre:
                con_mi_nombre.append(len(salida))
            salida.append({
                "id": i4(self.sco, b + OFF_ID),
                "ficha": v,              # su sitio en el buffer. Hace falta
                                         # porque esta lista se salta los
                                         # coches sin posicion y ya no cuadra
                                         # con el numero de orden del buffer

                "nombre": piloto,
                "vehiculo": txt(self.sco, b + OFF_VEHICULO, 64),
                "codigo": txt(self.sco, b + OFF_CODIGO, 32),
                "x": x,
                "z": z,
                "clase": txt(self.sco, b + self.off_clase, 32) if self.off_clase is not None else "",
                "es_yo": False,          # lo decide _elegir_mi_coche(), abajo
                "yo_fiable": False,      # y si esa decision es de fiar o es
                                         # una suposicion
                "dist": d(self.sco, b + OFF_DIST),        # metros de vuelta
                "lateral": d(self.sco, b + OFF_LATERAL),
                "borde": d(self.sco, b + OFF_BORDE),
                "vueltas": i2(self.sco, b + OFF_VUELTAS),
                "mejor": d(self.sco, b + OFF_MEJOR),      # s, 0 si aun no tiene
                "ultima": d(self.sco, b + OFF_ULTIMA),    # s, la que acaba de cerrar
                "sec1": d(self.sco, b + OFF_SEC1),        # sector 1 de esa vuelta
                "sec2": d(self.sco, b + OFF_SEC2),        # sectores 1+2 acumulados
                "vuelta_valida": u1(self.sco, b + OFF_VALIDA),
                "penalizaciones": i2(self.sco, b + OFF_PENAS),
                "en_boxes": bool(u1(self.sco, b + OFF_BOXES)),
                "fase": u1(self.sco, b + OFF_FASE),
                "bandera": u1(self.sco, b + OFF_BANDERA),
            })
        self._elegir_mi_coche(salida, con_marca, con_mi_nombre)
        return salida

    def circuito_descargado(self):
        """
        Si el juego ha DESCARGADO el circuito: la sesion se acabo.

        LMU deja en su memoria la lista de sus ultimos avisos, y al salir de
        una sesion aparece ahi UNLOAD. Sirve para lo unico que antes no se
        podia saber: **distinguir una PAUSA de haber salido al menu**. Desde
        fuera las dos se ven igual -el juego deja de publicar y la memoria se
        queda con la ultima sesion entera, circuito y coches incluidos-, pero
        una pausa no descarga nada.

        Medido el 28/08/2026: rodando en pista los avisos son FFB y
        UPDATE_TELEMETRY; nada mas salir al menu, UNLOAD.

        None si no se puede leer. Ojo: es una senal para BORRAR, nunca para
        pintar. Si fallara, el mapa se queda como estaba, que es lo de antes.
        """
        if self._lmu() is None:
            return None
        try:
            for i in range(LMU_AVISOS_N):
                if i4(self.lmu, LMU_AVISOS + i * 4) == AVISO_UNLOAD:
                    return True
            return False
        except OSError:
            return None

    def id_segun_el_juego(self):
        """
        El coche del jugador, dicho por el propio LMU. None si no lo dice.

        En su memoria compartida (`LMU_Data`) hay un bloque de telemetria que
        empieza por tres datos: cuantos coches hay, **cual es el del jugador**
        y si el jugador tiene coche. Se coge ese indice, se lee el `mID` de esa
        ficha, y ese numero es el que se cruza con la lista de scoring: asi da
        igual que las dos listas no vayan en el mismo orden.

        Es mejor fuente que la marca `mIsPlayer` y que el nombre del piloto,
        porque no hay que deducir nada: lo dice el juego.
        """
        if self._lmu() is None:
            return None
        try:
            activos = u1(self.lmu, LMU_TELE)
            cual = u1(self.lmu, LMU_TELE + 1)
            tiene = u1(self.lmu, LMU_TELE + 2)
            if not tiene or not 0 <= cual < min(activos, LMU_MAX_VEH):
                return None
            return i4(self.lmu, LMU_TELE_FICHAS + cual * LMU_TELE_STRIDE)
        except OSError:
            return None

    # De donde puede salir la respuesta a "cual de estos coches soy yo", y si
    # esa fuente SABE la respuesta o se la esta inventando. Solo las fiables
    # dejan grabar vueltas como tuyas.
    FIABLES = ("manual", "juego", "marca")

    def _elegir_mi_coche(self, coches, con_marca, con_mi_nombre):
        """
        Cual de todos los coches eres tu.

        Orden, y el porque de cada escalon:

        1. **El que hayas elegido A MANO** (`fijado`). Manda por encima de todo:
           si el usuario ha tenido que decirlo es porque el juego no lo decia.
        2. **Lo que diga el juego** (`id_segun_el_juego`), en CADA lectura.
        3. **El ultimo coche conocido**, cuando el juego no dice nada. Ese es el
           caso del RELEVO en una carrera por equipos: haces tu stint, paras en
           boxes, entra tu companero y tu te quedas de espectador. Ahi el juego
           deja de decir "tu coche es este", pero el coche del equipo sigue
           siendo el mismo y hay que seguir viendolo. La confianza se hereda de
           como se eligio en su momento.
        4. **La marca `mIsPlayer`**, y SOLO si la lleva exactamente un coche.
        5. **El nombre del piloto**, y solo si hay uno solo que se llame como
           tu. Este ultimo escalon NO es de fiar (ver abajo) y se marca como
           tal: el mapa lo pinta pero avisa, y no graba vueltas.

        Los escalones 4 y 5 van pegados a la PERSONA, no al coche, y por eso
        estan los ultimos: en un relevo los dos fallan.

        **Por que se hace en cada lectura y no una sola vez.** Se probo a
        fijarlo una vez y no soltarlo, y salio mal el mismo dia (28/08/2026,
        Interlagos): si el coche se fija en el momento malo -al entrar, con la
        memoria todavia llena de la sesion anterior- el mapa se queda pegado a
        OTRO coche durante toda la sesion, y ademas no se nota, porque el
        circulo se mueve por el trazado como si fuera el tuyo. Preguntando en
        cada lectura, un error dura una lectura.

        **Por que ninguna via inventa ya un coche.** Silverstone, 6 h del
        29/08/2026: Manuel entro de espectador, ninguna via sabia quien era, y
        el mapa se engancho a un BMW M4 ajeno durante las seis horas -y grabo
        sus vueltas como propias-. Un circulo verde en el coche equivocado es
        peor que no tener circulo, porque no hay forma de notarlo: da vueltas
        igual. Ahora, cuando no se sabe, no se sabe y se dice.
        """
        # 1) lo que haya dicho el usuario
        if self.fijado is not None:
            for c in coches:
                if c["id"] == self.fijado:
                    return self._marcar(c, "manual")
            self.fijado = None             # ese coche ya no esta en la sala

        # 2) lo que dice el juego
        del_juego = self.id_segun_el_juego()
        if del_juego is not None:
            for c in coches:
                if c["id"] == del_juego:
                    return self._marcar(c, "juego")

        # 3) el ultimo conocido: el caso del relevo. Se conserva la confianza
        #    que tuviera la eleccion original.
        if self.id_yo is not None:
            for c in coches:
                if c["id"] == self.id_yo:
                    return self._marcar(c, self.origen_yo or "recuerdo",
                                        fiable=self.yo_fiable)
            self.id_yo = None              # ese coche ya no esta

        # 4) la marca del juego, solo si no hay empate. Si la llevan varios
        #    -o ninguno, que es lo que pasa de espectador- no dice nada.
        if len(con_marca) == 1:
            return self._marcar(coches[con_marca[0]], "marca")

        # 5) el nombre, de ultimo recambio y sin fiarse. En una sala online la
        #    cabecera puede traer el nombre de quien estas MIRANDO, no el tuyo.
        if len(con_mi_nombre) == 1:
            return self._marcar(coches[con_mi_nombre[0]], "nombre")

        self._olvidar()

    def _marcar(self, coche, origen, fiable=None):
        """Deja marcado el coche elegido y apunta de donde salio la decision."""
        if fiable is None:
            fiable = origen in self.FIABLES
        coche["es_yo"] = True
        coche["yo_fiable"] = fiable
        self.id_yo = coche["id"]
        self.origen_yo = origen
        self.yo_fiable = fiable
        self._apuntar(origen, coche, fiable)

    def _olvidar(self):
        """Nadie es "yo". Es un resultado legitimo, no un fallo: de espectador
        recien entrado el juego no ha dicho todavia de quien eres."""
        self.origen_yo = None
        self.yo_fiable = False
        self._apuntar(None, None, False)

    def _apuntar(self, origen, coche, fiable):
        """
        Deja por escrito a quien esta siguiendo el mapa y por que.

        El mapa corre sin consola, asi que cuando algo sale mal no queda ni
        rastro de por que eligio ese coche. Despues de Silverstone hubo que
        deducirlo de los resultados del juego. Se apunta solo cuando CAMBIA,
        que en una carrera entera son cuatro lineas.
        """
        clave = (origen, coche["id"] if coche else None)
        if clave == self._apunte:
            return
        self._apunte = clave
        if coche is None:
            apuntar("tu coche: NADIE, ninguna via sabe cual es")
        else:
            apuntar("tu coche: %s (%s) mID %d  <- %s%s"
                    % (coche.get("nombre", "?"), coche.get("vehiculo", "?"),
                       coche["id"], origen,
                       "" if fiable else "  [SUPOSICION]"))


def calibrar_puesto(sco, n_coches):
    """
    Busca el byte con el puesto en carrera: sus valores entre todos los coches
    tienen que ser exactamente 1..N sin repetirse.
    """
    if n_coches < 2:
        return None
    esperado = list(range(1, n_coches + 1))
    for off in range(0, SCO_STRIDE):
        try:
            vals = [u1(sco, SCO_BASE + v * SCO_STRIDE + off) for v in range(n_coches)]
        except OSError:
            continue
        if sorted(vals) == esperado:
            return off
    return None
