from matplotlib.lines import Line2D
import matplotlib.pyplot as plt
from mpl_toolkits.axes_grid1.inset_locator import inset_axes
import numpy as np
from core import (
    aplicar_ajustes_eixos_e_legenda,
    estilar_figura_e_eixos,
    processar_cabecalho_e_dados,
)


def gerar_plot_bet(
    fonte_dados, eixo_x_label, eixo_y_label, rotulo_ads, rotulo_des,
    titulo_legenda, titulo_inset, mapa_cores, mapa_estilos, mapa_nomes,
    limites_manuais, posicao_legenda, tema, idioma="Português", areas_bet=None, exibir_inset=False,
    inset_bbox=(0.54, 0.22, 0.38, 0.28), inset_limites=None, modo_tracado="Scatter + Lines"
, legenda_horizontal=False):
    df, tokens_limpos = processar_cabecalho_e_dados(fonte_dados)
    if len(tokens_limpos) >= 2:
        nomes_detectados = [tokens_limpos[k] for k in range(1, len(tokens_limpos), 2)]
    else:
        nomes_detectados = tokens_limpos

    num_cols = df.shape[1]
    num_amostras = num_cols // 2
    isotherms = []

    for idx in range(num_amostras):
        col_x = idx * 2
        col_y = col_x + 1
        if col_y >= num_cols:
            break
        nome = nomes_detectados[idx] if idx < len(nomes_detectados) else f"Sample {idx + 1}"
        sub = df.iloc[:, [col_x, col_y]].dropna()
        if len(sub) == 0:
            continue

        p_p0 = sub.iloc[:, 0].to_numpy(dtype=float)
        v_ads = sub.iloc[:, 1].to_numpy(dtype=float)
        idx_pico = int(np.argmax(p_p0)) if len(p_p0) > 0 else 0
        tem_dessorcao = (idx_pico < (len(p_p0) - 2)) and (p_p0[-1] < p_p0[idx_pico])

        isotherms.append({
            "name": nome,
            "ads_p": p_p0[: idx_pico + 1],
            "ads_v": v_ads[: idx_pico + 1],
            "des_p": p_p0[idx_pico:] if tem_dessorcao else np.array([]),
            "des_v": v_ads[idx_pico:] if tem_dessorcao else np.array([]),
            "tem_dessorcao": tem_dessorcao,
            "v_max": np.max(v_ads) if len(v_ads) > 0 else 0,
        })

    fig, ax = plt.subplots(figsize=(8.8, 5.4), dpi=300)
    legend_elements = []
    todos_v_max = [iso["v_max"] for iso in isotherms if iso["v_max"] > 0]
    v_max = max(todos_v_max) if todos_v_max else 1000

    usar_linha = ("Lines" in modo_tracado)
    usar_pontos = ("Scatter" in modo_tracado)

    for idx, iso in enumerate(isotherms):
        chave = iso["name"]
        nome_exibicao = mapa_nomes.get(chave, chave)
        cor = mapa_cores.get(chave, list(mapa_cores.values())[idx % len(mapa_cores)])
        estilo = mapa_estilos.get(chave, "-")
        val_bet = areas_bet.get(chave, areas_bet.get(chave.replace(" ", ""), None)) if areas_bet else None
        rotulo = rf"{nome_exibicao}  $\mathbf{{({val_bet:.0f}\ m^2\ g^{{-1}})}}$" if val_bet else nome_exibicao

        if usar_linha:
            ax.plot(iso["ads_p"], iso["ads_v"], color=cor, linewidth=1.7, linestyle=estilo, alpha=0.85, zorder=3)
        if usar_pontos:
            ax.scatter(iso["ads_p"], iso["ads_v"], color=cor, s=28, marker="o", edgecolors=tema["marker_edge"], linewidths=0.6, zorder=4)

        if iso["tem_dessorcao"] and len(iso["des_p"]) > 0:
            if usar_linha:
                ax.plot(iso["des_p"], iso["des_v"], color=cor, linewidth=1.7, linestyle=estilo, alpha=0.85, zorder=3)
            if usar_pontos:
                ax.scatter(iso["des_p"], iso["des_v"], facecolors=tema["ax_bg"], edgecolors=cor, s=28, marker="o", linewidths=1.2, zorder=5)

        legend_elements.append(
            Line2D([0], [0], marker="o", color=cor if (usar_linha and not usar_pontos) else "none", linestyle=estilo if (usar_linha and not usar_pontos) else "none", markeredgecolor=tema["marker_edge"], markerfacecolor=cor, markersize=7, label=rotulo)
        )

    if exibir_inset and len(isotherms) > 1:
        amostras_baixas = [iso for iso in isotherms if iso["v_max"] < (v_max * 0.25)]
        curvas_inset = isotherms if (inset_limites and any(v is not None for v in inset_limites.values())) else amostras_baixas
        if curvas_inset:
            ax_ins = inset_axes(ax, width="100%", height="100%", bbox_to_anchor=inset_bbox, bbox_transform=ax.transAxes)
            ax_ins.set_facecolor(tema["ax_bg"])
            for idx, iso in enumerate(isotherms):
                cor_ins = mapa_cores.get(iso["name"], list(mapa_cores.values())[idx % len(mapa_cores)])
                estilo_ins = mapa_estilos.get(iso["name"], "-")
                if iso in curvas_inset:
                    if usar_linha:
                        ax_ins.plot(iso["ads_p"], iso["ads_v"], color=cor_ins, linewidth=1.4, linestyle=estilo_ins, alpha=0.9, zorder=3)
                    if usar_pontos:
                        ax_ins.scatter(iso["ads_p"], iso["ads_v"], color=cor_ins, s=18, marker="o", edgecolors=tema["marker_edge"], linewidths=0.4, zorder=4)
                    if iso["tem_dessorcao"] and len(iso["des_p"]) > 0:
                        if usar_linha:
                            ax_ins.plot(iso["des_p"], iso["des_v"], color=cor_ins, linewidth=1.4, linestyle=estilo_ins, alpha=0.9, zorder=3)
                        if usar_pontos:
                            ax_ins.scatter(iso["des_p"], iso["des_v"], facecolors=tema["ax_bg"], edgecolors=cor_ins, s=18, marker="o", linewidths=0.9, zorder=5)

            ax_ins.set_xlim(-0.02, 1.02)
            if inset_limites:
                if inset_limites.get("xmin") is not None: ax_ins.set_xlim(left=inset_limites["xmin"])
                if inset_limites.get("xmax") is not None: ax_ins.set_xlim(right=inset_limites["xmax"])
                if inset_limites.get("ymin") is not None: ax_ins.set_ylim(bottom=inset_limites["ymin"])
                if inset_limites.get("ymax") is not None: ax_ins.set_ylim(top=inset_limites["ymax"])

            ax_ins.tick_params(labelsize=8.0, colors=tema["subtext"])
            for sp in ax_ins.spines.values():
                sp.set_color(tema["spine"])
            ax_ins.grid(True, linestyle=":", alpha=0.4, color=tema["grid"])
            ax_ins.set_title(titulo_inset, fontsize=8.5, fontweight="bold", color=tema["subtext"], pad=3)
            estilar_figura_e_eixos(fig, ax_ins, tema, idioma=idioma)

    ax.set_xlabel(eixo_x_label, fontsize=12.5, labelpad=8)
    ax.set_ylabel(eixo_y_label, fontsize=12.5, labelpad=8)
    ax.set_xlim(-0.02, 1.02)
    ax.set_ylim(-20, v_max * 1.18)
    ax.grid(True, linestyle=":", alpha=0.4, color=tema["grid"])

    aplicar_ajustes_eixos_e_legenda(ax, limites_manuais, posicao_legenda, tema, handles=legend_elements, title_legenda=titulo_legenda, fontsize_leg=9.5, legenda_horizontal=legenda_horizontal)

    if posicao_legenda != "Ocultar / Hide":
        leg_principal = ax.get_legend()
        if leg_principal:
            ax.add_artist(leg_principal)

        loc_iupac = "upper right" if posicao_legenda != "upper right" else "lower right"
        elementos_tipo = [
            Line2D([0], [0], marker="o", color="none", markeredgecolor=tema["marker_edge"], markerfacecolor=tema["subtext"], markersize=6.5, label=rotulo_ads),
            Line2D([0], [0], marker="o", color="none", markeredgecolor=tema["subtext"], markerfacecolor=tema["ax_bg"], markeredgewidth=1.2, markersize=6.5, label=rotulo_des),
        ]
        leg2 = ax.legend(
            handles=elementos_tipo, frameon=True, facecolor=tema["box_bg"], edgecolor=tema["box_edge"],
            loc=loc_iupac, labelspacing=0.35, fontsize=9.0
        )
        for text in leg2.get_texts():
            text.set_color(tema["text"])

    estilar_figura_e_eixos(fig, ax, tema, idioma=idioma)
    plt.tight_layout()
    return fig
