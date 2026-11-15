from pathlib import Path
import re
from matplotlib.ticker import FixedFormatter, FixedLocator
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st

from core import (
    aplicar_ajustes_eixos_e_legenda,
    estilar_figura_e_eixos,
    processar_cabecalho_e_dados,
)
from core.io_readers import (
    _ciclo_tem_carga_e_descarga,
    _encontrar_coluna_corrente,
    _ler_mpr_para_dataframe,
    _obter_serie_ciclos,
)


def _formatar_taxa_limpa(nu_mvs, idioma="Português"):
    """Formata a velocidade de varredura (mV/s) de forma limpa (ex: 99.9849 -> 100)."""
    val = float(nu_mvs)
    if abs(val - round(val)) < 0.05 and val >= 1.0:
        texto = f"{int(round(val))}"
    else:
        texto = f"{val:.2f}".rstrip("0").rstrip(".")
    return texto.replace(".", ",") if idioma == "Português" else texto


def _extrair_taxa_mvs_nome(nome_str):
    if not nome_str:
        return None
    m_mv = re.search(r"(\d+(?:[.,]\d+)?)\s*m\s*v(?:\s*/?\s*s)?", str(nome_str), flags=re.IGNORECASE)
    if m_mv:
        try:
            return float(m_mv.group(1).replace(",", "."))
        except ValueError:
            pass
    m_vs = re.search(r"(\d+(?:[.,]\d+)?)\s*v\s*/?\s*s", str(nome_str), flags=re.IGNORECASE)
    if m_vs:
        try:
            return float(m_vs.group(1).replace(",", ".")) * 1000.0
        except ValueError:
            pass
    return None


def _coletar_voltamogramas_multi_taxa(fonte_dados, taxas_manuais=None):
    """
    Extrai e ordena os voltamogramas completos (E, I, nu_mvs, nome) de múltiplos arquivos .mpr
    ou de arquivos .txt/.dat/.csv multi-taxa.
    """
    taxas_manuais = taxas_manuais or {}
    arquivos_lista = st.session_state.get("arquivos_mpr_lista", [])
    mapa_ciclos_usuario = st.session_state.get("mpr_ciclos_por_amostra", {})
    voltamogramas = []

    if arquivos_lista and arquivos_lista[0]["nome"].lower().endswith(".mpr"):
        for idx, arq in enumerate(arquivos_lista):
            df_i = _ler_mpr_para_dataframe(arq["bytes"])
            nome_am = Path(arq["nome"]).stem
            c_i = [str(c) for c in df_i.columns]
            col_e = next((c for c in c_i if "Ewe" in c), None)
            col_cur = _encontrar_coluna_corrente(c_i)
            col_t = next((c for c in c_i if "time" in c.lower() and "step" not in c.lower()), None) or next((c for c in c_i if "time" in c.lower()), None)
            if not (col_e and col_cur):
                continue

            s_cic = _obter_serie_ciclos(df_i)
            ciclos_disp = sorted(int(x) for x in s_cic.dropna().unique())
            ciclos_completos = [
                c for c in ciclos_disp
                if _ciclo_tem_carga_e_descarga(df_i[s_cic == c], col_e)
            ]

            ciclos_alvo = mapa_ciclos_usuario.get(nome_am)
            if ciclos_alvo:
                cid_ref = ciclos_alvo[-1]
                if (
                    len(ciclos_alvo) == 1
                    and cid_ref == ciclos_disp[-1]
                    and ciclos_completos
                    and cid_ref not in ciclos_completos
                ):
                    cid_ref = ciclos_completos[-1]
            else:
                cid_ref = ciclos_completos[-1] if ciclos_completos else (ciclos_disp[-1] if ciclos_disp else 1)

            sub = df_i[s_cic == cid_ref].dropna(subset=[col_e, col_cur])
            if len(sub) < 8:
                continue

            e_arr = sub[col_e].to_numpy(float)
            i_arr = sub[col_cur].to_numpy(float)

            nu_mvs = taxas_manuais.get(nome_am) or taxas_manuais.get(f"curva_{idx}")
            if (nu_mvs is None or nu_mvs <= 0) and col_t and col_t in sub.columns:
                t_arr = sub[col_t].to_numpy(float)
                dt = np.diff(t_arr)
                de = np.abs(np.diff(e_arr))
                mask_dt = dt > 1e-5
                if np.any(mask_dt):
                    taxas_inst = (de[mask_dt] / dt[mask_dt]) * 1000.0
                    valid_t = taxas_inst[taxas_inst > 1e-4]
                    if len(valid_t) > 0:
                        nu_mvs = float(np.nanmedian(valid_t))
            if nu_mvs is None or nu_mvs <= 0:
                nu_mvs = _extrair_taxa_mvs_nome(nome_am)

            if nu_mvs and nu_mvs > 0:
                voltamogramas.append({
                    "nome": nome_am,
                    "nu_mvs": float(nu_mvs),
                    "E": e_arr,
                    "I": i_arr,
                })
    else:
        df, tokens_limpos = processar_cabecalho_e_dados(fonte_dados)
        num_cols = df.shape[1]
        if num_cols >= 2 and num_cols % 2 == 0:
            nomes_y = [tokens_limpos[k] for k in range(1, len(tokens_limpos), 2)] if len(tokens_limpos) >= 2 else tokens_limpos
            for idx, col in enumerate(range(0, num_cols, 2)):
                sub = df.iloc[:, [col, col + 1]].dropna()
                if len(sub) < 8:
                    continue
                nome_am = str(nomes_y[idx]).strip() if idx < len(nomes_y) else f"Scan {idx + 1}"
                nu_mvs = taxas_manuais.get(nome_am) or taxas_manuais.get(f"curva_{idx}") or _extrair_taxa_mvs_nome(nome_am)
                if nu_mvs and nu_mvs > 0:
                    voltamogramas.append({
                        "nome": nome_am,
                        "nu_mvs": float(nu_mvs),
                        "E": sub.iloc[:, 0].to_numpy(float),
                        "I": sub.iloc[:, 1].to_numpy(float),
                    })
        else:
            nomes_y = tokens_limpos[1:] if len(tokens_limpos) >= num_cols else tokens_limpos
            for idx, col in enumerate(range(1, num_cols)):
                sub = df.iloc[:, [0, col]].dropna()
                if len(sub) < 8:
                    continue
                nome_am = str(nomes_y[idx]).strip() if idx < len(nomes_y) else f"Scan {idx + 1}"
                nu_mvs = taxas_manuais.get(nome_am) or taxas_manuais.get(f"curva_{idx}") or _extrair_taxa_mvs_nome(nome_am)
                if nu_mvs and nu_mvs > 0:
                    voltamogramas.append({
                        "nome": nome_am,
                        "nu_mvs": float(nu_mvs),
                        "E": sub.iloc[:, 0].to_numpy(float),
                        "I": sub.iloc[:, 1].to_numpy(float),
                    })

    voltamogramas.sort(key=lambda item: item["nu_mvs"])
    unicos = []
    taxas_vistas = []
    for v in voltamogramas:
        if not any(abs(v["nu_mvs"] - tv) < 1e-4 for tv in taxas_vistas):
            unicos.append(v)
            taxas_vistas.append(v["nu_mvs"])
    return unicos


def _separar_ramos_anodico_catodico(e_arr, i_arr):
    """
    Detecta os vértices macroscópicos de inversão de potencial (E_min e E_max) ao longo
    da trajetória temporal do CV e extrai o segmento contínuo anódico (subida de E)
    e o segmento contínuo catódico (descida de E).
    """
    n = len(e_arr)
    if n < 8:
        return (np.array([]), np.array([])), (np.array([]), np.array([]))

    e_span = float(np.max(e_arr) - np.min(e_arr))
    if e_span < 1e-4:
        return (np.array([]), np.array([])), (np.array([]), np.array([]))

    win = min(5, max(1, (n // 40) | 1))
    if win > 1:
        pad = win // 2
        e_suave = np.convolve(np.pad(e_arr, (pad, pad), mode="edge"), np.ones(win) / win, mode="valid")
    else:
        e_suave = e_arr

    de_s = np.diff(e_suave)
    sinais = np.sign(de_s)
    for k in range(1, len(sinais)):
        if sinais[k] == 0:
            sinais[k] = sinais[k - 1]
    if sinais[0] == 0:
        nz = np.flatnonzero(sinais)
        if len(nz) > 0:
            sinais[: nz[0]] = sinais[nz[0]]

    mudancas = np.where(np.diff(sinais) != 0)[0] + 1
    vertices = np.unique(np.concatenate([[0], mudancas, [n - 1]]))

    vertices_macro = [int(vertices[0])]
    for idx_v in range(1, len(vertices)):
        v_cand = int(vertices[idx_v])
        if abs(float(e_arr[v_cand] - e_arr[vertices_macro[-1]])) >= (0.25 * e_span) or idx_v == len(vertices) - 1:
            vertices_macro.append(v_cand)

    melhor_anod = (np.array([]), np.array([]))
    melhor_cat = (np.array([]), np.array([]))
    span_anod_best = 0.0
    span_cat_best = 0.0

    for a, b in zip(vertices_macro[:-1], vertices_macro[1:]):
        if (b - a) < 4:
            continue
        e_seg = e_arr[a : b + 1]
        i_seg = i_arr[a : b + 1]
        delta_e = float(e_seg[-1] - e_seg[0])
        if delta_e > span_anod_best:
            span_anod_best = delta_e
            melhor_anod = (e_seg, i_seg)
        elif (-delta_e) > span_cat_best:
            span_cat_best = -delta_e
            melhor_cat = (e_seg, i_seg)

    def _limpar_e_ordenar(e_sub, i_sub):
        if len(e_sub) < 4:
            return np.array([]), np.array([])
        ord_idx = np.argsort(e_sub)
        e_s, i_s = e_sub[ord_idx], i_sub[ord_idx]
        e_u, inv = np.unique(np.round(e_s, 4), return_inverse=True)
        i_u = np.bincount(inv, weights=i_s) / np.bincount(inv)
        return e_u, i_u

    return _limpar_e_ordenar(*melhor_anod), _limpar_e_ordenar(*melhor_cat)


def _estimar_esr_pelos_cvs(vols):
    """
    Estima a resistência equivalente em série (ESR, em Ohm) diretamente a partir das curvas de CV:
    1) Rampa ôhmica pós-inversão nos vértices (|dE / dI| nos primeiros pontos após reversão nas taxas altas);
    2) Ajuste não-linear do modelo periódico RC nos picos: Ip(nu) = C * nu * tanh(dV / (2 * nu * R * C)).
    """
    if not vols:
        return 0.0

    nus_vs = np.array([v["nu_mvs"] / 1000.0 for v in vols], dtype=float)
    ipa_ma = np.array([max(abs(float(np.max(v["I"]))), 1e-6) for v in vols], dtype=float)
    ipc_ma = np.array([max(abs(float(np.min(v["I"]))), 1e-6) for v in vols], dtype=float)
    ip_med_amp = 0.5 * (ipa_ma + ipc_ma) / 1000.0

    e_spans = [float(np.max(v["E"]) - np.min(v["E"])) for v in vols]
    dv_janela = float(np.median(e_spans)) if e_spans else 1.0

    # 1) Inclinação pós-inversão nas curvas de maior taxa (onde o termo ôhmico domina)
    r_inversao_lista = []
    for v in vols[-min(2, len(vols)):]:
        e_arr, i_arr = v["E"], v["I"]
        idx_max = int(np.argmax(e_arr))
        idx_min = int(np.argmin(e_arr))
        for idx_v in [idx_max, idx_min]:
            if idx_v + 4 < len(e_arr):
                de_step = abs(float(e_arr[idx_v + 3] - e_arr[idx_v]))
                di_step = abs(float(i_arr[idx_v + 3] - i_arr[idx_v])) / 1000.0
                if di_step > 1e-5 and de_step > 1e-4:
                    r_inversao_lista.append(de_step / di_step)

    r_inversao = float(np.median(r_inversao_lista)) if r_inversao_lista else None

    # 2) Ajuste do modelo RC periódico Ip(nu) = C * nu * tanh(dV / (2 * nu * R * C)) via busca NumPy pura (sem SciPy)
    r_rc = None
    try:
        c_base = max(float(ip_med_amp[0] / max(nus_vs[0], 1e-5)), 1e-5)
        r_ref = r_inversao if (r_inversao is not None and r_inversao > 0) else 2.0
        c_grid = np.geomspace(c_base * 0.4, c_base * 3.0, 60)
        r_grid = np.concatenate([[0.0], np.geomspace(max(r_ref * 0.05, 1e-3), max(r_ref * 4.0, 100.0), 80)])

        # Vetoriza sobre (n_c, n_r, n_nu) para encontrar o mínimo erro quadrático relativo
        arg = np.clip(
            dv_janela / np.maximum(2.0 * nus_vs[None, None, :] * r_grid[None, :, None] * c_grid[:, None, None], 1e-9),
            1e-6,
            50.0,
        )
        ip_pred = c_grid[:, None, None] * nus_vs[None, None, :] * np.tanh(arg)
        erro = np.sum(((ip_pred - ip_med_amp[None, None, :]) / np.maximum(ip_med_amp[None, None, :], 1e-9)) ** 2, axis=2)
        idx_best = np.unravel_index(int(np.argmin(erro)), erro.shape)
        r_rc = float(r_grid[idx_best[1]])
    except Exception:
        r_rc = None

    if r_rc is not None and r_inversao is not None:
        # Combina ambos se forem consistentes; prioriza o ajuste RC limitado pela rampa de inversão
        return round(float(min(r_rc, r_inversao * 1.25)), 2)
    if r_rc is not None:
        return round(r_rc, 2)
    if r_inversao is not None:
        return round(r_inversao, 2)
    return 0.0


def analisar_cinetica_cv_dados(
    fonte_dados,
    taxas_manuais=None,
    taxa_alvo_dunn_mvs=None,
    n_pontos_grade=250,
    modo_esr="sem",
    valor_esr_ohm=0.0,
):
    """
    Executa a análise cinética completa em Voltametria Cíclica multi-taxa:
    1) Lei de Potência (b-value): i_p = a * nu^b  =>  log(|i_p|) = log(a) + b * log(nu)
    2) Método de Dunn: i(V) = k1(V) * nu + k2(V) * nu^(1/2)
       - Enforça restrição física de sinal nos ramos capacitivos:
         0 <= i_cap_an(V) <= max(0, i_tot_an(V)) e min(0, i_tot_ca(V)) <= i_cap_ca(V) <= 0.
       - Suporta compensação opcional de queda ôhmica E_corr = E - I * R_ESR.
    """
    vols = _coletar_voltamogramas_multi_taxa(fonte_dados, taxas_manuais=taxas_manuais)
    if len(vols) < 3:
        return None

    esr_usada_ohm = 0.0
    if modo_esr == "auto":
        esr_usada_ohm = _estimar_esr_pelos_cvs(vols)
    elif modo_esr == "manual" and valor_esr_ohm is not None and valor_esr_ohm > 0:
        esr_usada_ohm = float(valor_esr_ohm)

    nus_mvs = np.array([v["nu_mvs"] for v in vols], dtype=float)
    nus_vs = nus_mvs / 1000.0
    sqrt_nus = np.sqrt(nus_vs)

    ipa_list, ipc_list = [], []
    ramos_anod, ramos_cat = [], []
    vols_plot = []

    for v in vols:
        e_raw = v["E"]
        i_raw = v["I"]
        idx_max = int(np.argmax(i_raw))
        idx_min = int(np.argmin(i_raw))
        ipa_list.append(max(abs(float(i_raw[idx_max])), 1e-9))
        ipc_list.append(max(abs(float(i_raw[idx_min])), 1e-9))

        # Aplica compensação IR se solicitada: E_corr = E - (I_mA / 1000) * ESR
        e_eff = e_raw - (i_raw / 1000.0) * esr_usada_ohm if esr_usada_ohm > 0 else e_raw
        vols_plot.append({
            "nome": v["nome"],
            "nu_mvs": v["nu_mvs"],
            "E": e_eff,
            "I": i_raw,
        })

        (ea, ia), (ec, ic) = _separar_ramos_anodico_catodico(e_eff, i_raw)
        ramos_anod.append((ea, ia))
        ramos_cat.append((ec, ic))

    ipa_arr = np.array(ipa_list)
    ipc_arr = np.array(ipc_list)

    log_nu = np.log10(nus_vs)
    log_ipa = np.log10(ipa_arr)
    log_ipc = np.log10(ipc_arr)

    b_anod, log_a_anod = np.polyfit(log_nu, log_ipa, 1)
    r2_anod = float(np.corrcoef(log_nu, log_ipa)[0, 1] ** 2)

    b_cat, log_a_cat = np.polyfit(log_nu, log_ipc, 1)
    r2_cat = float(np.corrcoef(log_nu, log_ipc)[0, 1] ** 2)

    e_mins_an = [float(np.min(ea)) for ea, _ in ramos_anod if len(ea) > 4]
    e_maxs_an = [float(np.max(ea)) for ea, _ in ramos_anod if len(ea) > 4]
    e_mins_ca = [float(np.min(ec)) for ec, _ in ramos_cat if len(ec) > 4]
    e_maxs_ca = [float(np.max(ec)) for ec, _ in ramos_cat if len(ec) > 4]

    if (
        len(e_mins_an) != len(vols)
        or len(e_mins_ca) != len(vols)
        or not (e_mins_an and e_maxs_an and e_mins_ca and e_maxs_ca)
    ):
        return None

    e_lo = max(max(e_mins_an), max(e_mins_ca))
    e_hi = min(min(e_maxs_an), min(e_maxs_ca))
    if (e_hi - e_lo) < 0.02:
        return None

    n_pts = int(np.clip(n_pontos_grade, 100, 400))
    grid_e = np.linspace(e_lo, e_hi, n_pts)

    mat_i_an = np.vstack([np.interp(grid_e, ea, ia) for ea, ia in ramos_anod])
    mat_i_ca = np.vstack([np.interp(grid_e, ec, ic) for ec, ic in ramos_cat])

    def _resolver_k1_k2(mat_i):
        y_mat = mat_i / sqrt_nus[:, None]
        x_mean = float(np.mean(sqrt_nus))
        y_mean = np.mean(y_mat, axis=0)
        denom = float(np.sum((sqrt_nus - x_mean) ** 2))
        k1 = np.sum((sqrt_nus[:, None] - x_mean) * (y_mat - y_mean[None, :]), axis=0) / max(denom, 1e-12)
        k2 = y_mean - k1 * x_mean
        return k1, k2

    k1_an, _ = _resolver_k1_k2(mat_i_an)
    k1_ca, _ = _resolver_k1_k2(mat_i_ca)

    trapz_fn = getattr(np, "trapezoid", getattr(np, "trapz", None))
    linhas_dunn = []
    for idx_t, nu_mv in enumerate(nus_mvs):
        nu_v = nus_vs[idx_t]

        i_tot_an = mat_i_an[idx_t]
        i_tot_ca = mat_i_ca[idx_t]

        # Restrição física de sinal nos ramos capacitivos:
        # - No ramo anódico (corrente positiva): 0 <= i_cap_an <= max(0, i_tot_an)
        # - No ramo catódico (corrente negativa): min(0, i_tot_ca) <= i_cap_ca <= 0
        i_cap_an = np.clip(k1_an * nu_v, 0.0, np.maximum(0.0, i_tot_an))
        i_cap_ca = np.clip(k1_ca * nu_v, np.minimum(0.0, i_tot_ca), 0.0)

        area_tot = abs(float(trapz_fn(np.maximum(0.0, i_tot_an - i_tot_ca), grid_e)))
        area_cap = abs(float(trapz_fn(np.maximum(0.0, i_cap_an - i_cap_ca), grid_e)))
        frac_cap = float(np.clip((area_cap / max(area_tot, 1e-12)) * 100.0, 0.0, 100.0))
        frac_dif = 100.0 - frac_cap

        linhas_dunn.append({
            "Taxa (mV/s)": round(float(nu_mv), 2),
            "I_pa (mA)": round(float(ipa_arr[idx_t]), 4),
            "|I_pc| (mA)": round(float(ipc_arr[idx_t]), 4),
            "Capacitivo (%)": round(frac_cap, 1),
            "Difusional (%)": round(frac_dif, 1),
        })

    idx_alvo = len(nus_mvs) // 2
    if taxa_alvo_dunn_mvs is not None:
        idx_alvo = int(np.argmin(np.abs(nus_mvs - float(taxa_alvo_dunn_mvs))))

    nu_v_alvo = nus_vs[idx_alvo]
    i_tot_an_alvo = mat_i_an[idx_alvo]
    i_tot_ca_alvo = mat_i_ca[idx_alvo]
    i_cap_an_alvo = np.clip(k1_an * nu_v_alvo, 0.0, np.maximum(0.0, i_tot_an_alvo))
    i_cap_ca_alvo = np.clip(k1_ca * nu_v_alvo, np.minimum(0.0, i_tot_ca_alvo), 0.0)

    return {
        "vols": vols_plot,
        "nus_mvs": nus_mvs,
        "nus_vs": nus_vs,
        "ipa": ipa_arr,
        "ipc": ipc_arr,
        "b_anod": float(b_anod),
        "r2_anod": float(r2_anod),
        "log_a_anod": float(log_a_anod),
        "b_cat": float(b_cat),
        "r2_cat": float(r2_cat),
        "log_a_cat": float(log_a_cat),
        "grid_e": grid_e,
        "i_tot_an_alvo": i_tot_an_alvo,
        "i_cap_an_alvo": i_cap_an_alvo,
        "i_tot_ca_alvo": i_tot_ca_alvo,
        "i_cap_ca_alvo": i_cap_ca_alvo,
        "idx_alvo": idx_alvo,
        "esr_usada_ohm": float(esr_usada_ohm),
        "df_dunn": pd.DataFrame(linhas_dunn),
    }


def _construir_contorno_capacitivo_limpo(grid_e, i_cap_an, i_cap_ca):
    """
    Filtra o intervalo interno estrito onde existe separação positiva entre o ramo
    capacitivo superior e o inferior (i_cap_an > i_cap_ca), eliminando pontas nos vértices
    sem alterar os cálculos numéricos!
    """
    diff = i_cap_an - i_cap_ca
    valid = diff > 1e-4
    if np.sum(valid) < 6:
        return grid_e, i_cap_an, i_cap_ca

    indices = np.where(valid)[0]
    i_ini = int(indices[0])
    i_fim = int(indices[-1])

    e_sub = grid_e[i_ini : i_fim + 1].copy()
    an_sub = i_cap_an[i_ini : i_fim + 1].copy()
    ca_sub = i_cap_ca[i_ini : i_fim + 1].copy()

    if i_ini > 0:
        d0 = diff[i_ini - 1]
        d1 = diff[i_ini]
        if d0 <= 0 < d1 and (d1 - d0) > 1e-12:
            frac = -d0 / (d1 - d0)
            e_meet = grid_e[i_ini - 1] + frac * (grid_e[i_ini] - grid_e[i_ini - 1])
            i_meet = i_cap_an[i_ini - 1] + frac * (i_cap_an[i_ini] - i_cap_an[i_ini - 1])
            e_sub = np.concatenate([[e_meet], e_sub])
            an_sub = np.concatenate([[i_meet], an_sub])
            ca_sub = np.concatenate([[i_meet], ca_sub])

    if i_fim < len(grid_e) - 1:
        d0 = diff[i_fim]
        d1 = diff[i_fim + 1]
        if d0 > 0 >= d1 and (d0 - d1) > 1e-12:
            frac = d0 / (d0 - d1)
            e_meet = grid_e[i_fim] + frac * (grid_e[i_fim + 1] - grid_e[i_fim])
            i_meet = i_cap_an[i_fim] + frac * (i_cap_an[i_fim + 1] - i_cap_an[i_fim])
            e_sub = np.concatenate([e_sub, [e_meet]])
            an_sub = np.concatenate([an_sub, [i_meet]])
            ca_sub = np.concatenate([ca_sub, [i_meet]])

    return e_sub, an_sub, ca_sub


def gerar_plot_cinetica_cv(
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
    modo_grafico_cinetica="Decomposição de Dunn (Capacitivo vs. Difusional)",
    taxas_manuais=None,
    taxa_alvo_dunn_mvs=None,
    modo_esr="sem",
    valor_esr_ohm=0.0,
    legenda_horizontal=False,
):
    res = analisar_cinetica_cv_dados(
        fonte_dados,
        taxas_manuais=taxas_manuais,
        taxa_alvo_dunn_mvs=taxa_alvo_dunn_mvs,
        modo_esr=modo_esr,
        valor_esr_ohm=valor_esr_ohm,
    )
    if res is None:
        raise ValueError(
            "A Análise Cinética requer pelo menos 3 curvas de CV completas (ida e volta) em diferentes velocidades de varredura (mV/s)."
            if idioma == "Português"
            else "Kinetic Analysis requires at least 3 complete CV curves (anodic & cathodic sweeps) at different scan rates (mV/s)."
        )

    paleta_vals = list(mapa_cores.values()) if mapa_cores else ["#f97316", "#0284c7", "#10b981"]
    cor_primaria = paleta_vals[0]
    cor_secundaria = paleta_vals[1] if len(paleta_vals) > 1 else "#0284c7"

    # Modo 1: Lei de Potência (log(|i_p|) vs log(nu)) -> determinação do coeficiente b
    if "Potência" in modo_grafico_cinetica or "Power" in modo_grafico_cinetica or "b-value" in modo_grafico_cinetica:
        fig, ax = plt.subplots(figsize=(8.2, 5.2), dpi=300)
        log_nu = np.log10(res["nus_vs"])
        log_ipa = np.log10(res["ipa"])
        log_ipc = np.log10(res["ipc"])

        x_fit = np.linspace(float(np.min(log_nu)), float(np.max(log_nu)), 100)
        y_fit_an = res["b_anod"] * x_fit + res["log_a_anod"]
        y_fit_ca = res["b_cat"] * x_fit + res["log_a_cat"]

        lbl_an = (
            rf"Pico Anódico ($b = {res['b_anod']:.2f}$, $R^2 = {res['r2_anod']:.3f}$)"
            if idioma == "Português"
            else rf"Anodic Peak ($b = {res['b_anod']:.2f}$, $R^2 = {res['r2_anod']:.3f}$)"
        )
        lbl_ca = (
            rf"Pico Catódico ($b = {res['b_cat']:.2f}$, $R^2 = {res['r2_cat']:.3f}$)"
            if idioma == "Português"
            else rf"Cathodic Peak ($b = {res['b_cat']:.2f}$, $R^2 = {res['r2_cat']:.3f}$)"
        )

        ax.scatter(log_nu, log_ipa, color=cor_primaria, s=54, marker="o", edgecolors=tema["marker_edge"], linewidths=0.8, zorder=5, label=lbl_an)
        ax.plot(x_fit, y_fit_an, color=cor_primaria, linewidth=2.0, linestyle="-", zorder=4)

        ax.scatter(log_nu, log_ipc, color=cor_secundaria, s=54, marker="s", edgecolors=tema["marker_edge"], linewidths=0.8, zorder=5, label=lbl_ca)
        ax.plot(x_fit, y_fit_ca, color=cor_secundaria, linewidth=2.0, linestyle="--", zorder=4)

        ax.set_xlabel(r"$\mathbf{\log(\nu\ /\ V\ s^{-1})}$", fontsize=12.5, labelpad=8)
        ax.set_ylabel(r"$\mathbf{\log(|i_p|\ /\ mA)}$", fontsize=12.5, labelpad=8)
        ax.grid(True, linestyle=":", alpha=0.4, color=tema["grid"])

        aplicar_ajustes_eixos_e_legenda(ax, limites_manuais, posicao_legenda, tema, legenda_horizontal=legenda_horizontal)
        estilar_figura_e_eixos(fig, ax, tema, idioma=idioma)
        plt.tight_layout()
        return fig

    # Modo 2: Barras empilhadas de Contribuição Capacitiva vs. Difusional (%) por Taxa
    if "Barras" in modo_grafico_cinetica or "Bar" in modo_grafico_cinetica:
        fig, ax = plt.subplots(figsize=(8.4, 5.2), dpi=300)
        df_d = res["df_dunn"]
        x_pos = np.arange(len(df_d), dtype=float)
        cap_vals = df_d["Capacitivo (%)"].to_numpy(float)
        dif_vals = df_d["Difusional (%)"].to_numpy(float)
        labels_x = [_formatar_taxa_limpa(v, idioma=idioma) for v in df_d["Taxa (mV/s)"]]

        lbl_cap = "Capacitivo / Pseudocapacitivo (%)" if idioma == "Português" else "Capacitive / Pseudocapacitive (%)"
        lbl_dif = "Controlado por Difusão (%)" if idioma == "Português" else "Diffusion-Controlled (%)"

        ax.bar(x_pos, cap_vals, width=0.55, color=cor_primaria, edgecolor=tema["spine"], linewidth=0.9, label=lbl_cap, zorder=4)
        ax.bar(x_pos, dif_vals, width=0.55, bottom=cap_vals, color=cor_secundaria, edgecolor=tema["spine"], linewidth=0.9, label=lbl_dif, zorder=4)

        for idx_bar, (c_v, d_v) in enumerate(zip(cap_vals, dif_vals)):
            if c_v >= 10:
                txt_c = f"{c_v:.1f}%".replace(".", ",") if idioma == "Português" else f"{c_v:.1f}%"
                ax.text(idx_bar, c_v / 2.0, txt_c, ha="center", va="center", color="#ffffff", fontsize=9.0, fontweight="bold", zorder=6)
            if d_v >= 10:
                txt_d = f"{d_v:.1f}%".replace(".", ",") if idioma == "Português" else f"{d_v:.1f}%"
                ax.text(idx_bar, c_v + d_v / 2.0, txt_d, ha="center", va="center", color="#ffffff", fontsize=9.0, fontweight="bold", zorder=6)

        ax.set_xlabel(r"$\mathbf{Velocidade\ de\ Varredura\ (mV\ s^{-1})}$" if idioma == "Português" else r"$\mathbf{Scan\ Rate\ (mV\ s^{-1})}$", fontsize=12.5, labelpad=8)
        ax.set_ylabel(r"$\mathbf{Contribuição\ de\ Corrente\ (\%)}$" if idioma == "Português" else r"$\mathbf{Current\ Contribution\ (\%)}$", fontsize=12.5, labelpad=8)
        ax.set_ylim(0, 114)
        ax.grid(True, axis="y", linestyle=":", alpha=0.4, color=tema["grid"])

        aplicar_ajustes_eixos_e_legenda(ax, limites_manuais, posicao_legenda, tema, legenda_horizontal=legenda_horizontal)
        estilar_figura_e_eixos(fig, ax, tema, idioma=idioma)

        ax.xaxis.set_major_locator(FixedLocator(x_pos))
        ax.xaxis.set_major_formatter(FixedFormatter(labels_x))
        plt.tight_layout()
        return fig

    # Modo 3 (Padrão): Curva CV real completa + região capacitiva interna limpa (sem cruzamentos/bicos)
    fig, ax = plt.subplots(figsize=(8.4, 5.4), dpi=300)
    idx_alvo = res["idx_alvo"]
    vol_alvo = res["vols"][idx_alvo]
    nu_alvo = res["nus_mvs"][idx_alvo]
    frac_cap_alvo = float(res["df_dunn"].iloc[idx_alvo]["Capacitivo (%)"])
    esr_usada = res["esr_usada_ohm"]

    e_plot, i_cap_an_plot, i_cap_ca_plot = _construir_contorno_capacitivo_limpo(
        res["grid_e"],
        res["i_cap_an_alvo"],
        res["i_cap_ca_alvo"],
    )

    nu_txt = _formatar_taxa_limpa(nu_alvo, idioma=idioma)
    frac_txt = f"{frac_cap_alvo:.1f}".replace(".", ",") if idioma == "Português" else f"{frac_cap_alvo:.1f}"

    if esr_usada > 0:
        esr_txt = f"{esr_usada:g}".replace(".", ",") if idioma == "Português" else f"{esr_usada:g}"
        lbl_tot = (
            rf"Corrente Total ($\nu = {nu_txt}\ \mathrm{{mV\ s^{{-1}}}}$, $R_{{ESR}} = {esr_txt}\ \Omega$)"
            if idioma == "Português"
            else rf"Total Current ($\nu = {nu_txt}\ \mathrm{{mV\ s^{{-1}}}}$, $R_{{ESR}} = {esr_txt}\ \Omega$)"
        )
    else:
        lbl_tot = (
            rf"Corrente Total ($\nu = {nu_txt}\ \mathrm{{mV\ s^{{-1}}}}$)"
            if idioma == "Português"
            else rf"Total Current ($\nu = {nu_txt}\ \mathrm{{mV\ s^{{-1}}}}$)"
        )

    lbl_cap = (
        rf"Contribuição Capacitiva ({frac_txt}%)"
        if idioma == "Português"
        else rf"Capacitive Contribution ({frac_txt}%)"
    )

    ax.axhline(0, color=tema["ref_line"], linestyle="--", linewidth=1.0, alpha=0.65)
    ax.plot(vol_alvo["E"], vol_alvo["I"], color=cor_secundaria, linewidth=2.2, label=lbl_tot, zorder=4)

    ax.fill_between(e_plot, i_cap_ca_plot, i_cap_an_plot, facecolor=cor_primaria, alpha=0.32, edgecolor="none", zorder=3, label=lbl_cap)
    ax.plot(e_plot, i_cap_an_plot, color=cor_primaria, linewidth=1.6, linestyle="--", zorder=5)
    ax.plot(e_plot, i_cap_ca_plot, color=cor_primaria, linewidth=1.6, linestyle="--", zorder=5)

    ax.set_xlabel(eixo_x_label, fontsize=12.5, labelpad=8)
    ax.set_ylabel(eixo_y_label, fontsize=12.5, labelpad=8)
    ax.grid(True, linestyle=":", alpha=0.4, color=tema["grid"])

    aplicar_ajustes_eixos_e_legenda(ax, limites_manuais, posicao_legenda, tema, legenda_horizontal=legenda_horizontal)
    estilar_figura_e_eixos(fig, ax, tema, idioma=idioma)
    plt.tight_layout()
    return fig
