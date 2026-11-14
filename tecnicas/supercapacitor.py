from itertools import cycle
import matplotlib.pyplot as plt
import numpy as np
from core import (
    MARCADORES_PADRAO,
    aplicar_ajustes_eixos_e_legenda,
    estilar_figura_e_eixos,
    processar_cabecalho_e_dados,
)


def gerar_plot_sc_2e(
    fonte_dados, eixo_x_label, eixo_y_label,
    mapa_cores, mapa_estilos, mapa_nomes, limites_manuais, posicao_legenda, tema,
    idioma="Português", modo_tracado="Linhas (Lines)",
    exibir_densidade_corrente=False, texto_densidade_corrente="1 A/g",
    pos_densidade_corrente=(0.04, 0.92), legenda_horizontal=False, **_kwargs
):
    df, tokens_limpos = processar_cabecalho_e_dados(fonte_dados)
    num_cols = df.shape[1]
    curvas = []

    nomes_y = [tokens_limpos[k] for k in range(1, len(tokens_limpos), 2)] if len(tokens_limpos) >= 2 else tokens_limpos
    for idx, col in enumerate(range(0, num_cols, 2)):
        if col + 1 < num_cols:
            sub = df.iloc[:, [col, col + 1]].dropna()
            if len(sub) == 0:
                continue
            nome = nomes_y[idx] if idx < len(nomes_y) else f"Janela {idx + 1}"
            curvas.append({"nome": nome.strip(), "t": sub.iloc[:, 0].to_numpy(float), "v": sub.iloc[:, 1].to_numpy(float)})

    fig, ax = plt.subplots(figsize=(8.6, 5.4), dpi=300)
    todos_t = np.concatenate([c["t"] for c in curvas if len(c["t"]) > 0])
    todos_v = np.concatenate([c["v"] for c in curvas if len(c["v"]) > 0])
    t_min, t_max = np.min(todos_t), np.max(todos_t)
    v_min, v_max = np.min(todos_v), np.max(todos_v)

    usar_linha = ("Lines" in modo_tracado)
    usar_pontos = ("Scatter" in modo_tracado)
    marcadores_ciclo = cycle(MARCADORES_PADRAO)

    for idx, c in enumerate(curvas):
        chave = c["nome"]
        cor = mapa_cores.get(chave, list(mapa_cores.values())[idx % len(mapa_cores)])
        estilo = mapa_estilos.get(chave, "-")
        rotulo = mapa_nomes.get(chave, chave)
        marcador = next(marcadores_ciclo)

        if usar_linha and usar_pontos:
            ax.plot(c["t"], c["v"], color=cor, linewidth=1.9, linestyle=estilo, marker=marcador, markersize=4.5, markeredgecolor=tema["marker_edge"], markeredgewidth=0.5, label=rotulo, zorder=4)
        elif usar_linha:
            ax.plot(c["t"], c["v"], color=cor, linewidth=2.1, linestyle=estilo, label=rotulo, zorder=4)
        else:
            ax.scatter(c["t"], c["v"], color=cor, s=26, marker=marcador, edgecolors=tema["marker_edge"], linewidths=0.5, label=rotulo, zorder=4)

    if exibir_densidade_corrente and texto_densidade_corrente:
        ax.text(
            pos_densidade_corrente[0],
            pos_densidade_corrente[1],
            rf"$\mathbf{{{texto_densidade_corrente}}}$",
            transform=ax.transAxes,
            fontsize=10.5,
            fontweight="bold",
            color=tema["text"],
            bbox=dict(
                boxstyle="round,pad=0.36",
                facecolor=tema["box_bg"],
                edgecolor=tema["box_edge"],
                linewidth=1.1,
                alpha=0.96,
            ),
            zorder=7,
        )

    span_t = max(t_max - t_min, 1e-6)
    span_v = max(v_max - v_min, 1e-6)
    ax.set_xlabel(eixo_x_label, fontsize=12.5, labelpad=8)
    ax.set_ylabel(eixo_y_label, fontsize=12.5, labelpad=8)
    ax.set_xlim(min(0, t_min - span_t * 0.02), t_max + span_t * 0.05)

    ax.set_ylim(v_min, v_max + span_v * 0.12)
    ax.grid(True, linestyle=":", alpha=0.4, color=tema["grid"])

    aplicar_ajustes_eixos_e_legenda(ax, limites_manuais, posicao_legenda, tema, legenda_horizontal=legenda_horizontal)
    estilar_figura_e_eixos(fig, ax, tema, idioma=idioma)
    plt.tight_layout()
    return fig


def gerar_plot_sc_3e(
    fonte_dados, eixo_x_label, eixo_y1_label, eixo_y2_label,
    mapa_cores, mapa_estilos, mapa_nomes, limites_manuais, posicao_legenda, tema,
    idioma="Português", tag_amostra="", pos_amostra=(0.05, 0.90), exibir_zero_y2=True,
    modo_tracado="Linhas (Lines)", exibir_densidade_corrente=False,
    texto_densidade_corrente=r"1\ \mathrm{A\ g^{-1}}", pos_densidade_corrente=(0.05, 0.80),
    legenda_horizontal=False, **_kwargs
):
    df, _ = processar_cabecalho_e_dados(fonte_dados)
    if df.shape[1] < 4:
        raise ValueError("O ensaio de 3 eletrodos exige 4 colunas: Tempo, Ecell, Ewe e Ece.")

    sub = df.iloc[:, :4].dropna()
    t = sub.iloc[:, 0].to_numpy(float)
    ecell = sub.iloc[:, 1].to_numpy(float)
    ewe = sub.iloc[:, 2].to_numpy(float)
    ece = sub.iloc[:, 3].to_numpy(float)

    cor_ecell = mapa_cores.get("Ecell", "#0f172a" if tema["fig_bg"] == "#ffffff" else "#f8fafc")
    cor_ewe = mapa_cores.get("Ewe (Positivo)", "#e11d48")
    cor_ece = mapa_cores.get("Ece (Negativo)", "#0284c7")

    est_ecell = mapa_estilos.get("Ecell", "-")
    est_ewe = mapa_estilos.get("Ewe (Positivo)", "-")
    est_ece = mapa_estilos.get("Ece (Negativo)", "--")

    lbl_ecell = mapa_nomes.get("Ecell", "Ecell")
    lbl_ewe = mapa_nomes.get("Ewe (Positivo)", "Ewe (+)")
    lbl_ece = mapa_nomes.get("Ece (Negativo)", "Ece (-)")

    usar_linha = ("Lines" in modo_tracado)
    usar_pontos = ("Scatter" in modo_tracado)

    fig, ax1 = plt.subplots(figsize=(8.8, 5.4), dpi=300)
    if usar_linha:
        l1, = ax1.plot(t, ecell, color=cor_ecell, linewidth=2.2, linestyle=est_ecell, marker="o" if usar_pontos else None, markersize=4.0, label=lbl_ecell, zorder=4)
    else:
        l1 = ax1.scatter(t, ecell, color=cor_ecell, s=24, marker="o", label=lbl_ecell, zorder=4)

    span_y1 = max(np.max(ecell) - np.min(ecell), 1e-6)
    ax1.set_xlabel(eixo_x_label, fontsize=12.5, labelpad=8)
    ax1.set_ylabel(eixo_y1_label, fontsize=12.5, labelpad=8, color=cor_ecell)
    ax1.set_xlim(np.min(t), np.max(t))

    ax1.set_ylim(np.min(ecell), np.max(ecell) + span_y1 * 0.15)
    ax1.grid(True, linestyle=":", alpha=0.4, color=tema["grid"])

    aplicar_ajustes_eixos_e_legenda(ax1, limites_manuais, posicao_legenda=None, tema=tema)

    ax2 = ax1.twinx()
    if exibir_zero_y2:
        ax2.axhline(0, color=tema["ref_line"], linestyle=":", linewidth=1.1, alpha=0.85, zorder=2)

    if usar_linha:
        l2, = ax2.plot(t, ewe, color=cor_ewe, linewidth=2.0, linestyle=est_ewe, marker="s" if usar_pontos else None, markersize=4.0, label=lbl_ewe, zorder=5)
        l3, = ax2.plot(t, ece, color=cor_ece, linewidth=2.0, linestyle=est_ece, marker="^" if usar_pontos else None, markersize=4.0, label=lbl_ece, zorder=5)
    else:
        l2 = ax2.scatter(t, ewe, color=cor_ewe, s=24, marker="s", label=lbl_ewe, zorder=5)
        l3 = ax2.scatter(t, ece, color=cor_ece, s=24, marker="^", label=lbl_ece, zorder=5)

    all_y2 = np.concatenate([ewe, ece])
    span_y2 = max(np.max(all_y2) - np.min(all_y2), 1e-6)
    ax2.set_ylabel(eixo_y2_label, fontsize=12.5, labelpad=8, color=cor_ewe)
    ax2.tick_params(axis="y", labelcolor=cor_ewe, color=cor_ewe, width=1.4)
    ax2.spines["right"].set_color(cor_ewe)
    ax2.spines["right"].set_linewidth(1.4)
    ax2.spines["top"].set_visible(False)
    ax2.spines["bottom"].set_visible(False)
    ax2.spines["left"].set_visible(False)

    y2lim_user = limites_manuais.get("y2lim") if limites_manuais else (None, None)
    y2_min = y2lim_user[0] if (y2lim_user and y2lim_user[0] is not None) else (np.min(all_y2) - span_y2 * 0.12)
    y2_max = y2lim_user[1] if (y2lim_user and y2lim_user[1] is not None) else (np.max(all_y2) + span_y2 * 0.15)
    ax2.set_ylim(y2_min, y2_max)

    if tag_amostra:
        ax1.text(
            pos_amostra[0], pos_amostra[1], rf"$\mathbf{{{tag_amostra}}}$",
            transform=ax1.transAxes, fontsize=10.5, fontweight="bold", color=tema["text"],
            bbox=dict(boxstyle="round,pad=0.38", facecolor=tema["box_bg"], edgecolor=tema["box_edge"], linewidth=1.1, alpha=0.96),
            zorder=7
        )

    if posicao_legenda and posicao_legenda != "Ocultar / Hide":
        handles_unificados = [l1, l2, l3]
        leg = ax2.legend(
            handles=handles_unificados,
            loc=posicao_legenda,
            frameon=True,
            facecolor=tema["box_bg"],
            edgecolor=tema["box_edge"],
            fontsize=10.0,
            ncol=len(handles_unificados) if legenda_horizontal else 1,
        )
        for text in leg.get_texts():
            text.set_color(tema["text"])

    aplicar_ajustes_eixos_e_legenda(ax1, limites_manuais, posicao_legenda=None, tema=tema, eixo_y2=ax2)
    estilar_figura_e_eixos(fig, ax1, tema, y_color=cor_ecell, idioma=idioma, eixo_y2=ax2)
    plt.tight_layout()
    return fig
