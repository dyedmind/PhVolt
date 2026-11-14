from itertools import cycle
import matplotlib.pyplot as plt
import numpy as np
from core import (
    MARCADORES_PADRAO,
    aplicar_ajustes_eixos_e_legenda,
    estilar_figura_e_eixos,
    processar_cabecalho_e_dados,
)


def gerar_plot_cv(
    fonte_dados, velocidade, eixo_x_label, eixo_y_label, tag_carga, tag_descarga,
    mapa_cores, mapa_estilos, mapa_nomes, limites_manuais, posicao_legenda, tema,
    idioma="Português", exibir_setas=True, pos_carga=(0.35, 0.58), pos_descarga=(0.65, 0.38),
    modo_tracado="Linhas (Lines)", pos_velocidade=(0.04, 0.93), legenda_horizontal=False, **_kwargs
):
    df, tokens_limpos = processar_cabecalho_e_dados(fonte_dados)
    num_cols = df.shape[1]
    curvas = []

    if num_cols >= 2 and num_cols % 2 == 0:
        nomes_y = [tokens_limpos[k] for k in range(1, len(tokens_limpos), 2)] if len(tokens_limpos) >= 2 else tokens_limpos
        for idx, col in enumerate(range(0, num_cols, 2)):
            sub = df.iloc[:, [col, col + 1]].dropna(how="all")
            if len(sub) == 0:
                continue
            nome = nomes_y[idx] if idx < len(nomes_y) else f"Sample {idx + 1}"
            curvas.append({"nome": str(nome).strip(), "E": sub.iloc[:, 0].to_numpy(float), "I": sub.iloc[:, 1].to_numpy(float)})
    else:
        nomes_y = tokens_limpos[1:] if len(tokens_limpos) >= num_cols else tokens_limpos
        for col in range(1, num_cols):
            sub = df.iloc[:, [0, col]].dropna(how="all")
            if len(sub) == 0:
                continue
            nome = nomes_y[col - 1] if (col - 1) < len(nomes_y) else f"Sample {col}"
            curvas.append({"nome": str(nome).strip(), "E": sub.iloc[:, 0].to_numpy(float), "I": sub.iloc[:, 1].to_numpy(float)})

    fig, ax = plt.subplots(figsize=(8.4, 5.4), dpi=300)
    todos_e = np.concatenate([c["E"][~np.isnan(c["E"])] for c in curvas if len(c["E"]) > 0])
    todos_i = np.concatenate([c["I"][~np.isnan(c["I"])] for c in curvas if len(c["I"]) > 0])
    e_min, e_max = np.nanmin(todos_e), np.nanmax(todos_e)
    i_min, i_max = np.nanmin(todos_i), np.nanmax(todos_i)

    usar_linha = ("Lines" in modo_tracado)
    usar_pontos = ("Scatter" in modo_tracado)
    marcadores_ciclo = cycle(MARCADORES_PADRAO)

    ax.axhline(0, color=tema["ref_line"], linestyle="--", linewidth=1.1, alpha=0.7)
    for idx, c in enumerate(curvas):
        chave = c["nome"]
        cor = mapa_cores.get(chave, list(mapa_cores.values())[idx % len(mapa_cores)])
        estilo = mapa_estilos.get(chave, "-")
        rotulo = mapa_nomes.get(chave, chave)
        marcador = next(marcadores_ciclo)

        if usar_linha and usar_pontos:
            ax.plot(c["E"], c["I"], color=cor, linewidth=2.0, linestyle=estilo, marker=marcador, markersize=4.5, markeredgecolor=tema["marker_edge"], markeredgewidth=0.5, label=rotulo)
        elif usar_linha:
            ax.plot(c["E"], c["I"], color=cor, linewidth=2.2, linestyle=estilo, label=rotulo)
        else:
            mask = ~np.isnan(c["E"]) & ~np.isnan(c["I"])
            ax.scatter(c["E"][mask], c["I"][mask], color=cor, s=26, marker=marcador, edgecolors=tema["marker_edge"], linewidths=0.5, label=rotulo)

    span_e = max(e_max - e_min, 1e-6)
    span_i = max(i_max - i_min, 1e-6)
    if exibir_setas:
        ax.text(pos_carga[0], pos_carga[1], tag_carga, transform=ax.transAxes, fontsize=10.5, fontweight="semibold", color=tema["subtext"], zorder=5)
        ax.text(pos_descarga[0], pos_descarga[1], tag_descarga, transform=ax.transAxes, fontsize=10.5, fontweight="semibold", color=tema["subtext"], zorder=5)

    if velocidade:
        ax.text(
            pos_velocidade[0], pos_velocidade[1], rf"$\nu = {velocidade}$", transform=ax.transAxes, fontsize=10.5,
            fontweight="bold", color=tema["text"],
            bbox=dict(boxstyle="round,pad=0.35", facecolor=tema["box_bg"], edgecolor=tema["box_edge"]),
            zorder=7
        )

    ax.set_xlabel(eixo_x_label, fontsize=12.5, labelpad=8)
    ax.set_ylabel(eixo_y_label, fontsize=12.5, labelpad=8)
    ax.set_xlim(e_min - span_e * 0.05, e_max + span_e * 0.05)
    ax.set_ylim(i_min - span_i * 0.10, i_max + span_i * 0.18)
    ax.grid(True, linestyle=":", alpha=0.4, color=tema["grid"])

    aplicar_ajustes_eixos_e_legenda(ax, limites_manuais, posicao_legenda, tema, legenda_horizontal=legenda_horizontal)
    estilar_figura_e_eixos(fig, ax, tema, idioma=idioma)
    plt.tight_layout()
    return fig
