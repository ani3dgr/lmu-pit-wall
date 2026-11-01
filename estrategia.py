# -*- coding: utf-8 -*-
"""
La prediccion de carrera: a quien vamos a adelantar, quien nos va a adelantar
y que pasa si paramos ahora.

COMO LO HACEN LOS EQUIPOS (lo que se busco el 30/10/2026)
En F1 y en resistencia el muro hace lo mismo con mas o menos medios: una
simulacion que se alimenta EN DIRECTO de los tiempos propios y de los rivales
y que se rehace cada vuelta. Lo que entra siempre es:
  - la distancia de verdad con cada rival,
  - el ritmo de cada uno ahora mismo,
  - cuanto cuesta una parada (entrada, parada, salida),
  - cuantas paradas le faltan a cada uno hasta el final (en resistencia lo
    primero que limita es lo que dura un deposito),
  - y donde sale uno si para ahora: delante o detras de quien, y si sale
    metido en trafico o con la pista libre.
Con eso se sacan dos numeros que son los que se miran en el muro:
  - la DISTANCIA NETA: la de ahora contando las paradas que le faltan a cada
    uno. Un coche 40 s por delante que aun tiene que parar una vez mas que tu
    esta, de verdad, 36 s por DETRAS.
  - la PROYECCION al final: la neta mas lo que se gana o se pierde por ritmo
    en las vueltas que quedan.
Y de ahi sale la cuenta que pidio Manuel: a cuantos vamos a adelantar.

LO QUE NO SABE (y por eso es una prediccion)
Si un rival hace una parada corta (sin ruedas, solo energia) o larga (ruedas
y cambio de piloto), la lluvia, el coche de seguridad, un error... Se rehace
cada segundo con lo ultimo, asi que se va corrigiendo sola.

Todo sale de clasificacion.Tabla, que ya lo apunta: aqui solo se hacen las
cuentas.
"""
import time

PERDIDA_SIN_DATOS = 75.0    # s por parada si aun no se ha visto ninguna
TRAFICO_S = 3.0             # un coche a menos de esto de donde sales: trafico
# Vueltas con las que se mide el ritmo de cada coche. Con 5 una sola vuelta
# buena movia la prediccion entera; con 10 se lleva mejor.
RITMO_VUELTAS = 10


def _mediana(valores):
    valores = sorted(v for v in valores if v is not None)
    if not valores:
        return None
    mitad = len(valores) // 2
    if len(valores) % 2:
        return valores[mitad]
    return (valores[mitad - 1] + valores[mitad]) / 2.0


def tiempo_restante(tabla):
    """Segundos que le quedan a la sesion, o None."""
    queda = tabla.info.get("timeRemainingInGamePhase")
    if not isinstance(queda, (int, float)) or queda < 0:
        return None
    return max(0.0, queda - (time.monotonic() - tabla.info_sello))


def _paradas_en(f, ritmo, segundos):
    """
    Cuantas veces tiene que parar a repostar en los proximos `segundos`, o
    None si aun no se sabe lo que gasta.

    Con lo que le queda llega a `quedan` vueltas: si el plazo es mas corto, no
    para. Si no, para una vez ahi y despues una cada deposito entero (1/gasto
    vueltas).
    """
    comb = f.get("combustible") or {}
    quedan = comb.get("quedan")
    manda = comb.get("manda")
    gasto = (comb.get(manda) or {}).get("gasto") if manda else None
    if quedan is None or not gasto or not ritmo or segundos is None:
        return None
    vueltas = segundos / ritmo
    if vueltas <= quedan:
        return 0
    return 1 + int((vueltas - quedan) * gasto)


def _ritmos_de_boxes(parada):
    """
    (energia que se mete por segundo, segundos de cambiar las ruedas que
    llevamos marcadas). Del juego si lo da; si no, lo de LMU: el 2,5 % por
    segundo y 12 s las cuatro ruedas.
    """
    tasa, ruedas_s = 0.025, 12.0
    try:
        import boxes
        d = boxes.boxes._d or {}
        tasa = ((d.get("pitStopTimes") or {}).get("times") or {}).get(
            "virtualEnergyFillRate") or tasa
    except Exception:
        pass
    if parada and parada.get("ruedas") is not None:
        ruedas_s = parada.get("ruedas_s") or 0.0
    return tasa, ruedas_s


def _parada_estimada(f, ritmo, restante, carril, tasa, ruedas_s):
    """
    Lo que le costara a un coche su proxima parada, calculado como la nuestra:
    carril + la energia que le hace falta (la justa para llegar al final con
    un poco de margen, o el deposito entero si no llega) + las ruedas. None
    si no se sabe lo que gasta o falta el carril.

    La energia y las ruedas van una detras de otra (lo dice el juego, ver
    boxes.py); el cambio de piloto va a la vez y no se cuenta.
    """
    comb = f.get("combustible") or {}
    quedan, manda = comb.get("quedan"), comb.get("manda")
    gasto = (comb.get(manda) or {}).get("gasto") if manda else None
    if carril is None or quedan is None or not gasto or not ritmo or restante is None:
        return None
    despues = restante / ritmo - quedan        # vueltas que dara tras parar
    falta = min(1.0, max(0.0, despues) * gasto + 0.03)
    return carril + falta / tasa + ruedas_s


def _nuestra_parada(tabla, yo):
    """
    Lo que nos va a costar la proxima parada con lo marcado en el menu de
    boxes, o None si el juego no lo da:
    {"parado", "carril", "extra_piloto", "total", y el desglose de boxes.py}.
    """
    try:
        import boxes
    except Exception:
        return None
    prevision = boxes.boxes.prevision((yo.get("api") or {}).get("driverName", ""))
    if not prevision or prevision["parado"] is None:
        return None
    carril, extra = tabla.carril(yo["clase"])
    salida = dict(prevision)
    salida["carril"] = carril

    # El juego calcula lo parado con la energia que hay AHORA: recien llenado
    # el deposito, salian 20 s cuando la parada de verdad (que sera con el
    # deposito vacio) dura 50 (visto el 31/10/2026). Asi que, salvo en las
    # ultimas vueltas antes de parar, se cuenta como sera: la energia desde
    # casi vacio hasta lo marcado, y detras ruedas, reparar y frenos (medido
    # en Imola: todo eso va en serie; el cambio de piloto va a la vez).
    quedan = (yo.get("combustible") or {}).get("quedan")
    if prevision.get("energia_hasta") is not None and (quedan is None or quedan > 2):
        tasa = _ritmos_de_boxes(None)[0]
        energia_s = max(0.0, prevision["energia_hasta"] - 0.02) / tasa
        en_serie = (energia_s + prevision["ruedas_s"] + prevision["reparar_s"]
                    + prevision["frenos_s"])
        salida["energia_s"] = energia_s
        salida["parado"] = max(en_serie, prevision["piloto_s"] or 0.0)
        salida["al_vaciar"] = True
    salida["extra_piloto"] = extra if prevision["piloto"] else 0.0
    if carril is not None:
        salida["total"] = carril + salida["parado"] + (salida["extra_piloto"] or 0.0)
    else:
        salida["total"] = None
    return salida


def calcular(tabla, filas, horizonte=None):
    """
    Todo lo de la prediccion para el panel, o None si no se sabe cual es el
    nuestro. `filas` son las de tabla.filas() de TODOS los coches.

    `horizonte`: a cuantos segundos vista se predice (None = hasta el final).
    A 4 horas vista la prediccion no vale: un segundo por vuelta de mas o de
    menos son dos minutos al final, y bailaba de "adelantamos a 1" a
    "adelantamos a 7" con una sola vuelta buena (visto el 30/10/2026). Los
    equipos miran a la siguiente media hora, a la siguiente parada.
    """
    yo = next((f for f in filas if f["es_yo"]), None)
    if yo is None:
        return None
    restante = tiempo_restante(tabla)
    segundos = restante
    if horizonte and restante is not None:
        segundos = min(restante, float(horizonte))
    largo = tabla.info.get("lapDistance")
    ritmo_yo = (tabla.ritmo(yo["clave"], RITMO_VUELTAS) or yo.get("media")
                or yo.get("mejor"))
    if not ritmo_yo:
        return {"yo": yo, "falta": "ritmo"}

    clase = [f for f in filas if f["clase"] == yo["clase"]]

    # Lo que cuesta una parada: la mediana de TODAS las de la clase, la misma
    # para todos. Probado con la de cada coche y salian disparates: una
    # parada con reparacion o con sancion (130, 200, 400 s) se daba por
    # buena para todas las que le quedaban a ese coche, y lo "adelantabamos"
    # en boxes. Lo que distingue a unos de otros es CUANTAS paradas les
    # faltan, no lo que tardo una suya.
    todas = [p for f in clase for p in tabla.perdidas(f["clave"])]
    perdida_clase = _mediana(todas) or PERDIDA_SIN_DATOS
    vistas = len(todas)

    # La NUESTRA se afina con el menu de boxes: carril (medido) + lo que el
    # juego dice que estaremos parados con lo marcado + lo que se pierde de
    # mas si hay cambio de piloto (medido).
    parada = _nuestra_parada(tabla, yo)
    # La de cada rival se calcula IGUAL, con lo que le hace falta: carril +
    # la energia que necesita para llegar al final (o el deposito entero) +
    # las mismas ruedas que nosotros. Antes se les ponia la media de la clase
    # (84 s, con depositos llenos y cambios de piloto) contra nuestros 64 de
    # repostar al 60 %, y esos 20 s de diferencia daban "le pasamos en boxes"
    # a uno que nos sacaba 5 s y paraba despues (Manuel, 30/10/2026).
    carril = tabla.carril(yo["clase"])[0]
    tasa, ruedas_s = _ritmos_de_boxes(parada)

    def estimada(f, ritmo):
        return _parada_estimada(f, ritmo, restante, carril, tasa, ruedas_s) or perdida_clase

    perdida_yo = (parada["total"] if parada and parada.get("total")
                  else estimada(yo, ritmo_yo))
    perdidas = {}

    vueltas_yo = segundos / ritmo_yo if segundos is not None else None
    paradas_yo = _paradas_en(yo, ritmo_yo, segundos)

    ahora = tabla.info.get("currentEventTime")
    if isinstance(ahora, (int, float)):
        ahora += time.monotonic() - tabla.info_sello
    else:
        ahora = None

    def cruza(f, ritmo, m):
        """A que hora cruza (o cruzara) la meta al cerrar la vuelta m."""
        if m <= f["vueltas"]:
            return tabla.cruce(f["clave"], m, f["empieza_vuelta"], f["vueltas"])
        # La siguiente: la estimamos por lo que le falta de vuelta.
        if (m == f["vueltas"] + 1 and ahora is not None and largo
                and f.get("metros") is not None):
            falta = max(0.0, 1.0 - f["metros"] / largo)
            return ahora + falta * ritmo
        return None

    def distancia(f):
        """
        Segundos que va POR DETRAS de nosotros (negativo: por delante).

        Se comparan los dos coches en la PROXIMA meta que tiene que cruzar
        el que va detras: la del de delante ya se sabe y la suya se estima.
        Comparar en la ultima meta que han cruzado los dos se quedaba viejo:
        un coche que paraba en boxes seguia saliendo a 20 s cuando ya iba a
        mas de un minuto.
        """
        # Lo primero, la del propio juego: distancia de cada uno al primero de
        # su clase, si van en la misma vuelta. Es la que ensena la pantalla
        # del juego, cambia solo al pasar por los puntos de cronometraje y no
        # baila. La estimacion de abajo (lo que le falta de vuelta por el
        # ritmo) daba de 2 a 3 s de error y fluctuaba, porque la velocidad no
        # es la misma en toda la vuelta (Manuel, Barcelona 01/11/2026).
        suyo_api, mio_api = f.get("api") or {}, yo.get("api") or {}
        try:
            t_suyo = float(suyo_api.get("timeBehindClassLeader"))
            t_mio = float(mio_api.get("timeBehindClassLeader"))
            if (int(suyo_api.get("lapsBehindClassLeader") or 0)
                    == int(mio_api.get("lapsBehindClassLeader") or 0)
                    and t_suyo >= 0 and t_mio >= 0):
                return t_suyo - t_mio
        except (TypeError, ValueError):
            pass
        ritmo = tabla.ritmo(f["clave"], RITMO_VUELTAS) or ritmo_yo
        m = min(f["vueltas"], yo["vueltas"]) + 1
        mia = cruza(yo, ritmo_yo, m)
        suya = cruza(f, ritmo, m)
        if mia is not None and suya is not None:
            return suya - mia
        # Sin todas las vueltas apuntadas: por lo recorrido, a nuestro ritmo.
        if largo and f.get("metros") is not None and yo.get("metros") is not None:
            mio = yo["vueltas"] + yo["metros"] / largo
            suyo = f["vueltas"] + f["metros"] / largo
            return (mio - suyo) * ritmo_yo
        return None

    rivales = []
    for f in clase:
        if f["es_yo"]:
            continue
        dist = distancia(f)
        ritmo = tabla.ritmo(f["clave"], RITMO_VUELTAS)
        paradas = _paradas_en(f, ritmo or ritmo_yo, segundos)
        neta = proyeccion = None
        perdidas[f["clave"]] = estimada(f, ritmo or ritmo_yo)
        if dist is not None and paradas is not None and paradas_yo is not None:
            neta = dist + paradas * perdidas[f["clave"]] - paradas_yo * perdida_yo
            if ritmo and vueltas_yo is not None:
                proyeccion = neta + (ritmo - ritmo_yo) * vueltas_yo
        prevision, vuelta = None, None
        if dist is not None and proyeccion is not None:
            if dist < 0 < proyeccion:
                prevision = "pasamos"
            elif proyeccion < 0 < dist:
                prevision = "nos_pasa"
            # En que vuelta se cruzan por ritmo, si es por ritmo; si ya con
            # la neta ha cambiado de lado, es en las paradas.
            if prevision:
                if (neta < 0) == (dist < 0) and ritmo and ritmo != ritmo_yo:
                    x = -neta / (ritmo - ritmo_yo)
                    if x > 0:
                        vuelta = yo["vueltas"] + int(round(x))
                else:
                    vuelta = "boxes"
        dif_ritmo = _ritmo_vivo(f, yo, dist, ritmo_yo)
        if dif_ritmo is None and ritmo:
            dif_ritmo = ritmo - ritmo_yo
        rivales.append({
            "fila": f, "distancia": dist, "ritmo": ritmo,
            "dif_ritmo": dif_ritmo,
            "paradas": paradas, "neta": neta,
            "proyeccion": proyeccion, "prevision": prevision, "vuelta": vuelta,
        })

    # Puesto al final: los que acaban por delante, con la proyeccion si la
    # hay y si no con la distancia de ahora.
    delante_final = 0
    llegada_delante = llegada_detras = None    # (segundos, fila) al final
    for r in rivales:
        valor = r["proyeccion"] if r["proyeccion"] is not None else r["distancia"]
        if valor is None:
            continue
        if valor < 0:
            delante_final += 1
            if llegada_delante is None or valor > llegada_delante[0]:
                llegada_delante = (valor, r["fila"])
        elif llegada_detras is None or valor < llegada_detras[0]:
            llegada_detras = (valor, r["fila"])

    return {
        "yo": yo,
        "falta": None,
        "segundos": segundos,
        "restante": restante,
        "horizonte": horizonte,
        "ritmo": ritmo_yo,
        "vueltas_quedan": vueltas_yo,
        "paradas": paradas_yo,
        "perdida": perdida_yo,
        "paradas_vistas": vistas,
        "perdida_clase": perdida_clase,
        "perdidas": perdidas,
        "parada": parada,
        "rivales": rivales,
        "puesto": yo.get("puesto_clase"),
        "puesto_final": delante_final + 1,
        # Quien queda justo delante y detras al llegar, con sus paradas ya
        # contadas: es lo unico que importa cuando no nos quedan paradas.
        "llegada_delante": llegada_delante,
        "llegada_detras": llegada_detras,
        "pasamos": sum(1 for r in rivales if r["prevision"] == "pasamos"),
        "nos_pasan": sum(1 for r in rivales if r["prevision"] == "nos_pasa"),
        "si_paramos": _si_paramos(tabla, yo, rivales, filas, perdida_yo,
                                  perdida_clase, ritmo_yo, largo, 0.0, perdidas),
        # Y cuando toque de verdad: en la ultima vuelta que da la energia.
        "al_parar": _al_parar(tabla, yo, rivales, filas, perdida_yo,
                              perdida_clase, ritmo_yo, largo, perdidas),
    }


_brechas = {}       # clave del rival -> [(reloj, distancia), ...]


def _ritmo_vivo(f, yo, dist, ritmo_yo):
    """
    Lo que nos gana (-) o pierde (+) por vuelta AHORA, sacado de como cambia
    la distancia con el en la ultima vuelta, o None si aun no se sabe.

    La mediana de las ultimas 10 vueltas solo cambiaba al cruzar la meta y
    muy despacio; Manuel queria verlo moverse con la distancia (Barcelona,
    01/11/2026). Se compara con la distancia de hace una vuelta entera y no
    menos, porque cada coche es mas rapido en unas zonas que en otras: con
    medio minuto, uno que frena mejor parecia que volaba en el sector lento.
    La distancia del juego cambia en cada punto de cronometraje, asi que esto
    tambien. Si cualquiera de los dos entra en boxes se empieza de cero.
    """
    k = f["clave"]
    if (dist is None or not ritmo_yo or f.get("boxes_ya") or yo.get("boxes_ya")
            or f.get("en_boxes") or yo.get("en_boxes")):
        _brechas.pop(k, None)
        return None
    ahora = time.monotonic()
    lista = _brechas.setdefault(k, [])
    if not lista or lista[-1][1] != dist:
        lista.append((ahora, dist))
    while lista and ahora - lista[0][0] > 2.5 * ritmo_yo:
        lista.pop(0)
    # la muestra mas reciente que tenga ya una vuelta
    vieja = None
    for t, d in lista:
        if ahora - t >= 0.95 * ritmo_yo:
            vieja = (t, d)
    if vieja is None:
        return None
    vivo = (dist - vieja[1]) / (ahora - vieja[0]) * ritmo_yo
    return vivo if abs(vivo) < 5.0 else None      # un trompo o una sancion


def _si_paramos(tabla, yo, rivales, filas, perdida, perdida_otros, ritmo,
                largo, vueltas=0.0, perdidas=None):
    """
    Donde salimos si paramos dentro de `vueltas` (0 = ahora): puesto en la
    clase, quien queda justo delante y detras, y si salimos metidos en
    trafico (de cualquier clase).

    Para parar mas adelante se proyecta todo a esa vuelta: cada rival gana o
    pierde su diferencia de ritmo en esas vueltas, y si le toca parar ANTES
    que a nosotros, ya lleva su parada encima (`perdida_otros`). Igual con el
    trafico: donde estara cada coche de la pista cuando salgamos.
    """
    def a_futuro(f, ahora_s, ritmo_suyo):
        """Lo que estara por detras de nosotros (s) dentro de `vueltas`."""
        if not vueltas:
            return ahora_s
        futuro = ahora_s + ((ritmo_suyo or ritmo) - ritmo) * vueltas
        quedan = (f.get("combustible") or {}).get("quedan")
        if quedan is not None and quedan < vueltas:
            # habra parado antes que nosotros
            futuro += (perdidas or {}).get(f["clave"]) or perdida_otros
        return futuro

    proyectados = []
    for r in rivales:
        if r["distancia"] is None:
            continue
        proyectados.append((a_futuro(r["fila"], r["distancia"], r["ritmo"]), r["fila"]))
    # Al parar perdemos `perdida` segundos: todos se acercan eso.
    tras = [(d - perdida, f) for d, f in proyectados]
    delante_nuestro = sum(1 for d, f in tras if d < 0)
    delante = max((x for x in tras if x[0] < 0), key=lambda x: x[0], default=None)
    detras = min((x for x in tras if x[0] >= 0), key=lambda x: x[0], default=None)

    # Trafico: los coches que van en la pista, de cualquier clase, por donde
    # saldriamos. Saldremos `perdida` segundos por detras de donde estemos; se
    # pasa a metros a nuestro ritmo.
    trafico = []
    if largo and yo.get("metros") is not None:
        for f in filas:
            if f["es_yo"] or f.get("metros") is None:
                continue
            if f.get("boxes_ya") and not vueltas:
                continue
            detras_s = ((yo["metros"] - f["metros"]) % largo) / largo * ritmo
            detras_s = a_futuro(f, detras_s, tabla.ritmo(f["clave"], RITMO_VUELTAS)) % ritmo
            hueco = abs(detras_s - perdida % ritmo)
            if min(hueco, ritmo - hueco) < TRAFICO_S:
                trafico.append(f)
    return {
        "puesto": delante_nuestro + 1,
        "delante": delante,
        "detras": detras,
        "trafico": trafico,
        "vueltas": vueltas,
    }


def _al_parar(tabla, yo, rivales, filas, perdida, perdida_otros, ritmo, largo,
              perdidas=None):
    """Lo de _si_paramos para la vuelta en la que toca parar, o None."""
    comb = yo.get("combustible") or {}
    quedan, parar_en = comb.get("quedan"), comb.get("parar_en")
    if quedan is None or parar_en is None or quedan < 1:
        return None
    salida = _si_paramos(tabla, yo, rivales, filas, perdida, perdida_otros,
                         ritmo, largo, float(int(quedan)), perdidas)
    salida["vuelta"] = parar_en
    return salida


def ciclo(tabla, filas):
    """
    Segundos hasta que TODOS los de nuestra clase hayan hecho su proxima
    parada (y una vuelta mas, la de salida), o None si no se sabe.

    Es el plazo justo para comparar: a media hora vista, uno que para dentro
    de diez minutos sale "adelantado" aunque nosotros vayamos a parar a los
    cuarenta. Esperando a que paren todos, la parada se la come cada uno y lo
    que queda es lo de verdad: el ritmo y quien aguanta mas con un deposito.
    En el muro lo llaman la posicion NETA, la de despues del ciclo de paradas.
    """
    yo = next((f for f in filas if f["es_yo"]), None)
    if yo is None:
        return None
    plazos = []
    for f in filas:
        if f["clase"] != yo["clase"] or f.get("boxes_ya"):
            continue
        quedan = (f.get("combustible") or {}).get("quedan")
        ritmo = tabla.ritmo(f["clave"], RITMO_VUELTAS)
        if quedan is None or not ritmo:
            continue
        plazos.append((quedan + 1.0) * ritmo)
    if not plazos:
        return None
    restante = tiempo_restante(tabla)
    plazo = max(plazos)
    return min(plazo, restante) if restante is not None else plazo


_vigia = {"prevista": None, "apuntadas": set()}


def vigilar_paradas(tabla, d):
    """
    Apunta cada parada NUESTRA ya hecha con lo que se habia previsto justo
    antes de entrar (menu de boxes) y lo que fue de verdad, en
    vueltas_carreras/boxes_paradas_*.csv. Para comprobar las cuentas.
    """
    import datetime
    if not d or d.get("falta"):
        return
    yo = d["yo"]
    if not yo.get("boxes_ya") and d.get("parada"):
        _vigia["prevista"] = d["parada"]        # lo ultimo antes de entrar
    for p in tabla.paradas_medidas(yo.get("api") or {}):
        clave = (yo["clave"], p["vuelta"])
        if clave in _vigia["apuntadas"] or p["perdida"] is None:
            continue
        _vigia["apuntadas"].add(clave)
        prevista = _vigia["prevista"] or {}
        try:
            import boxes
            boxes.boxes.apuntar_parada([
                datetime.datetime.now().strftime("%H:%M:%S"), p["vuelta"],
                yo["piloto"], "si" if p["cambio_piloto"] else "", p["ruedas"],
                _coma(prevista.get("parado")), _coma(p["parado"]),
                _coma(p["perdida"])])
        except Exception:
            pass


def _coma(x):
    return "" if x is None else ("%.1f" % x).replace(".", ",")


def calcular_todo(tabla, filas, minutos):
    """
    Lo del panel: la prediccion a `minutos` vista (0 = tras el ciclo de
    paradas, ver `ciclo`) y, aparte, la de hasta el final (en "final").
    """
    horizonte = minutos * 60 if minutos else ciclo(tabla, filas)
    d = calcular(tabla, filas, horizonte)
    if not d or d.get("falta"):
        return d
    final = calcular(tabla, filas, None)
    d["final"] = final
    d["paradas_final"] = final.get("paradas") if final else None
    d["es_ciclo"] = not minutos
    return d


_apunte = {"cuando": 0.0, "archivo": None}


def apuntar(d, cada=60.0):
    """
    Guarda lo que predice, una linea por minuto, en vueltas_carreras/ junto
    a las vueltas. Es para la prueba de campo: despues de la carrera se mira
    si lo que dijo a los 40 minutos se cumplio.
    """
    import csv
    import datetime
    import os
    import rutas
    if not d or d.get("falta"):
        return
    ahora = time.monotonic()
    if ahora - _apunte["cuando"] < cada:
        return
    _apunte["cuando"] = ahora
    try:
        if _apunte["archivo"] is None:
            carpeta = rutas.datos("vueltas_carreras")
            os.makedirs(carpeta, exist_ok=True)
            _apunte["archivo"] = os.path.join(carpeta, datetime.datetime.now()
                                              .strftime("prediccion_%Y-%m-%d_%H%M%S.csv"))
        nuevo = not os.path.exists(_apunte["archivo"])
        final = d.get("final") or {}
        lista = lambda p, que: " ".join("#" + r["fila"]["dorsal"] for r in
                                        (p.get("rivales") or []) if r["prevision"] == que)
        with open(_apunte["archivo"], "a", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            if nuevo:
                w.writerow(["hora", "queda_s", "vuelta", "puesto", "ritmo",
                            "repostar_en", "paradas_final", "perdida_parada",
                            "plazo_min", "puesto_plazo", "pasamos_plazo",
                            "nos_pasan_plazo", "puesto_final", "pasamos_final",
                            "nos_pasan_final", "si_paramos_puesto"])
            num = lambda x: "" if x is None else ("%.1f" % x).replace(".", ",")
            w.writerow([datetime.datetime.now().strftime("%H:%M:%S"),
                        num(d.get("restante")), d["yo"]["vueltas"], d["puesto"],
                        num(d["ritmo"]),
                        (d["yo"].get("combustible") or {}).get("parar_en"),
                        d.get("paradas_final"), num(d["perdida"]),
                        num((d.get("horizonte") or 0) / 60.0), d["puesto_final"],
                        lista(d, "pasamos"), lista(d, "nos_pasa"),
                        final.get("puesto_final"), lista(final, "pasamos"),
                        lista(final, "nos_pasa"), d["si_paramos"]["puesto"]])
    except Exception:
        pass
