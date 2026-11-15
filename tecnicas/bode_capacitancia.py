from itertools import cycle
import matplotlib.pyplot as plt
import numpy as np
from core import (
    MARCADORES_PADRAO,
    aplicar_ajustes_eixos_e_legenda,
    estilar_figura_e_eixos,
    processar_cabecalho_e_dados,
)
from tecnicas.bode import _estimar_frequencia_joelho


def calcular_capacitancia_complexa_bode(freq, modz, fase_deg, massa_mg=1.0):
    """
    Calcula C'(f) e C''(f) em F/g a partir de |Z| (Ohm), freq (Hz) e Fase (graus)
    pelo modelo de capacitância complexa:
      Z'  = |Z| * cos(fase)
      Z'' = |Z| * sin(fase)
      C'  = -Z'' / (2 * pi * f * |Z|^2 * m_g)
      C'' =  Z'  / (2 * pi * f * |Z|^2 * m_g)
    """
    massa_g = max(float(massa_mg or 1.0), 1e-6) / 1000.0
    fase_rad = np.radians(fase_deg)
    z_real = modz * np.cos(fase_rad)
    z_imag = modz * np.sin(fase_rad)
    omega = 2.0 * np.pi * np.maximum(freq, 1e-12)
    denom = omega * np.maximum(modz ** 2, 1e-18) * massa_g

    c_real = -z_imag / denom
    c_imag = z_real / denom
    return c_real, c_imag


def gerar_plot_bode_capacitancia(
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
    massa_mg=1.0,
    modo_tracado="Scatter + Lines",
    exibir_freq_joelho=True,
    freq_joelho_manual=None,
    legenda_horizontal=False,
):
    """
    Curva de Capacitância Diferencial C'(f) (Eixo Y1) vs. Ângulo de Fase (°) (Eixo Y2) em escala log(f).
    Determina f_0 no cruzamento de Fase = -45° e calcula a constante de tempo dielétrica
    de relaxação τ_0 = 1 / (2 * π * f_0) (em ms ou s).
    """
    df, tokens_limpos = processar_cabecalho_e_dados(fonte_dados)
    num_cols = df.shape[1]
    if num_cols < 3:
        raise ValueError("A Curva de Capacitância Diferencial de Bode exige blocos de 3 colunas: (|Z|, Freq, Fase).")

    num_blocos = num_cols // 3
    fig, ax1 = plt.subplots(figsize=(8.6, 5.4), dpi=300)
    ax2 = ax1.twinx()

    marcadores_ciclo = cycle(MARCADORES_PADRAO)
    handles_legenda = []
    curvas_processadas = []
    usar_linha = ("Lines" in modo_tracado)
    usar_pontos = ("Scatter" in modo_tracado)

    for b in range(num_blocos):
        c_z, c_f, c_p = b * 3, b * 3 + 1, b * 3 + 2
        sub = df.iloc[:, [c_z, c_f, c_p]].dropna()
        if len(sub) < 3:
            continue

        chave = str(tokens_limpos[c_p]).strip() if c_p < len(tokens_limpos) else f"Sample {b + 1}"
        if chave.upper() in ["FASE", "PHASE", "DEG", ""]:
            chave = f"Sample {b + 1}"

        cor = mapa_cores.get(chave, list(mapa_cores.values())[b % len(mapa_cores)])
        estilo_user = mapa_estilos.get(chave, "-")
        rotulo = mapa_nomes.get(chave, chave)
        marcador = next(marcadores_ciclo)

        modz = sub.iloc[:, 0].to_numpy(float)
        freq = sub.iloc[:, 1].to_numpy(float)
        fase = sub.iloc[:, 2].to_numpy(float)

        mask = (freq > 0) & (modz > 0) & np.isfinite(fase)
        freq, modz, fase = freq[mask], modz[mask], fase[mask]
        if len(freq) < 3:
            continue

        ordem = np.argsort(freq)
        freq, modz, fase = freq[ordem], modz[ordem], fase[ordem]
        c_real, _ = calcular_capacitancia_complexa_bode(freq, modz, fase, massa_mg=massa_mg)

        curvas_processadas.append({
            "chave": chave,
            "rotulo": rotulo,
            "cor": cor,
            "freq": freq,
            "fase": fase,
            "c_real": c_real,
        })

        if usar_linha:
            h1, = ax1.plot(
                freq, c_real, color=cor, linewidth=2.0, linestyle=estilo_user,
                marker=marcador if usar_pontos else None, markersize=5.0,
                markeredgecolor=tema["marker_edge"], markeredgewidth=0.6,
                label=f"{rotulo} (C')", zorder=4
            )
            handles_legenda.append(h1)
        else:
            h1 = ax1.scatter(freq, c_real, color=cor, s=36, marker=marcador, label=f"{rotulo} (C')", zorder=4)
            handles_legenda.append(h1)

        estilo_fase = "--" if estilo_user == "-" else ":"
        lbl_fase = f"{rotulo} (Fase)" if idioma == "Português" else f"{rotulo} (Phase)"
        if usar_linha:
            h2, = ax2.plot(
                freq, fase, color=cor, linewidth=1.8, linestyle=estilo_fase,
                marker=marcador if usar_pontos else None, markersize=4.8,
                markerfacecolor=tema["ax_bg"], markeredgecolor=cor, markeredgewidth=1.1,
                alpha=0.88, label=lbl_fase, zorder=5
            )
            handles_legenda.append(h2)
        else:
            h2 = ax2.scatter(
                freq, fase, facecolors=tema["ax_bg"], edgecolors=cor, s=34, marker=marcador,
                linewidths=1.1, label=lbl_fase, zorder=5
            )
            handles_legenda.append(h2)

    ax1.set_xscale("log")

    # Marcação da Frequência de Joelho f_0 (Fase = -45°) e constante de tempo τ_0 = 1 / (2 * π * f_0)
    if exibir_freq_joelho:
        marcacoes_f0 = []
        if freq_joelho_manual is not None and freq_joelho_manual > 0:
            marcacoes_f0.append((float(freq_joelho_manual), tema["text"], None))
        else:
            for c_item in curvas_processadas:
                f0_est = _estimar_frequencia_joelho(c_item["freq"], c_item["fase"])
                if f0_est is not None and f0_est > 0:
                    marcacoes_f0.append((f0_est, c_item["cor"], c_item["rotulo"]))

        trans_topo = ax1.get_xaxis_transform()
        for idx_f, (f0_val, cor_f, rot_c) in enumerate(marcacoes_f0):
            tau0_s = 1.0 / (2.0 * np.pi * f0_val)
            if tau0_s < 1.0:
                tau_num = f"{tau0_s * 1000.0:.2f}".replace(".", ",") if idioma == "Português" else f"{tau0_s * 1000.0:.2f}"
                tau_un = r"\mathrm{ms}"
            else:
                tau_num = f"{tau0_s:.2f}".replace(".", ",") if idioma == "Português" else f"{tau0_s:.2f}"
                tau_un = r"\mathrm{s}"

            f0_str = f"{f0_val:.3g}".replace(".", ",") if idioma == "Português" else f"{f0_val:.3g}"
            prefixo = f"{rot_c}: " if (rot_c and len(marcacoes_f0) > 1) else ""
            texto_badge = rf"{prefixo}$f_0 = {f0_str}\ \mathrm{{Hz}}$ ($\tau_0 = {tau_num}\ {tau_un}$)"

            ax1.axvline(
                f0_val,
                color=cor_f if len(marcacoes_f0) > 1 else tema["ref_line"],
                linestyle="--",
                linewidth=1.5,
                alpha=0.9,
                zorder=6,
            )
            y_pos_badge = max(0.52, 0.91 - idx_f * 0.09)
            ax1.text(
                f0_val,
                y_pos_badge,
                texto_badge,
                transform=trans_topo,
                ha="left",
                va="center",
                fontsize=8.8,
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

    y2lim_user = limites_manuais.get("y2lim") if limites_manuais else (None, None)
    if y2lim_user:
        if y2lim_user[0] is not None:
            ax2.set_ylim(bottom=y2lim_user[0])
        if y2lim_user[1] is not None:
            ax2.set_ylim(top=y2lim_user[1])

    if posicao_legenda and posicao_legenda != "Ocultar / Hide" and handles_legenda:
        pos_xy_b = limites_manuais.get("legenda_xy") if isinstance(limites_manuais, dict) else None
        kw_leg_b = {"loc": "center", "bbox_to_anchor": (float(pos_xy_b[0]), float(pos_xy_b[1]))} if (posicao_legenda in ["Personalizada (X, Y)", "Custom (X, Y)"] and pos_xy_b is not None) else {"loc": posicao_legenda}
        leg = ax2.legend(
            handles=handles_legenda,
            **kw_leg_b,
            frameon=True,
            facecolor=tema["box_bg"],
            edgecolor=tema["box_edge"],
            fontsize=9.0,
            ncol=len(handles_legenda) if legenda_horizontal else 1,
        )
        for text in leg.get_texts():
            text.set_color(tema["text"])

    aplicar_ajustes_eixos_e_legenda(ax1, limites_manuais, posicao_legenda=None, tema=tema, eixo_y2=ax2)
    estilar_figura_e_eixos(fig, ax1, tema, idioma=idioma, eixo_y2=ax2)
    plt.tight_layout()
    return fig
