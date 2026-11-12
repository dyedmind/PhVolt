import io
import os
import re
from datetime import datetime
from itertools import cycle
from pathlib import Path
import matplotlib.image as mpimg
from matplotlib.lines import Line2D
from matplotlib.offsetbox import AnnotationBbox, OffsetImage
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
from mpl_toolkits.axes_grid1.inset_locator import inset_axes
import numpy as np
import pandas as pd
import streamlit as st

# ==============================================================================
# CONFIGURAÇÃO GERAL DA PÁGINA E MATPLOTLIB
# ==============================================================================
caminho_icone = Path(__file__).resolve().parent / "vikavolt.ico"
icone_pagina = str(caminho_icone) if caminho_icone.exists() else "⚡"

st.set_page_config(
    page_title="PhVolt - Análise Eletroquímica",
    page_icon=icone_pagina,
    layout="wide",
)

plt.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "DejaVu Sans", "Helvetica"],
        "axes.linewidth": 1.4,
        "xtick.major.width": 1.4,
        "ytick.major.width": 1.4,
    }
)

PALETAS_DISPONIVEIS = {
    "PhVolt Padrão": [
        "#f97316", "#334155", "#8b5cf6", "#0284c7", "#10b981", "#e11d48", "#d97706"
    ],
    "Deep (Seaborn Modern)": [
        "#4c72b0", "#dd8452", "#55a868", "#c44e52", "#8172b3", "#937860", "#da8bc3"
    ],
    "Tableau 10": [
        "#4e79a7", "#f28e2b", "#e15759", "#76b7b2", "#59a14f", "#edc948", "#b07aa1"
    ],
    "Dark2 (Alto Contraste)": [
        "#1b9e77", "#d95f02", "#7570b3", "#e7298a", "#66a61e", "#e6ab02", "#a6761d"
    ],
    "Set1 (Cores Vivas)": [
        "#e41a1c", "#377eb8", "#4daf4a", "#984ea3", "#ff7f00", "#ffff33", "#a65628"
    ],
    "Viridis (Perceptual)": [
        "#440154", "#414487", "#2a788e", "#22a884", "#7ad151", "#fde725", "#35b779"
    ],
    "Monocromático / Escala de Cinza": [
        "#0f172a", "#334155", "#475569", "#64748b", "#94a3b8", "#cbd5e1"
    ],
}

MARCADORES_PADRAO = ["o", "s", "^", "D", "v", "P", "*"]

TEXTOS_PADRAO = {
    "Português": {
        "cv_x": r"$\mathbf{Potencial\ vs\ Li/Li^+\ (V)}$",
        "cv_y": r"$\mathbf{Corrente\ (mA)}$",
        "cv_charge": "Carga →",
        "cv_discharge": "← Descarga",
        "eie_x": r"$\mathbf{Z_{Real}\ (\Omega)}$",
        "eie_y": r"$\mathbf{-Z_{Im}\ (\Omega)}$",
        "eie_inset": "Região de altas frequências",
        "gcd_x": r"$\mathbf{Capacidade\ Específica\ (mAh\ g_S^{-1})}$",
        "gcd_y": r"$\mathbf{Potencial\ vs\ Li/Li^+\ (V)}$",
        "rate_x": r"$\mathbf{Número\ de\ Ciclos}$",
        "rate_y": r"$\mathbf{Capacidade\ Específica\ (mAh\ g_S^{-1})}$",
        "ciclabilidade_x": r"$\mathbf{Número\ de\ Ciclos}$",
        "ciclabilidade_y": r"$\mathbf{Capacidade\ Específica\ (mAh\ g_S^{-1})}$",
        "ciclabilidade_rate": "Taxa: 0,5 C",
        "ce_x": r"$\mathbf{Número\ de\ Ciclos}$",
        "ce_y1": r"$\mathbf{Capacidade\ de\ Descarga\ (mAh\ g_S^{-1})}$",
        "ce_y2": r"$\mathbf{Eficiência\ Coulômbica\ (\%)}$",
        "sc_2e_x": r"$\mathbf{Tempo\ (s)}$",
        "sc_2e_y": r"$\mathbf{Potencial\ da\ Célula\ (V)}$",
        "sc_3e_x": r"$\mathbf{Tempo\ (s)}$",
        "sc_3e_y1": r"$\mathbf{Potencial\ da\ Célula\ -\ E_{cell}\ (V)}$",
        "sc_3e_y2": r"$\mathbf{Potencial\ dos\ Eletrodos\ -\ E_{we},\ E_{ce}\ (V)}$",
        "sc_rate_x": r"$\mathbf{Número\ de\ Ciclos}$",
        "sc_rate_y": r"$\mathbf{Capacitância\ Específica\ (F\ g^{-1})}$",
        "bet_x": r"$\mathbf{Pressão\ Relativa\ (p/p_0)}$",
        "bet_y": r"$\mathbf{Quantidade\ Adsorvida\ (cm^3\ g^{-1}\ STP)}$",
        "bet_ads": "Adsorção (fechado)",
        "bet_des": "Dessorção (aberto)",
        "bet_inset": "Região de baixo volume de poros",
        "bet_legenda": r"$\mathbf{Amostra}$",
        "bet_legenda_area": r"$\mathbf{Amostra\ (S_{BET})}$",
    },
    "Inglês": {
        "cv_x": r"$\mathbf{Potential\ vs\ Li/Li^+\ (V)}$",
        "cv_y": r"$\mathbf{Current\ (mA)}$",
        "cv_charge": "Charge →",
        "cv_discharge": "← Discharge",
        "eie_x": r"$\mathbf{Z_{Real}\ (\Omega)}$",
        "eie_y": r"$\mathbf{-Z_{Im}\ (\Omega)}$",
        "eie_inset": "High-frequency region",
        "gcd_x": r"$\mathbf{Specific\ Capacity\ (mAh\ g_S^{-1})}$",
        "gcd_y": r"$\mathbf{Potential\ vs\ Li/Li^+\ (V)}$",
        "rate_x": r"$\mathbf{Cycle\ Number}$",
        "rate_y": r"$\mathbf{Specific\ Capacity\ (mAh\ g_S^{-1})}$",
        "ciclabilidade_x": r"$\mathbf{Cycle\ Number}$",
        "ciclabilidade_y": r"$\mathbf{Specific\ Capacity\ (mAh\ g_S^{-1})}$",
        "ciclabilidade_rate": "Rate: 0.5 C",
        "ce_x": r"$\mathbf{Cycle\ Number}$",
        "ce_y1": r"$\mathbf{Discharge\ Capacity\ (mAh\ g_S^{-1})}$",
        "ce_y2": r"$\mathbf{Coulombic\ Efficiency\ (\%)}$",
        "sc_2e_x": r"$\mathbf{Time\ (s)}$",
        "sc_2e_y": r"$\mathbf{Cell\ Potential\ (V)}$",
        "sc_3e_x": r"$\mathbf{Time\ (s)}$",
        "sc_3e_y1": r"$\mathbf{Cell\ Potential\ -\ E_{cell}\ (V)}$",
        "sc_3e_y2": r"$\mathbf{Electrode\ Potential\ -\ E_{we},\ E_{ce}\ (V)}$",
        "sc_rate_x": r"$\mathbf{Cycle\ Number}$",
        "sc_rate_y": r"$\mathbf{Specific\ Capacitance\ (F\ g^{-1})}$",
        "bet_x": r"$\mathbf{Relative\ Pressure\ (p/p_0)}$",
        "bet_y": r"$\mathbf{Quantity\ Adsorbed\ (cm^3\ g^{-1}\ STP)}$",
        "bet_ads": "Adsorption (closed)",
        "bet_des": "Desorption (open)",
        "bet_inset": "Low-pore volume region",
        "bet_legenda": r"$\mathbf{Sample}$",
        "bet_legenda_area": r"$\mathbf{Sample\ (S_{BET})}$",
    },
}


# ==============================================================================
# FORMATAÇÃO DE NÚMEROS POR IDIOMA (VÍRGULA EM PT, PONTO EM EN)
# ==============================================================================
def fmt_num(valor, casas=1, idioma="Português"):
    texto = f"{valor:.{casas}f}"
    return texto.replace(".", ",") if idioma == "Português" else texto


def aplicar_separador_decimal_eixos(ax, idioma="Português"):
    if idioma == "Português":
        def formatador_pt(x, pos):
            if np.isclose(x, round(x)):
                return f"{int(round(x))}"
            return f"{x:g}".replace(".", ",")

        ax.xaxis.set_major_formatter(FuncFormatter(formatador_pt))
        ax.yaxis.set_major_formatter(FuncFormatter(formatador_pt))


# ==============================================================================
# GERENCIAMENTO DE TEMA (CLARO / DARK MODE)
# ==============================================================================
def obter_tema_visual(dark_mode=False):
    if dark_mode:
        return {
            "fig_bg": "#0f172a",
            "ax_bg": "#0f172a",
            "box_bg": "#1e293b",
            "text": "#f8fafc",
            "subtext": "#cbd5e1",
            "spine": "#64748b",
            "grid": "#334155",
            "box_edge": "#475569",
            "zebra": "#1e293b",
            "marker_edge": "#0f172a",
            "ref_line": "#94a3b8",
        }
    return {
        "fig_bg": "#ffffff",
        "ax_bg": "#ffffff",
        "box_bg": "#ffffff",
        "text": "#1e293b",
        "subtext": "#334155",
        "spine": "#334155",
        "grid": "#cbd5e1",
        "box_edge": "#cbd5e1",
        "zebra": "#f1f5f9",
        "marker_edge": "#ffffff",
        "ref_line": "#94a3b8",
    }


def estilar_figura_e_eixos(fig, ax, tema, idioma="Português", y_color=None):
    fig.patch.set_facecolor(tema["fig_bg"])
    ax.set_facecolor(tema["ax_bg"])
    ax.xaxis.label.set_color(tema["text"])
    ax.yaxis.label.set_color(y_color if y_color else tema["text"])
    ax.tick_params(axis="x", colors=tema["subtext"])
    ax.tick_params(axis="y", colors=y_color if y_color else tema["subtext"])
    for spine_name, spine in ax.spines.items():
        if spine_name == "right" and y_color:
            continue
        spine.set_color(tema["spine"])
        spine.set_linewidth(1.4)
    aplicar_separador_decimal_eixos(ax, idioma)


# ==============================================================================
# LEITURA ROBUSTA E SEGURA DE DADOS
# ==============================================================================
def extrair_linhas_arquivo(fonte_dados):
    if hasattr(fonte_dados, "getvalue"):
        linhas = [
            l.decode("utf-8", errors="ignore").rstrip("\r\n")
            for l in fonte_dados.getvalue().splitlines()
        ]
    elif isinstance(fonte_dados, (bytes, bytearray)):
        linhas = [
            l.decode("utf-8", errors="ignore").rstrip("\r\n")
            for l in fonte_dados.splitlines()
        ]
    else:
        with open(fonte_dados, "r", encoding="utf-8", errors="ignore") as f:
            linhas = [l.rstrip("\r\n") for l in f]
    return [l for l in linhas if l.strip()]


def processar_cabecalho_e_dados(fonte_dados):
    linhas = extrair_linhas_arquivo(fonte_dados)
    idx_primeiro_dado = 0
    idx_long_name, idx_comments = None, None

    for i, linha in enumerate(linhas):
        partes = linha.split()
        if not partes:
            continue
        if "Long Name" in linha or "LongName" in linha:
            idx_long_name = i
        elif "Comments" in linha or "Comment" in linha:
            idx_comments = i

        conseguiu = False
        for p in partes:
            try:
                float(p.replace(",", "."))
                conseguiu = True
                break
            except ValueError:
                continue

        if conseguiu and not any(
            tag in linha
            for tag in ["Long Name", "Comments", "Units", "Axis", r"\-(", r"\+("]
        ):
            idx_primeiro_dado = i
            break

    idx_rotulos = (
        idx_long_name
        if idx_long_name is not None
        else (idx_comments if idx_comments is not None else 0)
    )

    linha_cabecalho = linhas[idx_rotulos]
    tokens = [t.strip() for t in linha_cabecalho.split("\t")]
    if len(tokens) <= 1:
        tokens = [t.strip() for t in linha_cabecalho.split()]

    descartes = [
        "LONG NAME", "LONGNAME", "COMMENTS", "COMMENT", "UNITS", "UNIT", "AXIS", "",
        "PRESSÃO RELATIVA", "RELATIVE PRESSURE", "QUANTIDADE ADSORVIDA", "QUANTITY ADSORBED"
    ]
    tokens_limpos = [
        t for t in tokens
        if t.upper() not in descartes
        and not any(tag in t for tag in [r"\+(", r"\-(", "cm", "g-1", "STP", "p.p"])
    ]

    max_cols = max(len(l.split("\t")) for l in linhas[idx_primeiro_dado:])
    if max_cols <= 1:
        max_cols = max(len(l.split()) for l in linhas[idx_primeiro_dado:])

    matriz = []
    for l in linhas[idx_primeiro_dado:]:
        partes_tab = l.split("\t")
        if len(partes_tab) <= 1 and max_cols > 1:
            partes_tab = l.split()

        row = []
        for p in partes_tab:
            p_limpo = p.strip().replace(",", ".")
            try:
                row.append(float(p_limpo))
            except ValueError:
                row.append(np.nan)

        while len(row) < max_cols:
            row.append(np.nan)
        matriz.append(row[:max_cols])

    df = pd.DataFrame(matriz)
    return df, tokens_limpos


def extrair_ciclos_gcd(fonte_dados, df):
    linhas = extrair_linhas_arquivo(fonte_dados)
    linha_taxas = linhas[0].split("\t") if len(linhas) > 0 else []
    linha_sub = linhas[1].split("\t") if len(linhas) > 1 else []

    tem_subcabecalho = any(
        palavra in " ".join(linha_sub).upper()
        for palavra in ["CARGA", "DESCARGA", "CHARGE", "DISCHARGE", "CHG", "DCHG"]
    )

    ciclos = []
    num_cols = df.shape[1]

    if tem_subcabecalho and num_cols >= 4:
        contador_nomes = {}
        for idx_bloco, col in enumerate(range(0, num_cols, 4)):
            if col + 3 >= num_cols:
                break

            sub_chg = df.iloc[:, [col, col + 1]].dropna()
            sub_dch = df.iloc[:, [col + 2, col + 3]].dropna()

            if len(sub_chg) == 0 and len(sub_dch) == 0:
                continue

            nome_bruto = (
                linha_taxas[col].strip()
                if col < len(linha_taxas) and linha_taxas[col].strip()
                else f"Curve {idx_bloco + 1}"
            )

            contador_nomes[nome_bruto] = contador_nomes.get(nome_bruto, 0) + 1
            chave_unica = (
                nome_bruto
                if contador_nomes[nome_bruto] == 1
                else f"{nome_bruto} ({contador_nomes[nome_bruto]})"
            )

            ciclos.append({
                "nome": chave_unica,
                "label_legenda": nome_bruto,
                "x_chg": sub_chg.iloc[:, 0].to_numpy(float) if len(sub_chg) > 0 else np.array([]),
                "y_chg": sub_chg.iloc[:, 1].to_numpy(float) if len(sub_chg) > 0 else np.array([]),
                "x_dch": sub_dch.iloc[:, 0].to_numpy(float) if len(sub_dch) > 0 else np.array([]),
                "y_dch": sub_dch.iloc[:, 1].to_numpy(float) if len(sub_dch) > 0 else np.array([]),
            })
    else:
        _, tokens_limpos = processar_cabecalho_e_dados(fonte_dados)
        nomes_y = [tokens_limpos[k] for k in range(1, len(tokens_limpos), 2)] if len(tokens_limpos) >= 2 else tokens_limpos
        contador_nomes = {}
        for idx, col in enumerate(range(0, num_cols, 2)):
            if col + 1 >= num_cols:
                break
            sub = df.iloc[:, [col, col + 1]].dropna()
            if len(sub) == 0:
                continue
            nome_bruto = nomes_y[idx].strip() if idx < len(nomes_y) else f"Curve {idx + 1}"
            contador_nomes[nome_bruto] = contador_nomes.get(nome_bruto, 0) + 1
            chave_unica = (
                nome_bruto
                if contador_nomes[nome_bruto] == 1
                else f"{nome_bruto} ({contador_nomes[nome_bruto]})"
            )
            ciclos.append({
                "nome": chave_unica,
                "label_legenda": nome_bruto,
                "x_chg": sub.iloc[:, 0].to_numpy(float),
                "y_chg": sub.iloc[:, 1].to_numpy(float),
                "x_dch": np.array([]),
                "y_dch": np.array([]),
            })

    return ciclos


def extrair_curvas_3_eletrodos(fonte_dados, df):
    linhas = extrair_linhas_arquivo(fonte_dados)
    tokens_cab = [t.strip() for t in linhas[0].split("\t")] if linhas else []
    if len(tokens_cab) <= 1 and linhas:
        tokens_cab = [t.strip() for t in linhas[0].split()]

    num_cols = df.shape[1]
    curvas = []
    nomes_padrao = ["Ecell/V", "Ewe/V", "Ece/V"]

    for col_idx in range(1, num_cols):
        sub = df.iloc[:, [0, col_idx]].dropna()
        if len(sub) == 0:
            continue
        nome_col = (
            tokens_cab[col_idx]
            if col_idx < len(tokens_cab) and tokens_cab[col_idx]
            else (nomes_padrao[col_idx - 1] if (col_idx - 1) < len(nomes_padrao) else f"Signal {col_idx}")
        )
        curvas.append({
            "nome": nome_col,
            "x": sub.iloc[:, 0].to_numpy(float),
            "y": sub.iloc[:, 1].to_numpy(float),
        })

    return curvas


def identificar_amostras(df, tokens_limpos, tecnica_idx, fonte_dados=None):
    num_cols = df.shape[1]
    if tecnica_idx in [3, 8]:
        num_curvas = num_cols - 1
        legendas = tokens_limpos[1:] if len(tokens_limpos) > num_curvas else tokens_limpos
        if len(legendas) < num_curvas:
            legendas = [f"Sample {i+1}" for i in range(num_curvas)]
        return legendas[:num_curvas]
    elif tecnica_idx == 5:
        return ["Discharge Capacity", "Coulombic Efficiency"]
    elif tecnica_idx in [2, 6] and fonte_dados is not None:
        ciclos_gcd = extrair_ciclos_gcd(fonte_dados, df)
        return [c["nome"] for c in ciclos_gcd]
    elif tecnica_idx == 7 and fonte_dados is not None:
        curvas_3e = extrair_curvas_3_eletrodos(fonte_dados, df)
        return [c["nome"] for c in curvas_3e]
    else:
        num_amostras = num_cols // 2 if num_cols >= 2 else num_cols
        if len(tokens_limpos) >= 2:
            nomes = [tokens_limpos[k] for k in range(1, len(tokens_limpos), 2)]
        else:
            nomes = tokens_limpos
        if len(nomes) < num_amostras:
            nomes = nomes + [f"Sample {i+1}" for i in range(len(nomes), num_amostras)]
        return nomes[:num_amostras]


# ==============================================================================
# UTILITÁRIOS DE FORMATAÇÃO MANUAL (LIMITES E LEGENDA)
# ==============================================================================
def aplicar_ajustes_eixos_e_legenda(ax, limites_manuais, posicao_legenda, tema, handles=None, title_legenda=None, fontsize_leg=10.0):
    if limites_manuais:
        xlim = limites_manuais.get("xlim")
        if xlim:
            if xlim[0] is not None:
                ax.set_xlim(left=xlim[0])
            if xlim[1] is not None:
                ax.set_xlim(right=xlim[1])

        ylim = limites_manuais.get("ylim")
        if ylim:
            if ylim[0] is not None:
                ax.set_ylim(bottom=ylim[0])
            if ylim[1] is not None:
                ax.set_ylim(top=ylim[1])

    if posicao_legenda == "Ocultar / Hide":
        leg = ax.get_legend()
        if leg:
            leg.remove()
    elif posicao_legenda:
        kwargs_leg = dict(
            loc=posicao_legenda,
            frameon=True,
            facecolor=tema["box_bg"],
            edgecolor=tema["box_edge"],
            fontsize=fontsize_leg,
        )
        if handles is not None:
            kwargs_leg["handles"] = handles
        if title_legenda is not None:
            kwargs_leg["title"] = title_legenda
            kwargs_leg["title_fontsize"] = fontsize_leg + 0.5

        leg = ax.legend(**kwargs_leg)
        for text in leg.get_texts():
            text.set_color(tema["text"])
        if leg.get_title():
            leg.get_title().set_color(tema["text"])


# ==============================================================================
# FUNÇÕES DE PLOTAGEM
# ==============================================================================

# ------------------------------------------------------------------------------
# (1) CV MULTIPLOT
# ------------------------------------------------------------------------------
def gerar_plot_cv(
    fonte_dados, velocidade, eixo_x_label, eixo_y_label, tag_carga, tag_descarga,
    mapa_cores, mapa_nomes, mapa_estilos, limites_manuais, posicao_legenda, tema,
    idioma="Português", exibir_setas=True, pos_carga=(0.35, 0.58), pos_descarga=(0.65, 0.38)
):
    df, tokens_limpos = processar_cabecalho_e_dados(fonte_dados)
    num_cols = df.shape[1]
    curvas = []

    if num_cols >= 2 and num_cols % 2 == 0:
        nomes_y = [tokens_limpos[k] for k in range(1, len(tokens_limpos), 2)] if len(tokens_limpos) >= 2 else tokens_limpos
        for idx, col in enumerate(range(0, num_cols, 2)):
            sub = df.iloc[:, [col, col + 1]].dropna()
            if len(sub) == 0: continue
            nome = nomes_y[idx] if idx < len(nomes_y) else f"Sample {idx + 1}"
            curvas.append({"nome": nome.strip(), "E": sub.iloc[:, 0].to_numpy(float), "I": sub.iloc[:, 1].to_numpy(float)})
    else:
        nomes_y = tokens_limpos[1:] if len(tokens_limpos) >= num_cols else tokens_limpos
        for col in range(1, num_cols):
            sub = df.iloc[:, [0, col]].dropna()
            if len(sub) == 0: continue
            nome = nomes_y[col - 1] if (col - 1) < len(nomes_y) else f"Sample {col}"
            curvas.append({"nome": nome.strip(), "E": sub.iloc[:, 0].to_numpy(float), "I": sub.iloc[:, 1].to_numpy(float)})

    fig, ax = plt.subplots(figsize=(8.4, 5.4), dpi=300)
    todos_e = np.concatenate([c["E"] for c in curvas if len(c["E"]) > 0])
    todos_i = np.concatenate([c["I"] for c in curvas if len(c["I"]) > 0])
    e_min, e_max = np.min(todos_e), np.max(todos_e)
    i_min, i_max = np.min(todos_i), np.max(todos_i)

    ax.axhline(0, color=tema["ref_line"], linestyle="--", linewidth=1.1, alpha=0.7)
    for idx, c in enumerate(curvas):
        cor = mapa_cores.get(c["nome"], list(mapa_cores.values())[idx % len(mapa_cores)])
        estilo = mapa_estilos.get(c["nome"], "-")
        rotulo_curva = mapa_nomes.get(c["nome"], c["nome"])
        ax.plot(c["E"], c["I"], color=cor, linewidth=2.2, linestyle=estilo, label=rotulo_curva)

    span_e, span_i = e_max - e_min, i_max - i_min
    if exibir_setas:
        ax.text(
            pos_carga[0], pos_carga[1], tag_carga,
            transform=ax.transAxes, fontsize=10.5, fontweight="semibold", color=tema["subtext"], zorder=5
        )
        ax.text(
            pos_descarga[0], pos_descarga[1], tag_descarga,
            transform=ax.transAxes, fontsize=10.5, fontweight="semibold", color=tema["subtext"], zorder=5
        )

    if velocidade:
        ax.text(0.04, 0.93, rf"$\nu = {velocidade}$", transform=ax.transAxes, fontsize=10.5,
                fontweight="bold", color=tema["text"], bbox=dict(boxstyle="round,pad=0.35", facecolor=tema["box_bg"], edgecolor=tema["box_edge"]))

    ax.set_xlabel(eixo_x_label, fontsize=12.5, labelpad=8)
    ax.set_ylabel(eixo_y_label, fontsize=12.5, labelpad=8)
    ax.set_xlim(e_min - span_e * 0.05, e_max + span_e * 0.05)
    ax.set_ylim(i_min - span_i * 0.10, i_max + span_i * 0.18)
    ax.grid(True, linestyle=":", alpha=0.4, color=tema["grid"])

    aplicar_ajustes_eixos_e_legenda(ax, limites_manuais, posicao_legenda, tema)
    estilar_figura_e_eixos(fig, ax, tema, idioma)
    plt.tight_layout()
    return fig


# ------------------------------------------------------------------------------
# (2) EIE NYQUIST (COM INSET 1:1 PARA ALTAS FREQUÊNCIAS E MODO APENAS LINHA)
# ------------------------------------------------------------------------------
def gerar_plot_eie(
    fonte_dados, circuito_bytes, eixo_x_label, eixo_y_label, titulo_inset,
    mapa_cores, mapa_nomes, mapa_estilos, limites_manuais, posicao_legenda, tema,
    idioma="Português", pos_circuito=(0.62, 0.78), zoom_circuito=0.36,
    exibir_inset=False, inset_bbox=(0.48, 0.18, 0.44, 0.34), inset_limites=None,
    aspect_equal=False, modo_plot="Pontos + Linha"
):
    df, tokens_limpos = processar_cabecalho_e_dados(fonte_dados)
    num_cols = df.shape[1]
    curvas = []

    nomes_y = [tokens_limpos[k] for k in range(1, len(tokens_limpos), 2)] if len(tokens_limpos) >= 2 else tokens_limpos
    for idx, col in enumerate(range(0, num_cols, 2)):
        if col + 1 < num_cols:
            nome = nomes_y[idx] if idx < len(nomes_y) else f"Sample {idx + 1}"
            if nome.strip().upper() in ["Y", "ZIM", "-ZIM", ""]:
                nome = f"Sample {idx + 1}"
            sub = df.iloc[:, [col, col + 1]].dropna()
            if len(sub) == 0: continue
            curvas.append({"nome": nome.strip(), "re": sub.iloc[:, 0].to_numpy(float), "im": sub.iloc[:, 1].to_numpy(float)})

    fig, ax = plt.subplots(figsize=(8.4, 5.4), dpi=300)
    marcadores_ciclo = cycle(MARCADORES_PADRAO)

    todos_re = np.concatenate([c["re"] for c in curvas if len(c["re"]) > 0])
    todos_im = np.concatenate([c["im"] for c in curvas if len(c["im"]) > 0])
    re_min, re_max = np.min(todos_re), np.max(todos_re)
    im_min, im_max = np.min(todos_im), np.max(todos_im)

    marcadores_por_curva = []
    for idx, c in enumerate(curvas):
        cor = mapa_cores.get(c["nome"], list(mapa_cores.values())[idx % len(mapa_cores)])
        estilo = mapa_estilos.get(c["nome"], "-")
        rotulo_curva = mapa_nomes.get(c["nome"], c["nome"])
        marcador = next(marcadores_ciclo)
        marcadores_por_curva.append(marcador)

        if modo_plot == "Apenas Linha":
            ax.plot(c["re"], c["im"], color=cor, linewidth=2.2, linestyle=estilo, alpha=0.95, label=rotulo_curva, zorder=4)
        else:
            ax.plot(c["re"], c["im"], color=cor, linewidth=1.7, linestyle=estilo, alpha=0.65, zorder=3)
            ax.scatter(c["re"], c["im"], color=cor, s=40, marker=marcador, edgecolors=tema["marker_edge"], linewidths=0.75, label=rotulo_curva, zorder=4)

    # Inset para região de altas frequências com proporção 1:1 por padrão
    if exibir_inset and curvas:
        ax_ins = inset_axes(ax, width="100%", height="100%", bbox_to_anchor=inset_bbox, bbox_transform=ax.transAxes)
        ax_ins.set_facecolor(tema["ax_bg"])

        for idx, c in enumerate(curvas):
            cor_ins = mapa_cores.get(c["nome"], list(mapa_cores.values())[idx % len(mapa_cores)])
            estilo_ins = mapa_estilos.get(c["nome"], "-")
            marcador_ins = marcadores_por_curva[idx]

            if modo_plot == "Apenas Linha":
                ax_ins.plot(c["re"], c["im"], color=cor_ins, linewidth=1.9, linestyle=estilo_ins, alpha=0.95, zorder=4)
            else:
                ax_ins.plot(c["re"], c["im"], color=cor_ins, linewidth=1.4, linestyle=estilo_ins, alpha=0.75, zorder=3)
                ax_ins.scatter(c["re"], c["im"], color=cor_ins, s=24, marker=marcador_ins, edgecolors=tema["marker_edge"], linewidths=0.5, zorder=4)

        span_re_def = re_max - re_min
        ax_ins.set_xlim(min(0, re_min - 0.5), re_min + max(span_re_def * 0.25, 5.0))
        ax_ins.set_ylim(min(-0.5, im_min - 0.5), re_min + max(span_re_def * 0.25, 5.0))

        if inset_limites:
            if inset_limites.get("xmin") is not None: ax_ins.set_xlim(left=inset_limites["xmin"])
            if inset_limites.get("xmax") is not None: ax_ins.set_xlim(right=inset_limites["xmax"])
            if inset_limites.get("ymin") is not None: ax_ins.set_ylim(bottom=inset_limites["ymin"])
            if inset_limites.get("ymax") is not None: ax_ins.set_ylim(top=inset_limites["ymax"])

        # Proporção 1:1 garantida no Inset para preservar o semicírculo real
        ax_ins.set_aspect("equal", adjustable="box")
        ax_ins.tick_params(labelsize=8.0, colors=tema["subtext"])
        aplicar_separador_decimal_eixos(ax_ins, idioma)
        for sp in ax_ins.spines.values():
            sp.set_color(tema["spine"])
        ax_ins.grid(True, linestyle=":", alpha=0.4, color=tema["grid"])
        ax_ins.set_title(titulo_inset, fontsize=8.5, fontweight="bold", color=tema["subtext"], pad=3)

    if circuito_bytes is not None:
        img = mpimg.imread(circuito_bytes)
        ab = AnnotationBbox(
            OffsetImage(img, zoom=zoom_circuito),
            pos_circuito,
            xycoords="axes fraction",
            frameon=True, pad=0.35, bboxprops=dict(edgecolor=tema["box_edge"], facecolor="#ffffff", alpha=0.95, lw=1.0),
            zorder=8
        )
        ax.add_artist(ab)

    span_re = re_max - re_min
    span_im = im_max - im_min
    ax.set_xlabel(eixo_x_label, fontsize=12.5, labelpad=8)
    ax.set_ylabel(eixo_y_label, fontsize=12.5, labelpad=8)
    ax.set_xlim(min(0, re_min - span_re * 0.04), re_max + span_re * 0.12)
    ax.set_ylim(min(0, im_min - span_im * 0.03), im_max * 1.15)
    if aspect_equal:
        ax.set_aspect("equal", adjustable="box")
    ax.grid(True, linestyle=":", alpha=0.4, color=tema["grid"])

    aplicar_ajustes_eixos_e_legenda(ax, limites_manuais, posicao_legenda, tema)
    estilar_figura_e_eixos(fig, ax, tema, idioma)
    plt.tight_layout()
    return fig


# ------------------------------------------------------------------------------
# (3) CARGA/DESCARGA GALVANOSTÁTICA - GCD (BATERIA)
# ------------------------------------------------------------------------------
def gerar_plot_gcd(
    fonte_dados,
    eixo_x_label,
    eixo_y_label,
    mapa_cores,
    mapa_nomes,
    mapa_estilos,
    limites_manuais,
    posicao_legenda,
    tema,
    idioma="Português",
    exibir_delta_e=True,
    delta_e_texto=r"$\Delta E$",
    delta_e_x_frac=0.40,
    delta_e_y_topo=0.58,
    delta_e_y_base=0.46,
    delta_e_lado_texto="Direita / Right"
):
    df, _ = processar_cabecalho_e_dados(fonte_dados)
    ciclos = extrair_ciclos_gcd(fonte_dados, df)

    if not ciclos:
        raise ValueError("Nenhuma curva válida encontrada no arquivo de Carga/Descarga.")

    fig, ax = plt.subplots(figsize=(8.6, 5.4), dpi=300)

    todos_x, todos_y = [], []
    for idx, c in enumerate(ciclos):
        cor = mapa_cores.get(c["nome"], list(mapa_cores.values())[idx % len(mapa_cores)])
        estilo = mapa_estilos.get(c["nome"], "-")
        rotulo_legenda = mapa_nomes.get(c["nome"], c["label_legenda"])

        if len(c["x_chg"]) > 0:
            ax.plot(c["x_chg"], c["y_chg"], color=cor, linewidth=2.1, linestyle=estilo, label=rotulo_legenda, zorder=4)
            todos_x.append(c["x_chg"])
            todos_y.append(c["y_chg"])

        if len(c["x_dch"]) > 0:
            lbl_dch = "_nolegend_" if len(c["x_chg"]) > 0 else rotulo_legenda
            ax.plot(c["x_dch"], c["y_dch"], color=cor, linewidth=2.1, linestyle=estilo, label=lbl_dch, zorder=4)
            todos_x.append(c["x_dch"])
            todos_y.append(c["y_dch"])

    x_concat = np.concatenate(todos_x)
    y_concat = np.concatenate(todos_y)
    x_min, x_max = np.min(x_concat), np.max(x_concat)
    y_min, y_max = np.min(y_concat), np.max(y_concat)
    span_x = x_max - x_min
    span_y = y_max - y_min

    if exibir_delta_e:
        y_topo_ajustado = max(delta_e_y_topo, delta_e_y_base + 0.02)
        ax.annotate(
            "",
            xy=(delta_e_x_frac, y_topo_ajustado),
            xytext=(delta_e_x_frac, delta_e_y_base),
            xycoords="axes fraction",
            textcoords="axes fraction",
            arrowprops=dict(
                arrowstyle="<->",
                color=tema["text"],
                lw=1.5,
                shrinkA=0,
                shrinkB=0
            ),
            zorder=7
        )
        if delta_e_texto:
            offset_x = 0.018 if "Direita" in delta_e_lado_texto else -0.018
            alinhamento_h = "left" if "Direita" in delta_e_lado_texto else "right"
            y_meio = (y_topo_ajustado + delta_e_y_base) / 2.0
            ax.text(
                delta_e_x_frac + offset_x,
                y_meio,
                delta_e_texto,
                transform=ax.transAxes,
                fontsize=11.0,
                fontweight="bold",
                color=tema["text"],
                va="center",
                ha=alinhamento_h,
                zorder=8
            )

    ax.set_xlabel(eixo_x_label, fontsize=12.5, labelpad=8)
    ax.set_ylabel(eixo_y_label, fontsize=12.5, labelpad=8)
    ax.set_xlim(min(0, x_min - span_x * 0.03), x_max + span_x * 0.16)
    ax.set_ylim(y_min - span_y * 0.08, y_max + span_y * 0.08)
    ax.grid(True, linestyle=":", alpha=0.4, color=tema["grid"])

    aplicar_ajustes_eixos_e_legenda(ax, limites_manuais, posicao_legenda, tema)
    estilar_figura_e_eixos(fig, ax, tema, idioma)
    plt.tight_layout()
    return fig


# ------------------------------------------------------------------------------
# (4) RATE CAPABILITY (BATERIA)
# ------------------------------------------------------------------------------
def gerar_plot_rate(
    fonte_dados, eixo_x_label, eixo_y_label,
    mapa_cores, mapa_nomes, mapa_estilos, limites_manuais, posicao_legenda, tema,
    idioma="Português"
):
    df, tokens_limpos = processar_cabecalho_e_dados(fonte_dados)
    x_ciclos = df.iloc[:, 0].to_numpy(float)
    num_curvas = df.shape[1] - 1

    legendas = tokens_limpos[1:] if len(tokens_limpos) > num_curvas else tokens_limpos
    if len(legendas) < num_curvas:
        legendas = [f"Sample {i+1}" for i in range(num_curvas)]

    sep = "," if idioma == "Português" else "."
    zonas_c_rate = [
        {"label": f"0{sep}1 C", "start": 0.5, "end": 5.5, "mid": 3.0},
        {"label": f"0{sep}2 C", "start": 5.5, "end": 9.5, "mid": 7.5},
        {"label": f"0{sep}5 C", "start": 9.5, "end": 13.5, "mid": 11.5},
        {"label": "1 C", "start": 13.5, "end": 17.5, "mid": 15.5},
        {"label": "2 C", "start": 17.5, "end": 21.5, "mid": 19.5},
        {"label": f"0{sep}1 C", "start": 21.5, "end": 25.5, "mid": 23.5},
    ]

    fig, ax = plt.subplots(figsize=(8.6, 5.2), dpi=300)
    marcadores_ciclo = cycle(MARCADORES_PADRAO)

    y_max = np.nanmax(df.iloc[:, 1:].values)
    y_min = np.nanmin(df.iloc[:, 1:].values)
    y_topo = y_max * 1.18

    trans_topo_eixo = ax.get_xaxis_transform()

    for i, zone in enumerate(zonas_c_rate):
        if i % 2 == 1:
            ax.axvspan(zone["start"], zone["end"], color=tema["zebra"], alpha=0.9, zorder=1)
        if i > 0:
            ax.axvline(zone["start"], color=tema["grid"], linestyle="--", linewidth=1.1, zorder=2)

        ax.text(
            zone["mid"], 0.94, zone["label"],
            transform=trans_topo_eixo,
            ha="center", va="center",
            fontsize=10.0, fontweight="bold", color=tema["text"],
            bbox=dict(boxstyle="round,pad=0.25", facecolor=tema["box_bg"], edgecolor=tema["box_edge"], lw=1.0),
            zorder=5
        )

    offsets = np.linspace(-0.12, 0.12, num_curvas) if num_curvas > 1 else [0.0]
    for col_idx in range(num_curvas):
        y_valores = df.iloc[:, col_idx + 1].to_numpy(float)
        nome = legendas[col_idx]
        cor = mapa_cores.get(nome, list(mapa_cores.values())[col_idx % len(mapa_cores)])
        estilo = mapa_estilos.get(nome, "-")
        rotulo_curva = mapa_nomes.get(nome, nome)
        if estilo == "--":
            ax.plot(x_ciclos + offsets[col_idx], y_valores, color=cor, linewidth=1.2, linestyle="--", alpha=0.5, zorder=3)
        ax.scatter(
            x_ciclos + offsets[col_idx], y_valores, color=cor, s=52,
            marker=next(marcadores_ciclo), edgecolors=tema["marker_edge"], linewidths=0.85,
            label=rotulo_curva, zorder=4
        )

    ax.set_xlabel(eixo_x_label, fontsize=12.5, labelpad=8)
    ax.set_ylabel(eixo_y_label, fontsize=12.5, labelpad=8)
    ax.set_xlim(0, max(x_ciclos) + 1)
    ax.set_ylim(min(-10, y_min - 20), y_topo * 1.05)
    ax.yaxis.grid(True, linestyle=":", alpha=0.5, color=tema["grid"])

    aplicar_ajustes_eixos_e_legenda(ax, limites_manuais, posicao_legenda, tema)
    estilar_figura_e_eixos(fig, ax, tema, idioma)
    plt.tight_layout()
    return fig


# ------------------------------------------------------------------------------
# (5) CICLABILIDADE MULTIPLOT (BATERIA)
# ------------------------------------------------------------------------------
def gerar_plot_ciclabilidade(
    fonte_dados, rate_tag, pos_rate, eixo_x_label, eixo_y_label,
    mapa_cores, mapa_nomes, mapa_estilos, limites_manuais, posicao_legenda,
    tema, idioma="Português", unidade_y=r"mAh\ g^{-1}"
):
    df, tokens_limpos = processar_cabecalho_e_dados(fonte_dados)
    num_cols = df.shape[1]
    curvas = []

    if num_cols >= 2 and num_cols % 2 == 0:
        nomes_y = [tokens_limpos[k] for k in range(1, len(tokens_limpos), 2)] if len(tokens_limpos) >= 2 else tokens_limpos
        for idx, col in enumerate(range(0, num_cols, 2)):
            sub = df.iloc[:, [col, col + 1]].dropna()
            if len(sub) == 0: continue
            nome = nomes_y[idx] if idx < len(nomes_y) else f"Sample {idx + 1}"
            curvas.append({"nome": nome, "x": sub.iloc[:, 0].to_numpy(float), "y": sub.iloc[:, 1].to_numpy(float)})
    else:
        nomes_y = tokens_limpos[1:] if len(tokens_limpos) >= num_cols else tokens_limpos
        for col in range(1, num_cols):
            sub = df.iloc[:, [0, col]].dropna()
            if len(sub) == 0: continue
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

    dados_finais = []
    for idx, c in enumerate(curvas):
        cor = mapa_cores.get(c["nome"], list(mapa_cores.values())[idx % len(mapa_cores)])
        estilo = mapa_estilos.get(c["nome"], "-")
        rotulo_curva = mapa_nomes.get(c["nome"], c["nome"])
        ax.plot(c["x"], c["y"], color=cor, lw=2.0, linestyle=estilo, label=rotulo_curva, zorder=4)

        mascara = (c["x"] >= x_inicio_corte) & (c["x"] <= x_limite_corte)
        if np.any(mascara):
            x_vis = c["x"][mascara]
            y_vis = c["y"][mascara]
        else:
            x_vis = c["x"]
            y_vis = c["y"]

        c0, cf = y_vis[0], y_vis[-1]
        x_end_vis = x_vis[-1]
        ret = (cf / c0) * 100 if c0 != 0 else 0.0

        dados_finais.append({"nome": rotulo_curva, "x_end": x_end_vis, "y_end": cf, "ret": ret, "cor": cor})
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
        ret_str = fmt_num(d["ret"], casas=1, idioma=idioma)
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
    aplicar_ajustes_eixos_e_legenda(ax, limites_aplicar, posicao_legenda, tema)
    estilar_figura_e_eixos(fig, ax, tema, idioma)
    plt.tight_layout()
    return fig


# ------------------------------------------------------------------------------
# (6) CICLABILIDADE & EFICIÊNCIA COULÔMBICA INDIVIDUAL (BATERIA)
# ------------------------------------------------------------------------------
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
    modo_cap="Pontos + Linha",
    modo_eff="Pontos + Linha",
    limites_manuais=None,
    patamar_ref=None,
    tema=None,
    idioma="Português",
    unidade_y=r"mAh\ g_S^{-1}"
):
    df, tokens_limpos = processar_cabecalho_e_dados(fonte_dados)
    num_cols = df.shape[1]

    if num_cols >= 4:
        sub = df.iloc[:, [0, 2, 3]].dropna()
        x_ciclos = sub.iloc[:, 0].to_numpy(float)
        y_cap = sub.iloc[:, 1].to_numpy(float)
        y_eff = sub.iloc[:, 2].to_numpy(float)
    elif num_cols == 3:
        sub = df.dropna()
        x_ciclos = sub.iloc[:, 0].to_numpy(float)
        y_cap = sub.iloc[:, 1].to_numpy(float)
        y_eff = sub.iloc[:, 2].to_numpy(float)
    else:
        raise ValueError("O arquivo para Ciclabilidade + Eficiência precisa conter ao menos 3 colunas (Ciclo, Capacidade e Eficiência).")

    fig, ax1 = plt.subplots(figsize=(8.8, 5.4), dpi=300)

    if modo_cap == "Apenas Linha":
        ax1.plot(x_ciclos, y_cap, color=cor_capacidade, linewidth=2.2, linestyle=estilo_capacidade, alpha=0.95, zorder=4)
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
    if np.any(mascara):
        x_vis = x_ciclos[mascara]
        y_vis = y_cap[mascara]
    else:
        x_vis = x_ciclos
        y_vis = y_cap

    c0 = y_vis[0]
    cf = y_vis[-1]
    x_end_vis = x_vis[-1]
    ret = (cf / c0) * 100 if c0 != 0 else 0.0

    ax1.axvline(x_end_vis, color=tema["ref_line"], linestyle=":", linewidth=1.1, alpha=0.7, zorder=2)
    ax1.annotate("←", xy=(0.04, 0.55), xycoords="axes fraction", fontsize=14, fontweight="bold", color=cor_capacidade)

    ret_str = fmt_num(ret, casas=1, idioma=idioma)
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
    estilar_figura_e_eixos(fig, ax1, tema, idioma, y_color=cor_capacidade)

    if nome_amostra:
        ax1.text(0.05, 0.08, nome_amostra, transform=ax1.transAxes, fontsize=13, fontweight="bold", color=tema["text"])

    ax2 = ax1.twinx()
    if modo_eff == "Apenas Linha":
        ax2.plot(x_ciclos, y_eff, color=cor_eficiencia, linewidth=2.2, linestyle=estilo_eficiencia, alpha=0.95, zorder=6)
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
    aplicar_separador_decimal_eixos(ax2, idioma)

    plt.tight_layout()
    return fig


# ------------------------------------------------------------------------------
# (7) CGCD SUPERCAPACITOR (2 ELETRODOS / JANELAS DE POTENCIAL)
# ------------------------------------------------------------------------------
def gerar_plot_sc_2e_cgcd(
    fonte_dados,
    eixo_x_label,
    eixo_y_label,
    mapa_cores,
    mapa_nomes,
    mapa_estilos,
    limites_manuais,
    posicao_legenda,
    tema,
    idioma="Português",
    exibir_ir_drop=False,
    ir_texto=r"$IR_{drop}$",
    ir_x_frac=0.25,
    ir_y_topo=0.88,
    ir_y_base=0.78,
):
    df, _ = processar_cabecalho_e_dados(fonte_dados)
    ciclos = extrair_ciclos_gcd(fonte_dados, df)

    if not ciclos:
        raise ValueError("Nenhuma curva válida encontrada no arquivo CGCD (2 Eletrodos).")

    fig, ax = plt.subplots(figsize=(8.6, 5.4), dpi=300)

    todos_x, todos_y = [], []
    for idx, c in enumerate(ciclos):
        cor = mapa_cores.get(c["nome"], list(mapa_cores.values())[idx % len(mapa_cores)])
        estilo = mapa_estilos.get(c["nome"], "-")
        rotulo_legenda = mapa_nomes.get(c["nome"], c["label_legenda"])

        if len(c["x_chg"]) > 0:
            ax.plot(c["x_chg"], c["y_chg"], color=cor, linewidth=2.1, linestyle=estilo, label=rotulo_legenda, zorder=4)
            todos_x.append(c["x_chg"])
            todos_y.append(c["y_chg"])

        if len(c["x_dch"]) > 0:
            lbl_dch = "_nolegend_" if len(c["x_chg"]) > 0 else rotulo_legenda
            ax.plot(c["x_dch"], c["y_dch"], color=cor, linewidth=2.1, linestyle=estilo, label=lbl_dch, zorder=4)
            todos_x.append(c["x_dch"])
            todos_y.append(c["y_dch"])

    x_concat = np.concatenate(todos_x)
    y_concat = np.concatenate(todos_y)
    x_min, x_max = np.min(x_concat), np.max(x_concat)
    y_min, y_max = np.min(y_concat), np.max(y_concat)
    span_x = x_max - x_min
    span_y = y_max - y_min

    if exibir_ir_drop:
        y_topo_aj = max(ir_y_topo, ir_y_base + 0.02)
        ax.annotate(
            "",
            xy=(ir_x_frac, y_topo_aj),
            xytext=(ir_x_frac, ir_y_base),
            xycoords="axes fraction",
            textcoords="axes fraction",
            arrowprops=dict(arrowstyle="<->", color=tema["text"], lw=1.4, shrinkA=0, shrinkB=0),
            zorder=7
        )
        if ir_texto:
            ax.text(
                ir_x_frac + 0.018,
                (y_topo_aj + ir_y_base) / 2.0,
                ir_texto,
                transform=ax.transAxes,
                fontsize=10.5,
                fontweight="bold",
                color=tema["text"],
                va="center",
                ha="left",
                zorder=8
            )

    ax.set_xlabel(eixo_x_label, fontsize=12.5, labelpad=8)
    ax.set_ylabel(eixo_y_label, fontsize=12.5, labelpad=8)
    ax.set_xlim(min(0, x_min - span_x * 0.02), x_max + span_x * 0.14)
    ax.set_ylim(y_min - span_y * 0.06, y_max + span_y * 0.10)
    ax.grid(True, linestyle=":", alpha=0.4, color=tema["grid"])

    aplicar_ajustes_eixos_e_legenda(ax, limites_manuais, posicao_legenda, tema)
    estilar_figura_e_eixos(fig, ax, tema, idioma)
    plt.tight_layout()
    return fig


# ------------------------------------------------------------------------------
# (8) CGCD SUPERCAPACITOR (3 ELETRODOS: Ecell no Y1, Ewe & Ece no Y2)
# ------------------------------------------------------------------------------
def gerar_plot_sc_3e_cgcd(
    fonte_dados,
    eixo_x_label,
    eixo_y1_label,
    eixo_y2_label,
    mapa_cores,
    mapa_nomes,
    mapa_estilos,
    limites_manuais,
    posicao_legenda,
    tema,
    idioma="Português",
    exibir_linha_zero=True,
    nome_amostra_3e="Amostra / Sample",
    pos_amostra_3e=(0.05, 0.90)
):
    df, _ = processar_cabecalho_e_dados(fonte_dados)
    curvas = extrair_curvas_3_eletrodos(fonte_dados, df)

    if not curvas:
        raise ValueError("Nenhuma curva válida encontrada no arquivo de 3 Eletrodos (time/s | Ecell/V | Ewe/V | Ece/V).")

    fig, ax1 = plt.subplots(figsize=(8.8, 5.4), dpi=300)
    ax2 = ax1.twinx()

    if exibir_linha_zero:
        ax2.axhline(0, color=tema["ref_line"], linestyle="--", linewidth=1.1, alpha=0.75, zorder=2)

    handles_unificados = []
    todos_x, todos_y1, todos_y2 = [], [], []

    for idx, c in enumerate(curvas):
        cor = mapa_cores.get(c["nome"], list(mapa_cores.values())[idx % len(mapa_cores)])
        estilo = mapa_estilos.get(c["nome"], "-")
        rotulo_legenda = mapa_nomes.get(c["nome"], c["nome"])

        todos_x.append(c["x"])

        if idx == 0:
            linha, = ax1.plot(c["x"], c["y"], color=cor, linewidth=2.2, linestyle=estilo, label=rotulo_legenda, zorder=5)
            todos_y1.append(c["y"])
        else:
            linha, = ax2.plot(c["x"], c["y"], color=cor, linewidth=2.2, linestyle=estilo, label=rotulo_legenda, zorder=4)
            todos_y2.append(c["y"])

        handles_unificados.append(linha)

    x_concat = np.concatenate(todos_x)
    x_min, x_max = np.min(x_concat), np.max(x_concat)
    span_x = x_max - x_min

    if todos_y1:
        y1_concat = np.concatenate(todos_y1)
        y1_min, y1_max = np.min(y1_concat), np.max(y1_concat)
        span_y1 = max(y1_max - y1_min, 0.1)
        ax1.set_ylim(min(0, y1_min - span_y1 * 0.08), y1_max + span_y1 * 0.14)

    if todos_y2:
        y2_concat = np.concatenate(todos_y2)
        y2_min, y2_max = np.min(y2_concat), np.max(y2_concat)
        span_y2 = max(y2_max - y2_min, 0.1)
        ax2.set_ylim(y2_min - span_y2 * 0.12, y2_max + span_y2 * 0.15)

    ax1.set_xlabel(eixo_x_label, fontsize=12.5, labelpad=8)
    ax1.set_ylabel(eixo_y1_label, fontsize=12.5, labelpad=8)
    ax1.set_xlim(min(0, x_min - span_x * 0.02), x_max + span_x * 0.05)
    ax1.grid(True, linestyle=":", alpha=0.4, color=tema["grid"])

    aplicar_ajustes_eixos_e_legenda(ax1, limites_manuais, posicao_legenda=None, tema=tema)
    estilar_figura_e_eixos(fig, ax1, tema, idioma)

    ax2.set_ylabel(eixo_y2_label, fontsize=12.5, labelpad=8, color=tema["text"])
    ax2.tick_params(axis="y", labelcolor=tema["subtext"], width=1.4, color=tema["spine"])
    ax2.spines["right"].set_color(tema["spine"])
    ax2.spines["right"].set_linewidth(1.4)
    ax2.spines["top"].set_visible(False)
    ax2.spines["bottom"].set_visible(False)
    ax2.spines["left"].set_visible(False)

    y2lim_user = limites_manuais.get("y2lim") if limites_manuais else (None, None)
    if y2lim_user:
        if y2lim_user[0] is not None:
            ax2.set_ylim(bottom=y2lim_user[0])
        if y2lim_user[1] is not None:
            ax2.set_ylim(top=y2lim_user[1])
    aplicar_separador_decimal_eixos(ax2, idioma)

    if nome_amostra_3e and nome_amostra_3e.strip():
        ax2.text(
            pos_amostra_3e[0], pos_amostra_3e[1],
            rf"$\mathbf{{{nome_amostra_3e.strip()}}}$",
            transform=ax2.transAxes,
            fontsize=10.5,
            fontweight="bold",
            color=tema["text"],
            bbox=dict(
                boxstyle="round,pad=0.38",
                facecolor=tema["box_bg"],
                edgecolor=tema["box_edge"],
                linewidth=1.1,
                alpha=0.95
            ),
            zorder=8
        )

    if posicao_legenda and posicao_legenda != "Ocultar / Hide":
        leg = ax2.legend(
            handles=handles_unificados,
            loc=posicao_legenda,
            frameon=True,
            facecolor=tema["box_bg"],
            edgecolor=tema["box_edge"],
            fontsize=10.0,
        )
        for text in leg.get_texts():
            text.set_color(tema["text"])

    plt.tight_layout()
    return fig


# ------------------------------------------------------------------------------
# (9) RATE CAPABILITY (SUPERCAPACITOR)
# ------------------------------------------------------------------------------
def gerar_plot_sc_rate(
    fonte_dados, eixo_x_label, eixo_y_label,
    mapa_cores, mapa_nomes, mapa_estilos, limites_manuais, posicao_legenda, tema,
    idioma="Português", protocolo_correntes="0.5, 1, 2, 5, 10, 0.5", ciclos_por_degrau=5
):
    df, tokens_limpos = processar_cabecalho_e_dados(fonte_dados)
    x_ciclos = df.iloc[:, 0].to_numpy(float)
    num_curvas = df.shape[1] - 1

    legendas = tokens_limpos[1:] if len(tokens_limpos) > num_curvas else tokens_limpos
    if len(legendas) < num_curvas:
        legendas = [f"Sample {i+1}" for i in range(num_curvas)]

    lista_taxas = [t.strip() for t in protocolo_correntes.split(",") if t.strip()]
    if not lista_taxas:
        lista_taxas = ["0.5", "1", "2", "5", "10", "0.5"]

    zonas_corrente = []
    for i, taxa in enumerate(lista_taxas):
        taxa_fmt = taxa.replace(".", ",") if idioma == "Português" else taxa.replace(",", ".")
        inicio = i * ciclos_por_degrau + 0.5
        fim = (i + 1) * ciclos_por_degrau + 0.5
        meio = (inicio + fim) / 2.0
        zonas_corrente.append({
            "label": rf"{taxa_fmt} $\mathrm{{A\ g^{{-1}}}}$",
            "start": inicio,
            "end": fim,
            "mid": meio
        })

    fig, ax = plt.subplots(figsize=(8.8, 5.2), dpi=300)
    marcadores_ciclo = cycle(MARCADORES_PADRAO)

    y_max = np.nanmax(df.iloc[:, 1:].values)
    y_min = np.nanmin(df.iloc[:, 1:].values)
    y_topo = y_max * 1.18

    trans_topo_eixo = ax.get_xaxis_transform()

    for i, zone in enumerate(zonas_corrente):
        if i % 2 == 1:
            ax.axvspan(zone["start"], zone["end"], color=tema["zebra"], alpha=0.9, zorder=1)
        if i > 0:
            ax.axvline(zone["start"], color=tema["grid"], linestyle="--", linewidth=1.1, zorder=2)

        ax.text(
            zone["mid"], 0.94, zone["label"],
            transform=trans_topo_eixo,
            ha="center", va="center",
            fontsize=9.2, fontweight="bold", color=tema["text"],
            bbox=dict(boxstyle="round,pad=0.25", facecolor=tema["box_bg"], edgecolor=tema["box_edge"], lw=1.0),
            zorder=5
        )

    offsets = np.linspace(-0.12, 0.12, num_curvas) if num_curvas > 1 else [0.0]
    for col_idx in range(num_curvas):
        y_valores = df.iloc[:, col_idx + 1].to_numpy(float)
        nome = legendas[col_idx]
        cor = mapa_cores.get(nome, list(mapa_cores.values())[col_idx % len(mapa_cores)])
        estilo = mapa_estilos.get(nome, "-")
        rotulo_curva = mapa_nomes.get(nome, nome)
        if estilo == "--":
            ax.plot(x_ciclos + offsets[col_idx], y_valores, color=cor, linewidth=1.2, linestyle="--", alpha=0.5, zorder=3)
        ax.scatter(
            x_ciclos + offsets[col_idx], y_valores, color=cor, s=52,
            marker=next(marcadores_ciclo), edgecolors=tema["marker_edge"], linewidths=0.85,
            label=rotulo_curva, zorder=4
        )

    ax.set_xlabel(eixo_x_label, fontsize=12.5, labelpad=8)
    ax.set_ylabel(eixo_y_label, fontsize=12.5, labelpad=8)
    ax.set_xlim(0, max(x_ciclos) + 1)
    ax.set_ylim(min(0, y_min - 10), y_topo * 1.05)
    ax.yaxis.grid(True, linestyle=":", alpha=0.5, color=tema["grid"])

    aplicar_ajustes_eixos_e_legenda(ax, limites_manuais, posicao_legenda, tema)
    estilar_figura_e_eixos(fig, ax, tema, idioma)
    plt.tight_layout()
    return fig


# ------------------------------------------------------------------------------
# (10) BET ISOTERMAS
# ------------------------------------------------------------------------------
def gerar_plot_bet(
    fonte_dados, eixo_x_label, eixo_y_label, rotulo_ads, rotulo_des,
    titulo_legenda, titulo_inset, mapa_cores, mapa_nomes, mapa_estilos,
    limites_manuais, posicao_legenda, tema, idioma="Português",
    areas_bet=None, exibir_inset=False,
    inset_bbox=(0.54, 0.22, 0.38, 0.28), inset_limites=None
):
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
        if col_y >= num_cols: break
        nome = nomes_detectados[idx] if idx < len(nomes_detectados) else f"Sample {idx + 1}"
        sub = df.iloc[:, [col_x, col_y]].dropna()
        if len(sub) == 0: continue

        p_p0 = sub.iloc[:, 0].to_numpy(dtype=float)
        v_ads = sub.iloc[:, 1].to_numpy(dtype=float)
        idx_pico = int(np.argmax(p_p0)) if len(p_p0) > 0 else 0
        tem_dessorcao = (idx_pico < (len(p_p0) - 2)) and (p_p0[-1] < p_p0[idx_pico])

        isotherms.append({
            "name": nome,
            "ads_p": p_p0[: idx_pico + 1],
            "ads_v": v_ads[: idx_pico + 1],
            "des_p": p_p0[idx_pico :] if tem_dessorcao else np.array([]),
            "des_v": v_ads[idx_pico :] if tem_dessorcao else np.array([]),
            "tem_dessorcao": tem_dessorcao,
            "v_max": np.max(v_ads) if len(v_ads) > 0 else 0,
        })

    fig, ax = plt.subplots(figsize=(8.8, 5.4), dpi=300)
    legend_elements = []
    todos_v_max = [iso["v_max"] for iso in isotherms if iso["v_max"] > 0]
    v_max = max(todos_v_max) if todos_v_max else 1000

    for idx, iso in enumerate(isotherms):
        nome = iso["name"]
        cor = mapa_cores.get(nome, list(mapa_cores.values())[idx % len(mapa_cores)])
        estilo = mapa_estilos.get(nome, "-")
        nome_exibido = mapa_nomes.get(nome, nome)
        val_bet = areas_bet.get(nome, areas_bet.get(nome.replace(" ", ""), None)) if areas_bet else None
        val_bet_str = fmt_num(val_bet, casas=0, idioma=idioma) if val_bet else None
        rotulo = rf"{nome_exibido}  $\mathbf{{({val_bet_str}\ m^2\ g^{{-1}})}}$" if val_bet_str else nome_exibido

        ax.plot(iso["ads_p"], iso["ads_v"], color=cor, linewidth=1.7, linestyle=estilo, alpha=0.85, zorder=3)
        ax.scatter(iso["ads_p"], iso["ads_v"], color=cor, s=28, marker="o", edgecolors=tema["marker_edge"], linewidths=0.6, zorder=4)

        if iso["tem_dessorcao"] and len(iso["des_p"]) > 0:
            ax.plot(iso["des_p"], iso["des_v"], color=cor, linewidth=1.7, linestyle=estilo, alpha=0.85, zorder=3)
            ax.scatter(iso["des_p"], iso["des_v"], facecolors=tema["ax_bg"], edgecolors=cor, s=28, marker="o", linewidths=1.2, zorder=5)

        legend_elements.append(Line2D([0], [0], marker="o", color="none", markeredgecolor=tema["marker_edge"], markerfacecolor=cor, markersize=7, label=rotulo))

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
                    ax_ins.plot(iso["ads_p"], iso["ads_v"], color=cor_ins, linewidth=1.4, linestyle=estilo_ins, alpha=0.9, zorder=3)
                    ax_ins.scatter(iso["ads_p"], iso["ads_v"], color=cor_ins, s=18, marker="o", edgecolors=tema["marker_edge"], linewidths=0.4, zorder=4)
                    if iso["tem_dessorcao"] and len(iso["des_p"]) > 0:
                        ax_ins.plot(iso["des_p"], iso["des_v"], color=cor_ins, linewidth=1.4, linestyle=estilo_ins, alpha=0.9, zorder=3)
                        ax_ins.scatter(iso["des_p"], iso["des_v"], facecolors=tema["ax_bg"], edgecolors=cor_ins, s=18, marker="o", linewidths=0.9, zorder=5)

            ax_ins.set_xlim(-0.02, 1.02)
            if inset_limites:
                if inset_limites.get("xmin") is not None: ax_ins.set_xlim(left=inset_limites["xmin"])
                if inset_limites.get("xmax") is not None: ax_ins.set_xlim(right=inset_limites["xmax"])
                if inset_limites.get("ymin") is not None: ax_ins.set_ylim(bottom=inset_limites["ymin"])
                if inset_limites.get("ymax") is not None: ax_ins.set_ylim(top=inset_limites["ymax"])

            ax_ins.tick_params(labelsize=8.0, colors=tema["subtext"])
            aplicar_separador_decimal_eixos(ax_ins, idioma)
            for sp in ax_ins.spines.values():
                sp.set_color(tema["spine"])
            ax_ins.grid(True, linestyle=":", alpha=0.4, color=tema["grid"])
            ax_ins.set_title(titulo_inset, fontsize=8.5, fontweight="bold", color=tema["subtext"], pad=3)

    ax.set_xlabel(eixo_x_label, fontsize=12.5, labelpad=8)
    ax.set_ylabel(eixo_y_label, fontsize=12.5, labelpad=8)
    ax.set_xlim(-0.02, 1.02)
    ax.set_ylim(-20, v_max * 1.18)
    ax.grid(True, linestyle=":", alpha=0.4, color=tema["grid"])

    aplicar_ajustes_eixos_e_legenda(ax, limites_manuais, posicao_legenda, tema, handles=legend_elements, title_legenda=titulo_legenda, fontsize_leg=9.5)

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

    estilar_figura_e_eixos(fig, ax, tema, idioma)
    plt.tight_layout()
    return fig


# ==============================================================================
# INTERFACE PRINCIPAL (STREAMLIT)
# ==============================================================================
def main():
    caminho_icone_local = Path(__file__).resolve().parent / "vikavolt.ico"
    if caminho_icone_local.exists():
        st.sidebar.image(str(caminho_icone_local), width=105)

    st.sidebar.title("⚡ PhVolt")
    st.sidebar.caption("Processamento e Gráficos Automatizados")

    # 1. Carregamento do Arquivo no Topo
    label_upload = "📁 Carregue o arquivo de dados (.txt, .dat, .csv):"
    arquivo_upload = st.sidebar.file_uploader(
        label_upload,
        type=["txt", "dat", "csv"],
        key="main_file_uploader"
    )

    if arquivo_upload is not None:
        nome_atual = arquivo_upload.name
        nome_anterior = st.session_state.get("nome_arquivo_anterior", None)

        if nome_atual != nome_anterior:
            st.session_state["dados_carregados"] = arquivo_upload.getvalue()
            st.session_state["nome_arquivo_anterior"] = nome_atual
            plt.close("all")
            st.rerun()
    else:
        if "dados_carregados" in st.session_state:
            del st.session_state["dados_carregados"]
        if "nome_arquivo_anterior" in st.session_state:
            del st.session_state["nome_arquivo_anterior"]

    dados_bytes = st.session_state.get("dados_carregados", None)

    st.sidebar.markdown("---")

    # 2. Idioma
    idioma = st.sidebar.radio("🌐 Idioma / Language:", ["Português", "Inglês"], key="app_lang")
    textos = TEXTOS_PADRAO[idioma]

    # 3. Seleção de Técnica (Ordem Lógica: Geral -> Baterias -> Supercapacitores -> Caracterização)
    tecnicas_pt = [
        "(1) Voltametria Cíclica (CV)",
        "(2) Espectroscopia de Impedância (EIE / Nyquist)",
        "(3) Carga/Descarga Galvanostática — GCD (Bateria)",
        "(4) Rate Capability (Bateria)",
        "(5) Ciclabilidade Multiplot (Bateria)",
        "(6) Ciclabilidade & Eficiência Individual (Bateria)",
        "(7) CGCD Supercapacitor (2 Eletrodos / Janelas)",
        "(8) CGCD Supercapacitor (3 Eletrodos: Ecell, Ewe, Ece)",
        "(9) Rate Capability (Supercapacitor)",
        "(10) Isotermas BET (Adsorção / Dessorção)",
    ]
    tecnicas_en = [
        "(1) Cyclic Voltammetry (CV)",
        "(2) Electrochemical Impedance (EIS / Nyquist)",
        "(3) Galvanostatic Charge/Discharge — GCD (Battery)",
        "(4) Rate Capability (Battery)",
        "(5) Multiplot Cyclability (Battery)",
        "(6) Individual Cyclability & Efficiency (Battery)",
        "(7) Supercapacitor CGCD (2-Electrode / Windows)",
        "(8) Supercapacitor CGCD (3-Electrode: Ecell, Ewe, Ece)",
        "(9) Rate Capability (Supercapacitor)",
        "(10) BET Isotherms (Adsorption / Desorption)",
    ]

    lista_tecnicas = tecnicas_pt if idioma == "Português" else tecnicas_en

    if "tecnica_idx" not in st.session_state:
        st.session_state["tecnica_idx"] = 0

    def atualizar_tecnica():
        nova_escolha = st.session_state["seletor_tecnica"]
        st.session_state["tecnica_idx"] = lista_tecnicas.index(nova_escolha)

    escolha_tecnica = st.sidebar.selectbox(
        "Selecione o ensaio:" if idioma == "Português" else "Select Technique:",
        lista_tecnicas,
        index=st.session_state["tecnica_idx"],
        key="seletor_tecnica",
        on_change=atualizar_tecnica
    )
    tecnica_idx = st.session_state["tecnica_idx"]
    tags_tecnicas = ["cv", "eie", "gcd", "rate", "cicl", "ce_ind", "sc_2e", "sc_3e", "sc_rate", "bet"]
    tag_tec = tags_tecnicas[tecnica_idx]

    # 4. Esquema Global de Cores e Tema (Claro / Dark Mode)
    st.sidebar.markdown(f"### 🎨 {'Esquema de Cores & Tema' if idioma == 'Português' else 'Color Scheme & Theme'}")

    dark_mode_ativo = st.sidebar.toggle(
        "🌙 Dark Mode (Gráfico Escuro)" if idioma == "Português" else "🌙 Dark Mode (Dark Plot)",
        value=False,
        key="plot_dark_mode"
    )
    tema_visual = obter_tema_visual(dark_mode_ativo)

    nome_paleta_escolhida = st.sidebar.selectbox(
        "Paleta Global:" if idioma == "Português" else "Global Palette:",
        list(PALETAS_DISPONIVEIS.keys()),
        index=0,
        key="global_palette_selector"
    )
    paleta_ativa = PALETAS_DISPONIVEIS[nome_paleta_escolhida]

    # 5. Cores, Nomes e Estilos de Linha Manuais por Curva
    mapa_cores_curvas = {}
    mapa_nomes_curvas = {}
    mapa_estilos_curvas = {}
    amostras_detectadas = []
    if dados_bytes is not None:
        try:
            df_temp, tokens_temp = processar_cabecalho_e_dados(dados_bytes)
            amostras_detectadas = identificar_amostras(df_temp, tokens_temp, tecnica_idx, dados_bytes)

            titulo_custom_curvas = "🖌️ " + ("Cores, Nomes e Estilos por Curva" if idioma == "Português" else "Colors, Names & Styles per Curve")
            with st.sidebar.expander(titulo_custom_curvas, expanded=False):
                st.caption("Personalize cor, nome na legenda e traçado de cada curva:" if idioma == "Português" else "Customize color, legend label and line style per curve:")
                for i, nome_amostra in enumerate(amostras_detectadas):
                    nome_arquivo_seguro = st.session_state.get("nome_arquivo_anterior", "def")

                    nome_default_limpo = nome_amostra.split(" (")[0] if " (" in nome_amostra else nome_amostra
                    novo_nome = st.text_input(
                        f"Nome da Curva {i+1}:" if idioma == "Português" else f"Curve {i+1} Label:",
                        value=nome_default_limpo,
                        key=f"rename_{nome_arquivo_seguro}_{tag_tec}_{nome_amostra}_{i}"
                    )
                    mapa_nomes_curvas[nome_amostra] = novo_nome.strip() if novo_nome.strip() else nome_default_limpo

                    c1, c2 = st.columns([1.6, 1.4])
                    cor_padrao = paleta_ativa[i % len(paleta_ativa)]
                    if dark_mode_ativo and cor_padrao in ["#334155", "#0f172a"]:
                        cor_padrao = "#e2e8f0"

                    chave_color_picker = f"cp_{nome_arquivo_seguro}_{tag_tec}_{nome_paleta_escolhida}_{dark_mode_ativo}_{nome_amostra}_{i}"
                    cor_escolhida = c1.color_picker("Cor" if idioma == "Português" else "Color", cor_padrao, key=chave_color_picker)
                    mapa_cores_curvas[nome_amostra] = cor_escolhida

                    default_dash = True if (tecnica_idx == 5 and i == 0) else False
                    e_tracejado = c2.checkbox(
                        "Tracejada" if idioma == "Português" else "Dashed",
                        value=default_dash,
                        key=f"chk_dash_{nome_arquivo_seguro}_{tag_tec}_{nome_amostra}_{i}"
                    )
                    mapa_estilos_curvas[nome_amostra] = "--" if e_tracejado else "-"

                    if i < len(amostras_detectadas) - 1:
                        st.markdown("<hr style='margin: 0.4rem 0; opacity: 0.25;'>", unsafe_allow_html=True)
        except Exception:
            pass

    # ==========================================================================
    # 6. CONFIGURAÇÃO DOS EIXOS, LIMITES MANUAIS E LEGENDA
    # ==========================================================================
    rotulos_default_x = [
        textos["cv_x"], textos["eie_x"], textos["gcd_x"], textos["rate_x"],
        textos["ciclabilidade_x"], textos["ce_x"], textos["sc_2e_x"],
        textos["sc_3e_x"], textos["sc_rate_x"], textos["bet_x"]
    ]
    rotulos_default_y = [
        textos["cv_y"], textos["eie_y"], textos["gcd_y"], textos["rate_y"],
        textos["ciclabilidade_y"], textos["ce_y1"], textos["sc_2e_y"],
        textos["sc_3e_y1"], textos["sc_rate_y"], textos["bet_y"]
    ]

    def converter_float_seguro(val_str):
        if val_str and val_str.strip():
            try:
                return float(val_str.replace(",", "."))
            except ValueError:
                return None
        return None

    tem_eixo_y2 = tecnica_idx in [5, 7]

    titulo_expander_eixos = "⚙️ " + ("Configuração dos Eixos & Legenda" if idioma == "Português" else "Axis & Legend Settings")
    with st.sidebar.expander(titulo_expander_eixos, expanded=False):
        eixo_x_input = st.text_input(
            "Eixo X" if idioma == "Português" else "X Axis",
            rotulos_default_x[tecnica_idx],
            key=f"eixo_x_{tag_tec}_{idioma}"
        )
        label_y1_ui = (
            "Eixo Y" if not tem_eixo_y2
            else ("Eixo Y1 (Capacidade)" if tecnica_idx == 5 else "Eixo Y1 (Ecell)")
        ) if idioma == "Português" else (
            "Y Axis" if not tem_eixo_y2
            else ("Y1 Axis (Capacity)" if tecnica_idx == 5 else "Y1 Axis (Ecell)")
        )
        eixo_y_input = st.text_input(
            label_y1_ui,
            rotulos_default_y[tecnica_idx],
            key=f"eixo_y_{tag_tec}_{idioma}"
        )

        eixo_y2_input = ""
        if tem_eixo_y2:
            default_y2_txt = textos["ce_y2"] if tecnica_idx == 5 else textos["sc_3e_y2"]
            label_y2_ui = (
                ("Eixo Y2 (Eficiência)" if tecnica_idx == 5 else "Eixo Y2 (Ewe / Ece)")
                if idioma == "Português"
                else ("Y2 Axis (Efficiency)" if tecnica_idx == 5 else "Y2 Axis (Ewe / Ece)")
            )
            eixo_y2_input = st.text_input(
                label_y2_ui,
                default_y2_txt,
                key=f"eixo_y2_{tag_tec}_{idioma}"
            )

        st.markdown("---")
        st.caption("Limites Manuais (deixe em branco para automático):" if idioma == "Português" else "Manual Limits (leave blank for auto):")
        col_lim_x1, col_lim_x2 = st.columns(2)
        xlim_min_str = col_lim_x1.text_input("X Mín:", "", key=f"xlim_min_{tag_tec}")
        xlim_max_str = col_lim_x2.text_input("X Máx:", "", key=f"xlim_max_{tag_tec}")

        col_lim_y1, col_lim_y2 = st.columns(2)
        ylim_min_str = col_lim_y1.text_input("Y Mín:" if not tem_eixo_y2 else "Y1 Mín:", "", key=f"ylim_min_{tag_tec}")
        ylim_max_str = col_lim_y2.text_input("Y Máx:" if not tem_eixo_y2 else "Y1 Máx:", "", key=f"ylim_max_{tag_tec}")

        y2lim_min_str, y2lim_max_str = "", ""
        if tem_eixo_y2:
            col_lim_y2_1, col_lim_y2_2 = st.columns(2)
            def_y2_min = "0" if tecnica_idx == 5 else ""
            def_y2_max = "110" if tecnica_idx == 5 else ""
            y2lim_min_str = col_lim_y2_1.text_input("Y2 Mín:", def_y2_min, key=f"y2lim_min_{tag_tec}")
            y2lim_max_str = col_lim_y2_2.text_input("Y2 Máx:", def_y2_max, key=f"y2lim_max_{tag_tec}")

        limites_manuais = {
            "xlim": (converter_float_seguro(xlim_min_str), converter_float_seguro(xlim_max_str)),
            "ylim": (converter_float_seguro(ylim_min_str), converter_float_seguro(ylim_max_str)),
            "y2lim": (converter_float_seguro(y2lim_min_str), converter_float_seguro(y2lim_max_str)),
        }

        posicao_legenda = None
        if tecnica_idx != 5:
            opcoes_legenda = ["upper right", "upper left", "lower right", "lower left", "best", "Ocultar / Hide"]
            idx_default_leg = (
                1 if tecnica_idx in [1, 9]
                else (3 if tecnica_idx in [3, 8]
                else (2 if tecnica_idx == 2 else 0))
            )
            posicao_legenda = st.selectbox(
                "Posição da Legenda:" if idioma == "Português" else "Legend Position:",
                opcoes_legenda,
                index=idx_default_leg,
                key=f"leg_pos_{tag_tec}"
            )

    # ==========================================================================
    # 7. PARÂMETROS ESPECÍFICOS DA TÉCNICA
    # ==========================================================================
    cv_speed_input = r"0,3\ \mathrm{mV\ s^{-1}}" if idioma == "Português" else r"0.3\ \mathrm{mV\ s^{-1}}"
    exibir_setas_cv = True
    pos_carga_cv = (0.35, 0.58)
    pos_descarga_cv = (0.65, 0.38)

    circuito_upload = None
    pos_circuito_eie = (0.62, 0.78)
    zoom_circuito_eie = 0.36
    exibir_inset_eie = False
    inset_bbox_eie = (0.48, 0.18, 0.44, 0.34)
    inset_limites_eie = {}
    aspect_equal_eie = False
    modo_plot_eie = "Pontos + Linha"

    exibir_delta_e_gcd = True
    delta_e_texto_gcd = r"$\Delta E$"
    delta_e_x_gcd = 0.40
    delta_e_y_topo_gcd = 0.58
    delta_e_y_base_gcd = 0.46
    delta_e_lado_gcd = "Direita / Right"

    rate_tag_input = textos["ciclabilidade_rate"]
    pos_rate_multi = (0.04, 0.93)

    ce_rate_input = textos["ciclabilidade_rate"]
    pos_rate_ce = (0.04, 0.78)
    ce_nome_amostra = "CHZn700@S60"
    ce_patamar_ref = 0.0
    modo_cap_ce = "Pontos + Linha"
    modo_eff_ce = "Pontos + Linha"

    exibir_ir_sc = False
    ir_texto_sc = r"$IR_{drop}$"
    ir_x_sc = 0.25
    ir_y_topo_sc = 0.88
    ir_y_base_sc = 0.78

    exibir_zero_3e = True
    nome_amostra_3e = "Amostra / Sample"
    pos_amostra_3e = (0.05, 0.90)

    protocolo_sc_rate = "0.5, 1, 2, 5, 10, 0.5"
    ciclos_por_degrau_sc = 5

    areas_bet_dict = {}
    exibir_inset_check = False
    inset_bbox_bet = (0.54, 0.22, 0.38, 0.28)
    inset_limites_bet = {}

    titulo_expander_params = "🔬 " + ("Parâmetros da Técnica" if idioma == "Português" else "Technique Parameters")
    with st.sidebar.expander(titulo_expander_params, expanded=False):
        if tecnica_idx == 0:  # CV
            cv_speed_input = st.text_input(
                "Velocidade de Varredura" if idioma == "Português" else "Scan Rate",
                cv_speed_input,
                key=f"cv_v_{tag_tec}_{idioma}"
            )
            exibir_setas_cv = st.checkbox(
                "Exibir indicadores Carga / Descarga" if idioma == "Português" else "Show Charge / Discharge indicators",
                value=True,
                key="cv_show_arrows"
            )
            if exibir_setas_cv:
                st.caption("Posição relativa de 'Carga →':" if idioma == "Português" else "Relative position of 'Charge →':")
                c_chg1, c_chg2 = st.columns(2)
                chg_x = c_chg1.slider("X Carga", 0.0, 0.95, 0.35, 0.02, key="cv_chg_x")
                chg_y = c_chg2.slider("Y Carga", 0.0, 0.95, 0.58, 0.02, key="cv_chg_y")
                pos_carga_cv = (chg_x, chg_y)

                st.caption("Posição relativa de '← Descarga':" if idioma == "Português" else "Relative position of '← Discharge':")
                c_dch1, c_dch2 = st.columns(2)
                dch_x = c_dch1.slider("X Desc.", 0.0, 0.95, 0.65, 0.02, key="cv_dch_x")
                dch_y = c_dch2.slider("Y Desc.", 0.0, 0.95, 0.38, 0.02, key="cv_dch_y")
                pos_descarga_cv = (dch_x, dch_y)

        elif tecnica_idx == 1:  # EIE / Nyquist
            opcoes_modo_eie = ["Pontos + Linha", "Apenas Linha"] if idioma == "Português" else ["Scatter + Line", "Line Only"]
            sel_modo_eie = st.radio(
                "Estilo das Curvas:" if idioma == "Português" else "Curve Style:",
                opcoes_modo_eie,
                index=0,
                horizontal=True,
                key="eie_plot_mode"
            )
            modo_plot_eie = "Apenas Linha" if sel_modo_eie in ["Apenas Linha", "Line Only"] else "Pontos + Linha"

            aspect_equal_eie = st.checkbox(
                "Forçar proporção 1:1 no gráfico principal" if idioma == "Português" else "Force 1:1 aspect ratio on main plot",
                value=False,
                key="eie_aspect_equal"
            )
            st.markdown("---")
            exibir_inset_eie = st.checkbox(
                "Exibir Inset (Altas Frequências - 1:1)" if idioma == "Português" else "Show Inset (High Frequencies - 1:1)",
                value=False,
                key="eie_inset_check"
            )
            if exibir_inset_eie:
                st.caption("Posição do Inset no gráfico:" if idioma == "Português" else "Inset Position:")
                ce_ins1, ce_ins2 = st.columns(2)
                eins_x = ce_ins1.slider("Posição X", 0.05, 0.60, 0.48, 0.02, key="eie_ins_x")
                eins_y = ce_ins2.slider("Posição Y", 0.05, 0.60, 0.18, 0.02, key="eie_ins_y")
                inset_bbox_eie = (eins_x, eins_y, 0.44, 0.34)

                st.caption("Eixos do Inset (opcional):" if idioma == "Português" else "Inset Axes Limits (optional):")
                cei_x1, cei_x2 = st.columns(2)
                eix_min = cei_x1.text_input("Inset Z' Mín:", "", key="eie_ix_min")
                eix_max = cei_x2.text_input("Inset Z' Máx:", "", key="eie_ix_max")
                cei_y1, cei_y2 = st.columns(2)
                eiy_min = cei_y1.text_input("Inset -Z'' Mín:", "", key="eie_iy_min")
                eiy_max = cei_y2.text_input("Inset -Z'' Máx:", "", key="eie_iy_max")

                inset_limites_eie = {
                    "xmin": converter_float_seguro(eix_min),
                    "xmax": converter_float_seguro(eix_max),
                    "ymin": converter_float_seguro(eiy_min),
                    "ymax": converter_float_seguro(eiy_max),
                }

            st.markdown("---")
            circuito_upload = st.file_uploader(
                "Circuito Equivalente (PNG/JPG)" if idioma == "Português" else "Equivalent Circuit (PNG/JPG)",
                type=["png", "jpg", "jpeg"],
                key="circuit_uploader"
            )
            if circuito_upload is not None:
                st.caption("Posição e Escala do Circuito:" if idioma == "Português" else "Circuit Position & Scale:")
                c_eie1, c_eie2 = st.columns(2)
                circ_x = c_eie1.slider("Posição X", 0.05, 0.95, 0.62, 0.02, key="eie_circ_x")
                circ_y = c_eie2.slider("Posição Y", 0.05, 0.95, 0.78, 0.02, key="eie_circ_y")
                pos_circuito_eie = (circ_x, circ_y)
                zoom_circuito_eie = st.slider("Tamanho (Zoom)", 0.15, 0.80, 0.36, 0.02, key="eie_circ_zoom")

        elif tecnica_idx == 2:  # GCD Bateria
            exibir_delta_e_gcd = st.checkbox(
                "Exibir indicador de polarização (ΔE)" if idioma == "Português" else "Show polarization indicator (ΔE)",
                value=True,
                key="gcd_show_delta_e"
            )
            if exibir_delta_e_gcd:
                delta_e_texto_gcd = st.text_input(
                    "Texto do Indicador:" if idioma == "Português" else "Indicator Text:",
                    value=r"$\Delta E$",
                    key="gcd_delta_e_text"
                )
                delta_e_x_gcd = st.slider(
                    "Posição Horizontal (X):" if idioma == "Português" else "Horizontal Position (X):",
                    0.05, 0.90, 0.40, 0.01,
                    key="gcd_de_x"
                )
                c_de1, c_de2 = st.columns(2)
                delta_e_y_topo_gcd = c_de1.slider(
                    "Ponta Superior (Carga):" if idioma == "Português" else "Top Tip (Charge):",
                    0.05, 0.95, 0.58, 0.01,
                    key="gcd_de_y_top"
                )
                delta_e_y_base_gcd = c_de2.slider(
                    "Ponta Inferior (Descarga):" if idioma == "Português" else "Bottom Tip (Discharge):",
                    0.05, 0.95, 0.46, 0.01,
                    key="gcd_de_y_bot"
                )
                delta_e_lado_gcd = st.radio(
                    "Posição do Texto:" if idioma == "Português" else "Text Alignment:",
                    ["Direita / Right", "Esquerda / Left"],
                    index=0,
                    horizontal=True,
                    key="gcd_de_side"
                )

        elif tecnica_idx == 3:  # Rate Capability Bateria
            st.caption("Protocolo padrão de bateria: 0,1 C → 0,2 C → 0,5 C → 1 C → 2 C → 0,1 C." if idioma == "Português" else "Standard battery C-rate protocol: 0.1 C → 0.2 C → 0.5 C → 1 C → 2 C → 0.1 C.")

        elif tecnica_idx == 4:  # Ciclabilidade Multiplot Bateria
            rate_tag_input = st.text_input(
                "Tag de Taxa" if idioma == "Português" else "Rate Tag",
                textos["ciclabilidade_rate"],
                key=f"rate_tag_{tag_tec}_{idioma}"
            )
            st.caption("Posição do Balão de Taxa:" if idioma == "Português" else "Rate Badge Position:")
            cr1, cr2 = st.columns(2)
            rx_multi = cr1.slider("X Taxa", 0.0, 0.90, 0.04, 0.02, key="cicl_rate_x")
            ry_multi = cr2.slider("Y Taxa", 0.0, 0.95, 0.93, 0.02, key="cicl_rate_y")
            pos_rate_multi = (rx_multi, ry_multi)

        elif tecnica_idx == 5:  # CE Individual Bateria
            opcoes_modo_plot = ["Pontos + Linha", "Apenas Linha"] if idioma == "Português" else ["Scatter + Line", "Line Only"]
            sel_cap = st.radio(
                "Estilo da Curva de Capacidade:" if idioma == "Português" else "Capacity Curve Style:",
                opcoes_modo_plot,
                index=0,
                horizontal=True,
                key="ce_mode_cap"
            )
            modo_cap_ce = "Apenas Linha" if sel_cap in ["Apenas Linha", "Line Only"] else "Pontos + Linha"

            sel_eff = st.radio(
                "Estilo da Curva de Eficiência:" if idioma == "Português" else "Efficiency Curve Style:",
                opcoes_modo_plot,
                index=0,
                horizontal=True,
                key="ce_mode_eff"
            )
            modo_eff_ce = "Apenas Linha" if sel_eff in ["Apenas Linha", "Line Only"] else "Pontos + Linha"

            st.markdown("---")
            ce_rate_input = st.text_input(
                "Taxa de Ciclagem (Rate Tag):" if idioma == "Português" else "Cycling Rate (Rate Tag):",
                value=textos["ciclabilidade_rate"],
                key="ce_rate_tag_input"
            )
            st.caption("Posição do Balão de Taxa:" if idioma == "Português" else "Rate Badge Position:")
            cr_ce1, cr_ce2 = st.columns(2)
            rx_ce = cr_ce1.slider("X Taxa", 0.0, 0.90, 0.04, 0.02, key="ce_rate_x")
            ry_ce = cr_ce2.slider("Y Taxa", 0.0, 0.95, 0.78, 0.02, key="ce_rate_y")
            pos_rate_ce = (rx_ce, ry_ce)

            ce_nome_amostra = st.text_input(
                "Nome da Amostra (canto inferior):" if idioma == "Português" else "Sample Name (lower corner):",
                value="CHZn700@S60",
                key="ce_sample_name_input"
            )
            val_patamar_str = st.text_input(
                "Linha de Patamar de Referência (ex: 330 mAh/g, 0 para desativar):" if idioma == "Português" else "Reference Plateau Line (e.g. 330 mAh/g, 0 to disable):",
                value="0",
                key="ce_patamar_input"
            )
            try:
                ce_patamar_ref = float(val_patamar_str.replace(",", "."))
            except ValueError:
                ce_patamar_ref = 0.0

        elif tecnica_idx == 6:  # CGCD Supercapacitor (2 Eletrodos / Janelas)
            exibir_ir_sc = st.checkbox(
                "Exibir indicador de queda ôhmica (IR drop)" if idioma == "Português" else "Show ohmic drop indicator (IR drop)",
                value=False,
                key="sc_show_ir"
            )
            if exibir_ir_sc:
                ir_texto_sc = st.text_input(
                    "Texto do Indicador:" if idioma == "Português" else "Indicator Text:",
                    value=r"$IR_{drop}$",
                    key="sc_ir_text"
                )
                ir_x_sc = st.slider("Posição X (Vértice):", 0.05, 0.90, 0.25, 0.01, key="sc_ir_x")
                c_ir1, c_ir2 = st.columns(2)
                ir_y_topo_sc = c_ir1.slider("Topo:", 0.05, 0.95, 0.88, 0.01, key="sc_ir_y_top")
                ir_y_base_sc = c_ir2.slider("Base:", 0.05, 0.95, 0.78, 0.01, key="sc_ir_y_bot")

        elif tecnica_idx == 7:  # CGCD Supercapacitor (3 Eletrodos: Ecell, Ewe, Ece)
            nome_amostra_3e = st.text_input(
                "Balão de Identificação da Amostra:" if idioma == "Português" else "Sample Identification Badge:",
                value="Amostra / Sample",
                key="sc_3e_sample_badge"
            )
            st.caption("Posição do Balão da Amostra:" if idioma == "Português" else "Sample Badge Position:")
            c_3e1, c_3e2 = st.columns(2)
            s3e_x = c_3e1.slider("X Balão", 0.0, 0.90, 0.05, 0.02, key="sc_3e_badge_x")
            s3e_y = c_3e2.slider("Y Balão", 0.0, 0.95, 0.90, 0.02, key="sc_3e_badge_y")
            pos_amostra_3e = (s3e_x, s3e_y)

            exibir_zero_3e = st.checkbox(
                "Exibir linha de referência em 0 V (Eixo Y2)" if idioma == "Português" else "Show 0 V reference line (Y2 Axis)",
                value=True,
                key="sc_3e_zero_line"
            )

        elif tecnica_idx == 8:  # Rate Capability (Supercapacitor)
            protocolo_sc_rate = st.text_input(
                "Densidades de Corrente (A/g, separadas por vírgula):" if idioma == "Português" else "Current Densities (A/g, comma-separated):",
                value="0.5, 1, 2, 5, 10, 0.5",
                key="sc_rate_protocol"
            )
            ciclos_por_degrau_sc = st.number_input(
                "Ciclos por degrau:" if idioma == "Português" else "Cycles per step:",
                min_value=1,
                max_value=500,
                value=5,
                step=1,
                key="sc_rate_cycles_step"
            )

        elif tecnica_idx == 9:  # BET
            st.markdown(
                "**Áreas Específicas BET ($S_{BET}$ em $\mathrm{m^2\ g^{-1}}$):**"
                if idioma == "Português"
                else "**Specific BET Surface Area ($S_{BET}$ in $\mathrm{m^2\ g^{-1}}$):**"
            )
            if dados_bytes is not None and amostras_detectadas:
                for amostra in amostras_detectadas:
                    nome_exibicao = mapa_nomes_curvas.get(amostra, amostra)
                    val_str = st.text_input(
                        f"{nome_exibicao}:",
                        value="",
                        placeholder="ex: 1200",
                        key=f"bet_txt_input_{amostra}"
                    )
                    if val_str.strip():
                        try:
                            areas_bet_dict[amostra] = float(val_str.replace(",", "."))
                        except ValueError:
                            pass
            else:
                st.caption("Carregue o arquivo de dados para listar as amostras." if idioma == "Português" else "Upload a data file to list detected samples.")

            st.markdown("---")
            exibir_inset_check = st.checkbox(
                "Exibir Inset (Zoom)" if idioma == "Português" else "Show Inset (Zoom)",
                False,
                key="bet_inset_check"
            )
            if exibir_inset_check:
                st.caption("Posição do Inset no gráfico:" if idioma == "Português" else "Inset Position:")
                c_ins1, c_ins2 = st.columns(2)
                ins_x = c_ins1.slider("Posição X", 0.05, 0.65, 0.54, 0.02, key="bet_ins_x")
                ins_y = c_ins2.slider("Posição Y", 0.05, 0.65, 0.22, 0.02, key="bet_ins_y")
                inset_bbox_bet = (ins_x, ins_y, 0.38, 0.28)

                st.caption("Eixos do Inset (opcional):" if idioma == "Português" else "Inset Axes Limits (optional):")
                ci_x1, ci_x2 = st.columns(2)
                ix_min = ci_x1.text_input("Inset X Mín:", "", key="bet_ix_min")
                ix_max = ci_x2.text_input("Inset X Máx:", "", key="bet_ix_max")
                ci_y1, ci_y2 = st.columns(2)
                iy_min = ci_y1.text_input("Inset Y Mín:", "", key="bet_iy_min")
                iy_max = ci_y2.text_input("Inset Y Máx:", "", key="bet_iy_max")

                inset_limites_bet = {
                    "xmin": converter_float_seguro(ix_min),
                    "xmax": converter_float_seguro(ix_max),
                    "ymin": converter_float_seguro(iy_min),
                    "ymax": converter_float_seguro(iy_max),
                }

    st.title(escolha_tecnica)

    # 8. Renderização do Gráfico
    if dados_bytes is not None:
        try:
            fig = None
            if tecnica_idx == 0:
                fig = gerar_plot_cv(
                    dados_bytes, cv_speed_input, eixo_x_input, eixo_y_label=eixo_y_input,
                    tag_carga=textos["cv_charge"], tag_descarga=textos["cv_discharge"],
                    mapa_cores=mapa_cores_curvas, mapa_nomes=mapa_nomes_curvas, mapa_estilos=mapa_estilos_curvas,
                    limites_manuais=limites_manuais, posicao_legenda=posicao_legenda, tema=tema_visual,
                    idioma=idioma, exibir_setas=exibir_setas_cv, pos_carga=pos_carga_cv, pos_descarga=pos_descarga_cv
                )
            elif tecnica_idx == 1:
                fig = gerar_plot_eie(
                    dados_bytes, circuito_upload, eixo_x_input, eixo_y_input, textos["eie_inset"],
                    mapa_cores_curvas, mapa_nomes_curvas, mapa_estilos_curvas,
                    limites_manuais, posicao_legenda, tema_visual, idioma=idioma,
                    pos_circuito=pos_circuito_eie, zoom_circuito=zoom_circuito_eie,
                    exibir_inset=exibir_inset_eie, inset_bbox=inset_bbox_eie, inset_limites=inset_limites_eie,
                    aspect_equal=aspect_equal_eie, modo_plot=modo_plot_eie
                )
            elif tecnica_idx == 2:
                fig = gerar_plot_gcd(
                    dados_bytes,
                    eixo_x_label=eixo_x_input,
                    eixo_y_label=eixo_y_input,
                    mapa_cores=mapa_cores_curvas,
                    mapa_nomes=mapa_nomes_curvas,
                    mapa_estilos=mapa_estilos_curvas,
                    limites_manuais=limites_manuais,
                    posicao_legenda=posicao_legenda,
                    tema=tema_visual,
                    idioma=idioma,
                    exibir_delta_e=exibir_delta_e_gcd,
                    delta_e_texto=delta_e_texto_gcd,
                    delta_e_x_frac=delta_e_x_gcd,
                    delta_e_y_topo=delta_e_y_topo_gcd,
                    delta_e_y_base=delta_e_y_base_gcd,
                    delta_e_lado_texto=delta_e_lado_gcd
                )
            elif tecnica_idx == 3:
                fig = gerar_plot_rate(
                    dados_bytes, eixo_x_input, eixo_y_label=eixo_y_input,
                    mapa_cores=mapa_cores_curvas, mapa_nomes=mapa_nomes_curvas, mapa_estilos=mapa_estilos_curvas,
                    limites_manuais=limites_manuais, posicao_legenda=posicao_legenda, tema=tema_visual, idioma=idioma
                )
            elif tecnica_idx == 4:
                fig = gerar_plot_ciclabilidade(
                    dados_bytes, rate_tag_input, pos_rate_multi, eixo_x_input, eixo_y_input,
                    mapa_cores_curvas, mapa_nomes_curvas, mapa_estilos_curvas,
                    limites_manuais, posicao_legenda, tema_visual, idioma=idioma
                )
            elif tecnica_idx == 5:
                cor_cap_padrao = "#e2e8f0" if dark_mode_ativo else "#0f172a"
                cor_eff_padrao = "#38bdf8" if dark_mode_ativo else "#2563eb"
                cor_cap = mapa_cores_curvas.get("Discharge Capacity", cor_cap_padrao)
                cor_eff = mapa_cores_curvas.get("Coulombic Efficiency", cor_eff_padrao)
                est_cap = mapa_estilos_curvas.get("Discharge Capacity", "--")
                est_eff = mapa_estilos_curvas.get("Coulombic Efficiency", "-")
                fig = gerar_plot_ciclabilidade_eficiencia(
                    dados_bytes,
                    eixo_x_label=eixo_x_input,
                    eixo_y1_label=eixo_y_input,
                    eixo_y2_label=eixo_y2_input,
                    nome_amostra=ce_nome_amostra,
                    rate_tag=ce_rate_input,
                    pos_rate=pos_rate_ce,
                    cor_capacidade=cor_cap,
                    cor_eficiencia=cor_eff,
                    estilo_capacidade=est_cap,
                    estilo_eficiencia=est_eff,
                    modo_cap=modo_cap_ce,
                    modo_eff=modo_eff_ce,
                    limites_manuais=limites_manuais,
                    patamar_ref=ce_patamar_ref,
                    tema=tema_visual,
                    idioma=idioma
                )
            elif tecnica_idx == 6:
                fig = gerar_plot_sc_2e_cgcd(
                    dados_bytes,
                    eixo_x_label=eixo_x_input,
                    eixo_y_label=eixo_y_input,
                    mapa_cores=mapa_cores_curvas,
                    mapa_nomes=mapa_nomes_curvas,
                    mapa_estilos=mapa_estilos_curvas,
                    limites_manuais=limites_manuais,
                    posicao_legenda=posicao_legenda,
                    tema=tema_visual,
                    idioma=idioma,
                    exibir_ir_drop=exibir_ir_sc,
                    ir_texto=ir_texto_sc,
                    ir_x_frac=ir_x_sc,
                    ir_y_topo=ir_y_topo_sc,
                    ir_y_base=ir_y_base_sc
                )
            elif tecnica_idx == 7:
                fig = gerar_plot_sc_3e_cgcd(
                    dados_bytes,
                    eixo_x_label=eixo_x_input,
                    eixo_y1_label=eixo_y_input,
                    eixo_y2_label=eixo_y2_input,
                    mapa_cores=mapa_cores_curvas,
                    mapa_nomes=mapa_nomes_curvas,
                    mapa_estilos=mapa_estilos_curvas,
                    limites_manuais=limites_manuais,
                    posicao_legenda=posicao_legenda,
                    tema=tema_visual,
                    idioma=idioma,
                    exibir_linha_zero=exibir_zero_3e,
                    nome_amostra_3e=nome_amostra_3e,
                    pos_amostra_3e=pos_amostra_3e
                )
            elif tecnica_idx == 8:
                fig = gerar_plot_sc_rate(
                    dados_bytes,
                    eixo_x_label=eixo_x_input,
                    eixo_y_label=eixo_y_input,
                    mapa_cores=mapa_cores_curvas,
                    mapa_nomes=mapa_nomes_curvas,
                    mapa_estilos=mapa_estilos_curvas,
                    limites_manuais=limites_manuais,
                    posicao_legenda=posicao_legenda,
                    tema=tema_visual,
                    idioma=idioma,
                    protocolo_correntes=protocolo_sc_rate,
                    ciclos_por_degrau=ciclos_por_degrau_sc
                )
            elif tecnica_idx == 9:
                titulo_legenda = textos["bet_legenda_area"] if areas_bet_dict else textos["bet_legenda"]
                fig = gerar_plot_bet(
                    dados_bytes, eixo_x_input, eixo_y_input,
                    textos["bet_ads"], textos["bet_des"], titulo_legenda,
                    textos["bet_inset"], mapa_cores_curvas, mapa_nomes_curvas, mapa_estilos_curvas,
                    limites_manuais, posicao_legenda, tema_visual, idioma=idioma,
                    areas_bet=areas_bet_dict, exibir_inset=exibir_inset_check,
                    inset_bbox=inset_bbox_bet, inset_limites=inset_limites_bet
                )

            if fig is not None:
                st.pyplot(fig)

                col1, col2 = st.columns(2)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

                buf_png = io.BytesIO()
                fig.savefig(buf_png, format="png", dpi=300, bbox_inches="tight", facecolor=fig.get_facecolor())
                col1.download_button(
                    label="📥 Baixar PNG (300 DPI)" if idioma == "Português" else "📥 Download PNG (300 DPI)",
                    data=buf_png.getvalue(),
                    file_name=f"grafico_{timestamp}.png",
                    mime="image/png",
                )

                buf_svg = io.BytesIO()
                fig.savefig(buf_svg, format="svg", bbox_inches="tight", facecolor=fig.get_facecolor())
                col2.download_button(
                    label="📥 Baixar SVG (Vetorial)" if idioma == "Português" else "📥 Download SVG (Vector)",
                    data=buf_svg.getvalue(),
                    file_name=f"grafico_{timestamp}.svg",
                    mime="image/svg+xml",
                )

        except Exception as e:
            st.error(f"Erro ao processar arquivo: {e}" if idioma == "Português" else f"Error processing file: {e}")
    else:
        st.info("👈 Carregue um arquivo no topo da barra lateral para gerar o gráfico correspondente." if idioma == "Português" else "👈 Upload a file at the top of the sidebar to generate the plot.")


if __name__ == "__main__":
    main()