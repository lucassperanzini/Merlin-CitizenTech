"""Estado compartilhado entre as threads de escuta, de comandos e da janela."""
import queue
import threading
import time


class EstadoAssistente:
    def __init__(self):
        self.ativo = threading.Event()  # o Merlin foi chamado e a janela está aberta
        self.falando = threading.Event()  # evita que ele escute a própria voz
        self.reproduzindo = threading.Event()  # o áudio está saindo pelas caixas de som (só aí dá para interromper)
        self.interromper = threading.Event()  # a pessoa falou por cima: a fala atual deve parar
        self.encerrando = threading.Event()  # o programa deve fechar
        self.microfone_desligado = threading.Event()  # botão de mudo da janela: nada do que é falado é ouvido
        self.fila_comandos = queue.Queue()  # frases reconhecidas, à espera de processamento
        self._ultima_atividade = time.time()
        self._nivel_voz = 0.0  # maior volume captado desde a última leitura da janela (0 a 1)
        self._microfone_mudo_ate = 0.0

    def silenciar_microfone(self, segundos: float) -> None:
        self._microfone_mudo_ate = time.time() + segundos

    def microfone_mudo(self) -> bool:
        """Verdadeiro enquanto sai das caixas de som algo que o reconhecimento não deve ouvir."""
        return self.falando.is_set() or time.time() < self._microfone_mudo_ate

    def registrar_atividade(self) -> None:
        self._ultima_atividade = time.time()

    def segundos_sem_atividade(self) -> float:
        return time.time() - self._ultima_atividade

    def registrar_nivel(self, nivel: float) -> None:
        self._nivel_voz = max(self._nivel_voz, nivel)

    def consumir_nivel(self) -> float:
        nivel, self._nivel_voz = self._nivel_voz, 0.0
        return nivel
