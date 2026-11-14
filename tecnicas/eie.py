from itertools import cycle
import matplotlib.image as mpimg
from matplotlib.offsetbox import AnnotationBbox, OffsetImage
import matplotlib.pyplot as plt
from mpl_toolkits.axes_grid1.inset_locator import inset_axes
import numpy as np
from core import (
    MARCADORES_PADRAO,
    aplicar_ajustes_eixos_e_legenda,
    estilar_figura_e_eixos,
    processar_cabecalho_e_dados,
)


def _quebrar_ciclos_nyquist(re_raw, im_raw):
    valid_mask = np.isfinite(re_raw) & np.isfinite(im_raw)
    valid_re = re_raw[valid_mask]
    valid_im = im_raw[valid_mask]
    span_re_c = (np.nanmax(valid_re) - np.nanmin(valid_re)) if len(valid_re) > 2 else 0.0
    span_im_c = (np.nanmax(valid_im) - np.nanmin(valid_im)) if len(valid_im) > 2 else 0.0
    diag_c = float(np.hypot(span_re_c, span_im_c))
    dists_c = np.hypot(np.diff(valid_re), np.diff(valid_im)) if len(valid_re) > 2 else np.array([])
    med_step_c = float(np.nanmedian(dists_c[dists_c > 0])) if np.any(dists_c > 0) else 0.0

    if diag_c <= 0:
        return re_raw, im_raw

    re_sep, im_sep = [], []
    prev_r, prev_i = None, None
    for rv, iv in zip(re_raw, im_raw):
        if np.isnan(rv) or np.isnan(iv):
            re_sep.append(np.nan)
            im_sep.append(np.nan)
            prev_r, prev_i = None, None
            continue
        if prev_r is not None and prev_i is not None:
            dx = rv - prev_r
            dy = iv - prev_i
            dist_2d = float(np.hypot(dx, dy))
            if (
                (span_re_c > 0 and dx < -(span_re_c * 0.15))
                or (span_im_c > 0 and dy < -(span_im_c * 0.25))
                or (med_step_c > 0 and dist_2d > max(diag_c * 0.25, med_step_c * 8.0))
            ):
                re_sep.append(np.nan)
                im_sep.append(np.nan)
        re_sep.append(rv)
        im_sep.append(iv)
        prev_r, prev_i = rv, iv

    return np.array(re_sep, dtype=float), np.array(im_sep, dtype=float)


def gerar_plot_eie(
    fonte_dados, circuito_bytes, eixo_x_label, eixo_y_label,
    mapa_cores, mapa_estilos, mapa_nomes, limites_manuais, posicao_legenda, tema,
    idioma="Português", pos_circuito=(0.62, 0.78), zoom_circuito=0.36,
    modo_tracado="Scatter + Lines", aspect_equal=True, exibir_inset=False,
    inset_bbox=(0.48, 0.42, 0.44, 0.42), inset_limites=None, legenda_horizontal=False
):
    df, tokens_limpos = processar_cabecalho_e_dados(fonte_dados)
    num_cols = df.shape[1]
    curvas = []

    nomes_y = [tokens_limpos[k] for k in range(1, len(tokens_limpos), 2)] if len(tokens_limpos) >= 2 else tokens_limpos
    for idx, col in enumerate(range(0, num_cols, 2)):
        if col + 1 < num_cols:
            nome = str(nomes_y[idx]) if idx < len(nomes_y) else f"Sample {idx + 1}"
            if nome.strip().upper() in ["Y", "ZIM", "-ZIM", ""]:
                nome = f"Sample {idx + 1}"
            sub = df.iloc[:, [col, col + 1]].dropna(how="all")
            if len(sub) == 0:
                continue
            re_q, im_q = _quebrar_ciclos_nyquist(sub.iloc[:, 0].to_numpy(float), sub.iloc[:, 1].to_numpy(float))
            curvas.append({"nome": nome.strip(), "re": re_q, "im": im_q})

    fig, ax = plt.subplots(figsize=(8.2, 5.2), dpi=300)
    marcadores_ciclo = cycle(MARCADORES_PADRAO)

    todos_re = np.concatenate([c["re"][~np.isnan(c["re"])] for c in curvas if len(c["re"]) > 0])
    todos_im = np.concatenate([c["im"][~np.isnan(c["im"])] for c in curvas if len(c["im"]) > 0])
    re_min, re_max = np.nanmin(todos_re), np.nanmax(todos_re)
    im_min, im_max = np.nanmin(todos_im), np.nanmax(todos_im)

    usar_linha = ("Lines" in modo_tracado)
    usar_pontos = ("Scatter" in modo_tracado)

    for idx, c in enumerate(curvas):
        chave = c["nome"]
        cor = mapa_cores.get(chave, list(mapa_cores.values())[idx % len(mapa_cores)])
        estilo = mapa_estilos.get(chave, "-")
        rotulo = mapa_nomes.get(chave, chave)
        marcador = next(marcadores_ciclo)

        if usar_linha and not usar_pontos:
            ax.plot(c["re"], c["im"], color=cor, linewidth=2.1, linestyle=estilo, label=rotulo, zorder=4)
        elif usar_pontos and not usar_linha:
            mask_val = ~np.isnan(c["re"]) & ~np.isnan(c["im"])
            ax.scatter(
                c["re"][mask_val], c["im"][mask_val], color=cor, s=42, marker=marcador,
                edgecolors=tema["marker_edge"], linewidths=0.75, label=rotulo, zorder=4
            )
        else:
            ax.plot(c["re"], c["im"], color=cor, linewidth=1.6, linestyle=estilo, alpha=0.55, zorder=3)
            mask_val = ~np.isnan(c["re"]) & ~np.isnan(c["im"])
            ax.scatter(
                c["re"][mask_val], c["im"][mask_val], color=cor, s=42, marker=marcador,
                edgecolors=tema["marker_edge"], linewidths=0.75, label=rotulo, zorder=4
            )

    if exibir_inset and len(curvas) > 0:
        ax_ins = inset_axes(ax, width="100%", height="100%", bbox_to_anchor=inset_bbox, bbox_transform=ax.transAxes)
        ax_ins.set_facecolor(tema["ax_bg"])
        marc_ins = cycle(MARCADORES_PADRAO)

        for idx, c in enumerate(curvas):
            chave = c["nome"]
            cor = mapa_cores.get(chave, list(mapa_cores.values())[idx % len(mapa_cores)])
            estilo = mapa_estilos.get(chave, "-")
            m_ins = next(marc_ins)
            if usar_linha and not usar_pontos:
                ax_ins.plot(c["re"], c["im"], color=cor, linewidth=1.7, linestyle=estilo, zorder=4)
            elif usar_pontos and not usar_linha:
                mask_val = ~np.isnan(c["re"]) & ~np.isnan(c["im"])
                ax_ins.scatter(c["re"][mask_val], c["im"][mask_val], color=cor, s=22, marker=m_ins, edgecolors=tema["marker_edge"], linewidths=0.5, zorder=4)
            else:
                ax_ins.plot(c["re"], c["im"], color=cor, linewidth=1.3, linestyle=estilo, alpha=0.55, zorder=3)
                mask_val = ~np.isnan(c["re"]) & ~np.isnan(c["im"])
                ax_ins.scatter(c["re"][mask_val], c["im"][mask_val], color=cor, s=22, marker=m_ins, edgecolors=tema["marker_edge"], linewidths=0.5, zorder=4)

        if inset_limites:
            if inset_limites.get("xmin") is not None: ax_ins.set_xlim(left=inset_limites["xmin"])
            if inset_limites.get("xmax") is not None: ax_ins.set_xlim(right=inset_limites["xmax"])
            if inset_limites.get("ymin") is not None: ax_ins.set_ylim(bottom=inset_limites["ymin"])
            if inset_limites.get("ymax") is not None: ax_ins.set_ylim(top=inset_limites["ymax"])

        ax_ins.set_aspect("equal", adjustable="box")
        ax_ins.tick_params(labelsize=8.0, colors=tema["subtext"])
        for sp in ax_ins.spines.values():
            sp.set_color(tema["spine"])
        ax_ins.grid(True, linestyle=":", alpha=0.4, color=tema["grid"])
        titulo_ins = "Altas Frequências" if idioma == "Português" else "High Frequencies"
        ax_ins.set_title(titulo_ins, fontsize=8.5, fontweight="bold", color=tema["subtext"], pad=3)
        estilar_figura_e_eixos(fig, ax_ins, tema, idioma=idioma)

    if circuito_bytes is not None:
        img = mpimg.imread(circuito_bytes)
        ab = AnnotationBbox(
            OffsetImage(img, zoom=zoom_circuito),
            pos_circuito,
            xycoords="axes fraction",
            frameon=True, pad=0.35,
            bboxprops=dict(edgecolor=tema["box_edge"], facecolor="#ffffff", alpha=0.95, lw=1.0),
            zorder=8
        )
        ax.add_artist(ab)

    span_re = max(re_max - re_min, 1e-6)
    x_left_def = min(0.0, re_min - 2.0)
    x_right_def = re_max + span_re * 0.08
    y_bot_def = min(-1.5, im_min - 1.0)
    y_top_def = max(im_max * 1.15, im_min + 1.0)

    largura_x = max(x_right_def - x_left_def, 1e-6)
    altura_y = max(y_top_def - y_bot_def, 1e-6)

    xlim_user = limites_manuais.get("xlim") if limites_manuais else (None, None)
    ylim_user = limites_manuais.get("ylim") if limites_manuais else (None, None)
    usuario_definiu_limites = (
        (xlim_user and (xlim_user[0] is not None or xlim_user[1] is not None))
        or (ylim_user and (ylim_user[0] is not None or ylim_user[1] is not None))
    )

    if aspect_equal and not usuario_definiu_limites:
        largura_minima_aceitavel = altura_y * 1.25
        if largura_x < largura_minima_aceitavel:
            x_right_def = x_left_def + largura_minima_aceitavel
        altura_minima_aceitavel = largura_x * 0.55
        if altura_y < altura_minima_aceitavel:
            y_top_def = y_bot_def + altura_minima_aceitavel

    ax.set_xlabel(eixo_x_label, fontsize=12.5, labelpad=8)
    ax.set_ylabel(eixo_y_label, fontsize=12.5, labelpad=8)
    ax.set_xlim(x_left_def, x_right_def)
    ax.set_ylim(y_bot_def, y_top_def)
    if aspect_equal:
        ax.set_aspect("equal", adjustable="box")
    ax.grid(True, linestyle=":", alpha=0.4, color=tema["grid"])

    aplicar_ajustes_eixos_e_legenda(ax, limites_manuais, posicao_legenda, tema, legenda_horizontal=legenda_horizontal)
    estilar_figura_e_eixos(fig, ax, tema, idioma=idioma)
    plt.tight_layout()
    return fig
