from pathlib import Path
import re
import numpy as np
import pandas as pd
import streamlit as st

from .io_readers import (
    _ciclo_tem_carga_e_descarga,
    _encontrar_coluna_corrente,
    _ler_mpr_para_dataframe,
    _obter_potencial_celula_ou_ewe,
    _obter_serie_ciclos,
    _recortar_inicio_ativo_ciclo,
    extrair_ciclos_gcd,
    processar_cabecalho_e_dados,
)


def _trapz(y, x):
    fn = getattr(np, "trapezoid", getattr(np, "trapz", None))
    return float(fn(y, x))


def _extrair_velocidade_mvs(vel_str):
    if not vel_str:
        return None
    limpo = re.sub(r"\\mathrm\{.*?\}", "", str(vel_str))
    limpo = limpo.replace("\\", " ").replace("$", " ").strip()
    m = re.search(r"([-+]?\d+[.,]?\d*(?:[eE][-+]?\d+)?)", limpo)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", "."))
    except ValueError:
        return None


def _extrair_taxa_do_nome_arquivo(nome_str):
    if not nome_str:
        return None
    m_mv = re.search(r"(\d+(?:[.,]\d+)?)\s*m\s*v(?:\s*/?\s*s)?", nome_str, flags=re.IGNORECASE)
    if m_mv:
        try:
            return float(m_mv.group(1).replace(",", "."))
        except ValueError:
            pass
    m_vs = re.search(r"(\d+(?:[.,]\d+)?)\s*v\s*/?\s*s", nome_str, flags=re.IGNORECASE)
    if m_vs:
        try:
            return float(m_vs.group(1).replace(",", ".")) * 1000.0
        except ValueError:
            pass
    return None


def _extrair_densidade_do_nome(nome_str):
    """Tenta extrair densidade de corrente em A/g do nome da curva/arquivo (ex: '1 A/g', '0.5Ag', '2A_g')."""
    if not nome_str:
        return None
    m_ag = re.search(r"(\d+(?:[.,]\d+)?)\s*a\s*/?\s*g", nome_str, flags=re.IGNORECASE)
    if m_ag:
        try:
            return float(m_ag.group(1).replace(",", "."))
        except ValueError:
            pass
    m_mag = re.search(r"(\d+(?:[.,]\d+)?)\s*m\s*a\s*/?\s*g", nome_str, flags=re.IGNORECASE)
    if m_mag:
        try:
            return float(m_mag.group(1).replace(",", ".")) / 1000.0
        except ValueError:
            pass
    return None


def _estimar_f0_joelho(freq, fase):
    mask = np.isfinite(freq) & (freq > 0) & np.isfinite(fase)
    f_val = freq[mask]
    p_val = fase[mask]
    if len(f_val) < 2:
        return None

    alvo = 45.0 if np.nanmedian(p_val) > 0 else -45.0
    diff = p_val - alvo

    for i in range(len(diff) - 1):
        if diff[i] == 0:
            return float(f_val[i])
        if diff[i] * diff[i + 1] < 0:
            lf1, lf2 = np.log10(f_val[i]), np.log10(f_val[i + 1])
            frac = abs(diff[i]) / (abs(diff[i]) + abs(diff[i + 1]))
            return float(10 ** (lf1 + frac * (lf2 - lf1)))

    idx_min = int(np.argmin(np.abs(diff)))
    if abs(diff[idx_min]) <= 10.0:
        return float(f_val[idx_min])
    return None


def _separar_blocos_nan(arr_list):
    n = len(arr_list[0])
    mask_valid = np.ones(n, dtype=bool)
    for a in arr_list:
        mask_valid &= np.isfinite(a)

    blocos = []
    inicio = None
    for i in range(n):
        if mask_valid[i]:
            if inicio is None:
                inicio = i
        else:
            if inicio is not None:
                if i - inicio >= 3:
                    blocos.append(tuple(a[inicio:i] for a in arr_list))
                inicio = None
    if inicio is not None and (n - inicio) >= 3:
        blocos.append(tuple(a[inicio:n] for a in arr_list))
    return blocos


def _encontrar_indice_vi_descarga(t_dchg, v_sinal):
    """
    Localiza o índice exato do início da descarga efetiva (Vi_descarga) imediatamente após
    os passos sub-amostragem de inversão/queda ôhmica (onde dt << dt_amostragem normal).
    """
    n_pts = len(v_sinal)
    if n_pts < 4:
        return 1 if n_pts > 1 else 0

    dt = np.diff(t_dchg)
    dv = np.diff(v_sinal)
    taxas_queda = np.where(dt > 1e-7, -dv / np.maximum(dt, 1e-7), 0.0)

    i_ini_ref = max(1, int(len(taxas_queda) * 0.20))
    i_fim_ref = max(i_ini_ref + 2, int(len(taxas_queda) * 0.80))
    fatia_ref = taxas_queda[i_ini_ref:i_fim_ref] if i_fim_ref <= len(taxas_queda) else taxas_queda
    pos_ref = fatia_ref[fatia_ref > 0]
    taxa_rampa = float(np.nanmedian(pos_ref)) if len(pos_ref) > 0 else 0.0
    dt_amostragem = float(np.nanmedian(dt[i_ini_ref:i_fim_ref])) if i_fim_ref <= len(dt) else float(np.nanmedian(dt[dt > 0]))

    max_busca = min(max(4, int(len(taxas_queda) * 0.10)), 12, len(taxas_queda) - 1)

    # 1) Detecta transição sub-amostragem (dt < 0.5 * dt_amostragem, ex: passos de 0.2 ms e 0.8 ms antes da grade regular)
    idx_vi = 0
    while idx_vi < max_busca and dt[idx_vi] < (dt_amostragem * 0.5):
        idx_vi += 1

    if idx_vi > 0:
        return max(1, min(idx_vi, n_pts - 2))

    # 2) Fallback para arquivos sem sub-amostragem temporal:
    if taxa_rampa > 0:
        while idx_vi < max_busca and taxas_queda[idx_vi] < (taxa_rampa * 0.25):
            idx_vi += 1
        if idx_vi < max_busca and taxas_queda[idx_vi] > (taxa_rampa * 8.0):
            idx_vi += 1
            while idx_vi < max_busca and taxas_queda[idx_vi] > (taxa_rampa * 8.0):
                idx_vi += 1

    return max(1, min(idx_vi, n_pts - 2))


def _calcular_ir_drop_e_esr_transicao(t_chg, v_chg, t_dchg, v_dchg, i_chg_amp=None, i_dchg_amp=None):
    """
    Calcula o IR Drop (mV), a ESR (Ohm) e o índice de início efetivo da descarga (Vi_descarga):
    - IR_drop = V_max - Vi_descarga
    - ESR = IR_drop / (|I_chg| + |I_dchg|)
    """
    if len(v_dchg) < 4 or len(t_dchg) < 4:
        return 0.0, None, 0

    descida_normal = (float(v_dchg[0]) >= float(v_dchg[-1]))
    v_sinal = v_dchg if descida_normal else -v_dchg
    v_chg_sinal = (v_chg if descida_normal else -v_chg) if (v_chg is not None and len(v_chg) > 0) else np.array([])

    v_antes = float(np.nanmax(v_chg_sinal)) if len(v_chg_sinal) > 0 else float(v_sinal[0])
    v_topo = max(v_antes, float(np.nanmax(v_sinal[: min(5, len(v_sinal))])))

    idx_vi = _encontrar_indice_vi_descarga(t_dchg, v_sinal)
    vi_desc_sinal = float(v_sinal[idx_vi])

    ir_drop_v = max(0.0, v_topo - vi_desc_sinal)
    ir_drop_mv = ir_drop_v * 1000.0

    esr_ohm = None
    if i_dchg_amp is not None and i_dchg_amp > 1e-7:
        delta_i = (float(i_chg_amp) + float(i_dchg_amp)) if (i_chg_amp is not None and i_chg_amp > 1e-7) else (2.0 * float(i_dchg_amp))
        if delta_i > 0:
            esr_ohm = ir_drop_v / delta_i

    return ir_drop_mv, esr_ohm, idx_vi


def _calcular_metricas_cv(fonte_dados, mapa_nomes, massa_mg, eh_supercap, vel_str, taxas_por_curva=None):
    massa_g = max(float(massa_mg or 1.0), 1e-6) / 1000.0
    taxas_por_curva = taxas_por_curva or {}
    arquivos_mpr = st.session_state.get("arquivos_mpr_lista", [])
    mapa_ciclos_usuario = st.session_state.get("mpr_ciclos_por_amostra", {})

    # 1) Arquivos .mpr do EC-Lab: calcula taxa real \nu = |dE/dt| automaticamente
    if arquivos_mpr and arquivos_mpr[0]["nome"].lower().endswith(".mpr"):
        multi_arq = len(arquivos_mpr) > 1
        linhas = []
        for arq in arquivos_mpr:
            df_i = _ler_mpr_para_dataframe(arq["bytes"])
            nome_amostra = Path(arq["nome"]).stem
            c_i = [str(c) for c in df_i.columns]

            col_e = next((c for c in c_i if "Ewe" in c), None)
            col_cur = _encontrar_coluna_corrente(c_i)
            col_t = next((c for c in c_i if "time" in c.lower() and "step" not in c.lower()), None) or next((c for c in c_i if "time" in c.lower()), None)

            if not (col_e and col_cur):
                continue

            s_cic = _obter_serie_ciclos(df_i)
            ciclos_disp = sorted(int(x) for x in s_cic.dropna().unique())
            ciclos_alvo = mapa_ciclos_usuario.get(nome_amostra)
            if not ciclos_alvo:
                ciclos_alvo = [ciclos_disp[-1]] if ciclos_disp else [1]

            rotulo_base = mapa_nomes.get(nome_amostra, nome_amostra)

            for cid in ciclos_alvo:
                sub = df_i[s_cic == cid].dropna(subset=[col_e, col_cur])
                if len(sub) < 4:
                    continue

                e_v = sub[col_e].to_numpy(float)
                i_v = sub[col_cur].to_numpy(float)

                nu_vs = None
                if col_t and col_t in sub.columns:
                    t_v = sub[col_t].to_numpy(float)
                    dt = np.diff(t_v)
                    de = np.abs(np.diff(e_v))
                    mask_dt = dt > 1e-5
                    if np.any(mask_dt):
                        taxas_inst = de[mask_dt] / dt[mask_dt]
                        taxas_validas = taxas_inst[taxas_inst > 1e-6]
                        if len(taxas_validas) > 0:
                            nu_vs = float(np.nanmedian(taxas_validas))

                # Permite sobrescrever se o usuário digitou explicitamente uma taxa na sidebar
                taxa_user_mvs = taxas_por_curva.get(nome_amostra) or taxas_por_curva.get("__unica__")
                if taxa_user_mvs and taxa_user_mvs > 0 and nu_vs is None:
                    nu_vs = float(taxa_user_mvs) / 1000.0

                e_min, e_max = float(np.min(e_v)), float(np.max(e_v))
                delta_v = max(e_max - e_min, 1e-6)
                i_pa = float(np.max(i_v))
                i_pc = float(np.min(i_v))
                e_pa = float(e_v[int(np.argmax(i_v))])
                e_pc = float(e_v[int(np.argmin(i_v))])
                delta_ep_mv = abs(e_pa - e_pc) * 1000.0

                area_mav = abs(_trapz(i_v, e_v))
                area_av = area_mav / 1000.0

                nome_exib = (
                    f"{rotulo_base} (Ciclo {int(cid)})"
                    if (multi_arq and len(ciclos_alvo) > 1)
                    else (f"Ciclo {int(cid)}" if (not multi_arq and len(ciclos_alvo) > 1) else rotulo_base)
                )

                row = {
                    "Curva": nome_exib,
                    "Taxa Calculada (mV/s)": round(nu_vs * 1000.0, 2) if nu_vs else "—",
                    "Janela ΔE (V)": round(delta_v, 3),
                    "I_pa (mA)": round(i_pa, 4),
                    "I_pc (mA)": round(i_pc, 4),
                    "E_pa (V)": round(e_pa, 3),
                    "E_pc (V)": round(e_pc, 3),
                    "ΔE_p (mV)": round(delta_ep_mv, 1),
                    "Área ∫I dE (mA·V)": round(area_mav, 4),
                }
                if eh_supercap and nu_vs and nu_vs > 0:
                    c_sp = area_av / (2.0 * massa_g * nu_vs * delta_v)
                    row["C_sp CV (F/g)"] = round(c_sp, 2)
                linhas.append(row)

        return pd.DataFrame(linhas)

    # 2) Arquivos .txt / .dat / .csv: usa taxa discriminada por curva, taxa única informada ou inferência pelo nome
    df, tokens_limpos = processar_cabecalho_e_dados(fonte_dados)
    num_cols = df.shape[1]
    curvas = []

    if num_cols >= 2 and num_cols % 2 == 0:
        nomes_y = [tokens_limpos[k] for k in range(1, len(tokens_limpos), 2)] if len(tokens_limpos) >= 2 else tokens_limpos
        for idx, col in enumerate(range(0, num_cols, 2)):
            sub = df.iloc[:, [col, col + 1]].dropna(how="all")
            if len(sub) < 3:
                continue
            nome = str(nomes_y[idx]).strip() if idx < len(nomes_y) else f"Sample {idx + 1}"
            curvas.append((nome, sub.iloc[:, 0].to_numpy(float), sub.iloc[:, 1].to_numpy(float)))
    else:
        nomes_y = tokens_limpos[1:] if len(tokens_limpos) >= num_cols else tokens_limpos
        for col in range(1, num_cols):
            sub = df.iloc[:, [0, col]].dropna(how="all")
            if len(sub) < 3:
                continue
            nome = str(nomes_y[col - 1]).strip() if (col - 1) < len(nomes_y) else f"Sample {col}"
            curvas.append((nome, sub.iloc[:, 0].to_numpy(float), sub.iloc[:, 1].to_numpy(float)))

    vel_balao_mvs = _extrair_velocidade_mvs(vel_str)

    linhas = []
    for chave, e_arr, i_arr in curvas:
        rotulo = mapa_nomes.get(chave, chave)
        blocos = _separar_blocos_nan([e_arr, i_arr])
        if not blocos:
            continue

        taxa_curva_mvs = (
            taxas_por_curva.get(chave)
            or taxas_por_curva.get(rotulo)
            or taxas_por_curva.get("__unica__")
            or _extrair_taxa_do_nome_arquivo(rotulo)
            or _extrair_taxa_do_nome_arquivo(chave)
            or vel_balao_mvs
        )
        vel_vs = (float(taxa_curva_mvs) / 1000.0) if (taxa_curva_mvs and float(taxa_curva_mvs) > 0) else None

        for b_idx, (e_v, i_v) in enumerate(blocos):
            if len(e_v) < 4:
                continue
            nome_exib = f"{rotulo} (Ciclo {b_idx + 1})" if len(blocos) > 1 else rotulo

            e_min, e_max = float(np.min(e_v)), float(np.max(e_v))
            delta_v = max(e_max - e_min, 1e-6)
            i_pa = float(np.max(i_v))
            i_pc = float(np.min(i_v))
            e_pa = float(e_v[int(np.argmax(i_v))])
            e_pc = float(e_v[int(np.argmin(i_v))])
            delta_ep_mv = abs(e_pa - e_pc) * 1000.0

            area_mav = abs(_trapz(i_v, e_v))
            area_av = area_mav / 1000.0

            row = {
                "Curva": nome_exib,
                "Taxa (mV/s)": round(float(taxa_curva_mvs), 2) if taxa_curva_mvs else "—",
                "Janela ΔE (V)": round(delta_v, 3),
                "I_pa (mA)": round(i_pa, 4),
                "I_pc (mA)": round(i_pc, 4),
                "E_pa (V)": round(e_pa, 3),
                "E_pc (V)": round(e_pc, 3),
                "ΔE_p (mV)": round(delta_ep_mv, 1),
                "Área ∫I dE (mA·V)": round(area_mav, 4),
            }
            if eh_supercap and vel_vs is not None:
                c_sp = area_av / (2.0 * massa_g * vel_vs * delta_v)
                row["C_sp CV (F/g)"] = round(c_sp, 2)
            linhas.append(row)

    return pd.DataFrame(linhas)


def _calcular_metricas_eie_nyquist(fonte_dados, mapa_nomes):
    arquivos_mpr = st.session_state.get("arquivos_mpr_lista", [])
    mapa_ciclos_usuario = st.session_state.get("mpr_ciclos_por_amostra", {})

    if arquivos_mpr and arquivos_mpr[0]["nome"].lower().endswith(".mpr"):
        multi_arq = len(arquivos_mpr) > 1
        linhas = []
        for arq in arquivos_mpr:
            df_i = _ler_mpr_para_dataframe(arq["bytes"])
            nome_amostra = Path(arq["nome"]).stem
            c_i = [str(c) for c in df_i.columns]

            cx = next((c for c in c_i if "Re(Z)" in c), None)
            cy = next((c for c in c_i if "-Im(Z)" in c), None)
            cf = next((c for c in c_i if "freq" in c.lower()), None)
            cp = next((c for c in c_i if "phase" in c.lower()), None)
            if not (cx and cy):
                continue

            s_cic = _obter_serie_ciclos(df_i)
            ciclos_disp = sorted(int(x) for x in s_cic.dropna().unique())
            ciclos_alvo = mapa_ciclos_usuario.get(nome_amostra)
            if not ciclos_alvo:
                ciclos_alvo = [ciclos_disp[-1]] if ciclos_disp else [1]

            rotulo_base = mapa_nomes.get(nome_amostra, nome_amostra)

            for cid in ciclos_alvo:
                sub = df_i[s_cic == cid].dropna(subset=[cx, cy])
                if cf and cf in sub.columns:
                    sub = sub[sub[cf] > 0]
                if len(sub) < 3:
                    continue

                re_z = sub[cx].to_numpy(float)
                neg_im_z = sub[cy].to_numpy(float)
                f_arr = sub[cf].to_numpy(float) if (cf and cf in sub.columns) else None
                p_arr = sub[cp].to_numpy(float) if (cp and cp in sub.columns) else np.degrees(np.arctan2(-neg_im_z, re_z))

                if re_z[0] > re_z[-1]:
                    re_z = re_z[::-1]
                    neg_im_z = neg_im_z[::-1]

                pos_mask = neg_im_z >= 0
                rs = float(np.min(re_z[pos_mask])) if np.any(pos_mask) else float(re_z[0])

                n_hf = max(4, int(len(re_z) * 0.7))
                re_hf = re_z[:n_hf]
                im_hf = neg_im_z[:n_hf]
                idx_pico_semi = int(np.argmax(im_hf))
                r_ct = None
                if 0 < idx_pico_semi < len(im_hf) - 2:
                    idx_vale = idx_pico_semi + int(np.argmin(im_hf[idx_pico_semi:]))
                    if im_hf[idx_vale] < im_hf[idx_pico_semi] * 0.85:
                        r_ct = max(0.0, float(re_hf[idx_vale]) - rs)

                nome_exib = (
                    f"{rotulo_base} (Ciclo {int(cid)})"
                    if (multi_arq and len(ciclos_alvo) > 1)
                    else (f"Ciclo {int(cid)}" if (not multi_arq and len(ciclos_alvo) > 1) else rotulo_base)
                )

                row = {
                    "Curva": nome_exib,
                    "R_s / ESR (Ω)": round(rs, 3),
                    "R_ct estimado (Ω)": round(r_ct, 3) if r_ct is not None else "—",
                    "Z_Real máx (Ω)": round(float(np.max(re_z)), 2),
                    "-Z_Im máx (Ω)": round(float(np.max(neg_im_z)), 2),
                }
                if f_arr is not None:
                    f0_val = _estimar_f0_joelho(f_arr, p_arr)
                    if f0_val and f0_val > 0:
                        tau_ms = (1.0 / (2.0 * np.pi * f0_val)) * 1000.0
                        row["f₀ Joelho (Hz)"] = round(f0_val, 3)
                        row["τ₀ Relaxação (ms)"] = round(tau_ms, 2)
                linhas.append(row)

        return pd.DataFrame(linhas)

    df, tokens_limpos = processar_cabecalho_e_dados(fonte_dados)
    num_cols = df.shape[1]
    nomes_y = [tokens_limpos[k] for k in range(1, len(tokens_limpos), 2)] if len(tokens_limpos) >= 2 else tokens_limpos

    linhas = []
    for idx, col in enumerate(range(0, num_cols, 2)):
        if col + 1 >= num_cols:
            continue
        chave = str(nomes_y[idx]).strip() if idx < len(nomes_y) else f"Sample {idx + 1}"
        if chave.upper() in ["Y", "ZIM", "-ZIM", ""]:
            chave = f"Sample {idx + 1}"
        rotulo = mapa_nomes.get(chave, chave)

        sub = df.iloc[:, [col, col + 1]].dropna(how="all")
        if len(sub) < 3:
            continue

        re_raw = sub.iloc[:, 0].to_numpy(float)
        im_raw = sub.iloc[:, 1].to_numpy(float)

        valid_re = re_raw[np.isfinite(re_raw)]
        span_r = float(np.max(valid_re) - np.min(valid_re)) if len(valid_re) > 2 else 0.0
        re_sep, im_sep = [], []
        prev_r = None
        for rv, iv in zip(re_raw, im_raw):
            if not (np.isfinite(rv) and np.isfinite(iv)):
                re_sep.append(np.nan)
                im_sep.append(np.nan)
                prev_r = None
                continue
            if prev_r is not None and span_r > 0 and (rv - prev_r) < -(span_r * 0.15):
                re_sep.append(np.nan)
                im_sep.append(np.nan)
            re_sep.append(rv)
            im_sep.append(iv)
            prev_r = rv

        blocos = _separar_blocos_nan([np.array(re_sep), np.array(im_sep)])
        for b_idx, (re_z, neg_im_z) in enumerate(blocos):
            if len(re_z) < 3:
                continue
            if re_z[0] > re_z[-1]:
                re_z = re_z[::-1]
                neg_im_z = neg_im_z[::-1]

            pos_mask = neg_im_z >= 0
            rs = float(np.min(re_z[pos_mask])) if np.any(pos_mask) else float(re_z[0])

            n_hf = max(4, int(len(re_z) * 0.7))
            re_hf = re_z[:n_hf]
            im_hf = neg_im_z[:n_hf]
            idx_pico_semi = int(np.argmax(im_hf))
            r_ct = None
            if 0 < idx_pico_semi < len(im_hf) - 2:
                idx_vale = idx_pico_semi + int(np.argmin(im_hf[idx_pico_semi:]))
                if im_hf[idx_vale] < im_hf[idx_pico_semi] * 0.85:
                    r_ct = max(0.0, float(re_hf[idx_vale]) - rs)

            nome_exib = f"{rotulo} (Ciclo {b_idx + 1})" if len(blocos) > 1 else rotulo
            linhas.append({
                "Curva": nome_exib,
                "R_s / ESR (Ω)": round(rs, 3),
                "R_ct estimado (Ω)": round(r_ct, 3) if r_ct is not None else "—",
                "Z_Real máx (Ω)": round(float(np.max(re_z)), 2),
                "-Z_Im máx (Ω)": round(float(np.max(neg_im_z)), 2),
            })

    return pd.DataFrame(linhas)


def _calcular_metricas_bode(fonte_dados, mapa_nomes):
    df, tokens_limpos = processar_cabecalho_e_dados(fonte_dados)
    num_cols = df.shape[1]
    num_blocos = num_cols // 3
    linhas = []

    for b in range(num_blocos):
        c_z, c_f, c_p = b * 3, b * 3 + 1, b * 3 + 2
        sub = df.iloc[:, [c_z, c_f, c_p]].dropna(how="all")
        if len(sub) < 2:
            continue

        chave = str(tokens_limpos[c_p]).strip() if c_p < len(tokens_limpos) else f"Sample {b + 1}"
        if chave.upper() in ["FASE", "PHASE", "DEG", ""]:
            chave = f"Sample {b + 1}"
        rotulo = mapa_nomes.get(chave, chave)

        modz_raw = sub.iloc[:, 0].to_numpy(float)
        freq_raw = sub.iloc[:, 1].to_numpy(float)
        fase_raw = sub.iloc[:, 2].to_numpy(float)

        valid_f = freq_raw[np.isfinite(freq_raw) & (freq_raw > 0)]
        med_step = -0.1
        if len(valid_f) > 3:
            dl = np.diff(np.log10(valid_f))
            nz = dl[np.abs(dl) > 1e-4]
            if len(nz) > 0:
                med_step = float(np.nanmedian(nz))

        z_sep, f_sep, p_sep = [], [], []
        prev_f = None
        for zv, fv, pv in zip(modz_raw, freq_raw, fase_raw):
            if not (np.isfinite(zv) and np.isfinite(fv) and np.isfinite(pv) and fv > 0):
                z_sep.append(np.nan)
                f_sep.append(np.nan)
                p_sep.append(np.nan)
                prev_f = None
                continue
            if prev_f is not None:
                dlog = np.log10(fv) - np.log10(prev_f)
                if (dlog > 0.25 if med_step < 0 else dlog < -0.25):
                    z_sep.append(np.nan)
                    f_sep.append(np.nan)
                    p_sep.append(np.nan)
            z_sep.append(zv)
            f_sep.append(fv)
            p_sep.append(pv)
            prev_f = fv

        ciclos_bode = _separar_blocos_nan([np.array(z_sep), np.array(f_sep), np.array(p_sep)])
        for c_idx, (modz, freq, fase) in enumerate(ciclos_bode):
            if len(freq) < 2:
                continue
            nome_exib = f"{rotulo} (Ciclo {c_idx + 1})" if len(ciclos_bode) > 1 else rotulo
            idx_hf = int(np.argmax(freq))
            idx_lf = int(np.argmin(freq))
            f0 = _estimar_f0_joelho(freq, fase)
            tau_ms = (1.0 / (2.0 * np.pi * f0)) * 1000.0 if (f0 and f0 > 0) else None

            linhas.append({
                "Curva": nome_exib,
                "|Z| Alta Freq. (Ω)": round(float(modz[idx_hf]), 3),
                "|Z| Baixa Freq. (Ω)": round(float(modz[idx_lf]), 2),
                "Ângulo de Fase máx (°)": round(float(np.min(fase)) if np.nanmedian(fase) < 0 else float(np.max(fase)), 2),
                "f₀ Joelho -45° (Hz)": round(f0, 3) if f0 else "—",
                "τ₀ Relaxação (ms)": round(tau_ms, 2) if tau_ms else "—",
            })

    return pd.DataFrame(linhas)


def _calcular_metricas_gcd_bateria(fonte_dados, mapa_nomes, massa_mg):
    df, _ = processar_cabecalho_e_dados(fonte_dados)
    ciclos = extrair_ciclos_gcd(fonte_dados, df)
    linhas = []

    for c in ciclos:
        chave = c["nome"]
        rotulo = mapa_nomes.get(chave, chave)
        x_chg, y_chg = c["x_chg"], c["y_chg"]
        x_dchg, y_dchg = c["x_dchg"], c["y_dchg"]

        cap_chg = float(np.nanmax(x_chg) - np.nanmin(x_chg)) if len(x_chg) > 1 else 0.0
        cap_dchg = float(np.nanmax(x_dchg) - np.nanmin(x_dchg)) if len(x_dchg) > 1 else 0.0
        eficiencia = (cap_dchg / cap_chg * 100.0) if cap_chg > 1e-6 else np.nan

        t_dummy_chg = np.arange(len(y_chg), dtype=float)
        t_dummy_dchg = np.arange(len(y_dchg), dtype=float)
        ir_drop_mv, _, _ = _calcular_ir_drop_e_esr_transicao(t_dummy_chg, y_chg, t_dummy_dchg, y_dchg)

        v_med_dchg = np.nan
        energia_wh_kg = np.nan
        if len(x_dchg) > 1 and cap_dchg > 1e-6:
            ordem = np.argsort(x_dchg)
            q_ord = x_dchg[ordem]
            v_ord = y_dchg[ordem]
            energia_mwh_g = abs(_trapz(v_ord, q_ord))
            v_med_dchg = energia_mwh_g / cap_dchg
            energia_wh_kg = energia_mwh_g

        linhas.append({
            "Curva / Ciclo": rotulo,
            "Cap. Carga (mAh/g)": round(cap_chg, 2),
            "Cap. Descarga (mAh/g)": round(cap_dchg, 2),
            "Eficiência Coulômbica (%)": round(eficiencia, 2) if np.isfinite(eficiencia) else "—",
            "IR Drop (mV)": round(ir_drop_mv, 1),
            "Potencial Médio Desc. (V)": round(v_med_dchg, 3) if np.isfinite(v_med_dchg) else "—",
            "Energia Específica (Wh/kg)": round(energia_wh_kg, 2) if np.isfinite(energia_wh_kg) else "—",
        })

    return pd.DataFrame(linhas)


def _calcular_metricas_rate_bateria(fonte_dados, mapa_nomes):
    df, tokens_limpos = processar_cabecalho_e_dados(fonte_dados)
    if df.empty or df.shape[1] < 2:
        return pd.DataFrame()

    num_curvas = df.shape[1] - 1
    legendas = tokens_limpos[1:] if len(tokens_limpos) > num_curvas else tokens_limpos
    if len(legendas) < num_curvas:
        legendas = [f"Sample {i+1}" for i in range(num_curvas)]

    linhas = []
    for col_idx in range(num_curvas):
        chave = str(legendas[col_idx])
        rotulo = mapa_nomes.get(chave, chave)
        vals = df.iloc[:, col_idx + 1].to_numpy(float)
        vals = vals[np.isfinite(vals) & (vals > 0)]
        if len(vals) == 0:
            continue

        cap_ini = float(vals[0])
        cap_max = float(np.max(vals))
        cap_min = float(np.min(vals))
        cap_fin = float(vals[-1])
        ret_rate = (cap_min / cap_max * 100.0) if cap_max > 0 else 0.0
        recup = (cap_fin / cap_ini * 100.0) if cap_ini > 0 else 0.0

        linhas.append({
            "Amostra": rotulo,
            "Cap. Inicial (mAh/g)": round(cap_ini, 2),
            "Cap. Máxima (mAh/g)": round(cap_max, 2),
            "Cap. Alta Taxa / Mín. (mAh/g)": round(cap_min, 2),
            "Cap. Final / Retorno (mAh/g)": round(cap_fin, 2),
            "Retenção Alta Taxa (%)": round(ret_rate, 1),
            "Recuperação Final (%)": round(recup, 1),
        })

    return pd.DataFrame(linhas)


def _calcular_metricas_ciclabilidade(fonte_dados, mapa_nomes, tecnica_idx):
    df, tokens_limpos = processar_cabecalho_e_dados(fonte_dados)
    if df.empty:
        return pd.DataFrame()

    linhas = []
    if tecnica_idx == 5:
        sub = df.iloc[:, [0, 2, 3]].dropna() if df.shape[1] >= 4 else df.iloc[:, :3].dropna()
        if sub.empty:
            return pd.DataFrame()
        cic = sub.iloc[:, 0].to_numpy(float)
        cap = sub.iloc[:, 1].to_numpy(float)
        eff = sub.iloc[:, 2].to_numpy(float)
        ret = (cap[-1] / cap[0] * 100.0) if cap[0] > 0 else 0.0
        linhas.append({
            "Amostra": st.session_state.get("ce_nm", "Amostra"),
            "Ciclos Avaliados": int(len(cic)),
            "Cap. Inicial (mAh/g)": round(float(cap[0]), 2),
            "Cap. Final (mAh/g)": round(float(cap[-1]), 2),
            "Retenção (%)": round(float(ret), 1),
            "Eficiência Coulômbica Média (%)": round(float(np.mean(eff)), 2),
        })
        return pd.DataFrame(linhas)

    num_cols = df.shape[1]
    if num_cols >= 2 and num_cols % 2 == 0:
        nomes_y = [tokens_limpos[k] for k in range(1, len(tokens_limpos), 2)] if len(tokens_limpos) >= 2 else tokens_limpos
        pares = [(col, col + 1, nomes_y[idx] if idx < len(nomes_y) else f"Sample {idx+1}") for idx, col in enumerate(range(0, num_cols, 2))]
    else:
        nomes_y = tokens_limpos[1:] if len(tokens_limpos) >= num_cols else tokens_limpos
        pares = [(0, col, nomes_y[col - 1] if (col - 1) < len(nomes_y) else f"Sample {col}") for col in range(1, num_cols)]

    for cx, cy, chave in pares:
        sub = df.iloc[:, [cx, cy]].dropna()
        if sub.empty:
            continue
        rotulo = mapa_nomes.get(chave, chave)
        cic = sub.iloc[:, 0].to_numpy(float)
        cap = sub.iloc[:, 1].to_numpy(float)
        ret = (cap[-1] / cap[0] * 100.0) if cap[0] > 0 else 0.0
        linhas.append({
            "Amostra": rotulo,
            "Ciclo Final": int(cic[-1]),
            "Cap. Inicial (mAh/g)": round(float(cap[0]), 2),
            "Cap. Final (mAh/g)": round(float(cap[-1]), 2),
            "Retenção (%)": round(float(ret), 1),
        })

    return pd.DataFrame(linhas)


def _analisar_ramo_cgcd_individual(
    nome_ramo, t_chg, v_chg, t_dchg, v_dchg, i_dchg_amp, massa_g, eh_celula=True, i_chg_amp=None
):
    ir_drop_mv, esr_ohm, idx_vi = _calcular_ir_drop_e_esr_transicao(
        t_chg, v_chg, t_dchg, v_dchg, i_chg_amp=i_chg_amp, i_dchg_amp=i_dchg_amp
    )

    dt_chg = float(max(1e-6, t_chg[-1] - t_chg[0]))
    t_dchg_ef = t_dchg[idx_vi:] if idx_vi < len(t_dchg) - 1 else t_dchg
    v_dchg_ef = v_dchg[idx_vi:] if idx_vi < len(v_dchg) - 1 else v_dchg
    dt_dchg = float(max(1e-6, t_dchg_ef[-1] - t_dchg_ef[0]))

    descida_normal = (float(v_dchg[0]) >= float(v_dchg[-1]))
    v_max_obs = float(np.nanmax(np.concatenate([v_chg, v_dchg]))) if len(v_chg) > 0 else float(np.nanmax(v_dchg))
    vi_descarga = float(v_dchg_ef[0])
    v_fim = float(v_dchg_ef[-1])

    if descida_normal:
        v_ref_min = max(0.0, v_fim) if v_fim >= -0.02 else v_fim
        delta_v_efetivo = max(vi_descarga - v_ref_min, 1e-3)
        v_shift = np.maximum(0.0, v_dchg_ef - v_ref_min)
    else:
        delta_v_efetivo = max(abs(v_fim - vi_descarga), 1e-3)
        v_shift = np.maximum(0.0, v_fim - v_dchg_ef)

    int_v_dt = _trapz(v_shift, t_dchg_ef)
    c_sp_integral = (2.0 * i_dchg_amp * int_v_dt) / (massa_g * (delta_v_efetivo ** 2)) if (i_dchg_amp and i_dchg_amp > 0) else 0.0
    c_sp_linear = (i_dchg_amp * dt_dchg) / (massa_g * delta_v_efetivo) if (i_dchg_amp and i_dchg_amp > 0) else 0.0
    eficiencia = (dt_dchg / dt_chg) * 100.0 if dt_chg > 0 else 100.0
    densidade_ag = (i_dchg_amp / massa_g) if (i_dchg_amp and i_dchg_amp > 0) else 0.0

    row = {
        "Componente / Curva": nome_ramo,
        "Densidade I (A/g)": round(densidade_ag, 2) if densidade_ag > 0 else "—",
        "V_máx (V)": round(v_max_obs, 4),
        "Vi_descarga (V)": round(vi_descarga, 4),
        "t_descarga (s)": round(dt_dchg, 2),
        "IR Drop (mV)": round(ir_drop_mv, 1),
        "ESR (Ω)": round(esr_ohm, 2) if esr_ohm is not None else "—",
        "C_sp Integral (F/g)": round(c_sp_integral, 2) if c_sp_integral > 0 else "—",
        "C_sp Linear (F/g)": round(c_sp_linear, 2) if c_sp_linear > 0 else "—",
    }
    if eh_celula:
        energia_wh_kg = (i_dchg_amp * int_v_dt) / (3.6 * massa_g) if (i_dchg_amp and i_dchg_amp > 0) else 0.0
        potencia_w_kg = (energia_wh_kg * 3600.0) / dt_dchg if dt_dchg > 0 else 0.0
        row["Energia (Wh/kg)"] = round(energia_wh_kg, 4) if energia_wh_kg > 0 else "—"
        row["Potência (W/kg)"] = round(potencia_w_kg, 2) if potencia_w_kg > 0 else "—"
    row["Eficiência (%)"] = round(eficiencia, 2)
    return row


def _calcular_metricas_supercapacitor_cgcd(
    fonte_dados,
    mapa_nomes,
    massa_mg,
    tecnica_idx,
    massa_pos_mg=None,
    massa_neg_mg=None,
    densidades_por_curva=None,
):
    massa_celula_g = max(float(massa_mg or 1.0), 1e-6) / 1000.0
    massa_pos_g = max(float(massa_pos_mg if massa_pos_mg is not None else massa_mg or 1.0), 1e-6) / 1000.0
    massa_neg_g = max(float(massa_neg_mg if massa_neg_mg is not None else massa_mg or 1.0), 1e-6) / 1000.0
    densidades_por_curva = densidades_por_curva or {}

    arquivos_mpr = st.session_state.get("arquivos_mpr_lista", [])
    mapa_ciclos_usuario = st.session_state.get("mpr_ciclos_por_amostra", {})

    linhas = []

    # 1) Arquivos .mpr do EC-Lab
    if arquivos_mpr and arquivos_mpr[0]["nome"].lower().endswith(".mpr"):
        arqs_uso = [arquivos_mpr[0]] if tecnica_idx == 7 else arquivos_mpr
        multi_arq = len(arqs_uso) > 1

        for arq in arqs_uso:
            df_raw = _ler_mpr_para_dataframe(arq["bytes"])
            nome_amostra = Path(arq["nome"]).stem
            cols = [str(c) for c in df_raw.columns]

            col_t = next((c for c in cols if "time" in c.lower() and "step" not in c.lower()), None) or next((c for c in cols if "time" in c.lower()), None)
            col_i = _encontrar_coluna_corrente(cols)
            col_q = next((c for c in cols if "Q charge/discharge" in c or "(Q-Qo)" in c), None)
            col_ewe = next((c for c in cols if "Ewe" in c), None)
            col_ece = next((c for c in cols if "Ece" in c), None)
            v_celula = _obter_potencial_celula_ou_ewe(df_raw)
            if col_t is None or v_celula is None:
                continue

            df = df_raw.copy()
            df["_v_cell"] = v_celula
            df["_ciclo"] = _obter_serie_ciclos(df)
            ciclos_disp = sorted(int(x) for x in df["_ciclo"].dropna().unique())
            ciclos_completos = [c for c in ciclos_disp if _ciclo_tem_carga_e_descarga(df[df["_ciclo"] == c], "_v_cell")]

            ciclos_alvo = mapa_ciclos_usuario.get(nome_amostra)
            if not ciclos_alvo:
                ciclos_alvo = [ciclos_completos[-1]] if ciclos_completos else ([ciclos_disp[-1]] if ciclos_disp else [1])
            elif len(ciclos_alvo) == 1 and ciclos_alvo[0] == ciclos_disp[-1] and ciclos_completos and (ciclos_alvo[0] not in ciclos_completos):
                ciclos_alvo = [ciclos_completos[-1]]

            for cid in ciclos_alvo:
                sub = df[df["_ciclo"] == cid].dropna(subset=[col_t, "_v_cell"])
                if len(sub) < 4:
                    continue
                sub = _recortar_inicio_ativo_ciclo(sub, col_t, "_v_cell")
                if len(sub) < 4:
                    continue

                t = sub[col_t].to_numpy(float) - sub[col_t].to_numpy(float)[0]
                v_cell = sub["_v_cell"].to_numpy(float)
                idx_pico = int(np.argmax(v_cell))
                if idx_pico <= 0 or idx_pico >= len(v_cell) - 1:
                    continue

                t_chg, v_chg = t[: idx_pico + 1], v_cell[: idx_pico + 1]
                t_dchg, v_dchg = t[idx_pico:], v_cell[idx_pico:]
                dt_dchg = float(max(1e-6, t_dchg[-1] - t_dchg[0]))

                i_dchg_amp = 0.0
                i_chg_amp = 0.0
                if col_i and col_i in sub.columns:
                    i_c = np.abs(sub[col_i].iloc[: idx_pico + 1].to_numpy(float))
                    ic_at = i_c[i_c > 1e-6]
                    if len(ic_at) > 0:
                        i_chg_amp = float(np.median(ic_at)) / 1000.0

                    i_d = np.abs(sub[col_i].iloc[idx_pico:].to_numpy(float))
                    id_at = i_d[i_d > 1e-6]
                    if len(id_at) > 0:
                        i_dchg_amp = float(np.median(id_at)) / 1000.0

                if i_dchg_amp <= 1e-7 and col_q and col_q in sub.columns:
                    q_d = np.abs(sub[col_q].iloc[idx_pico:].to_numpy(float))
                    dq_mah = float(np.max(q_d) - np.min(q_d))
                    i_dchg_amp = (dq_mah * 3.6) / dt_dchg
                    if i_chg_amp <= 1e-7:
                        i_chg_amp = i_dchg_amp

                if tecnica_idx == 7 and col_ewe and col_ece and col_ewe in sub.columns and col_ece in sub.columns:
                    sufixo_cic = f" (Ciclo {int(cid)})" if len(ciclos_alvo) > 1 else ""
                    ewe_arr = sub[col_ewe].to_numpy(float)
                    ece_arr = sub[col_ece].to_numpy(float)

                    lbl_cell = mapa_nomes.get("Ecell", "Ecell (Célula)") + sufixo_cic
                    lbl_ewe = mapa_nomes.get("Ewe (Positivo)", "Ewe (Positivo)") + sufixo_cic
                    lbl_ece = mapa_nomes.get("Ece (Negativo)", "Ece (Negativo)") + sufixo_cic

                    linhas.append(_analisar_ramo_cgcd_individual(lbl_cell, t_chg, v_chg, t_dchg, v_dchg, i_dchg_amp, massa_celula_g, eh_celula=True, i_chg_amp=i_chg_amp))
                    linhas.append(_analisar_ramo_cgcd_individual(lbl_ewe, t_chg, ewe_arr[: idx_pico + 1], t_dchg, ewe_arr[idx_pico:], i_dchg_amp, massa_pos_g, eh_celula=False, i_chg_amp=i_chg_amp))
                    linhas.append(_analisar_ramo_cgcd_individual(lbl_ece, t_chg, ece_arr[: idx_pico + 1], t_dchg, ece_arr[idx_pico:], i_dchg_amp, massa_neg_g, eh_celula=False, i_chg_amp=i_chg_amp))
                else:
                    if multi_arq and len(ciclos_alvo) == 1:
                        chave = nome_amostra
                    elif multi_arq:
                        chave = f"{nome_amostra} (Ciclo {int(cid)})"
                    else:
                        chave = f"Ciclo {int(cid)}" if len(ciclos_alvo) > 1 else nome_amostra
                    rotulo = mapa_nomes.get(chave, chave)
                    linhas.append(_analisar_ramo_cgcd_individual(rotulo, t_chg, v_chg, t_dchg, v_dchg, i_dchg_amp, massa_celula_g, eh_celula=True, i_chg_amp=i_chg_amp))

        return pd.DataFrame(linhas)

    # 2) Arquivos .txt / .dat / .csv: obtém densidade de corrente informada (única ou discriminada por curva)
    df, tokens_limpos = processar_cabecalho_e_dados(fonte_dados)
    num_cols = df.shape[1]

    if tecnica_idx == 7 and num_cols >= 4:
        sub = df.iloc[:, :4].dropna()
        t = sub.iloc[:, 0].to_numpy(float)
        ecell = sub.iloc[:, 1].to_numpy(float)
        ewe = sub.iloc[:, 2].to_numpy(float)
        ece = sub.iloc[:, 3].to_numpy(float)
        idx_pico = int(np.argmax(ecell))

        j_ag = densidades_por_curva.get("__unica__") or _extrair_densidade_do_nome(st.session_state.get("nome_arquivo_anterior", ""))
        i_amp = (float(j_ag) * massa_celula_g) if (j_ag and float(j_ag) > 0) else 0.0

        if 0 < idx_pico < len(ecell) - 1:
            t_chg, t_dchg = t[: idx_pico + 1], t[idx_pico:]
            linhas.append(_analisar_ramo_cgcd_individual(mapa_nomes.get("Ecell", "Ecell (Célula)"), t_chg, ecell[: idx_pico + 1], t_dchg, ecell[idx_pico:], i_amp, massa_celula_g, eh_celula=True, i_chg_amp=i_amp))
            linhas.append(_analisar_ramo_cgcd_individual(mapa_nomes.get("Ewe (Positivo)", "Ewe (Positivo)"), t_chg, ewe[: idx_pico + 1], t_dchg, ewe[idx_pico:], i_amp, massa_pos_g, eh_celula=False, i_chg_amp=i_amp))
            linhas.append(_analisar_ramo_cgcd_individual(mapa_nomes.get("Ece (Negativo)", "Ece (Negativo)"), t_chg, ece[: idx_pico + 1], t_dchg, ece[idx_pico:], i_amp, massa_neg_g, eh_celula=False, i_chg_amp=i_amp))
        return pd.DataFrame(linhas)

    nomes_y = [tokens_limpos[k] for k in range(1, len(tokens_limpos), 2)] if len(tokens_limpos) >= 2 else tokens_limpos
    for idx, col in enumerate(range(0, num_cols, 2)):
        if col + 1 >= num_cols:
            continue
        sub = df.iloc[:, [col, col + 1]].dropna(how="all")
        if len(sub) < 4:
            continue
        chave = str(nomes_y[idx]).strip() if idx < len(nomes_y) else f"Janela {idx + 1}"
        rotulo = mapa_nomes.get(chave, chave)

        j_ag = (
            densidades_por_curva.get(chave)
            or densidades_por_curva.get(rotulo)
            or densidades_por_curva.get("__unica__")
            or _extrair_densidade_do_nome(rotulo)
            or _extrair_densidade_do_nome(chave)
        )
        i_amp = (float(j_ag) * massa_celula_g) if (j_ag and float(j_ag) > 0) else 0.0

        blocos = _separar_blocos_nan([sub.iloc[:, 0].to_numpy(float), sub.iloc[:, 1].to_numpy(float)])
        for b_idx, (t, v) in enumerate(blocos):
            idx_pico = int(np.argmax(v))
            if 0 < idx_pico < len(v) - 1:
                nome_exib = f"{rotulo} (Ciclo {b_idx + 1})" if len(blocos) > 1 else rotulo
                linhas.append(
                    _analisar_ramo_cgcd_individual(
                        nome_exib, t[: idx_pico + 1], v[: idx_pico + 1], t[idx_pico:], v[idx_pico:],
                        i_amp, massa_celula_g, eh_celula=True, i_chg_amp=i_amp
                    )
                )

    return pd.DataFrame(linhas)


def _calcular_metricas_bet(fonte_dados, mapa_nomes, areas_bet):
    df, tokens_limpos = processar_cabecalho_e_dados(fonte_dados)
    nomes_detectados = [tokens_limpos[k] for k in range(1, len(tokens_limpos), 2)] if len(tokens_limpos) >= 2 else tokens_limpos
    num_amostras = df.shape[1] // 2
    linhas = []

    for idx in range(num_amostras):
        col_x, col_y = idx * 2, idx * 2 + 1
        if col_y >= df.shape[1]:
            break
        chave = str(nomes_detectados[idx]).strip() if idx < len(nomes_detectados) else f"Sample {idx + 1}"
        rotulo = mapa_nomes.get(chave, chave)
        sub = df.iloc[:, [col_x, col_y]].dropna()
        if sub.empty:
            continue

        p_p0 = sub.iloc[:, 0].to_numpy(float)
        v_ads = sub.iloc[:, 1].to_numpy(float)
        v_max = float(np.max(v_ads))
        idx_99 = int(np.argmin(np.abs(p_p0 - 0.99)))
        v_poro_cm3_g = float(v_ads[idx_99]) * 0.0015468
        s_bet = areas_bet.get(chave) if areas_bet else None

        row = {
            "Amostra": rotulo,
            "Q_ads máx (cm³/g STP)": round(v_max, 2),
            "Vol. Total Poros (cm³/g)": round(v_poro_cm3_g, 4),
        }
        if s_bet and s_bet > 0:
            dp_nm = (4.0 * v_poro_cm3_g / s_bet) * 1000.0
            row["S_BET (m²/g)"] = round(float(s_bet), 1)
            row["Diâmetro Médio Poros (nm)"] = round(dp_nm, 2)
        linhas.append(row)

    return pd.DataFrame(linhas)


def calcular_resumo_parametros(
    fonte_dados,
    tecnica_idx,
    mapa_nomes=None,
    massa_mg=1.0,
    eh_supercap=False,
    params=None,
):
    mapa_nomes = mapa_nomes or {}
    params = params or {}

    try:
        if tecnica_idx == 0:
            return _calcular_metricas_cv(
                fonte_dados,
                mapa_nomes,
                massa_mg,
                eh_supercap,
                params.get("velocidade"),
                taxas_por_curva=params.get("taxas_por_curva"),
            )
        elif tecnica_idx == 1:
            return _calcular_metricas_eie_nyquist(fonte_dados, mapa_nomes)
        elif tecnica_idx == 2:
            return _calcular_metricas_gcd_bateria(fonte_dados, mapa_nomes, massa_mg)
        elif tecnica_idx == 3:
            return _calcular_metricas_rate_bateria(fonte_dados, mapa_nomes)
        elif tecnica_idx in [4, 5]:
            return _calcular_metricas_ciclabilidade(fonte_dados, mapa_nomes, tecnica_idx)
        elif tecnica_idx in [6, 7]:
            return _calcular_metricas_supercapacitor_cgcd(
                fonte_dados,
                mapa_nomes,
                massa_mg,
                tecnica_idx,
                massa_pos_mg=params.get("massa_pos_mg"),
                massa_neg_mg=params.get("massa_neg_mg"),
                densidades_por_curva=params.get("densidades_por_curva"),
            )
        elif tecnica_idx == 8:
            return _calcular_metricas_bet(fonte_dados, mapa_nomes, params.get("areas_bet"))
        elif tecnica_idx == 9:
            return _calcular_metricas_bode(fonte_dados, mapa_nomes)
    except Exception:
        return pd.DataFrame()

    return pd.DataFrame()
