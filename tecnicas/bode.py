from itertools import cycle
import matplotlib.pyplot as plt
import numpy as np
from core import (
    MARCADORES_PADRAO,
    aplicar_ajustes_eixos_e_legenda,
    estilar_figura_e_eixos,
    processar_cabecalho_e_dados,
)


def _estimar_frequencia_joelho(freq, fase):
    """
    Estima a frequência de joelho (knee frequency, f_0) onde a fase cruza -45°
    (ou +45° caso a fase esteja registrada em valores positivos).
    """
    mask = np.isfinite(freq) & (freq > 0) & np.isfinite(fase)
    f_val = freq[mask]
    p_val = fase[mask]
    if len(f_val) < 2:
        return None

    alvo = 45.0 if np.nanmedian(p_val) > 0 else -45.0
    diff = p_val - alvo

    # Procura cruzamento exato de sinal (interpolação linear em log10(freq))
    for i in range(len(diff) - 1):
        if diff[i] == 0:
            return float(f_val[i])
        if diff[i] * diff[i + 1] < 0:
            log_f1 = np.log10(f_val[i])
            log_f2 = np.log10(f_val[i + 1])
            frac = abs(diff[i]) / (abs(diff[i]) + abs(diff[i + 1]))
            log_fk = log_f1 + frac * (log_f2 - log_f1)
            return float(10 ** log_fk)

    # Caso não cruze exatamente, retorna o ponto mais próximo se estiver dentro de ±10° de ±45°
    idx_min = int(np.argmin(np.abs(diff)))
    if abs(diff[idx_min]) <= 10.0:
        return float(f_val[idx_min])
    return None


def gerar_plot_bode(
    fonte_dados,
    eixo_x_label,
    eixo_y1_label,
    eixo_y2_label,
    mapa_cores,
    mapa_estilos,
    mapa_nomes,
    limites_manuais,
    posicao_legenda,
    tema,
    idioma="Português",
    modo_tracado="Scatter + Lines",
    y1_log=True,
    exibir_freq_joelho=False,
    freq_joelho_manual=None,
    legenda_horizontal=False,
):
    """
    Técnica geral EIE - Bode.
    Lê arquivos .txt/.dat/.csv na estrutura (|Z|  Freq  Fase) em blocos de 3 colunas por amostra,
    ou extrai automaticamente de arquivos brutos EC-Lab (.mpr).
    - Eixo X (Frequência): escala logarítmica
    - Eixo Y1 (|Z|): escala logarítmica opcional (padrão True) ou linear
    - Eixo Y2 (Fase): eixo secundário à direita
    - Frequência de Joelho (f_0, fase = -45°): opção para supercapacitores com linha vertical tracejada
    """
    df, tokens_limpos = processar_cabecalho_e_dados(fonte_dados)
    num_cols = df.shape[1]
    if num_cols < 3:
        raise ValueError("O gráfico EIE - Bode exige blocos de 3 colunas: (|Z|, Freq, Fase).")

    num_blocos = num_cols // 3
    curvas = []

    for b in range(num_blocos):
        c_z = b * 3
        c_f = b * 3 + 1
        c_p = b * 3 + 2
        sub = df.iloc[:, [c_z, c_f, c_p]].dropna(how="all")
        if len(sub) == 0:
            continue

        idx_tok = c_p
        if idx_tok < len(tokens_limpos) and str(tokens_limpos[idx_tok]).strip().upper() not in ["FASE", "PHASE", "DEG", ""]:
            nome = str(tokens_limpos[idx_tok]).strip()
        else:
            nome = f"Sample {b + 1}"

        modz = sub.iloc[:, 0].to_numpy(float)
        freq = sub.iloc[:, 1].to_numpy(float)
        fase = sub.iloc[:, 2].to_numpy(float)

        invalid_f = (~np.isnan(freq)) & (freq <= 0)
        freq = np.where(invalid_f, np.nan, freq)
        if y1_log:
            invalid_z = (~np.isnan(modz)) & (modz <= 0)
            modz = np.where(invalid_z, np.nan, modz)

        # Quebra automaticamente com NaN se houver múltiplos ciclos sequenciais na mesma curva
        valid_f = freq[~np.isnan(freq)]
        if len(valid_f) > 3:
            log_vf = np.log10(valid_f)
            diffs_vf = np.diff(log_vf)
            med_step = float(np.nanmedian(diffs_vf[diffs_vf != 0])) if np.any(diffs_vf != 0) else -0.1
            f_sep, z_sep, p_sep = [], [], []
            prev_f = None
            for fv, zv, pv in zip(freq, modz, fase):
                if np.isnan(fv) or np.isnan(zv) or np.isnan(pv):
                    f_sep.append(np.nan)
                    z_sep.append(np.nan)
                    p_sep.append(np.nan)
                    prev_f = None
                    continue
                if prev_f is not None:
                    dlog = np.log10(fv) - np.log10(prev_f)
                    if (dlog > 0.35 if med_step < 0 else dlog < -0.35):
                        f_sep.append(np.nan)
                        z_sep.append(np.nan)
                        p_sep.append(np.nan)
                f_sep.append(fv)
                z_sep.append(zv)
                p_sep.append(pv)
                prev_f = fv
            freq = np.array(f_sep, dtype=float)
            modz = np.array(z_sep, dtype=float)
            fase = np.array(p_sep, dtype=float)

        curvas.append({
            "nome": nome,
            "freq": freq,
            "modz": modz,
            "fase": fase,
        })

    if not curvas:
        raise ValueError("Nenhum dado válido encontrado para EIE - Bode.")

    fig, ax1 = plt.subplots(figsize=(8.6, 5.4), dpi=300)
    ax2 = ax1.twinx()

    marcadores_ciclo = cycle(MARCADORES_PADRAO)
    handles_legenda = []

    usar_linha = ("Lines" in modo_tracado)
    usar_pontos = ("Scatter" in modo_tracado)

    for idx, c in enumerate(curvas):
        chave = c["nome"]
        cor = mapa_cores.get(chave, list(mapa_cores.values())[idx % len(mapa_cores)])
        estilo_user = mapa_estilos.get(chave, "-")
        rotulo = mapa_nomes.get(chave, chave)
        marcador = next(marcadores_ciclo)

        mask_val = ~np.isnan(c["freq"]) & ~np.isnan(c["modz"]) & ~np.isnan(c["fase"])

        if usar_linha:
            h1, = ax1.plot(
                c["freq"], c["modz"], color=cor, linewidth=2.0, linestyle=estilo_user,
                marker=marcador if usar_pontos else None, markersize=5.0,
                markeredgecolor=tema["marker_edge"], markeredgewidth=0.6,
                label=f"{rotulo} (|Z|)", zorder=4
            )
            handles_legenda.append(h1)
        elif usar_pontos:
            h1 = ax1.scatter(
                c["freq"][mask_val], c["modz"][mask_val], color=cor, s=36, marker=marcador,
                edgecolors=tema["marker_edge"], linewidths=0.7,
                label=f"{rotulo} (|Z|)", zorder=4
            )
            handles_legenda.append(h1)

        estilo_fase = "--" if estilo_user == "-" else ":"
        if usar_linha:
            h2, = ax2.plot(
                c["freq"], c["fase"], color=cor, linewidth=1.8, linestyle=estilo_fase,
                marker=marcador if usar_pontos else None, markersize=4.8,
                markerfacecolor=tema["ax_bg"], markeredgecolor=cor, markeredgewidth=1.1,
                alpha=0.88, label=f"{rotulo} (Fase)" if idioma == "Português" else f"{rotulo} (Phase)", zorder=5
            )
            handles_legenda.append(h2)
        elif usar_pontos:
            h2 = ax2.scatter(
                c["freq"][mask_val], c["fase"][mask_val], facecolors=tema["ax_bg"], edgecolors=cor,
                s=34, marker=marcador, linewidths=1.1,
                label=f"{rotulo} (Fase)" if idioma == "Português" else f"{rotulo} (Phase)", zorder=5
            )
            handles_legenda.append(h2)

    ax1.set_xscale("log")
    if y1_log:
        ax1.set_yscale("log")

    # Marcação da Frequência de Joelho (f_0) para Supercapacitores
    if exibir_freq_joelho:
        marcacoes_f0 = []
        if freq_joelho_manual is not None and freq_joelho_manual > 0:
            marcacoes_f0.append((float(freq_joelho_manual), tema["text"], None))
        else:
            for idx, c in enumerate(curvas):
                f0_est = _estimar_frequencia_joelho(c["freq"], c["fase"])
                if f0_est is not None and f0_est > 0:
                    chave = c["nome"]
                    cor_c = mapa_cores.get(chave, list(mapa_cores.values())[idx % len(mapa_cores)])
                    rot_c = mapa_nomes.get(chave, chave)
                    marcacoes_f0.append((f0_est, cor_c, rot_c))

        trans_topo = ax1.get_xaxis_transform()
        for idx_f, (f0_val, cor_f, rot_c) in enumerate(marcacoes_f0):
            ax1.axvline(
                f0_val,
                color=cor_f if len(marcacoes_f0) > 1 else tema["ref_line"],
                linestyle="--",
                linewidth=1.5,
                alpha=0.9,
                zorder=6,
            )
            f0_str = f"{f0_val:.3g}".replace(".", ",") if idioma == "Português" else f"{f0_val:.3g}"
            prefixo = f"{rot_c}: " if (rot_c and len(marcacoes_f0) > 1) else ""
            texto_badge = rf"{prefixo}$f_0 = {f0_str}\ \mathrm{{Hz}}$"
            y_pos_badge = max(0.55, 0.92 - idx_f * 0.09)
            ax1.text(
                f0_val,
                y_pos_badge,
                texto_badge,
                transform=trans_topo,
                ha="left",
                va="center",
                fontsize=9.2,
                fontweight="bold",
                color=tema["text"],
                bbox=dict(
                    boxstyle="round,pad=0.28",
                    facecolor=tema["box_bg"],
                    edgecolor=cor_f if len(marcacoes_f0) > 1 else tema["box_edge"],
                    lw=1.1,
                    alpha=0.95,
                ),
                zorder=7,
            )

    ax1.set_xlabel(eixo_x_label, fontsize=12.5, labelpad=8)
    ax1.set_ylabel(eixo_y1_label, fontsize=12.5, labelpad=8)
    ax2.set_ylabel(eixo_y2_label, fontsize=12.5, labelpad=8, color=tema["subtext"])
    ax2.tick_params(axis="y", colors=tema["subtext"], width=1.4)
    ax2.spines["right"].set_color(tema["spine"])
    ax2.spines["right"].set_linewidth(1.4)
    ax2.spines["top"].set_visible(False)
    ax2.spines["bottom"].set_visible(False)
    ax2.spines["left"].set_visible(False)

    ax1.grid(True, which="both", linestyle=":", alpha=0.4, color=tema["grid"])

    aplicar_ajustes_eixos_e_legenda(ax1, limites_manuais, posicao_legenda=None, tema=tema)

    y2lim_user = limites_manuais.get("y2lim") if limites_manuais else (None, None)
    if y2lim_user:
        if y2lim_user[0] is not None:
            ax2.set_ylim(bottom=y2lim_user[0])
        if y2lim_user[1] is not None:
            ax2.set_ylim(top=y2lim_user[1])

    if posicao_legenda and posicao_legenda != "Ocultar / Hide" and handles_legenda:
        leg = ax2.legend(
            handles=handles_legenda,
            loc=posicao_legenda,
            frameon=True,
            facecolor=tema["box_bg"],
            edgecolor=tema["box_edge"],
            fontsize=9.2,
            ncol=len(handles_legenda) if legenda_horizontal else 1,
        )
        for text in leg.get_texts():
            text.set_color(tema["text"])

    aplicar_ajustes_eixos_e_legenda(ax1, limites_manuais, posicao_legenda=None, tema=tema, eixo_y2=ax2)
    estilar_figura_e_eixos(fig, ax1, tema, idioma=idioma, eixo_y2=ax2)
    plt.tight_layout()
    return fig
