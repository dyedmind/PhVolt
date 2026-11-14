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
        "cv_x_sc": r"$\mathbf{Potencial\ vs\ Ag/Ag^+\ (V)}$",
        "cv_y": r"$\mathbf{Corrente\ (mA)}$",
        "cv_charge": "Carga →",
        "cv_discharge": "← Descarga",
        "eie_x": r"$\mathbf{Z_{Real}\ (\Omega)}$",
        "eie_y": r"$\mathbf{-Z_{Im}\ (\Omega)}$",
        "bode_x": r"$\mathbf{Frequência\ (Hz)}$",
        "bode_y1": r"$\mathbf{|Z|\ (\Omega)}$",
        "bode_y2": r"$\mathbf{Fase\ (^\circ)}$",
        "gcd_x": r"$\mathbf{Capacidade\ Específica\ (mAh\ g^{-1})}$",
        "gcd_y": r"$\mathbf{Potencial\ vs\ Li/Li^+\ (V)}$",
        "rate_bat_x": r"$\mathbf{Número\ de\ Ciclos}$",
        "rate_bat_y": r"$\mathbf{Capacidade\ Específica\ (mAh\ g^{-1})}$",
        "cicl_x": r"$\mathbf{Número\ de\ Ciclos}$",
        "cicl_y": r"$\mathbf{Capacidade\ Específica\ (mAh\ g^{-1})}$",
        "cicl_rate": "Taxa: 0,5 C",
        "ce_x": r"$\mathbf{Número\ de\ Ciclos}$",
        "ce_y1": r"$\mathbf{Capacidade\ de\ Descarga\ (mAh\ g^{-1})}$",
        "ce_y2": r"$\mathbf{Eficiência\ Coulômbica\ (\%)}$",
        "sc_2e_x": r"$\mathbf{Tempo\ (s)}$",
        "sc_2e_y": r"$\mathbf{Potencial\ da\ Célula\ E_{cell}\ (V)}$",
        "sc_3e_x": r"$\mathbf{Tempo\ (s)}$",
        "sc_3e_y1": r"$\mathbf{Potencial\ da\ Célula\ E_{cell}\ (V)}$",
        "sc_3e_y2": r"$\mathbf{Potencial\ do\ Eletrodo\ E_{we},\ E_{ce}\ (V)}$",
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
        "cv_x_sc": r"$\mathbf{Potential\ vs\ Ag/Ag^+\ (V)}$",
        "cv_y": r"$\mathbf{Current\ (mA)}$",
        "cv_charge": "Charge →",
        "cv_discharge": "← Discharge",
        "eie_x": r"$\mathbf{Z_{Real}\ (\Omega)}$",
        "eie_y": r"$\mathbf{-Z_{Im}\ (\Omega)}$",
        "bode_x": r"$\mathbf{Frequency\ (Hz)}$",
        "bode_y1": r"$\mathbf{|Z|\ (\Omega)}$",
        "bode_y2": r"$\mathbf{Phase\ (^\circ)}$",
        "gcd_x": r"$\mathbf{Specific\ Capacity\ (mAh\ g^{-1})}$",
        "gcd_y": r"$\mathbf{Potential\ vs\ Li/Li^+\ (V)}$",
        "rate_bat_x": r"$\mathbf{Cycle\ Number}$",
        "rate_bat_y": r"$\mathbf{Specific\ Capacity\ (mAh\ g^{-1})}$",
        "cicl_x": r"$\mathbf{Cycle\ Number}$",
        "cicl_y": r"$\mathbf{Specific\ Capacity\ (mAh\ g^{-1})}$",
        "cicl_rate": "Rate: 0.5 C",
        "ce_x": r"$\mathbf{Cycle\ Number}$",
        "ce_y1": r"$\mathbf{Discharge\ Capacity\ (mAh\ g^{-1})}$",
        "ce_y2": r"$\mathbf{Coulombic\ Efficiency\ (\%)}$",
        "sc_2e_x": r"$\mathbf{Time\ (s)}$",
        "sc_2e_y": r"$\mathbf{Cell\ Potential\ E_{cell}\ (V)}$",
        "sc_3e_x": r"$\mathbf{Time\ (s)}$",
        "sc_3e_y1": r"$\mathbf{Cell\ Potential\ E_{cell}\ (V)}$",
        "sc_3e_y2": r"$\mathbf{Electrode\ Potential\ E_{we},\ E_{ce}\ (V)}$",
        "bet_x": r"$\mathbf{Relative\ Pressure\ (p/p_0)}$",
        "bet_y": r"$\mathbf{Quantity\ Adsorbed\ (cm^3\ g^{-1}\ STP)}$",
        "bet_ads": "Adsorption (closed)",
        "bet_des": "Desorption (open)",
        "bet_inset": "Low-pore volume region",
        "bet_legenda": r"$\mathbf{Sample}$",
        "bet_legenda_area": r"$\mathbf{Sample\ (S_{BET})}$",
    },
}


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
