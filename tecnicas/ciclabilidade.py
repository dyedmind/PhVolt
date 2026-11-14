from itertools import cycle
import matplotlib.pyplot as plt
import numpy as np
from core import (
    MARCADORES_PADRAO,
    aplicar_ajustes_eixos_e_legenda,
    estilar_figura_e_eixos,
    processar_cabecalho_e_dados,
)


def gerar_plot_ciclabilidade(
    fonte_dados, rate_tag, pos_rate, eixo_x_label, eixo_y_label,
    mapa_cores, mapa_estilos, mapa_nomes, limites_manuais, posicao_legenda,
    tema, idioma="Português", unidade_y=r"mAh\ g^{-1}", modo_tracado="Linhas (Lines)"
, legenda_horizontal=False):
    df, tokens_limpos = processar_cabecalho_e_dados(fonte_dados)
    num_cols = df.shape[1]
    curvas = []

    if num_cols >= 2 and num_cols % 2 == 0:
        nomes_y = [tokens_limpos[k] for k in range(1, len(tokens_limpos), 2)] if len(tokens_limpos) >= 2 else tokens_limpos
        for idx, col in enumerate(range(0, num_cols, 2)):
            sub = df.iloc[:, [col, col + 1]].dropna()
            if len(sub) == 0:
                continue
            nome = nomes_y[idx] if idx < len(nomes_y) else f"Sample {idx + 1}"
            curvas.append({"nome": nome, "x": sub.iloc[:, 0].to_numpy(float), "y": sub.iloc[:, 1].to_numpy(float)})
    else:
        nomes_y = tokens_limpos[1:] if len(tokens_limpos) >= num_cols else tokens_limpos
        for col in range(1, num_cols):
            sub = df.iloc[:, [0, col]].dropna()
            if len(sub) == 0:
                continue
            nome = nomes_y[col - 1] if (col - 1) < len(nomes_y) else f"Sample {col}"
            curvas.append({"nome": nome, "x": sub.iloc[:, 0].to_numpy(float), "y": sub.iloc[:, 1].to_numpy(float)})

    fig, ax = plt.subplots(figsize=(9.2, 5.2), dpi=300)
    todos_x = np.concatenate([c["x"] for c in curvas if len(c["x"]) > 0])
    todos_y = np.concatenate([c["y"] for c in curvas if len(c["y"]) > 0])
    x_min_dados, x_max_dados = np.min(todos_x), np.max(todos_x)
    y_min_dados, y_max_dados = np.min(todos_y), np.max(todos_y)

    xlim_user = limites_manuais.get("xlim") if limites_manuais else (None, None)
    x_limite_corte = xlim_user[1] if (xlim_user and xlim_user[1] is not None) else x_max_dados
    x_inicio_corte = xlim_user[0] if (xlim_user and xlim_user[0] is not None) else x_min_dados

    usar_linha = ("Lines" in modo_tracado)
    usar_pontos = ("Scatter" in modo_tracado)
    marcadores_ciclo = cycle(MARCADORES_PADRAO)

    dados_finais = []
    for idx, c in enumerate(curvas):
        chave = c["nome"]
        cor = mapa_cores.get(chave, list(mapa_cores.values())[idx % len(mapa_cores)])
        estilo = mapa_estilos.get(chave, "-")
        rotulo = mapa_nomes.get(chave, chave)
        marcador = next(marcadores_ciclo)

        if usar_linha and usar_pontos:
            ax.plot(c["x"], c["y"], color=cor, lw=1.8, linestyle=estilo, marker=marcador, markersize=4.5, markeredgecolor=tema["marker_edge"], markeredgewidth=0.5, label=rotulo, zorder=4)
        elif usar_linha:
            ax.plot(c["x"], c["y"], color=cor, lw=2.0, linestyle=estilo, label=rotulo, zorder=4)
        else:
            ax.scatter(c["x"], c["y"], color=cor, s=26, marker=marcador, edgecolors=tema["marker_edge"], linewidths=0.5, label=rotulo, zorder=4)

        mascara = (c["x"] >= x_inicio_corte) & (c["x"] <= x_limite_corte)
        x_vis = c["x"][mascara] if np.any(mascara) else c["x"]
        y_vis = c["y"][mascara] if np.any(mascara) else c["y"]

        c0, cf = y_vis[0], y_vis[-1]
        x_end_vis = x_vis[-1]
        ret = (cf / c0) * 100 if c0 != 0 else 0.0

        dados_finais.append({"nome": rotulo, "x_end": x_end_vis, "y_end": cf, "ret": ret, "cor": cor})
        ax.scatter(x_end_vis, cf, color=cor, s=30, zorder=6, edgecolors=tema["marker_edge"], linewidths=0.8)

    dados_finais.sort(key=lambda item: item["y_end"], reverse=True)
    num_amostras = len(dados_finais)
    x_ancora_direita = max(d["x_end"] for d in dados_finais)

    span_x = x_ancora_direita - x_inicio_corte
    span_y = y_max_dados - (y_min_dados if y_min_dados < 0 else 0)
    ylim_user = limites_manuais.get("ylim") if limites_manuais else (None, None)
    topo_y_ref = ylim_user[1] if (ylim_user and ylim_user[1] is not None) else y_max_dados

    y_posicoes = np.linspace(topo_y_ref * 0.34, topo_y_ref * 0.07, num_amostras) if num_amostras > 1 else [topo_y_ref * 0.34]

    for i, d in enumerate(dados_finais):
        ret_str = f"{d['ret']:.1f}".replace(".", ",") if idioma == "Português" else f"{d['ret']:.1f}"
        ax.annotate(
            rf"$\mathbf{{{d['y_end']:.0f}\ {unidade_y}}}$  ({ret_str}%)",
            xy=(d["x_end"], d["y_end"]),
            xytext=(x_ancora_direita + span_x * 0.045, y_posicoes[i]),
            fontsize=8.5, fontweight="semibold", color=tema["text"], va="center",
            bbox=dict(boxstyle="round,pad=0.36", facecolor=tema["box_bg"], edgecolor=d["cor"], linewidth=1.3, alpha=0.98),
            arrowprops=dict(arrowstyle="->", color=d["cor"], lw=1.0, connectionstyle="arc3,rad=-0.08"),
            zorder=7,
        )

    ax.axvline(x_ancora_direita, color=tema["ref_line"], linestyle=":", linewidth=1.1, alpha=0.8, zorder=2)
    if rate_tag:
        ax.text(
            pos_rate[0], pos_rate[1], rf"$\mathbf{{{rate_tag}}}$",
            transform=ax.transAxes, fontsize=10.5, fontweight="bold", color=tema["subtext"],
            bbox=dict(boxstyle="round,pad=0.4", facecolor=tema["box_bg"], edgecolor=tema["box_edge"], linewidth=1.1, alpha=0.95),
            zorder=6
        )

    ax.set_xlabel(eixo_x_label, fontsize=12.5, labelpad=8)
    ax.set_ylabel(eixo_y_label, fontsize=12.5, labelpad=8)
    ax.set_xlim(x_inicio_corte - span_x * 0.02, x_ancora_direita + span_x * 0.32)
    ax.set_ylim(min(-span_y * 0.02, y_min_dados), y_max_dados * 1.15)
    ax.grid(True, linestyle=":", alpha=0.4, color=tema["grid"])

    limites_aplicar = {
        "xlim": (
            xlim_user[0],
            (xlim_user[1] + span_x * 0.32) if (xlim_user and xlim_user[1] is not None) else None
        ),
        "ylim": ylim_user,
    }
    aplicar_ajustes_eixos_e_legenda(ax, limites_aplicar, posicao_legenda, tema, legenda_horizontal=legenda_horizontal)
    estilar_figura_e_eixos(fig, ax, tema, idioma=idioma)
    plt.tight_layout()
    return fig


def gerar_plot_ciclabilidade_eficiencia(
    fonte_dados,
    eixo_x_label,
    eixo_y1_label,
    eixo_y2_label,
    nome_amostra="CHZn700@S60",
    rate_tag="0,5 C",
    pos_rate=(0.04, 0.78),
    cor_capacidade="#0f172a",
    cor_eficiencia="#2563eb",
    estilo_capacidade="--",
    estilo_eficiencia="-",
    modo_tracado="Scatter + Lines",
    limites_manuais=None,
    patamar_ref=None,
    tema=None,
    idioma="Português",
    unidade_y=r"mAh\ g^{-1}"
, legenda_horizontal=False):
    df, _ = processar_cabecalho_e_dados(fonte_dados)
    num_cols = df.shape[1]

    if num_cols >= 4:
        sub = df.iloc[:, [0, 2, 3]].dropna()
    elif num_cols == 3:
        sub = df.dropna()
    else:
        raise ValueError("O arquivo para Ciclabilidade + Eficiência precisa conter ao menos 3 colunas (Ciclo, Capacidade e Eficiência).")

    x_ciclos = sub.iloc[:, 0].to_numpy(float)
    y_cap = sub.iloc[:, 1].to_numpy(float)
    y_eff = sub.iloc[:, 2].to_numpy(float)

    usar_linha = ("Lines" in modo_tracado)
    usar_pontos = ("Scatter" in modo_tracado)

    fig, ax1 = plt.subplots(figsize=(8.8, 5.4), dpi=300)

    if usar_linha and not usar_pontos:
        ax1.plot(x_ciclos, y_cap, color=cor_capacidade, linewidth=2.0, linestyle=estilo_capacidade, zorder=4)
    elif usar_pontos and not usar_linha:
        ax1.scatter(x_ciclos, y_cap, color=cor_capacidade, s=20, marker="s", linewidths=0.0, zorder=4)
    else:
        ax1.plot(x_ciclos, y_cap, color=cor_capacidade, linewidth=1.3, linestyle=estilo_capacidade, alpha=0.5, zorder=3)
        ax1.scatter(x_ciclos, y_cap, color=cor_capacidade, s=18, marker="s", linewidths=0.0, zorder=4)

    if patamar_ref is not None and patamar_ref > 0:
        ax1.axhline(patamar_ref, color=tema["ref_line"], linestyle=":", linewidth=1.2, alpha=0.85, zorder=2)

    x_min_dados, x_max_dados = np.min(x_ciclos), np.max(x_ciclos)
    y1_max_dados = np.max(y_cap)

    xlim_user = limites_manuais.get("xlim") if limites_manuais else (None, None)
    x_inicio_corte = xlim_user[0] if (xlim_user and xlim_user[0] is not None) else x_min_dados
    x_limite_corte = xlim_user[1] if (xlim_user and xlim_user[1] is not None) else x_max_dados

    mascara = (x_ciclos >= x_inicio_corte) & (x_ciclos <= x_limite_corte)
    x_vis = x_ciclos[mascara] if np.any(mascara) else x_ciclos
    y_vis = y_cap[mascara] if np.any(mascara) else y_cap

    c0, cf = y_vis[0], y_vis[-1]
    x_end_vis = x_vis[-1]
    ret = (cf / c0) * 100 if c0 != 0 else 0.0
    ret_str = f"{ret:.1f}".replace(".", ",") if idioma == "Português" else f"{ret:.1f}"

    ax1.axvline(x_end_vis, color=tema["ref_line"], linestyle=":", linewidth=1.1, alpha=0.7, zorder=2)
    ax1.annotate("←", xy=(0.04, 0.55), xycoords="axes fraction", fontsize=14, fontweight="bold", color=cor_capacidade)

    texto_retencao = rf"$\mathbf{{{cf:.0f}\ {unidade_y}}}$  ({ret_str}%)"
    ax1.annotate(
        texto_retencao,
        xy=(x_end_vis, cf),
        xytext=(0.42, 0.40),
        textcoords="axes fraction",
        fontsize=9.5,
        fontweight="semibold",
        color=tema["text"],
        bbox=dict(boxstyle="round,pad=0.38", facecolor=tema["box_bg"], edgecolor=cor_capacidade, linewidth=1.2, alpha=0.98),
        arrowprops=dict(arrowstyle="->", color=cor_capacidade, lw=1.0, connectionstyle="arc3,rad=-0.1"),
        zorder=7
    )

    if rate_tag:
        ax1.text(
            pos_rate[0], pos_rate[1],
            rf"$\mathbf{{{rate_tag}}}$",
            transform=ax1.transAxes,
            fontsize=10.5,
            fontweight="bold",
            color=tema["subtext"],
            bbox=dict(boxstyle="round,pad=0.35", facecolor=tema["box_bg"], edgecolor=tema["box_edge"], linewidth=1.1, alpha=0.95),
            zorder=6
        )

    ax1.set_xlabel(eixo_x_label, fontsize=12.5, labelpad=8)
    ax1.set_ylabel(eixo_y1_label, fontsize=12.5, labelpad=8, color=cor_capacidade)
    ax1.tick_params(axis="y", labelcolor=cor_capacidade, color=cor_capacidade, width=1.4)
    ax1.tick_params(axis="x", width=1.4)
    ax1.set_xlim(0, x_max_dados + max(2, x_max_dados * 0.02))
    ax1.set_ylim(0, y1_max_dados * 1.35)

    aplicar_ajustes_eixos_e_legenda(ax1, limites_manuais, posicao_legenda=None, tema=tema)

    if nome_amostra:
        ax1.text(0.05, 0.08, nome_amostra, transform=ax1.transAxes, fontsize=13, fontweight="bold", color=tema["text"])

    ax2 = ax1.twinx()
    if usar_linha and not usar_pontos:
        ax2.plot(x_ciclos, y_eff, color=cor_eficiencia, linewidth=2.0, linestyle=estilo_eficiencia, zorder=6)
    elif usar_pontos and not usar_linha:
        ax2.scatter(x_ciclos, y_eff, color=cor_eficiencia, s=18, marker="o", linewidths=0.0, zorder=6)
    else:
        ax2.plot(x_ciclos, y_eff, color=cor_eficiencia, linewidth=1.2, linestyle=estilo_eficiencia, alpha=0.45, zorder=5)
        ax2.scatter(x_ciclos, y_eff, color=cor_eficiencia, s=16, marker="o", linewidths=0.0, zorder=6)

    ax2.annotate("→", xy=(0.92, 0.82), xycoords="axes fraction", fontsize=14, fontweight="bold", color=cor_eficiencia)

    ax2.set_ylabel(eixo_y2_label, fontsize=12.5, labelpad=8, color=cor_eficiencia)
    ax2.tick_params(axis="y", labelcolor=cor_eficiencia, width=1.4, color=cor_eficiencia)
    ax2.spines["right"].set_color(cor_eficiencia)
    ax2.spines["right"].set_linewidth(1.4)
    ax2.spines["top"].set_visible(False)
    ax2.spines["bottom"].set_visible(False)
    ax2.spines["left"].set_visible(False)

    y2lim_user = limites_manuais.get("y2lim") if limites_manuais else (None, None)
    y2_min_val = y2lim_user[0] if (y2lim_user and y2lim_user[0] is not None) else 0.0
    y2_max_val = y2lim_user[1] if (y2lim_user and y2lim_user[1] is not None) else 110.0
    ax2.set_ylim(y2_min_val, y2_max_val)

    aplicar_ajustes_eixos_e_legenda(ax1, limites_manuais, posicao_legenda=None, tema=tema, eixo_y2=ax2)
    estilar_figura_e_eixos(fig, ax1, tema, y_color=cor_capacidade, idioma=idioma, eixo_y2=ax2)
    plt.tight_layout()
    return fig
