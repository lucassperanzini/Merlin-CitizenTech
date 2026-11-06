"""Mede a precisão e o tempo do classificador de intenções com o modelo de IA de verdade (Ollama).

Uso:  .venv\\Scripts\\python.exe ferramentas\\avaliar_classificador.py [modelo] [uma|duas|ambas]

Rode antes e depois de mexer nos prompts ou nas habilidades: se o número de acertos cair, algo piorou.
"""
import inspect
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from frases_avaliacao import FRASES  # noqa: E402

from merlin.ia.cliente import ClienteIA  # noqa: E402
from merlin.ia.intencoes import ClassificadorIntencao  # noqa: E402


def avaliar(classificador, rotulo):
    classificador.classificar("oi")  # carrega o modelo antes de medir
    acertos, tempos, erros = 0, [], []
    for frase, esperada, alvo in FRASES:
        inicio = time.perf_counter()
        intencao = classificador.classificar(frase)
        tempos.append(time.perf_counter() - inicio)
        certo = intencao.tipo.value == esperada and (alvo is None or intencao.alvo.lower() == alvo)
        acertos += certo
        if not certo:
            erros.append(f"   {frase!r}: esperado {esperada}{f' ({alvo})' if alvo else ''}, "
                         f"veio {intencao.tipo.value} ({intencao.alvo})")
    tempos.sort()
    print(f"{rotulo}: {acertos}/{len(FRASES)} acertos | média {sum(tempos) / len(tempos):.2f} s | "
          f"mais lenta {tempos[-1]:.2f} s")
    print("\n".join(erros) if erros else "   sem erros")
    return acertos


def main():
    modelo = sys.argv[1] if len(sys.argv) > 1 else "qwen3:8b"
    modo = sys.argv[2] if len(sys.argv) > 2 else "ambas"
    cliente = ClienteIA(lambda: modelo)
    print(f"Modelo: {modelo} | {len(FRASES)} frases")
    if "duas_etapas" not in inspect.signature(ClassificadorIntencao).parameters:  # versão antiga, sem etapas
        avaliar(ClassificadorIntencao(cliente), "classificador")
        return
    if modo in ("uma", "ambas"):
        avaliar(ClassificadorIntencao(cliente, duas_etapas=False), "uma etapa ")
    if modo in ("duas", "ambas"):
        avaliar(ClassificadorIntencao(cliente, duas_etapas=True), "duas etapas")


if __name__ == "__main__":
    main()
