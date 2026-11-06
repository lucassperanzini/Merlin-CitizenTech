"""Pesquisar na internet: abre a pesquisa (ou o site pedido) no navegador."""
from merlin.habilidades import grupos
from merlin.habilidades.base import Campo, Correcao, Exemplo, Habilidade


def regra(leitura):
    """O alvo da ação é o termo a pesquisar; sem termo, pesquisa a frase inteira."""
    busca = leitura.campos.get("busca", "")
    if busca:
        return Correcao("pesquisar_web", alvo=busca)
    return Correcao("pesquisar_web", "o modelo não deu o termo da busca: uso a frase inteira", alvo=leitura.comando)


def criar_acao(recursos):
    from merlin.acoes.web import PesquisarWeb
    return recursos.compartilhado("pesquisa_web", PesquisarWeb)


HABILIDADE = Habilidade(
    nome="pesquisar_web",
    grupo=grupos.INTERNET,
    ordem=30,
    descricao="a pessoa manda pesquisar ou procurar algo na internet, ou abrir um site.",
    campos=(Campo("busca", "o termo completo a pesquisar, ou o endereço quando for abrir um site"),),
    exemplos=(
        Exemplo("pesquise receitas de pão", "receitas de pão", campos={"busca": "receitas de pão"}),
        Exemplo("procura na internet como sair do nano", "nano", campos={"busca": "como sair do nano"}),
        Exemplo("abre o site da globo", "globo", campos={"busca": "globo.com"}),
        Exemplo("entra no github", "github", campos={"busca": "github.com"}),
    ),
    regra=regra,
    mexe_no_computador=True,
    criar_acao=criar_acao,
)
