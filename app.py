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
from mpl_toolkits.axes_grid1.inset_locator import inset_axes
import numpy as np
import pandas as pd
import streamlit as st

# ==============================================================================
# CONFIGURAÇÃO GERAL DA PÁGINA E MATPLOTLIB
# ==============================================================================
st.set_page_config(
    page_title="PhVolt - Análise Eletroquímica",
    page_icon="⚡",
    layout="wide",
)

plt.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "DejaVu Sans", "Helvetica"],
        "axes.edgecolor": "#334155",
        "axes.linewidth": 1.4,
        "xtick.color": "#334155",
        "ytick.color": "#334155",
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
        "ciclabilidade_x": r"$\mathbf{Número\ de\ Ciclos}$",
        "ciclabilidade_y": r"$\mathbf{Capacidade\ Específica\ (mAh\ g_S^{-1})}$",
        "ciclabilidade_rate": "Taxa: 0.5 C",
        "cv_x": r"$\mathbf{Potencial\ vs\ Li/Li^+\ (V)}$",
        "cv_y": r"$\mathbf{Corrente\ (mA)}$",
        "cv_charge": "Carga →",
        "cv_discharge": "← Descarga",
        "eie_x": r"$\mathbf{Z_{Real}\ (\Omega)}$",
        "eie_y": r"$\mathbf{-Z_{Im}\ (\Omega)}$",
        "rate_x": r"$\mathbf{Número\ de\ Ciclos}$",
        "rate_y": r"$\mathbf{Capacidade\ Específica\ (mAh\ g_S^{-1})}$",
        "bet_x": r"$\mathbf{Pressão\ Relativa\ (p/p_0)}$",
        "bet_y": r"$\mathbf{Quantidade\ Adsorvida\ (cm^3\ g^{-1}\ STP)}$",
        "bet_ads": "Adsorção (fechado)",
        "bet_des": "Dessorção (aberto)",
        "bet_inset": "Região de baixo volume de poros",
        "bet_legenda": r"$\mathbf{Amostra}$",
        "bet_legenda_area": r"$\mathbf{Amostra\ (S_{BET})}$",
    },
    "Inglês": {
        "ciclabilidade_x": r"$\mathbf{Cycle\ Number}$",
        "ciclabilidade_y": r"$\mathbf{Specific\ Capacity\ (mAh\ g_S^{-1})}$",
        "ciclabilidade_rate": "Rate: 0.5 C",
        "cv_x": r"$\mathbf{Potential\ vs\ Li/Li^+\ (V)}$",
        "cv_y": r"$\mathbf{Current\ (mA)}$",
        "cv_charge": "Charge →",
        "cv_discharge": "← Discharge",
        "eie_x": r"$\mathbf{Z_{Real}\ (\Omega)}$",
        "eie_y": r"$\mathbf{-Z_{Im}\ (\Omega)}$",
        "rate_x": r"$\mathbf{Cycle\ Number}$",
        "rate_y": r"$\mathbf{Specific\ Capacity\ (mAh\ g_S^{-1})}$",
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


def identificar_amostras(df, tokens_limpos, tecnica_idx):
    num_cols = df.shape[1]
    if tecnica_idx == 3:  # Rate Capability
        num_curvas = num_cols - 1
        legendas = tokens_limpos[1:] if len(tokens_limpos) > num_curvas else tokens_limpos
        if len(legendas) < num_curvas:
            legendas = [f"Sample {i+1}" for i in range(num_curvas)]
        return legendas[:num_curvas]
    else:  # Pareadas
        num_amostras = num_cols // 2 if num_cols >= 2 else num_cols
        if len(tokens_limpos) >= 2:
            nomes = [tokens_limpos[k] for k in range(1, len(tokens_limpos), 2)]
        else:
            nomes = tokens_limpos
        if len(nomes) < num_amostras:
            nomes = nomes + [f"Sample {i+1}" for i in range(len(nomes), num_amostras)]
        return nomes[:num_amostras]


# ==============================================================================
# FUNÇÕES DE PLOTAGEM
# ==============================================================================

def gerar_plot_ciclabilidade(fonte_dados, rate_tag, eixo_x_label, eixo_y_label, mapa_cores, unidade_y=r"mAh\ g^{-1}"):
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
    x_min, x_max = np.min(todos_x), np.max(todos_x)
    y_min, y_max = np.min(todos_y), np.max(todos_y)

    dados_finais = []
    for idx, c in enumerate(curvas):
        cor = mapa_cores.get(c["nome"], list(mapa_cores.values())[idx % len(mapa_cores)])
        ax.plot(c["x"], c["y"], color=cor, lw=2.0, label=c["nome"], zorder=4)
        c0, cf = c["y"][0], c["y"][-1]
        ret = (cf / c0) * 100 if c0 != 0 else 0.0
        dados_finais.append({"nome": c["nome"], "x_end": c["x"][-1], "y_end": cf, "ret": ret, "cor": cor})
        ax.scatter(c["x"][-1], cf, color=cor, s=30, zorder=6, edgecolors="white", linewidths=0.8)

    dados_finais.sort(key=lambda item: item["y_end"], reverse=True)
    num_amostras = len(dados_finais)
    span_x = x_max - x_min
    span_y = y_max - (y_min if y_min < 0 else 0)
    y_posicoes = np.linspace(span_y * 0.32, span_y * 0.06, num_amostras) if num_amostras > 1 else [span_y * 0.32]

    for i, d in enumerate(dados_finais):
        ax.annotate(
            rf"$\mathbf{{{d['y_end']:.0f}\ {unidade_y}}}$  ({d['ret']:.1f}%)",
            xy=(d["x_end"], d["y_end"]),
            xytext=(x_max + span_x * 0.045, y_posicoes[i]),
            fontsize=8.5, fontweight="semibold", color="#1e293b", va="center",
            bbox=dict(boxstyle="round,pad=0.36", facecolor="#ffffff", edgecolor=d["cor"], linewidth=1.3, alpha=0.98),
            arrowprops=dict(arrowstyle="->", color=d["cor"], lw=1.0, connectionstyle="arc3,rad=-0.08"),
            zorder=7,
        )

    ax.axvline(x_max, color="#94a3b8", linestyle=":", linewidth=1.1, alpha=0.8, zorder=2)
    if rate_tag:
        ax.text(0.04, 0.93, rf"$\mathbf{{{rate_tag}}}$", transform=ax.transAxes, fontsize=10.5,
                fontweight="bold", color="#334155", bbox=dict(boxstyle="round,pad=0.4", facecolor="white", edgecolor="#cbd5e1", linewidth=1.1))

    ax.set_xlabel(eixo_x_label, fontsize=12.5, labelpad=8)
    ax.set_ylabel(eixo_y_label, fontsize=12.5, labelpad=8)
    ax.set_xlim(x_min - span_x * 0.02, x_max + span_x * 0.32)
    ax.set_ylim(min(-span_y * 0.02, y_min), y_max * 1.15)
    ax.grid(True, linestyle=":", alpha=0.4, color="#cbd5e1")
    ax.legend(frameon=True, facecolor="white", edgecolor="#cbd5e1", loc="upper right")
    plt.tight_layout()
    return fig


def gerar_plot_cv(fonte_dados, velocidade, eixo_x_label, eixo_y_label, tag_carga, tag_descarga, mapa_cores, exibir_setas=True):
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

    ax.axhline(0, color="#94a3b8", linestyle="--", linewidth=1.1, alpha=0.7)
    for idx, c in enumerate(curvas):
        cor = mapa_cores.get(c["nome"], list(mapa_cores.values())[idx % len(mapa_cores)])
        ax.plot(c["E"], c["I"], color=cor, linewidth=2.2, label=c["nome"])

    span_e, span_i = e_max - e_min, i_max - i_min
    if exibir_setas and span_i > 0:
        ax.annotate(tag_carga, xy=(e_min + span_e * 0.35, i_max * 0.15), fontsize=10.5, fontweight="semibold", color="#475569")
        ax.annotate(tag_descarga, xy=(e_min + span_e * 0.65, i_min * 0.20), fontsize=10.5, fontweight="semibold", color="#475569")

    if velocidade:
        ax.text(0.04, 0.93, rf"$\nu = {velocidade}$", transform=ax.transAxes, fontsize=10.5,
                fontweight="bold", color="#1e293b", bbox=dict(boxstyle="round,pad=0.35", facecolor="#ffffff", edgecolor="#cbd5e1"))

    ax.set_xlabel(eixo_x_label, fontsize=12.5, labelpad=8)
    ax.set_ylabel(eixo_y_label, fontsize=12.5, labelpad=8)
    ax.set_xlim(e_min - span_e * 0.05, e_max + span_e * 0.05)
    ax.set_ylim(i_min - span_i * 0.10, i_max + span_i * 0.18)
    ax.grid(True, linestyle=":", alpha=0.4, color="#cbd5e1")
    ax.legend(frameon=True, facecolor="white", edgecolor="#cbd5e1", loc="upper right")
    plt.tight_layout()
    return fig


def gerar_plot_eie(fonte_dados, circuito_bytes, eixo_x_label, eixo_y_label, mapa_cores):
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

    fig, ax = plt.subplots(figsize=(8.2, 5.0), dpi=300)
    marcadores_ciclo = cycle(MARCADORES_PADRAO)

    todos_re = np.concatenate([c["re"] for c in curvas if len(c["re"]) > 0])
    todos_im = np.concatenate([c["im"] for c in curvas if len(c["im"]) > 0])
    re_min, re_max = np.min(todos_re), np.max(todos_re)
    im_min, im_max = np.min(todos_im), np.max(todos_im)

    for idx, c in enumerate(curvas):
        cor = mapa_cores.get(c["nome"], list(mapa_cores.values())[idx % len(mapa_cores)])
        marcador = next(marcadores_ciclo)
        ax.plot(c["re"], c["im"], color=cor, linewidth=1.6, alpha=0.55, zorder=3)
        ax.scatter(c["re"], c["im"], color=cor, s=42, marker=marcador, edgecolors="white", linewidths=0.75, label=c["nome"], zorder=4)

    if circuito_bytes is not None:
        img = mpimg.imread(circuito_bytes)
        ab = AnnotationBbox(
            OffsetImage(img, zoom=0.36),
            (re_min + (re_max - re_min) * 0.55, im_max * 0.85),
            frameon=True, pad=0.35, bboxprops=dict(edgecolor="#cbd5e1", facecolor="white", alpha=0.95, lw=1.0)
        )
        ax.add_artist(ab)

    span_re = re_max - re_min
    ax.set_xlabel(eixo_x_label, fontsize=12.5, labelpad=8)
    ax.set_ylabel(eixo_y_label, fontsize=12.5, labelpad=8)
    ax.set_xlim(min(0, re_min - 2), re_max + span_re * 0.08)
    ax.set_ylim(min(-1.5, im_min - 1), im_max * 1.25)
    ax.set_aspect("equal", adjustable="box")
    ax.grid(True, linestyle=":", alpha=0.4, color="#cbd5e1")
    ax.legend(frameon=True, facecolor="white", edgecolor="#cbd5e1", loc="upper left")
    plt.tight_layout()
    return fig


def gerar_plot_rate(fonte_dados, eixo_x_label, eixo_y_label, mapa_cores):
    df, tokens_limpos = processar_cabecalho_e_dados(fonte_dados)
    x_ciclos = df.iloc[:, 0].to_numpy(float)
    num_curvas = df.shape[1] - 1

    legendas = tokens_limpos[1:] if len(tokens_limpos) > num_curvas else tokens_limpos
    if len(legendas) < num_curvas:
        legendas = [f"Sample {i+1}" for i in range(num_curvas)]

    zonas_c_rate = [
        {"label": "0.1 C", "start": 0.5, "end": 5.5, "mid": 3.0},
        {"label": "0.2 C", "start": 5.5, "end": 9.5, "mid": 7.5},
        {"label": "0.5 C", "start": 9.5, "end": 13.5, "mid": 11.5},
        {"label": "1 C", "start": 13.5, "end": 17.5, "mid": 15.5},
        {"label": "2 C", "start": 17.5, "end": 21.5, "mid": 19.5},
        {"label": "0.1 C", "start": 21.5, "end": 25.5, "mid": 23.5},
    ]

    fig, ax = plt.subplots(figsize=(8.6, 5.2), dpi=300)
    marcadores_ciclo = cycle(MARCADORES_PADRAO)

    y_max = np.nanmax(df.iloc[:, 1:].values)
    y_min = np.nanmin(df.iloc[:, 1:].values)
    y_topo = y_max * 1.15

    for i, zone in enumerate(zonas_c_rate):
        if i % 2 == 1:
            ax.axvspan(zone["start"], zone["end"], color="#f1f5f9", alpha=0.9, zorder=1)
        if i > 0:
            ax.axvline(zone["start"], color="#cbd5e1", linestyle="--", linewidth=1.1, zorder=2)
        ax.text(zone["mid"], y_topo * 0.96, zone["label"], ha="center", va="center",
                fontsize=10.0, fontweight="bold", color="#1e293b",
                bbox=dict(boxstyle="round,pad=0.25", facecolor="#ffffff", edgecolor="#cbd5e1", lw=1.0))

    offsets = np.linspace(-0.12, 0.12, num_curvas) if num_curvas > 1 else [0.0]
    for col_idx in range(num_curvas):
        y_valores = df.iloc[:, col_idx + 1].to_numpy(float)
        nome = legendas[col_idx]
        cor = mapa_cores.get(nome, list(mapa_cores.values())[col_idx % len(mapa_cores)])
        ax.scatter(
            x_ciclos + offsets[col_idx], y_valores, color=cor, s=52,
            marker=next(marcadores_ciclo), edgecolors="white", linewidths=0.85,
            label=nome, zorder=4
        )

    ax.set_xlabel(eixo_x_label, fontsize=12.5, labelpad=8)
    ax.set_ylabel(eixo_y_label, fontsize=12.5, labelpad=8)
    ax.set_xlim(0, max(x_ciclos) + 1)
    ax.set_ylim(min(-10, y_min - 20), y_topo * 1.05)
    ax.yaxis.grid(True, linestyle=":", alpha=0.5, color="#cbd5e1")
    ax.legend(frameon=True, facecolor="white", edgecolor="#cbd5e1", loc="lower left")
    plt.tight_layout()
    return fig


def gerar_plot_bet(fonte_dados, eixo_x_label, eixo_y_label, rotulo_ads, rotulo_des, titulo_legenda, titulo_inset, mapa_cores, areas_bet=None, exibir_inset=False):
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
        val_bet = areas_bet.get(nome, areas_bet.get(nome.replace(" ", ""), None)) if areas_bet else None
        rotulo = rf"{nome}  $\mathbf{{({val_bet:.0f}\ m^2\ g^{{-1}})}}$" if val_bet else nome

        ax.plot(iso["ads_p"], iso["ads_v"], color=cor, linewidth=1.7, alpha=0.85, zorder=3)
        ax.scatter(iso["ads_p"], iso["ads_v"], color=cor, s=28, marker="o", edgecolors="white", linewidths=0.6, zorder=4)

        if iso["tem_dessorcao"] and len(iso["des_p"]) > 0:
            ax.plot(iso["des_p"], iso["des_v"], color=cor, linewidth=1.7, alpha=0.85, zorder=3)
            ax.scatter(iso["des_p"], iso["des_v"], facecolors="white", edgecolors=cor, s=28, marker="o", linewidths=1.2, zorder=5)

        legend_elements.append(Line2D([0], [0], marker="o", color="none", markeredgecolor="white", markerfacecolor=cor, markersize=7, label=rotulo))

    if exibir_inset and len(isotherms) > 1:
        amostras_baixas = [iso for iso in isotherms if iso["v_max"] < (v_max * 0.25)]
        if amostras_baixas:
            ax_ins = inset_axes(ax, width="100%", height="100%", bbox_to_anchor=(0.54, 0.22, 0.38, 0.28), bbox_transform=ax.transAxes)
            ax_ins.set_facecolor("white")
            for idx, iso in enumerate(isotherms):
                cor_ins = mapa_cores.get(iso["name"], list(mapa_cores.values())[idx % len(mapa_cores)])
                if iso in amostras_baixas:
                    ax_ins.plot(iso["ads_p"], iso["ads_v"], color=cor_ins, linewidth=1.4, alpha=0.9, zorder=3)
                    ax_ins.scatter(iso["ads_p"], iso["ads_v"], color=cor_ins, s=18, marker="o", edgecolors="white", linewidths=0.4, zorder=4)
                    if iso["tem_dessorcao"] and len(iso["des_p"]) > 0:
                        ax_ins.plot(iso["des_p"], iso["des_v"], color=cor_ins, linewidth=1.4, alpha=0.9, zorder=3)
                        ax_ins.scatter(iso["des_p"], iso["des_v"], facecolors="white", edgecolors=cor_ins, s=18, marker="o", linewidths=0.9, zorder=5)
            ax_ins.set_xlim(-0.02, 1.02)
            ax_ins.grid(True, linestyle=":", alpha=0.4, color="#cbd5e1")
            ax_ins.set_title(titulo_inset, fontsize=8.5, fontweight="bold", color="#475569", pad=3)

    ax.set_xlabel(eixo_x_label, fontsize=12.5, labelpad=8)
    ax.set_ylabel(eixo_y_label, fontsize=12.5, labelpad=8)
    ax.set_xlim(-0.02, 1.02)
    ax.set_ylim(-20, v_max * 1.18)
    ax.grid(True, linestyle=":", alpha=0.4, color="#cbd5e1")

    leg_amostras = ax.legend(
        handles=legend_elements, title=titulo_legenda, title_fontsize=10.5,
        frameon=True, facecolor="white", edgecolor="#cbd5e1", loc="upper left",
        bbox_to_anchor=(0.03, 0.98), labelspacing=0.45
    )
    ax.add_artist(leg_amostras)

    elementos_tipo = [
        Line2D([0], [0], marker="o", color="none", markeredgecolor="white", markerfacecolor="#475569", markersize=6.5, label=rotulo_ads),
        Line2D([0], [0], marker="o", color="none", markeredgecolor="#475569", markerfacecolor="white", markeredgewidth=1.2, markersize=6.5, label=rotulo_des),
    ]
    ax.legend(
        handles=elementos_tipo, frameon=True, facecolor="white", edgecolor="#cbd5e1",
        loc="upper right", bbox_to_anchor=(0.97, 0.98), labelspacing=0.35, fontsize=9.0
    )

    plt.tight_layout()
    return fig


# ==============================================================================
# INTERFACE PRINCIPAL (STREAMLIT)
# ==============================================================================
def main():
    # Ícone / Logo acima do título
    caminho_logo = Path(__file__).parent / "vikavolt.ico"  # ou o nome do seu arquivo
    if caminho_logo.exists():
        st.sidebar.image(str(caminho_logo), width=120)  # ajuste a largura (width) como preferir
    st.sidebar.title("⚡ PhVolt")
    st.sidebar.caption("Processamento de Gráficos Eletroquímicos")

    # 1. Carregamento do Arquivo no Topo
    label_upload = "📁 Carregue o arquivo de dados (.txt, .dat, .csv):"
    arquivo_upload = st.sidebar.file_uploader(
        label_upload,
        type=["txt", "dat", "csv"],
        key="main_file_uploader"
    )

    # 2. Detecção e Reset automático ao trocar arquivo
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

    # 3. Idioma
    idioma = st.sidebar.radio("🌐 Idioma / Language:", ["Português", "Inglês"], key="app_lang")
    textos = TEXTOS_PADRAO[idioma]

    # 4. Seleção de Técnica - CORRIGIDO: usa index direto via callback/índice sem duplicar estado
    tecnicas_pt = [
        "(1) Ciclabilidade Multiplot",
        "(2) CV Multiplot",
        "(3) EIE Multiplot (Nyquist)",
        "(4) Rate Capability",
        "(5) BET (Adsorção / Dessorção)",
    ]
    tecnicas_en = [
        "(1) Multiplot Cyclability",
        "(2) Multiplot CV",
        "(3) Multiplot EIS (Nyquist)",
        "(4) Rate Capability",
        "(5) BET (Adsorption / Desorption)",
    ]
    
    lista_tecnicas = tecnicas_pt if idioma == "Português" else tecnicas_en
    
    # Gerencia a troca de técnica em 1 único clique
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

    # Identificador abreviado para desvincular chaves de inputs
    tags_tecnicas = ["cicl", "cv", "eie", "rate", "bet"]
    tag_tec = tags_tecnicas[tecnica_idx]

    # 5. Esquema Global de Cores
    st.sidebar.markdown(f"### 🎨 {'Esquema de Cores' if idioma == 'Português' else 'Color Scheme'}")
    nome_paleta_escolhida = st.sidebar.selectbox(
        "Paleta Global:" if idioma == "Português" else "Global Palette:",
        list(PALETAS_DISPONIVEIS.keys()),
        index=0,
        key="global_palette_selector"
    )
    paleta_ativa = PALETAS_DISPONIVEIS[nome_paleta_escolhida]

    # 6. Cores Manuais por Amostra
    mapa_cores_curvas = {}
    if dados_bytes is not None:
        try:
            df_temp, tokens_temp = processar_cabecalho_e_dados(dados_bytes)
            amostras_detectadas = identificar_amostras(df_temp, tokens_temp, tecnica_idx)

            with st.sidebar.expander("🖌️ " + ("Cores Manuais por Amostra" if idioma == "Português" else "Custom Sample Colors"), expanded=False):
                st.caption("Ajuste a cor individual de qualquer curva:" if idioma == "Português" else "Fine-tune individual curve colors:")
                for i, nome_amostra in enumerate(amostras_detectadas):
                    cor_padrao = paleta_ativa[i % len(paleta_ativa)]
                    nome_arquivo_seguro = st.session_state.get("nome_arquivo_anterior", "def")
                    chave_color_picker = f"cp_{nome_arquivo_seguro}_{tag_tec}_{nome_paleta_escolhida}_{nome_amostra}_{i}"
                    cor_escolhida = st.color_picker(f"{nome_amostra}:", cor_padrao, key=chave_color_picker)
                    mapa_cores_curvas[nome_amostra] = cor_escolhida
        except Exception:
            pass

    # 7. Configuração dos Eixos (Expander recolhido e isolado)
    circuito_upload = None
    exibir_inset_check = False
    areas_bet_input = ""

    titulo_expander_eixos = "⚙️ " + ("Configuração dos Eixos" if idioma == "Português" else "Axis Settings")
    with st.sidebar.expander(titulo_expander_eixos, expanded=False):
        if tecnica_idx == 0:
            eixo_x_input = st.text_input("Eixo X" if idioma == "Português" else "X Axis", textos["ciclabilidade_x"], key=f"eixo_x_{tag_tec}_{idioma}")
            eixo_y_input = st.text_input("Eixo Y" if idioma == "Português" else "Y Axis", textos["ciclabilidade_y"], key=f"eixo_y_{tag_tec}_{idioma}")
            rate_tag_input = st.text_input("Tag de Taxa" if idioma == "Português" else "Rate Tag", textos["ciclabilidade_rate"], key=f"rate_tag_{tag_tec}_{idioma}")

        elif tecnica_idx == 1:
            eixo_x_input = st.text_input("Eixo X" if idioma == "Português" else "X Axis", textos["cv_x"], key=f"eixo_x_{tag_tec}_{idioma}")
            eixo_y_input = st.text_input("Eixo Y" if idioma == "Português" else "Y Axis", textos["cv_y"], key=f"eixo_y_{tag_tec}_{idioma}")
            cv_speed_input = st.text_input("Velocidade / Scan rate", r"0.3\ \mathrm{mV\ s^{-1}}", key=f"cv_v_{tag_tec}_{idioma}")

        elif tecnica_idx == 2:
            eixo_x_input = st.text_input("Eixo X" if idioma == "Português" else "X Axis", textos["eie_x"], key=f"eixo_x_{tag_tec}_{idioma}")
            eixo_y_input = st.text_input("Eixo Y" if idioma == "Português" else "Y Axis", textos["eie_y"], key=f"eixo_y_{tag_tec}_{idioma}")
            circuito_upload = st.file_uploader(
                "Circuito Equivalente (PNG/JPG)" if idioma == "Português" else "Equivalent Circuit (PNG/JPG)",
                type=["png", "jpg", "jpeg"],
                key="circuit_uploader"
            )

        elif tecnica_idx == 3:
            eixo_x_input = st.text_input("Eixo X" if idioma == "Português" else "X Axis", textos["rate_x"], key=f"eixo_x_{tag_tec}_{idioma}")
            eixo_y_input = st.text_input("Eixo Y" if idioma == "Português" else "Y Axis", textos["rate_y"], key=f"eixo_y_{tag_tec}_{idioma}")

        elif tecnica_idx == 4:
            eixo_x_input = st.text_input("Eixo X" if idioma == "Português" else "X Axis", textos["bet_x"], key=f"eixo_x_{tag_tec}_{idioma}")
            eixo_y_input = st.text_input("Eixo Y" if idioma == "Português" else "Y Axis", textos["bet_y"], key=f"eixo_y_{tag_tec}_{idioma}")
            areas_bet_input = st.text_input(
                "Áreas BET (ex: Amostra1: 1200, Amostra2: 850)" if idioma == "Português" else "BET Areas (e.g. Sample1: 1200, Sample2: 850)",
                "",
                key="bet_areas_input"
            )
            exibir_inset_check = st.checkbox(
                "Exibir Inset (Zoom em baixos volumes)" if idioma == "Português" else "Show Inset (Zoom in low-pore vol)",
                False,
                key="bet_inset_check"
            )

    st.title(escolha_tecnica)

    # 8. Renderização do Gráfico
    if dados_bytes is not None:
        try:
            fig = None
            if tecnica_idx == 0:
                fig = gerar_plot_ciclabilidade(dados_bytes, rate_tag_input, eixo_x_input, eixo_y_input, mapa_cores_curvas)
            elif tecnica_idx == 1:
                fig = gerar_plot_cv(
                    dados_bytes, cv_speed_input, eixo_x_input, eixo_y_label=eixo_y_input,
                    tag_carga=textos["cv_charge"], tag_descarga=textos["cv_discharge"], mapa_cores=mapa_cores_curvas
                )
            elif tecnica_idx == 2:
                fig = gerar_plot_eie(dados_bytes, circuito_upload, eixo_x_input, eixo_y_input, mapa_cores_curvas)
            elif tecnica_idx == 3:
                fig = gerar_plot_rate(dados_bytes, eixo_x_input, eixo_y_label=eixo_y_input, mapa_cores=mapa_cores_curvas)
            elif tecnica_idx == 4:
                areas_dict = {}
                if areas_bet_input.strip():
                    for item in areas_bet_input.split(","):
                        if ":" in item:
                            k, v = item.split(":")
                            try:
                                areas_dict[k.strip()] = float(v.strip())
                            except ValueError:
                                pass
                titulo_legenda = textos["bet_legenda_area"] if areas_dict else textos["bet_legenda"]
                fig = gerar_plot_bet(
                    dados_bytes, eixo_x_input, eixo_y_input,
                    textos["bet_ads"], textos["bet_des"], titulo_legenda,
                    textos["bet_inset"], mapa_cores_curvas, areas_bet=areas_dict, exibir_inset=exibir_inset_check
                )

            if fig is not None:
                st.pyplot(fig)

                col1, col2 = st.columns(2)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

                buf_png = io.BytesIO()
                fig.savefig(buf_png, format="png", dpi=300, bbox_inches="tight")
                col1.download_button(
                    label="📥 Baixar PNG (300 DPI)" if idioma == "Português" else "📥 Download PNG (300 DPI)",
                    data=buf_png.getvalue(),
                    file_name=f"grafico_{timestamp}.png",
                    mime="image/png",
                )

                buf_svg = io.BytesIO()
                fig.savefig(buf_svg, format="svg", bbox_inches="tight")
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