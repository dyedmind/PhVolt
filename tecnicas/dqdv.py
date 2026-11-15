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


def _suavizar_sinal(y, janela=11):
    """Suavização móvel centrada com preservação de bordas para reduzir ruído numérico da derivada dQ/dV."""
    n = len(y)
    janela = int(janela)
    if janela <= 1 or n < 5:
        return y.copy()
    if janela % 2 == 0:
        janela += 1
    if janela >= n:
        janela = n - 1 if (n - 1) % 2 == 1 else max(1, n - 2)
    if janela <= 1:
        return y.copy()

    meio = janela // 2
    kernel = np.ones(janela, dtype=float) / float(janela)
    y_pad = np.pad(y, (meio, meio), mode="edge")
    return np.convolve(y_pad, kernel, mode="valid")


def _calcular_curva_dqdv_ramo(q_arr, v_arr, eh_carga=True, janela_suav=11, passo_v_min=0.002):
    """
    Calcula dQ/dV (mAh g^-1 V^-1) a partir de um ramo monotônico de carga ou descarga.
    Reamostra sobre uma grade uniforme de potencial (passo_v_min) antes de diferenciar
    para eliminar picos espúrios causados por ruído de quantização de tensão (dV -> 0).
    """
    mask = np.isfinite(q_arr) & np.isfinite(v_arr)
    q = q_arr[mask]
    v = v_arr[mask]
    if len(q) < 6:
        return np.array([]), np.array([])

    # Garante ordenação crescente de potencial para interpolação limpa
    ordem = np.argsort(v)
    v_ord = v[ordem]
    q_ord = q[ordem]

    # Agrupa pontos duplicados de mesmo potencial fazendo a média de Q
    v_unicos, inv_idx = np.unique(np.round(v_ord, 5), return_inverse=True)
    if len(v_unicos) < 6:
        return np.array([]), np.array([])
    q_medios = np.bincount(inv_idx, weights=q_ord) / np.bincount(inv_idx)

    v_min, v_max = float(v_unicos[0]), float(v_unicos[-1])
    span_v = v_max - v_min
    if span_v < 0.02:
        return np.array([]), np.array([])

    n_grid = int(np.clip(round(span_v / max(passo_v_min, 0.0005)), 40, 1200))
    v_grid = np.linspace(v_min, v_max, n_grid)
    q_grid = np.interp(v_grid, v_unicos, q_medios)

    q_suave = _suavizar_sinal(q_grid, janela=janela_suav)
    dq_dv = np.gradient(q_suave, v_grid)
    dq_dv = _suavizar_sinal(dq_dv, janela=max(3, janela_suav // 2))

    # Por convenção eletroquímica:
    # - Carga (oxidação / delitiação): dQ/dV > 0 (picos para cima)
    # - Descarga (redução / litiação): dQ/dV < 0 (picos para baixo)
    if eh_carga:
        dq_dv = np.abs(dq_dv)
    else:
        dq_dv = -np.abs(dq_dv)

    return v_grid, dq_dv


def gerar_plot_dqdv(
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
    janela_suavizacao=11,
    passo_potencial_mv=3.0,
    exibir_carga=True,
    exibir_descarga=True,
    modo_tracado="Linhas (Lines)",
    legenda_horizontal=False,
):
    df, _ = processar_cabecalho_e_dados(fonte_dados)
    ciclos = extrair_ciclos_gcd(fonte_dados, df)

    fig, ax = plt.subplots(figsize=(8.6, 5.4), dpi=300)
    todos_v, todos_dqdv = [], []

    usar_linha = ("Lines" in modo_tracado)
    usar_pontos = ("Scatter" in modo_tracado)
    marcadores_ciclo = cycle(MARCADORES_PADRAO)
    passo_v = max(float(passo_potencial_mv or 3.0) / 1000.0, 0.0005)

    ax.axhline(0, color=tema["ref_line"], linestyle="--", linewidth=1.1, alpha=0.75, zorder=2)

    for idx, c in enumerate(ciclos):
        chave = c["nome"]
        cor = mapa_cores.get(chave, list(mapa_cores.values())[idx % len(mapa_cores)])
        estilo = mapa_estilos.get(chave, "-")
        rotulo = mapa_nomes.get(chave, chave)
        marcador = next(marcadores_ciclo)
        rotulo_usado = False

        if exibir_carga and len(c["x_chg"]) > 5:
            v_c, dq_c = _calcular_curva_dqdv_ramo(
                c["x_chg"], c["y_chg"], eh_carga=True, janela_suav=janela_suavizacao, passo_v_min=passo_v
            )
            if len(v_c) > 0:
                lbl = rotulo if not rotulo_usado else None
                rotulo_usado = True
                if usar_linha:
                    ax.plot(v_c, dq_c, color=cor, linewidth=2.1, linestyle=estilo, marker=marcador if usar_pontos else None, markersize=4.0, label=lbl, zorder=4)
                else:
                    ax.scatter(v_c, dq_c, color=cor, s=24, marker=marcador, edgecolors=tema["marker_edge"], linewidths=0.5, label=lbl, zorder=4)
                todos_v.append(v_c)
                todos_dqdv.append(dq_c)

        if exibir_descarga and len(c["x_dchg"]) > 5:
            v_d, dq_d = _calcular_curva_dqdv_ramo(
                c["x_dchg"], c["y_dchg"], eh_carga=False, janela_suav=janela_suavizacao, passo_v_min=passo_v
            )
            if len(v_d) > 0:
                lbl = rotulo if not rotulo_usado else None
                rotulo_usado = True
                if usar_linha:
                    ax.plot(v_d, dq_d, color=cor, linewidth=2.1, linestyle=estilo, marker=marcador if usar_pontos else None, markersize=4.0, label=lbl, zorder=4)
                else:
                    ax.scatter(v_d, dq_d, color=cor, s=24, marker=marcador, edgecolors=tema["marker_edge"], linewidths=0.5, label=lbl, zorder=4)
                todos_v.append(v_d)
                todos_dqdv.append(dq_d)

    if not todos_v:
        raise ValueError(
            "Não foi possível calcular dQ/dV. Carregue dados de GCD com colunas de Capacidade e Potencial."
            if idioma == "Português"
            else "Could not compute dQ/dV. Please upload GCD data with Capacity and Potential columns."
        )

    v_all = np.concatenate(todos_v)
    dq_all = np.concatenate(todos_dqdv)
    v_min, v_max = float(np.nanmin(v_all)), float(np.nanmax(v_all))
    dq_min, dq_max = float(np.nanmin(dq_all)), float(np.nanmax(dq_all))
    span_v = max(v_max - v_min, 1e-4)
    span_dq = max(dq_max - dq_min, 1e-4)

    ax.set_xlabel(eixo_x_label, fontsize=12.5, labelpad=8)
    ax.set_ylabel(eixo_y_label, fontsize=12.5, labelpad=8)
    ax.set_xlim(v_min - span_v * 0.04, v_max + span_v * 0.04)
    ax.set_ylim(dq_min - span_dq * 0.12, dq_max + span_dq * 0.14)
    ax.grid(True, linestyle=":", alpha=0.4, color=tema["grid"])

    aplicar_ajustes_eixos_e_legenda(ax, limites_manuais, posicao_legenda, tema, legenda_horizontal=legenda_horizontal)
    estilar_figura_e_eixos(fig, ax, tema, idioma=idioma)
    plt.tight_layout()
    return fig
