from itertools import cycle
import matplotlib.pyplot as plt
import numpy as np
from core import (
    MARCADORES_PADRAO,
    aplicar_ajustes_eixos_e_legenda,
    estilar_figura_e_eixos,
    extrair_ciclos_gcd,
    processar_cabecalho_e_dados,
)


def gerar_plot_gcd(
    fonte_dados,
    eixo_x_label,
    eixo_y_label,
    mapa_cores,
    mapa_estilos,
    mapa_nomes,
    limites_manuais,
    posicao_legenda,
    tema,
    idioma="Português",
    exibir_delta_e=True,
    delta_e_texto=r"$\Delta E$",
    delta_e_x_frac=0.40,
    delta_e_y_topo=0.58,
    delta_e_y_base=0.46,
    delta_e_lado_texto="Direita / Right",
    modo_tracado="Linhas (Lines)"
, legenda_horizontal=False):
    df, _ = processar_cabecalho_e_dados(fonte_dados)
    ciclos = extrair_ciclos_gcd(fonte_dados, df)

    fig, ax = plt.subplots(figsize=(8.6, 5.4), dpi=300)
    todos_x, todos_y = [], []

    usar_linha = ("Lines" in modo_tracado)
    usar_pontos = ("Scatter" in modo_tracado)
    marcadores_ciclo = cycle(MARCADORES_PADRAO)

    for idx, c in enumerate(ciclos):
        chave = c["nome"]
        cor = mapa_cores.get(chave, list(mapa_cores.values())[idx % len(mapa_cores)])
        estilo = mapa_estilos.get(chave, "-")
        rotulo = mapa_nomes.get(chave, chave)
        marcador = next(marcadores_ciclo)

        if len(c["x_chg"]) > 0:
            if usar_linha:
                ax.plot(c["x_chg"], c["y_chg"], color=cor, linewidth=2.1, linestyle=estilo, label=rotulo, zorder=4)
            if usar_pontos:
                lbl_s = None if usar_linha else rotulo
                ax.scatter(c["x_chg"], c["y_chg"], color=cor, s=26, marker=marcador, edgecolors=tema["marker_edge"], linewidths=0.5, label=lbl_s, zorder=5)
            todos_x.append(c["x_chg"])
            todos_y.append(c["y_chg"])

        if len(c["x_dchg"]) > 0:
            lbl = None if len(c["x_chg"]) > 0 else rotulo
            if usar_linha:
                ax.plot(c["x_dchg"], c["y_dchg"], color=cor, linewidth=2.1, linestyle=estilo, label=lbl, zorder=4)
            if usar_pontos:
                lbl_s = None if usar_linha else lbl
                ax.scatter(c["x_dchg"], c["y_dchg"], color=cor, s=26, marker=marcador, edgecolors=tema["marker_edge"], linewidths=0.5, label=lbl_s, zorder=5)
            todos_x.append(c["x_dchg"])
            todos_y.append(c["y_dchg"])

    x_all = np.concatenate(todos_x) if todos_x else np.array([0.0, 1.0])
    y_all = np.concatenate(todos_y) if todos_y else np.array([0.0, 1.0])
    x_min, x_max = np.min(x_all), np.max(x_all)
    y_min, y_max = np.min(y_all), np.max(y_all)
    span_x = max(x_max - x_min, 1e-6)
    span_y = max(y_max - y_min, 1e-6)

    if exibir_delta_e:
        y_topo_ajustado = max(delta_e_y_topo, delta_e_y_base + 0.02)
        ax.annotate(
            "",
            xy=(delta_e_x_frac, y_topo_ajustado),
            xytext=(delta_e_x_frac, delta_e_y_base),
            xycoords="axes fraction",
            textcoords="axes fraction",
            arrowprops=dict(arrowstyle="<->", color=tema["text"], lw=1.5, shrinkA=0, shrinkB=0),
            zorder=7
        )
        if delta_e_texto:
            offset_x = 0.018 if "Direita" in delta_e_lado_texto else -0.018
            alinhamento_h = "left" if "Direita" in delta_e_lado_texto else "right"
            y_meio = (y_topo_ajustado + delta_e_y_base) / 2.0
            ax.text(
                delta_e_x_frac + offset_x,
                y_meio,
                delta_e_texto,
                transform=ax.transAxes,
                fontsize=11.0,
                fontweight="bold",
                color=tema["text"],
                va="center",
                ha=alinhamento_h,
                zorder=8
            )

    ax.set_xlabel(eixo_x_label, fontsize=12.5, labelpad=8)
    ax.set_ylabel(eixo_y_label, fontsize=12.5, labelpad=8)
    ax.set_xlim(min(0, x_min - span_x * 0.03), x_max + span_x * 0.14)
    ax.set_ylim(y_min, y_max + span_y * 0.08)
    ax.grid(True, linestyle=":", alpha=0.4, color=tema["grid"])

    aplicar_ajustes_eixos_e_legenda(ax, limites_manuais, posicao_legenda, tema, legenda_horizontal=legenda_horizontal)
    estilar_figura_e_eixos(fig, ax, tema, idioma=idioma)
    plt.tight_layout()
    return fig
