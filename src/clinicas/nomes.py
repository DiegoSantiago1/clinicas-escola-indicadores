"""Nomes fictícios de pacientes e alunos, montados a partir de nomes e sobrenomes comuns no Brasil."""

import numpy as np

NOMES_F = [
    "Maria", "Ana", "Juliana", "Fernanda", "Patrícia", "Aline", "Camila", "Amanda", "Bruna", "Jéssica",
    "Letícia", "Mariana", "Larissa", "Gabriela", "Beatriz", "Rafaela", "Vanessa", "Débora", "Luana", "Tatiane",
    "Cláudia", "Rosângela", "Severina", "Josefa", "Lúcia", "Sandra", "Adriana", "Márcia", "Simone", "Renata",
    "Isabela", "Lívia", "Natália", "Carolina", "Priscila", "Elaine", "Joana", "Raquel", "Sofia", "Helena",
]
NOMES_M = [
    "José", "João", "Antônio", "Francisco", "Carlos", "Paulo", "Pedro", "Lucas", "Luiz", "Marcos",
    "Gabriel", "Rafael", "Daniel", "Marcelo", "Bruno", "Eduardo", "Felipe", "Rodrigo", "Gustavo", "Thiago",
    "Severino", "Manoel", "Sebastião", "Edson", "Fábio", "Leandro", "Diego", "André", "Vinícius", "Matheus",
    "Henrique", "Igor", "Caio", "Renato", "Alexandre", "Sérgio", "Cícero", "Davi", "Arthur", "Heitor",
]
SOBRENOMES = [
    "Silva", "Santos", "Oliveira", "Souza", "Lima", "Pereira", "Ferreira", "Costa", "Rodrigues", "Almeida",
    "Nascimento", "Alves", "Carvalho", "Araújo", "Ribeiro", "Barbosa", "Cavalcanti", "Albuquerque", "Melo",
    "Gomes", "Freitas", "Monteiro", "Moura", "Vasconcelos", "Barros", "Lins", "Correia", "Batista", "Farias",
    "Bezerra", "Tavares", "Siqueira", "Andrade", "Pontes", "Queiroz", "Rocha", "Mendes", "Teixeira", "Brito",
]


def gerar_nome(rng: np.random.Generator, sexo: str) -> str:
    primeiros = NOMES_F if sexo == "F" else NOMES_M
    primeiro = primeiros[int(rng.integers(len(primeiros)))]
    s1, s2 = rng.choice(len(SOBRENOMES), 2, replace=False)
    if rng.random() < 0.35:
        return f"{primeiro} {SOBRENOMES[s1]}"
    return f"{primeiro} {SOBRENOMES[s1]} {SOBRENOMES[s2]}"


def gerar_nomes_unicos(rng: np.random.Generator, quantidade: int) -> list[str]:
    """Nomes sem repetição (os alunos são procurados pelo nome nas planilhas)."""
    vistos: set[str] = set()
    saida: list[str] = []
    while len(saida) < quantidade:
        sexo = "F" if rng.random() < 0.7 else "M"
        primeiros = NOMES_F if sexo == "F" else NOMES_M
        primeiro = primeiros[int(rng.integers(len(primeiros)))]
        s1, s2 = rng.choice(len(SOBRENOMES), 2, replace=False)
        nome = f"{primeiro} {SOBRENOMES[s1]} {SOBRENOMES[s2]}"
        if nome not in vistos:
            vistos.add(nome)
            saida.append(nome)
    return saida
