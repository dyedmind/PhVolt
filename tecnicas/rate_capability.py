from itertools import cycle
import matplotlib.pyplot as plt
import numpy as np
import streamlit as st
from core import (
    MARCADORES_PADRAO,
    aplicar_ajustes_eixos_e_legenda,
    estilar_figura_e_eixos,
    processar_cabecalho_e_dados,
)


def gerar_plot_rate(
    fonte_dados, eixo_x_label, eixo_y_label,
    mapa_cores, mapa_estilos, mapa_nomes, limites_manuais, posicao_legenda, tema,
    idioma="Português", labels_zonas=None, modo_tracado="Pontos (Scatter)"
, legenda_horizontal=False):
    df, tokens_limpos = processar_cabecalho_e_dados(fonte_dados)
    x_ciclos = df.iloc[:, 0].to_numpy(float)
    num_curvas = df.shape[1] - 1

    legendas = tokens_limpos[1:] if len(tokens_limpos) > num_curvas else tokens_limpos
    if len(legendas) < num_curvas:
        legendas = [f"Sample {i+1}" for i in range(num_curvas)]

    if not labels_zonas:
        labels_zonas = (
            ["0,1 C", "0,2 C", "0,5 C", "1 C", "2 C", "0,1 C"]
            if idioma == "Português"
            else ["0.1 C", "0.2 C", "0.5 C", "1 C", "2 C", "0.1 C"]
        )

    max_ciclo_real = float(np.nanmax(x_ciclos)) if len(x_ciclos) > 0 else 25.0
    n_zonas = len(labels_zonas)

    zonas_dinamicas = st.session_state.get("_rate_mpr_zonas_dinamicas")
    if zonas_dinamicas:
        zonas_c_rate = []
        for i, z in enumerate(zonas_dinamicas):
            lbl = labels_zonas[i] if i < len(labels_zonas) else f"Etapa {i+1}"
            zonas_c_rate.append({
                "label": lbl,
                "start": float(z["start"]),
                "end": float(z["end"]),
                "mid": float(z["mid"]),
            })
    elif 22 <= max_ciclo_real <= 27 and n_zonas == 6:
        zonas_c_rate = [
            {"label": labels_zonas[0], "start": 0.5, "end": 5.5, "mid": 3.0},
            {"label": labels_zonas[1], "start": 5.5, "end": 9.5, "mid": 7.5},
            {"label": labels_zonas[2], "start": 9.5, "end": 13.5, "mid": 11.5},
            {"label": labels_zonas[3], "start": 13.5, "end": 17.5, "mid": 15.5},
            {"label": labels_zonas[4], "start": 17.5, "end": 21.5, "mid": 19.5},
            {"label": labels_zonas[5], "start": 21.5, "end": max(25.5, max_ciclo_real + 0.5), "mid": 23.5},
        ]
    else:
        bordas = np.linspace(0.5, max_ciclo_real + 0.5, n_zonas + 1)
        zonas_c_rate = [
            {
                "label": labels_zonas[i],
                "start": float(bordas[i]),
                "end": float(bordas[i + 1]),
                "mid": float((bordas[i] + bordas[i + 1]) / 2.0),
            }
            for i in range(n_zonas)
        ]

    fig, ax = plt.subplots(figsize=(8.6, 5.2), dpi=300)
    marcadores_ciclo = cycle(MARCADORES_PADRAO)

    y_vals_all = df.iloc[:, 1:].to_numpy(float)
    y_max = float(np.nanmax(y_vals_all)) if np.any(np.isfinite(y_vals_all)) else 100.0
    y_min = float(np.nanmin(y_vals_all)) if np.any(np.isfinite(y_vals_all)) else 0.0
    y_topo = y_max * 1.18
    trans_topo_eixo = ax.get_xaxis_transform()

    xlim_right = max_ciclo_real + 1.0
    for i, zone in enumerate(zonas_c_rate):
        if zone["start"] > xlim_right:
            continue
        if i % 2 == 1:
            ax.axvspan(zone["start"], min(zone["end"], xlim_right), color=tema["zebra"], alpha=0.9, zorder=1)
        if i > 0:
            ax.axvline(zone["start"], color=tema["grid"], linestyle="--", linewidth=1.1, zorder=2)

        if 0 <= zone["mid"] <= xlim_right:
            ax.text(
                zone["mid"], 0.94, zone["label"],
                transform=trans_topo_eixo,
                ha="center", va="center",
                fontsize=9.5, fontweight="bold", color=tema["text"],
                bbox=dict(boxstyle="round,pad=0.25", facecolor=tema["box_bg"], edgecolor=tema["box_edge"], lw=1.0),
                clip_on=True,
                zorder=5
            )

    usar_linha = ("Lines" in modo_tracado)
    usar_pontos = ("Scatter" in modo_tracado)

    offsets = np.linspace(-0.12, 0.12, num_curvas) if num_curvas > 1 else [0.0]
    for col_idx in range(num_curvas):
        y_valores = df.iloc[:, col_idx + 1].to_numpy(float)
        chave = str(legendas[col_idx])
        cor = mapa_cores.get(chave, list(mapa_cores.values())[col_idx % len(mapa_cores)])
        estilo = mapa_estilos.get(chave, "-")
        rotulo = mapa_nomes.get(chave, chave)
        marcador = next(marcadores_ciclo)

        if usar_linha and not usar_pontos:
            ax.plot(x_ciclos + offsets[col_idx], y_valores, color=cor, linewidth=2.0, linestyle=estilo, label=rotulo, zorder=4)
        elif usar_pontos and not usar_linha:
            # Mantém o comportamento original de permitir tracejar via checkbox
            if estilo == "--":
                ax.plot(x_ciclos + offsets[col_idx], y_valores, color=cor, linewidth=1.2, linestyle="--", alpha=0.55, zorder=3)
            ax.scatter(
                x_ciclos + offsets[col_idx], y_valores, color=cor, s=52,
                marker=marcador, edgecolors=tema["marker_edge"], linewidths=0.85,
                label=rotulo, zorder=4
            )
        else:
            ax.plot(x_ciclos + offsets[col_idx], y_valores, color=cor, linewidth=1.5, linestyle=estilo, alpha=0.65, zorder=3)
            ax.scatter(
                x_ciclos + offsets[col_idx], y_valores, color=cor, s=52,
                marker=marcador, edgecolors=tema["marker_edge"], linewidths=0.85,
                label=rotulo, zorder=4
            )

    ax.set_xlabel(eixo_x_label, fontsize=12.5, labelpad=8)
    ax.set_ylabel(eixo_y_label, fontsize=12.5, labelpad=8)
    ax.set_xlim(0, xlim_right)
    ax.set_ylim(min(0, y_min - (y_max * 0.05)), y_topo * 1.05)
    ax.yaxis.grid(True, linestyle=":", alpha=0.5, color=tema["grid"])

    aplicar_ajustes_eixos_e_legenda(ax, limites_manuais, posicao_legenda, tema, legenda_horizontal=legenda_horizontal)
    estilar_figura_e_eixos(fig, ax, tema, idioma=idioma)
    plt.tight_layout()
    return fig
