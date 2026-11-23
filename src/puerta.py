
"""Consola P1 Norte, P2 Sur o P3 Este."""

import argparse
import threading

from comun import Proceso, cargar_config, pedir

NOMBRES = {1: "Norte", 2: "Sur", 3: "Este"}


def mostrar(respuesta):
    if respuesta is None:
        print("SIN COORDINADOR: se deniega la operacion para conservar el aforo")
        return
    print(f"{respuesta['resultado']}: {respuesta['motivo']}")
    print(f"Dentro: {respuesta['dentro']}/{respuesta['aforo']}")
    estados = respuesta.get("puertas", {})
    print("Puertas: " + ", ".join(
        f"P{p}={estados.get(str(p), 'DESCONOCIDA')}" for p in (1, 2, 3)
    ))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("puerta", type=int, choices=(1, 2, 3))
    parser.add_argument("--token-falso", action="store_true", help="Prueba de autenticacion E2")
    args = parser.parse_args()

    config = cargar_config()
    proceso = Proceso(args.puerta)
    detener = threading.Event()

    def latidos():
        while not detener.is_set():
            pedir(config, proceso, args.puerta, "LATIDO")
            if detener.wait(config["latido"]):
                break

    threading.Thread(target=latidos, daemon=True).start()
    print(f"Puerta P{args.puerta} - {NOMBRES[args.puerta]}")
    print("Ordenes: entrar, salir, estado, fin")
    try:
        while True:
            orden = input("puerta> ").strip().lower()
            if orden == "fin":
                break
            if orden not in ("entrar", "salir", "estado"):
                print("Escribe entrar, salir, estado o fin")
                continue
            token = "token_incorrecto" if args.token_falso else None
            respuesta = pedir(config, proceso, args.puerta, orden.upper(), token=token)
            mostrar(respuesta)
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        detener.set()
        print("Puerta detenida")


if __name__ == "__main__":
    main()
