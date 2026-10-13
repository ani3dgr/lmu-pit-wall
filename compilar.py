# -*- coding: utf-8 -*-
"""
Compila el programa y prepara el ZIP que se reparte.

Se ejecuta a mano cuando toca sacar una version:

    python compilar.py

Deja en dist/ la carpeta lista y un ZIP al lado. Quien lo descargue solo tiene
que descomprimirlo donde quiera y abrir MapaLMU.exe: no hay que instalar nada,
ni siquiera Python.

QUE VA DENTRO DEL EJECUTABLE Y QUE NO
  Dentro van el codigo y Python. Fuera, al lado del .exe, van los circuitos,
  los idiomas y la tabla de coches, para que se puedan cambiar, compartir y
  ampliar sin volver a compilar. Esa es la gracia: alguien escanea Monza y lo
  pasa por WhatsApp, y el que lo recibe lo copia en su carpeta y ya esta.
"""
import os
import shutil
import subprocess
import sys
import zipfile

AQUI = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(AQUI, "dist")
BUILD = os.path.join(AQUI, "build")
CARPETA_FINAL = os.path.join(DIST, "MapaLMU")

VERSION = "1.10.5"

# Lo que se copia al lado del .exe. Carpetas y archivos sueltos.
#
# coches.json NO va, aunque parezca que deberia. Es el unico archivo que el
# programa escribe y que ademas viajaba dentro del ZIP: quien actualizara
# descomprimiendo encima perdia las correcciones que hubiera hecho a mano. Y
# tampoco se pierde gran cosa por no repartirlo, porque los coches se
# identifican solos con el catalogo que sale de los resultados del juego
# (resultados.py); esto son solo retoques a mano, y encima van por nombre de
# equipo, que online se lo pone cada uno como quiere.
# el manual (manual_*.json) va suelto por lo mismo que reglas.json: es
# texto, y quien sepa de reglajes tiene que poder corregirlo o traducirlo
# sin recompilar. Si el de conduccion aun no existe, compilar.py avisa y
# sigue.
# reglas.json es la tabla del ingeniero y va suelta, fuera del .exe, a
# proposito: es el conocimiento del programa y tiene que poder tocarlo
# quien sepa de reglajes sin recompilar nada. calibracion.json NO va:
# lo genera cada uno con SUS reglajes, y ademas cambia de un ordenador
# a otro segun los coches que tenga.
# los sonidos van sueltos para que cualquiera pueda dejar el suyo en la
# carpeta y que salga en la lista sin recompilar nada.
ACOMPANA = ["circuitos", "idiomas", "sonidos", "reglas.json",
            "manual_reglajes.json", "manual_conduccion.json",
            "INSTRUCCIONES.txt", "README.md"]

# Lo que NO se copia aunque este en esas carpetas.
# catalogo_coches.json lo monta cada programa leyendo los resultados de SU
# juego: si se repartiera el mio, todo el mundo empezaria con mis carreras
# dentro. Aparece en dist/ en cuanto se prueba el .exe compilado, asi que
# tiene que estar aqui o se colaria en el ZIP de la siguiente compilacion.
BASURA = ("__pycache__", ".pyc", ".bak", ".antes", ".orig",
          "catalogo_coches.json", "calibracion.json",
          "historial_reglajes.json", "fichas_coches.json")


# Lo que en dist/MapaLMU es DEL USUARIO y no del programa. Compilar borra esa
# carpeta entera, asi que esto se aparta antes y se devuelve despues del ZIP.
# Se aprende por las malas: una compilacion se llevo por delante las vueltas
# grabadas de una sesion de pruebas, que no estaban en ningun otro sitio.
# copias_reglajes son los reglajes originales que guarda la biblioteca antes
# de tocarles nada. Van aqui por lo mismo que las sesiones: son de quien usa
# el programa, y encima puede que los haya pagado.
MIO = ["sesiones", "escaneos", "copias_reglajes", "mapa_config.json",
       "ruta_juego.txt", "idioma.txt", "catalogo_coches.json",
       "coches.json", "historial_reglajes.json", "fichas_coches.json"]

GUARDADO = os.path.join(AQUI, ".mio_mientras_compilo")


def apartar_lo_mio():
    """Saca lo del usuario de dist antes de que el rmtree se lo lleve."""
    if os.path.isdir(GUARDADO):
        shutil.rmtree(GUARDADO)
    salvados = []
    for cosa in MIO:
        origen = os.path.join(CARPETA_FINAL, cosa)
        if not os.path.exists(origen):
            continue
        os.makedirs(GUARDADO, exist_ok=True)
        shutil.move(origen, os.path.join(GUARDADO, cosa))
        salvados.append(cosa)
    if salvados:
        print("  guardado lo tuyo    : %s" % ", ".join(salvados))
    return salvados


def devolver_lo_mio():
    """
    Lo devuelve DESPUES del ZIP, nunca antes.

    Antes del ZIP se colaria dentro y se repartirian los ajustes y las vueltas
    de uno mismo. Si ya existe el del programa recien copiado, manda el del
    usuario: es el que tiene sus cosas dentro.
    """
    if not os.path.isdir(GUARDADO):
        return
    for cosa in sorted(os.listdir(GUARDADO)):
        destino = os.path.join(CARPETA_FINAL, cosa)
        if os.path.isdir(destino):
            shutil.rmtree(destino)
        elif os.path.isfile(destino):
            os.remove(destino)
        shutil.move(os.path.join(GUARDADO, cosa), destino)
        print("  devuelto            : %s" % cosa)
    shutil.rmtree(GUARDADO, ignore_errors=True)


def limpio(nombre):
    return not any(nombre.endswith(b) or nombre == b for b in BASURA)


def paso(texto):
    print()
    print("=" * 68)
    print("  " + texto)
    print("=" * 68)


def abierto():
    """
    Los ejecutables que esten corriendo ahora mismo.

    Hace falta mirarlo ANTES de borrar nada. Windows no deja borrar un archivo
    en uso, pero rmtree no lo sabe hasta que se topa con el: para entonces ya
    ha borrado media carpeta y lo que queda es un ejecutable descuartizado que
    arranca y suelta "Failed to start embedded python interpreter". Ha pasado,
    y cuesta un rato entender que el fallo no estaba en el codigo.
    """
    corriendo = []
    for nombre in ("MapaLMU.exe", "MapaLMU-consola.exe"):
        try:
            salida = subprocess.check_output(
                ["tasklist", "/fi", "imagename eq " + nombre],
                text=True, errors="replace")
        except (OSError, subprocess.SubprocessError):
            continue          # sin tasklist no se puede saber; que siga
        if nombre.lower() in salida.lower():
            corriendo.append(nombre)
    return corriendo


def compilar():
    paso("COMPILANDO")
    corriendo = abierto()
    if corriendo:
        raise SystemExit(
            "\n  NO PUEDO COMPILAR: tienes abierto %s.\n"
            "  Cierralo y vuelve a lanzar la compilacion.\n"
            "  (No he borrado nada: la carpeta dist sigue como estaba.)"
            % " y ".join(corriendo))
    apartar_lo_mio()
    for carpeta in (BUILD, DIST):
        if os.path.isdir(carpeta):
            shutil.rmtree(carpeta)
    orden = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
             os.path.join(AQUI, "MapaLMU.spec")]
    if subprocess.call(orden, cwd=AQUI) != 0:
        raise SystemExit("PyInstaller ha fallado")


def acompanar():
    paso("COPIANDO LO QUE VA FUERA DEL EJECUTABLE")
    for cosa in ACOMPANA:
        origen = os.path.join(AQUI, cosa)
        destino = os.path.join(CARPETA_FINAL, cosa)
        if os.path.isdir(origen):
            shutil.copytree(origen, destino,
                            ignore=shutil.ignore_patterns(*BASURA))
            n = len(os.listdir(destino))
            print("  %-20s carpeta con %d archivos" % (cosa, n))
        elif os.path.isfile(origen):
            shutil.copy2(origen, destino)
            print("  %-20s %d KB" % (cosa, os.path.getsize(origen) / 1024))
        else:
            print("  %-20s NO EXISTE, me lo salto" % cosa)


def primeros_pasos():
    """Un papel corto encima de todo, que es lo unico que la gente lee."""
    texto = """MAPA DE PISTA PARA LE MANS ULTIMATE
===================================

QUE HAY QUE HACER (dos minutos)

  1. Descomprime esta carpeta DONDE QUIERAS: el escritorio, documentos,
     donde te venga bien. NO la metas en "Archivos de programa": Windows
     no deja escribir ahi y el programa necesita guardar sus cosas.

  2. En Le Mans Ultimate:
       - Ajustes -> Video: pon la pantalla en BORDERLESS (ventana sin
         bordes). Es obligatorio; a pantalla completa Windows no deja
         poner nada encima del juego.
       - Ajustes -> HUD: quita el mapa que trae el juego, o tendras dos.

  3. Abre MapaLMU.exe

     La primera vez Windows puede decir "Windows protegio tu PC". Es
     porque el programa no esta firmado (firmarlo cuesta dinero). Pulsa
     "Mas informacion" y luego "Ejecutar de todas formas".

SI YA TENIAS UNA VERSION ANTERIOR

  Descomprime el ZIP ENCIMA de la carpeta que ya tenias, diciendo que
  si a reemplazar. NO la borres antes.

  No pierdes nada de lo tuyo: tus pistas escaneadas, tus vueltas
  grabadas ("sesiones"), los colores, el sitio donde tengas puesto el
  mapa y el idioma se quedan como estaban. Lo unico que se sustituye
  es el programa y los circuitos que vengan con el.

MIENTRAS JUEGAS

  F9   oculta o muestra el mapa
  F10  abre las opciones
  F11  dice cual de los coches es el tuyo

LA BOLA DE FUERZAS G (nueva)

  Una circunferencia con un punto que se va hacia donde tira el peso
  del coche: arriba al frenar, abajo al acelerar y hacia fuera en las
  curvas. Viene APAGADA: se enciende en Opciones -> En pista ->
  Fuerzas G, y se arrastra con el raton a donde quieras.

  Con las opciones abiertas puedes arrastrar el mapa con el raton.

  Lo normal es que el juego diga cual es tu coche y no haya que tocar
  nada. Pero si entras de espectador, o coges el coche en un relevo,
  el juego no lo dice: entonces sale un aviso en rojo encima del mapa
  y con F11 lo eliges de la lista.

EL IDIOMA

  Opciones -> pestana "Acerca de" -> Idioma. Estan espanol, ingles,
  frances, italiano, aleman, portugues y polaco.

LO DEMAS

  Cada pestana de las opciones lleva un boton (i) que explica lo que
  hay dentro. Y en INSTRUCCIONES.txt esta el manual entero.

COMPARTIR CIRCUITOS

  Cada circuito medido es un archivo suelto de la carpeta "circuitos".
  Para pasarle una pista a alguien le mandas ese archivo y lo copia en
  su carpeta "circuitos". El programa lo detecta al arrancar.

DE DONDE SALE ESTO

  Pagina del programa, donde esta siempre la ultima version:
  https://github.com/ani3dgr/mapa-lmu

  Ahi tambien se pueden pedir cosas o avisar de fallos.

Es gratuito. Usalo y pasalo a quien quieras.
Apoya a CicloTracker y nos ayudas a seguir creando proyectos: ciclotracker.com
"""
    ruta = os.path.join(CARPETA_FINAL, "LEEME PRIMERO.txt")
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(texto)
    print("  LEEME PRIMERO.txt")

    # Un boton de revision: si a alguien no le funciona, hace doble clic aqui
    # y manda una foto de lo que sale. Se ve enseguida que le falta.
    lineas = ["@echo off",
              "title Revision del mapa de pista",
              'cd /d "%~dp0"',
              "MapaLMU-consola.exe comprobar"]
    ruta = os.path.join(CARPETA_FINAL, "COMPROBAR SI ALGO NO VA.bat")
    with open(ruta, "w", encoding="utf-8", newline="\r\n") as f:
        f.write("\n".join(lineas) + "\n")
    print("  COMPROBAR SI ALGO NO VA.bat")


def comprimir():
    paso("HACIENDO EL ZIP")
    nombre = os.path.join(DIST, "MapaLMU-%s.zip" % VERSION)
    if os.path.isfile(nombre):
        os.remove(nombre)
    with zipfile.ZipFile(nombre, "w", zipfile.ZIP_DEFLATED) as z:
        for raiz, carpetas, archivos in os.walk(CARPETA_FINAL):
            carpetas[:] = [c for c in carpetas if limpio(c)]
            for archivo in archivos:
                if not limpio(archivo):
                    continue
                completo = os.path.join(raiz, archivo)
                dentro = os.path.relpath(completo, DIST)
                z.write(completo, dentro)
    print("  %s   (%.1f MB)" % (nombre, os.path.getsize(nombre) / 1048576.0))
    return nombre


def main():
    compilar()
    acompanar()
    primeros_pasos()
    zip_final = comprimir()
    devolver_lo_mio()

    paso("LISTO")
    print("  Carpeta : %s" % CARPETA_FINAL)
    print("  ZIP     : %s" % zip_final)
    print()
    print("  Pruebalo antes de repartirlo: abre el .exe de la carpeta dist,")
    print("  no el de aqui. Si algo falla sera por una ruta, y se ve enseguida.")


if __name__ == "__main__":
    main()
