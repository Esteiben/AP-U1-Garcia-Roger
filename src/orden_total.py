
"""Combina logs/0.log ... logs/3.log, ordenando por (lamport, id)."""

from comun import RAIZ


def main():
    carpeta = RAIZ / "logs"
    eventos = []
    for proceso in (0, 1, 2, 3):
        archivo = carpeta / f"{proceso}.log"
        if not archivo.exists():
            print(f"AVISO: falta {archivo.name}")
            continue
        for numero, linea in enumerate(archivo.read_text(encoding="utf-8").splitlines(), 1):
            partes = linea.split(";", 3)
            try:
                if len(partes) != 4:
                    raise ValueError("faltan campos")
                lamport, identificador = int(partes[0]), int(partes[1])
                eventos.append(((lamport, identificador), linea))
            except ValueError:
                print(f"Linea ignorada: {archivo.name}:{numero}")

    eventos.sort(key=lambda elemento: elemento[0])
    salida = carpeta / "orden_total.log"
    salida.write_text(
        "\n".join(linea for _, linea in eventos) + ("\n" if eventos else ""),
        encoding="utf-8",
    )
    print(f"Generado {salida} ({len(eventos)} eventos)")


if __name__ == "__main__":
    main()
