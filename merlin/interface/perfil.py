"""Perfis de uso: o operador usa o assistente; só o administrador muda como a IA decide e age.

O perfil vem do campo "perfil" do merlin_config.json e vale ao abrir o Merlin. Sem o campo, ou com qualquer outro
valor, a máquina fica no perfil operador: quem instala escolhe abrir, e não o contrário.
"""
import logging

logger = logging.getLogger(__name__)

AVISO_SO_ADMINISTRADOR = ("Só o administrador pode mudar isso. Peça à equipe responsável pelo Merlin "
                          "(o perfil fica no arquivo merlin_config.json).")


def so_administrador(api, administrador: bool):
    """A própria api para o administrador. Para o operador, uma cópia com as mesmas funções, todas recusando.

    A página continua achando as funções (o pywebview só expõe o que existe), mas nenhuma muda nada: o bloqueio
    vale mesmo que alguém chame a função sem passar pela tela.
    """
    if administrador:
        return api
    nomes = [n for n in dir(api) if not n.startswith("_") and callable(getattr(api, n))]

    def recusar(nome):
        def funcao(self, *args, **kwargs):
            logger.warning("[PERFIL] Pedido recusado no perfil operador: %s.%s", type(api).__name__, nome)
            return {"erro": AVISO_SO_ADMINISTRADOR}
        return funcao

    bloqueada = type(f"{type(api).__name__}SoAdministrador", (), {n: recusar(n) for n in nomes})
    return bloqueada()
