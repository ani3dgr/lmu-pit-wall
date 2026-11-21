# -*- coding: utf-8 -*-
"""
El plan de carrera: las cuentas que el equipo hacia a mano (Manuel,
20/11/2026).

COMBUSTIBLE: cuantas paradas quedan al ritmo de ahora y cuanto hay que
ahorrar por vuelta (lift and coast) para hacer UNA MENOS. Lo que se gasta por
vuelta ya se mide con las 3 ultimas vueltas (clasificacion.VUELTAS_GASTO), asi
que en cuanto se empieza a ahorrar la cuenta lo nota.

NEUMATICOS: los juegos que quedan de los que da el servidor, cuantos hacen
falta para acabar con la peor rueda por encima del limite (60 % por defecto:
Manuel aguanta hasta ahi; alguna vez ha llegado al 50 %) y lo que dura un
juego con el desgaste medido en pista.

Son estimaciones, como el resto del panel: se rehacen solas cada vuelta.
"""
import math
import time

MARGEN = 0.02          # 2 % de deposito que se deja sin contar, por si acaso
AHORRO_MAX = 0.15      # mas de esto por vuelta no se saca con lift and coast

# desgaste de las ruedas, vuelta a vuelta, de NUESTRO coche
_rueda = {"inicio": None, "previa": None, "ultima_vuelta": None, "ritmo": None}


def _peor_rueda():
    """Lo que le queda a la rueda mas gastada (1 = nueva), o None."""
    try:
        import boxes
        d = boxes.boxes._d or {}
        ruedas = [float(x) for x in (d.get("wearables") or {}).get("tires") or []]
    except Exception:
        return None
    ruedas = [x for x in ruedas if 0.0 < x <= 1.0]
    return min(ruedas) if len(ruedas) >= 4 else None


def _seguir_ruedas(vueltas):
    """
    Apunta el desgaste al cruzar cada meta y devuelve lo que se gasta por
    vuelta con el juego de ahora (o el ultimo medido), o None.
    Si la rueda vuelve a estar mas entera que antes, es que se cambiaron.
    """
    w = _peor_rueda()
    if w is None:
        return _rueda["ritmo"]
    previa = _rueda["previa"]
    if _rueda["inicio"] is None or (previa is not None and w > previa + 0.03):
        _rueda["inicio"] = (vueltas, w)        # juego nuevo (o recien abierto)
    _rueda["previa"] = w
    if vueltas != _rueda["ultima_vuelta"]:
        _rueda["ultima_vuelta"] = vueltas
        v0, w0 = _rueda["inicio"]
        if vueltas - v0 >= 2 and w0 > w:
            _rueda["ritmo"] = (w0 - w) / (vueltas - v0)
    return _rueda["ritmo"]


def vueltas_que_faltan(restante, ritmo, metros, largo):
    """
    Vueltas que nos quedan hasta la bandera, contando desde donde estamos:
    se acaba la vuelta en la que se agota el tiempo.
    """
    if restante is None or not ritmo:
        return None
    p = (metros / largo) if (largo and metros is not None) else 0.0
    p = min(max(p, 0.0), 0.999)
    hasta_meta = (1.0 - p) * ritmo
    if restante <= hasta_meta:
        return 1.0 - p
    return (1.0 - p) + math.ceil((restante - hasta_meta) / ritmo)


def combustible(d, largo):
    """
    {"paradas", "objetivo", "gasto", "ahorro", "compensa", "posible",
     "sobra"} o None si aun no se sabe lo que gastamos.
    """
    yo = d["yo"]
    comb = yo.get("combustible") or {}
    manda = comb.get("manda")
    gasto = (comb.get(manda) or {}).get("gasto") if manda else None
    quedan = comb.get("quedan")
    faltan = vueltas_que_faltan(d.get("restante"), d.get("ritmo"),
                                yo.get("metros"), largo)
    if not gasto or quedan is None or not faltan:
        return None
    hay = quedan * gasto                      # deposito de ahora (1 = lleno)
    necesita = faltan * gasto + MARGEN
    salida = {"gasto": gasto, "faltan": faltan, "que": manda}
    if necesita <= hay:
        salida.update(paradas=0, sobra=(hay - necesita) / gasto)
        return salida
    paradas = int(math.ceil(necesita - hay - 1e-9))   # cada parada, lleno
    salida["paradas"] = paradas
    # con una menos: todo lo que entra (lo de ahora + depositos llenos) entre
    # las vueltas que faltan
    objetivo = (hay + (paradas - 1) - MARGEN) / faltan
    ahorro = 1.0 - objetivo / gasto
    salida.update(objetivo=objetivo, ahorro=ahorro,
                  posible=0.0 < ahorro <= AHORRO_MAX)
    # Lo que se gana sin esa parada, repartido por vuelta: si el ahorro cuesta
    # menos que esto por vuelta, sale a cuenta.
    perdida = d.get("perdida")
    salida["compensa"] = perdida / faltan if perdida else None
    if paradas == 1:
        salida["ultima"] = ultima_parada(d, largo, gasto, quedan, faltan)
    return salida


VUELTAS_SOBRA = 2      # lo que el equipo deja de mas en el ultimo stint


def ultima_parada(d, largo, gasto, quedan, faltan):
    """
    En el penultimo stint: hasta cuanto llenar en la ULTIMA parada para
    acabar con VUELTAS_SOBRA vueltas de sobra (Manuel, 20/11/2026: el ultimo
    stint no se hace con el deposito lleno).

    El juego ya lo propone, pero con lo que hay EN ESE MOMENTO, no con lo que
    habra al entrar a boxes. Aqui se cuenta como sera: se para cuando no da
    para otra vuelta, con lo que sobre en el deposito; despues quedan las
    vueltas que falten.
    {"hasta": nivel al salir (1 = lleno), "vueltas_despues", "menu": lo que
     esta marcado en el menu de boxes o None}.
    """
    yo = d["yo"]
    p = (yo.get("metros") / largo) if (largo and yo.get("metros") is not None) else 0.0
    p = min(max(p, 0.0), 0.999)
    # `quedan` se cuenta desde la ultima meta: hasta boxes faltan las vueltas
    # enteras que da el deposito menos lo que ya llevamos de esta.
    hasta_boxes = max(0.0, math.floor(quedan) - p)
    despues = max(0.0, faltan - hasta_boxes)
    hasta = min(1.0, (despues + VUELTAS_SOBRA) * gasto)
    menu = (d.get("parada") or {}).get("energia_hasta")
    return {"hasta": hasta, "vueltas_despues": despues,
            "menu": menu if isinstance(menu, (int, float)) else None}


def nuevas_usadas(tabla, yo):
    """
    Ruedas NUEVAS que ha montado nuestro coche en la carrera, contando las de
    la salida: las paradas del juego (/rest/strategy/overall) dicen rueda a
    rueda si era nueva. None si no se sabe.
    """
    try:
        paradas = tabla._paradas_de(yo.get("api") or {})
    except Exception:
        return None
    if not paradas:
        return None
    # Si lo hemos visto parado en boxes y el juego aun no ha apuntado esa
    # parada, no se sabe: "?" mejor que un juego de mas. Tras 15 min se da
    # por buena la lista (seria un stop and go o algo sin ruedas).
    visto = getattr(tabla, "parado_en", {}).get(yo.get("clave"))
    if visto:
        vuelta, cuando = visto
        apuntada = any(int((p or {}).get("lap") or 0) >= vuelta - 1 for p in paradas[1:])
        if not apuntada and time.monotonic() - cuando < 15 * 60:
            return "pendiente"
    n = 0
    for p in paradas:
        for r in ((p or {}).get("tyres") or {}).values():
            if isinstance(r, dict) and r.get("new"):
                n += 1
    return n


def ruedas(d, tabla, limite, paradas, ruedas_carrera=0):
    """
    {"desgaste", "peor", "aguanta_juego", "aguantan_estas", "stints_juego",
     "juegos_quedan", "hacen_falta"} con lo que se sepa, o None.
    `limite`: lo minimo que se quiere en la peor rueda (0.60).
    """
    yo = d["yo"]
    desgaste = _seguir_ruedas(yo.get("vueltas") or 0)
    peor = _peor_rueda()
    salida = {"peor": peor, "desgaste": desgaste, "limite": limite}

    # Las que quedan: las de la carrera (las pone el usuario en Opciones; el
    # juego lo ensena en su ventana de neumaticos, "8 Ruedas nuevas", pero no
    # lo publica en la API) menos las nuevas que ya se han montado. El ajuste
    # del servidor (SESSSET_tires_available_in_garage, 56) es para TODO el
    # fin de semana y daba "quedan 11 juegos" con 2 (Paul Ricard, 21/11/2026).
    if ruedas_carrera:
        usadas = nuevas_usadas(tabla, yo)
        if usadas == "pendiente":
            salida["juegos_pendiente"] = True
        elif usadas is not None:
            salida["juegos_quedan"] = max(0.0, (ruedas_carrera - usadas) / 4.0)

    if desgaste and desgaste > 0:
        salida["aguanta_juego"] = (1.0 - limite) / desgaste
        if peor is not None:
            salida["aguantan_estas"] = max(0.0, (peor - limite) / desgaste)
        gasto = ((yo.get("combustible") or {}).get(
            (yo.get("combustible") or {}).get("manda")) or {}).get("gasto")
        if gasto:
            salida["stints_juego"] = salida["aguanta_juego"] * gasto
        faltan = vueltas_que_faltan(d.get("restante"), d.get("ritmo"),
                                    yo.get("metros"), tabla.info.get("lapDistance"))
        if faltan is not None and salida.get("aguantan_estas") is not None:
            resto = faltan - salida["aguantan_estas"]
            salida["hacen_falta"] = (0 if resto <= 0 else
                                     int(math.ceil(resto / salida["aguanta_juego"])))
    salida["paradas"] = paradas
    if (peor is None and desgaste is None and "juegos_quedan" not in salida
            and not salida.get("juegos_pendiente")):
        return None
    return salida


def calcular(tabla, d, limite=0.60, ruedas_carrera=0):
    if not d or d.get("falta"):
        return None
    largo = tabla.info.get("lapDistance")
    c = combustible(d, largo)
    paradas = c["paradas"] if c else None
    return {"combustible": c, "ruedas": ruedas(d, tabla, limite, paradas, ruedas_carrera)}
