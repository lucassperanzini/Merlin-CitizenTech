"""Ações sobre o próprio Merlin: dispensar (fica em espera) e encerrar (fecha o programa)."""


class Dispensar:
    def __init__(self, locutor, sessao):
        self._locutor = locutor
        self._sessao = sessao

    def __call__(self, _intencao) -> None:
        self._locutor.falar("Até mais. Estarei por aqui se precisar.")
        self._sessao.desativar()


class Encerrar:
    def __init__(self, locutor, estado):
        self._locutor = locutor
        self._estado = estado

    def __call__(self, _intencao) -> None:
        self._locutor.falar("Encerrando todos os sistemas. Até logo.")
        self._estado.encerrando.set()
