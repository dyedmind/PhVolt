from itertools import cycle
import re
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st

from core import (
    MARCADORES_PADRAO,
    aplicar_ajustes_eixos_e_legenda,
    estilar_figura_e_eixos,
)
from core.metrics import _calcular_metricas_supercapacitor_cgcd


def _extrair_grupo_amostra_sc(nome_curva):
    """
    Agrupa curvas pertencentes à mesma amostra (removendo sufixos de taxa como '_01_GCPL6', '_01_G', '1 A/g', '0.5Ag-1')
    para permitir comparar múltiplas amostras no mesmo gráfico de Ragone ou Rate Capability SC!
    """
    txt = str(nome_curva).strip()
    limpo = re.sub(r"[_\-\s]+0?\d+[_\-\s]*(?:GCPL\d*|CP\d*|GCD\d*|G\b|C\b).*$", "", txt, flags=re.IGNORECASE)
    limpo = re.sub(r"[_\-\s]*\d+(?:[.,]\d+)?\s*A\s*/?\s*g(?:\^-?1|-1)?.*$", "", limpo, flags=re.IGNORECASE)
    limpo = re.sub(r"\s*\(Ciclo\s*\d+\)\s*$", "", limpo, flags=re.IGNORECASE).strip(" _-")
    return limpo if limpo else txt


def extrair_series_ragone_rate_sc(
    fonte_dados,
    mapa_nomes,
    massa_mg=1.0,
    densidades_por_curva=None,
    densidades_lista_por_amostra=None,
    massas_por_amostra=None,
    agrupar_por_amostra=True,
    nome_amostra_unica="Supercapacitor",
):
    """
    Calcula as métricas validadas de CGCD (técnica 6) usando a massa ativa específica de cada amostra
    e organiza os pontos ordenados por densidade de corrente crescente para Ragone (E vs P) e Rate Capability (C_sp vs J).
    """
    # Passa mapa_nomes vazio para _calcular_metricas_supercapacitor_cgcd para preservar os nomes originais
    # das curvas durante o agrupamento por amostra, aplicando mapa_nomes apenas no nome final do grupo!
    df_cgcd = _calcular_metricas_supercapacitor_cgcd(
        fonte_dados,
        mapa_nomes={},
        massa_mg=massa_mg,
        tecnica_idx=6,
        densidades_por_curva=densidades_por_curva,
        densidades_lista_por_amostra=densidades_lista_por_amostra,
        massas_por_amostra=massas_por_amostra,
    )
    if df_cgcd is None or df_cgcd.empty:
        return {}, pd.DataFrame()

    registros = []
    for _, row in df_cgcd.iterrows():
        j_val = row.get("Densidade I (A/g)")
        c_int = row.get("C_sp Integral (F/g)")
        c_lin = row.get("C_sp Linear (F/g)")
        e_val = row.get("Energia (Wh/kg)")
        p_val = row.get("Potência (W/kg)")
        esr_val = row.get("ESR (Ω)")
        eff_val = row.get("Eficiência (%)")
        nome_c = str(row.get("Componente / Curva", "Curva"))

        if not isinstance(j_val, (int, float)) or j_val <= 0:
            continue
        if not isinstance(c_int, (int, float)) or c_int <= 0:
            continue

        grupo_chave = _extrair_grupo_amostra_sc(nome_c) if agrupar_por_amostra else nome_amostra_unica
        registros.append({
            "GrupoChave": grupo_chave,
            "Curva": nome_c,
            "Densidade I (A/g)": float(j_val),
            "C_sp Integral (F/g)": float(c_int),
            "C_sp Linear (F/g)": float(c_lin) if isinstance(c_lin, (int, float)) else np.nan,
            "Energia (Wh/kg)": float(e_val) if isinstance(e_val, (int, float)) else np.nan,
            "Potência (W/kg)": float(p_val) if isinstance(p_val, (int, float)) else np.nan,
            "ESR (Ω)": float(esr_val) if isinstance(esr_val, (int, float)) else np.nan,
            "Eficiência (%)": float(eff_val) if isinstance(eff_val, (int, float)) else np.nan,
        })

    if not registros:
        return {}, pd.DataFrame()

    df_reg = pd.DataFrame(registros)

    if df_reg["GrupoChave"].nunique() == len(df_reg) and len(df_reg) >= 2 and agrupar_por_amostra:
        df_reg["GrupoChave"] = nome_amostra_unica

    series_dict = {}
    linhas_tabela = []

    for grp_chave, df_sub in df_reg.groupby("GrupoChave", sort=False):
        rotulo_amostra = mapa_nomes.get(grp_chave, grp_chave) if mapa_nomes else grp_chave
        df_ord = df_sub.sort_values("Densidade I (A/g)").reset_index(drop=True)
        df_ord.insert(0, "Amostra", rotulo_amostra)
        df_ord = df_ord.drop(columns=["GrupoChave"])
        c_ini = float(df_ord["C_sp Integral (F/g)"].iloc[0])
        df_ord["Retenção (%)"] = np.round((df_ord["C_sp Integral (F/g)"] / max(c_ini, 1e-9)) * 100.0, 1)
        series_dict[grp_chave] = {
            "rotulo": rotulo_amostra,
            "df": df_ord,
        }
        linhas_tabela.append(df_ord)

    df_tabela_final = pd.concat(linhas_tabela, ignore_index=True) if linhas_tabela else pd.DataFrame()
    return series_dict, df_tabela_final


def gerar_plot_ragone_sc(
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
    massa_mg=1.0,
    densidades_por_curva=None,
    densidades_lista_por_amostra=None,
    massas_por_amostra=None,
    escala_log_ragone=True,
    exibir_tempos_descarga=True,
    agrupar_por_amostra=True,
    modo_tracado="Scatter + Lines",
    legenda_horizontal=False,
):
    nome_def = st.session_state.get("nome_arquivo_anterior", "Supercapacitor").split(".")[0]
    series_dict, _ = extrair_series_ragone_rate_sc(
        fonte_dados,
        mapa_nomes=mapa_nomes,
        massa_mg=massa_mg,
        densidades_por_curva=densidades_por_curva,
        densidades_lista_por_amostra=densidades_lista_por_amostra,
        massas_por_amostra=massas_por_amostra,
        agrupar_por_amostra=agrupar_por_amostra,
        nome_amostra_unica=nome_def,
    )

    if not series_dict:
        raise ValueError(
            "Não foi possível calcular Energia e Potência. Verifique se a densidade de corrente (A/g) está informada ou presente no .mpr."
            if idioma == "Português"
            else "Could not compute Energy and Power. Ensure current density (A/g) is provided or present in the .mpr file."
        )

    fig, ax = plt.subplots(figsize=(8.4, 5.4), dpi=300)
    usar_linha = ("Lines" in modo_tracado)
    usar_pontos = ("Scatter" in modo_tracado)
    marcadores_ciclo = cycle(MARCADORES_PADRAO)
    paleta_vals = list(mapa_cores.values()) if mapa_cores else ["#f97316", "#334155", "#8b5cf6", "#0284c7", "#10b981"]

    todos_p, todos_e = [], []
    for idx, (grp_chave, item_s) in enumerate(series_dict.items()):
        df_s = item_s["df"]
        rotulo = item_s["rotulo"]
        df_v = df_s.dropna(subset=["Potência (W/kg)", "Energia (Wh/kg)"])
        df_v = df_v[(df_v["Potência (W/kg)"] > 0) & (df_v["Energia (Wh/kg)"] > 0)]
        if df_v.empty:
            continue

        p_vals = df_v["Potência (W/kg)"].to_numpy(float)
        e_vals = df_v["Energia (Wh/kg)"].to_numpy(float)
        cor = mapa_cores.get(grp_chave, paleta_vals[idx % len(paleta_vals)])
        estilo = mapa_estilos.get(grp_chave, "-")
        marcador = next(marcadores_ciclo)

        if usar_linha:
            ax.plot(
                p_vals,
                e_vals,
                color=cor,
                linewidth=2.1,
                linestyle=estilo,
                marker=marcador if usar_pontos else None,
                markersize=6.0,
                markeredgecolor=tema["text"],
                markeredgewidth=0.9,
                label=rotulo,
                zorder=4,
            )
        else:
            ax.scatter(
                p_vals,
                e_vals,
                color=cor,
                s=44,
                marker=marcador,
                edgecolors=tema["text"],
                linewidths=0.9,
                label=rotulo,
                zorder=4,
            )

        todos_p.append(p_vals)
        todos_e.append(e_vals)

    if not todos_p:
        raise ValueError(
            "Pontos válidos de Energia/Potência insuficientes para o Gráfico de Ragone."
            if idioma == "Português"
            else "Insufficient valid Energy/Power points for Ragone Plot."
        )

    p_all = np.concatenate(todos_p)
    e_all = np.concatenate(todos_e)
    p_min, p_max = float(np.min(p_all)), float(np.max(p_all))
    e_min, e_max = float(np.min(e_all)), float(np.max(e_all))

    if escala_log_ragone:
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlim(p_min * 0.65, p_max * 1.55)
        ax.set_ylim(e_min * 0.65, e_max * 1.45)
    else:
        span_p = max(p_max - p_min, 1.0)
        span_e = max(e_max - e_min, 0.1)
        ax.set_xlim(max(0.0, p_min - span_p * 0.08), p_max + span_p * 0.10)
        ax.set_ylim(max(0.0, e_min - span_e * 0.10), e_max + span_e * 0.14)

    if exibir_tempos_descarga and escala_log_ragone:
        xlim_cur = ax.get_xlim()
        ylim_cur = ax.get_ylim()
        p_grid = np.geomspace(xlim_cur[0], xlim_cur[1], 100)
        for tau_s, lbl_tau in [(1.0, "1 s"), (10.0, "10 s"), (100.0, "100 s"), (1000.0, "1000 s")]:
            e_line = (p_grid * tau_s) / 3600.0
            mask_vis = (e_line >= ylim_cur[0] * 1.05) & (e_line <= ylim_cur[1] * 0.92)
            if np.sum(mask_vis) >= 5:
                ax.plot(p_grid[mask_vis], e_line[mask_vis], color=tema["ref_line"], linestyle="--", linewidth=0.95, alpha=0.55, zorder=2)
                idx_lbl = int(np.where(mask_vis)[0][len(np.where(mask_vis)[0]) // 2])
                ax.text(
                    p_grid[idx_lbl],
                    e_line[idx_lbl] * 1.08,
                    lbl_tau,
                    color=tema["subtext"],
                    fontsize=8.5,
                    rotation=32,
                    ha="center",
                    va="bottom",
                    alpha=0.85,
                    zorder=3,
                )

    ax.set_xlabel(eixo_x_label, fontsize=12.5, labelpad=8)
    ax.set_ylabel(eixo_y_label, fontsize=12.5, labelpad=8)
    ax.grid(True, which="both" if escala_log_ragone else "major", linestyle=":", alpha=0.4, color=tema["grid"])

    aplicar_ajustes_eixos_e_legenda(ax, limites_manuais, posicao_legenda, tema, legenda_horizontal=legenda_horizontal)
    estilar_figura_e_eixos(fig, ax, tema, idioma=idioma)
    plt.tight_layout()
    return fig


def gerar_plot_rate_sc(
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
    massa_mg=1.0,
    densidades_por_curva=None,
    densidades_lista_por_amostra=None,
    massas_por_amostra=None,
    usar_capacitancia_integral=True,
    exibir_retencao_badge=True,
    agrupar_por_amostra=True,
    modo_tracado="Scatter + Lines",
    legenda_horizontal=False,
):
    nome_def = st.session_state.get("nome_arquivo_anterior", "Supercapacitor").split(".")[0]
    series_dict, _ = extrair_series_ragone_rate_sc(
        fonte_dados,
        mapa_nomes=mapa_nomes,
        massa_mg=massa_mg,
        densidades_por_curva=densidades_por_curva,
        densidades_lista_por_amostra=densidades_lista_por_amostra,
        massas_por_amostra=massas_por_amostra,
        agrupar_por_amostra=agrupar_por_amostra,
        nome_amostra_unica=nome_def,
    )

    if not series_dict:
        raise ValueError(
            "Não foi possível calcular Capacitância vs. Densidade de Corrente. Verifique os dados de CGCD."
            if idioma == "Português"
            else "Could not compute Capacitance vs. Current Density. Please check the GCD data."
        )

    col_cap = "C_sp Integral (F/g)" if usar_capacitancia_integral else "C_sp Linear (F/g)"
    fig, ax = plt.subplots(figsize=(8.4, 5.4), dpi=300)
    usar_linha = ("Lines" in modo_tracado)
    usar_pontos = ("Scatter" in modo_tracado)
    marcadores_ciclo = cycle(MARCADORES_PADRAO)
    paleta_vals = list(mapa_cores.values()) if mapa_cores else ["#f97316", "#334155", "#8b5cf6", "#0284c7", "#10b981"]

    todos_j, todos_c = [], []
    for idx, (grp_chave, item_s) in enumerate(series_dict.items()):
        df_s = item_s["df"]
        rotulo = item_s["rotulo"]
        df_v = df_s.dropna(subset=["Densidade I (A/g)", col_cap])
        if df_v.empty:
            continue

        j_vals = df_v["Densidade I (A/g)"].to_numpy(float)
        c_vals = df_v[col_cap].to_numpy(float)
        cor = mapa_cores.get(grp_chave, paleta_vals[idx % len(paleta_vals)])
        estilo = mapa_estilos.get(grp_chave, "-")
        marcador = next(marcadores_ciclo)

        ret_pct = (c_vals[-1] / max(c_vals[0], 1e-9)) * 100.0 if len(c_vals) >= 2 else 100.0
        ret_str = f"{ret_pct:.1f}%".replace(".", ",") if idioma == "Português" else f"{ret_pct:.1f}%"
        rotulo_leg = f"{rotulo} ({ret_str})" if (exibir_retencao_badge and len(c_vals) >= 2) else rotulo

        if usar_linha:
            ax.plot(
                j_vals,
                c_vals,
                color=cor,
                linewidth=2.1,
                linestyle=estilo,
                marker=marcador if usar_pontos else None,
                markersize=6.2,
                markeredgecolor=tema["text"],
                markeredgewidth=0.9,
                label=rotulo_leg,
                zorder=4,
            )
        else:
            ax.scatter(
                j_vals,
                c_vals,
                color=cor,
                s=46,
                marker=marcador,
                edgecolors=tema["text"],
                linewidths=0.9,
                label=rotulo_leg,
                zorder=4,
            )

        todos_j.append(j_vals)
        todos_c.append(c_vals)

    if not todos_j:
        raise ValueError(
            "Pontos insuficientes para o gráfico de Rate Capability."
            if idioma == "Português"
            else "Insufficient points for Rate Capability plot."
        )

    j_all = np.concatenate(todos_j)
    c_all = np.concatenate(todos_c)
    j_min, j_max = float(np.min(j_all)), float(np.max(j_all))
    c_min, c_max = float(np.min(c_all)), float(np.max(c_all))
    span_j = max(j_max - j_min, 0.05)
    span_c = max(c_max - c_min, 1.0)

    ax.set_xlim(max(0.0, j_min - span_j * 0.06), j_max + span_j * 0.08)
    ax.set_ylim(max(0.0, c_min - span_c * 0.15), c_max + span_c * 0.16)

    ax.set_xlabel(eixo_x_label, fontsize=12.5, labelpad=8)
    ax.set_ylabel(eixo_y_label, fontsize=12.5, labelpad=8)
    ax.grid(True, linestyle=":", alpha=0.4, color=tema["grid"])

    aplicar_ajustes_eixos_e_legenda(ax, limites_manuais, posicao_legenda, tema, legenda_horizontal=legenda_horizontal)
    estilar_figura_e_eixos(fig, ax, tema, idioma=idioma)
    plt.tight_layout()
    return fig
