import gc
import os
from pathlib import Path
import re
import struct
import tempfile
from galvani import BioLogic
import numpy as np
import pandas as pd
import streamlit as st

# ==============================================================================
# CORREÇÃO DO BUG DO GALVANI PARA EC-LAB >= 11.50 (data_module version 10/11)
# ==============================================================================
for _cid_full, _spec in list(BioLogic.VMPdata_colID_dtype_map.items()):
    if _cid_full >= 256:
        _cid_low = _cid_full & 0xFF
        if _cid_low not in BioLogic.VMPdata_colID_dtype_map:
            BioLogic.VMPdata_colID_dtype_map[_cid_low] = _spec

BioLogic.VMPdata_colID_dtype_map.update({
    175: ("|Zwe-ce|/Ohm", "<f4"),
    176: ("Re(Zwe-ce)/Ohm", "<f4"),
    177: ("-Im(Zwe-ce)/Ohm", "<f4"),
    178: ("(Q-Qo)/C", "<f4"),
    182: ("step time/s", "<f8"),
    185: ("col_185", "<f4"),
    215: ("<Ece>/V", "<f4"),
})


def _fallback_mpr_v11(dados_bytes):
    """
    Fallback para arquivos .mpr (como GCPL/CGCD do EC-Lab v11+) onde o tamanho
    da linha no módulo VMP data difere em alguns bytes do esperado pelo galvani,
    causando 'buffer size must be a multiple of element size'.
    """
    mapa_bruto = dict(BioLogic.VMPdata_colID_dtype_map)
    mapa_conhecido = {}
    for cid, val in mapa_bruto.items():
        if isinstance(val, tuple) and len(val) == 2:
            a, b = str(val[0]), str(val[1])
            if a.startswith(("<", ">", "|", "u", "i", "f")) and len(a) <= 4:
                mapa_conhecido[cid] = (b, a)
            else:
                mapa_conhecido[cid] = (a, b)

    idx_mod = -1
    pos = 0
    while pos < len(dados_bytes):
        i = dados_bytes.find(b"MODULE", pos)
        if i == -1:
            break
        nome = dados_bytes[i + 6 : i + 16].decode("latin1", errors="ignore").strip()
        if "VMP data" in nome:
            idx_mod = i
            break
        pos = i + 6

    if idx_mod == -1:
        raise ValueError("Módulo 'VMP data' não encontrado no arquivo .mpr.")

    data_length = struct.unpack_from("<I", dados_bytes, idx_mod + 45)[0]
    inicio_vmp = idx_mod + 65
    fim_vmp = min(inicio_vmp + data_length, len(dados_bytes))

    n_pontos = struct.unpack_from("<I", dados_bytes, inicio_vmp)[0]
    n_cols = struct.unpack_from("<B", dados_bytes, inicio_vmp + 4)[0]

    inicio_ids = inicio_vmp + (6 if dados_bytes[inicio_vmp + 5] == 0 else 5)
    col_ids = list(struct.unpack_from(f"<{n_cols}H", dados_bytes, inicio_ids))
    fim_ids = inicio_ids + (2 * n_cols)

    offset_dados = None
    stride_linha = None
    candidatos_header = [1005, 1007, fim_ids - inicio_vmp, (fim_ids - inicio_vmp) + 1, (fim_ids - inicio_vmp) + 2]
    for h_cand in candidatos_header + list(range(fim_ids - inicio_vmp, min(data_length, 2048))):
        restante = data_length - h_cand
        if n_pontos > 0 and restante > 0 and (restante % n_pontos == 0):
            s = restante // n_pontos
            if n_cols <= s <= n_cols * 12:
                offset_dados = inicio_vmp + h_cand
                stride_linha = s
                break

    if offset_dados is None or stride_linha is None:
        raise ValueError("Não foi possível alinhar os registros binários do arquivo .mpr.")

    campos = []
    acumulado = 0
    for idx, cid in enumerate(col_ids):
        cid_lookup = cid if cid in mapa_conhecido else (cid & 0xFF)
        if cid_lookup in mapa_conhecido:
            nome, dt = mapa_conhecido[cid_lookup]
        else:
            nome, dt = f"unknown_{cid}_{idx}", "<f4"
        tam = np.dtype(dt).itemsize
        if acumulado + tam <= stride_linha:
            nome_unico = str(nome) if not any(c[0] == str(nome) for c in campos) else f"{nome}_{idx}"
            campos.append((nome_unico, dt))
            acumulado += tam
        else:
            break

    if acumulado < stride_linha:
        diff = stride_linha - acumulado
        campos.append(("_pad_end", "u1" if diff == 1 else f"V{diff}"))

    dt_final = np.dtype(campos)
    n_seguro = min(n_pontos, (fim_vmp - offset_dados) // dt_final.itemsize)
    buf = dados_bytes[offset_dados : offset_dados + (n_seguro * dt_final.itemsize)]
    arr = np.frombuffer(buf, dtype=dt_final, count=n_seguro)

    colunas_validas = {
        str(nome_col): arr[nome_col]
        for nome_col in arr.dtype.names
        if not nome_col.startswith("_pad") and arr[nome_col].dtype.kind in ("f", "i", "u")
    }
    df = pd.DataFrame(colunas_validas)
    return df.replace([np.inf, -np.inf], np.nan)


def _remover_repouso_inicial_mpr(df):
    """
    Remove APENAS pontos de repouso/OCV inicial antes de iniciar a análise,
    sem nunca cortar rampas de carga quando Q=0.
    """
    if df.empty or len(df) < 4:
        return df

    cols = [str(c) for c in df.columns]

    if any("Re(Z)" in c or "freq" in c.lower() for c in cols):
        return df

    col_mode = next((c for c in cols if c.lower() == "mode" or c.lower().startswith("mode_")), None)
    if col_mode is not None:
        modes = df[col_mode].to_numpy()
        idx_ativos = np.where((modes == 1) | (modes == 2))[0]
        if len(idx_ativos) > 0 and idx_ativos[0] > 0:
            df = df.iloc[idx_ativos[0]:].reset_index(drop=True)

    col_ewe = next((c for c in cols if "Ewe" in c), None)
    col_ece = next((c for c in cols if "Ece" in c), None)
    col_t = next((c for c in cols if "time" in c.lower() and "step" not in c.lower()), None) or next((c for c in cols if "time" in c.lower()), None)

    if col_ewe is not None and len(df) > 8:
        v = df[col_ewe].to_numpy(float)
        if col_ece is not None:
            ece = df[col_ece].to_numpy(float)
            if np.any(np.abs(ece[~np.isnan(ece)]) > 1e-5):
                v = v - ece
        v_span = np.nanmax(v) - np.nanmin(v)
        if v_span > 0.05:
            if col_t is not None:
                t = df[col_t].to_numpy(float)
                dt = np.diff(t)
                dv = np.abs(np.diff(v))
                # Taxa |dV/dt| (V/s): durante OCP inicial |dV/dt| é muito menor que durante a carga galvanostática
                taxa = np.where(dt > 1e-6, dv / np.maximum(dt, 1e-6), 0.0)
                taxa_ref = float(np.nanpercentile(taxa[taxa > 0], 75)) if np.any(taxa > 0) else 0.0
                if taxa_ref > 0 and taxa[0] < (taxa_ref * 0.25):
                    # Procura onde começa a rampa ativa sustentada (3 pontos consecutivos > 35% da taxa de carga)
                    ativos_taxa = np.where(taxa > (taxa_ref * 0.35))[0]
                    for cand in ativos_taxa:
                        if cand + 2 < len(taxa) and np.all(taxa[cand : cand + 3] > (taxa_ref * 0.35)):
                            if cand > 0:
                                df = df.iloc[cand:].reset_index(drop=True)
                            break
            else:
                dv = np.abs(np.diff(v))
                if dv[0] < (v_span * 0.0005):
                    idx_var = np.where(dv > (v_span * 0.0015))[0]
                    if len(idx_var) > 0 and idx_var[0] > 0:
                        df = df.iloc[idx_var[0]:].reset_index(drop=True)

    return df


def _ler_mpr_para_dataframe(dados_bytes):
    """
    Usa o leitor oficial BioLogic.MPRfile do galvani (com fallback para v11+)
    e remove qualquer tempo morto/OCV inicial antes do começo real do Ciclo 1.
    """
    fd, tmp_path = tempfile.mkstemp(suffix=".mpr")
    try:
        with os.fdopen(fd, "wb") as tmp:
            tmp.write(dados_bytes)

        for _ in range(15):
            try:
                mpr = BioLogic.MPRfile(tmp_path)
                df = pd.DataFrame(mpr.data).copy()
                del mpr
                gc.collect()
                df.columns = [str(c) for c in df.columns]
                df = df.replace([np.inf, -np.inf], np.nan)
                return _remover_repouso_inicial_mpr(df)
            except ValueError as err:
                msg = str(err)
                match = re.search(r"Column ID (\d+)", msg)
                if match:
                    cid = int(match.group(1))
                    BioLogic.VMPdata_colID_dtype_map[cid] = (f"unknown_col_{cid}", "<f4")
                elif "buffer size must be a multiple of element size" in msg:
                    return _remover_repouso_inicial_mpr(_fallback_mpr_v11(dados_bytes))
                else:
                    raise

        return _remover_repouso_inicial_mpr(_fallback_mpr_v11(dados_bytes))
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except PermissionError:
                pass


def _encontrar_coluna_corrente(cols):
    col_i = next((c for c in cols if "<I>" in c or c.startswith("I/") or c == "I"), None)
    if col_i:
        return col_i
    col_ctrl = next((c for c in cols if "control/V/mA" in c or "control/mA" in c), None)
    return col_ctrl


def _obter_potencial_celula_ou_ewe(df):
    cols = [str(c) for c in df.columns]
    col_ecell = next((c for c in cols if "ecell" in c.lower() or "ewe-ece" in c.lower()), None)
    if col_ecell:
        return df[col_ecell].to_numpy(float)

    col_ewe = next((c for c in cols if "Ewe" in c), None)
    col_ece = next((c for c in cols if "Ece" in c), None)
    if col_ewe and col_ece:
        ewe = df[col_ewe].to_numpy(float)
        ece = df[col_ece].to_numpy(float)
        if np.any(np.abs(ece[~np.isnan(ece)]) > 1e-5):
            return ewe - ece
        return ewe

    if col_ewe:
        return df[col_ewe].to_numpy(float)
    return None


def _ciclo_tem_carga_e_descarga(sub_df, col_v):
    if len(sub_df) < 5 or col_v not in sub_df.columns:
        return False
    v = sub_df[col_v].to_numpy(float)
    v = v[~np.isnan(v)]
    if len(v) < 5:
        return False
    v_max = float(np.max(v))
    v_min = float(np.min(v))
    span = v_max - v_min
    if span <= 0.02:
        return False
    idx_max = int(np.argmax(v))
    subida_antes_pico = v_max - float(np.min(v[: idx_max + 1]))
    descida_apos_pico = v_max - float(np.min(v[idx_max:]))
    return (subida_antes_pico >= 0.20 * span) and (descida_apos_pico >= 0.20 * span)


def _obter_serie_ciclos(df):
    cols = [str(c) for c in df.columns]

    col_f = next((c for c in cols if "freq" in c.lower()), None)
    col_rez = next((c for c in cols if "Re(Z)" in c), None)
    if col_f is not None and len(df) > 3:
        freq = df[col_f].to_numpy(float)
        mask_f = ~np.isnan(freq) & (freq > 0)
        if np.sum(mask_f) > 3:
            log_f = np.log10(np.maximum(freq, 1e-12))
            diffs = np.diff(log_f)
            med = np.nanmedian(diffs[diffs != 0]) if np.any(diffs != 0) else -1.0
            saltos = (diffs > 0.5) if med < 0 else (diffs < -0.5)
            if np.any(saltos):
                ciclos = np.concatenate([[1], 1 + np.cumsum(saltos)])
                return pd.Series(ciclos, index=df.index)

    col_cyc = next((c for c in cols if "cycle number" in c.lower()), None)
    col_hc = next((c for c in cols if "half cycle" in c.lower()), None)
    col_ewe = next((c for c in cols if "Ewe" in c), None)

    if col_hc is not None:
        s_hc = df[col_hc].ffill().bfill().round().astype(int).to_numpy()
        mudou_hc = np.concatenate([[0], (np.diff(s_hc) != 0).astype(int)])
        hc_monotonico = np.cumsum(mudou_hc)

        if np.max(hc_monotonico) >= 1:
            cand_par = (hc_monotonico // 2) + 1
            cand_impar = ((hc_monotonico + 1) // 2)

            if col_ewe is not None and len(df) > 6:
                ultimo_id_par = int(np.max(cand_par))
                sub_ult_par = df[cand_par == ultimo_id_par]
                if not _ciclo_tem_carga_e_descarga(sub_ult_par, col_ewe):
                    if col_cyc is not None:
                        s_c = df[col_cyc].ffill().bfill().round().astype(int).to_numpy()
                        mudou_c = np.concatenate([[0], (np.diff(s_c) != 0).astype(int)])
                        c_mono = 1 + np.cumsum(mudou_c)
                        if _ciclo_tem_carga_e_descarga(df[c_mono == int(np.max(c_mono))], col_ewe):
                            return pd.Series(c_mono, index=df.index)

                    ultimo_id_imp = int(np.max(cand_impar))
                    if _ciclo_tem_carga_e_descarga(df[cand_impar == ultimo_id_imp], col_ewe):
                        return pd.Series(cand_impar, index=df.index)

            return pd.Series(cand_par, index=df.index)

    if col_cyc is not None:
        s_c = df[col_cyc].ffill().bfill().round().astype(int).to_numpy()
        mudou_c = np.concatenate([[0], (np.diff(s_c) != 0).astype(int)])
        c_monotonico = 1 + np.cumsum(mudou_c)
        if np.max(c_monotonico) > 1:
            return pd.Series(c_monotonico, index=df.index)

    if col_rez is not None and len(df) > 4:
        rez = df[col_rez].to_numpy(float)
        span_r = np.nanmax(rez) - np.nanmin(rez)
        if span_r > 0:
            diffs_r = np.diff(rez)
            saltos_r = diffs_r < -(span_r * 0.35)
            if np.any(saltos_r):
                ciclos = np.concatenate([[1], 1 + np.cumsum(saltos_r)])
                return pd.Series(ciclos, index=df.index)

    return pd.Series(1, index=df.index)


def listar_ciclos_disponiveis_mpr(lista_arquivos_mpr):
    info = {}
    for arq in lista_arquivos_mpr:
        if not arq["nome"].lower().endswith(".mpr"):
            continue
        try:
            df_i = _ler_mpr_para_dataframe(arq["bytes"])
            s_cic = _obter_serie_ciclos(df_i)
            ciclos_unicos = sorted(int(x) for x in s_cic.dropna().unique())
            info[Path(arq["nome"]).stem] = ciclos_unicos if ciclos_unicos else [1]
        except Exception:
            info[Path(arq["nome"]).stem] = [1]
    return info


def _filtrar_e_quebrar_ciclos(df, s_ciclos, ciclos_escolhidos, col_x, col_y, quebrar_salto_x=False, col_freq=None):
    cols_ler = [col_x, col_y] + ([col_freq] if (col_freq and col_freq in df.columns) else [])
    df_work = df[cols_ler].copy()
    df_work["_cic"] = s_ciclos.values
    df_work = df_work.replace([np.inf, -np.inf], np.nan).dropna(subset=[col_x, col_y])

    if col_freq and col_freq in df_work.columns:
        df_work = df_work[df_work[col_freq] > 0]

    if ciclos_escolhidos:
        df_work = df_work[df_work["_cic"].isin(ciclos_escolhidos)]

    if df_work.empty:
        return pd.Series(dtype=float), pd.Series(dtype=float)

    cic_vals = df_work["_cic"].to_numpy()
    x_vals = df_work[col_x].to_numpy(float)
    y_vals = df_work[col_y].to_numpy(float)
    f_vals = df_work[col_freq].to_numpy(float) if (col_freq and col_freq in df_work.columns) else None

    span_x = np.nanmax(x_vals) - np.nanmin(x_vals) if len(x_vals) > 1 else 0.0
    span_y = np.nanmax(y_vals) - np.nanmin(y_vals) if len(y_vals) > 1 else 0.0
    diag_span = float(np.hypot(span_x, span_y))

    med_dlog_f = -0.1
    if f_vals is not None and len(f_vals) > 2:
        lf = np.log10(np.maximum(f_vals, 1e-12))
        dlf = np.diff(lf)
        nz = dlf[np.abs(dlf) > 1e-4]
        if len(nz) > 0:
            med_dlog_f = float(np.nanmedian(nz))

    # Passo mediano 2D para detectar retorno brusco entre ciclos consecutivos (Nyquist)
    dists_2d = np.hypot(np.diff(x_vals), np.diff(y_vals)) if len(x_vals) > 2 else np.array([])
    med_step_2d = float(np.nanmedian(dists_2d[dists_2d > 0])) if np.any(dists_2d > 0) else 0.0

    out_x, out_y = [], []
    for i in range(len(x_vals)):
        if i > 0:
            mudou_ciclo = (cic_vals[i] != cic_vals[i - 1])
            salto_retorno = False
            if f_vals is not None and f_vals[i] > 0 and f_vals[i - 1] > 0:
                dlog = np.log10(f_vals[i]) - np.log10(f_vals[i - 1])
                if (dlog > 0.25 if med_dlog_f < 0 else dlog < -0.25):
                    salto_retorno = True
            if quebrar_salto_x:
                dx = x_vals[i] - x_vals[i - 1]
                dy = y_vals[i] - y_vals[i - 1]
                dist_2d = float(np.hypot(dx, dy))
                if span_x > 0 and dx < -(span_x * 0.15):
                    salto_retorno = True
                elif span_y > 0 and dy < -(span_y * 0.25):
                    salto_retorno = True
                elif diag_span > 0 and med_step_2d > 0 and dist_2d > max(diag_span * 0.25, med_step_2d * 8.0):
                    salto_retorno = True
            if mudou_ciclo or salto_retorno:
                out_x.append(np.nan)
                out_y.append(np.nan)
        out_x.append(x_vals[i])
        out_y.append(y_vals[i])

    return pd.Series(out_x, name=col_x), pd.Series(out_y, name=col_y)


def _recortar_inicio_ativo_ciclo(sub_df, col_t, col_v):
    if len(sub_df) < 4:
        return sub_df

    cols = [str(c) for c in sub_df.columns]
    col_mode = next((c for c in cols if c.lower() == "mode" or c.lower().startswith("mode_")), None)
    if col_mode is not None:
        m = sub_df[col_mode].to_numpy()
        ativos = np.where((m == 1) | (m == 2))[0]
        if len(ativos) > 0 and ativos[0] > 0:
            sub_df = sub_df.iloc[ativos[0]:].copy()

    if len(sub_df) > 8 and col_v in sub_df.columns:
        v = sub_df[col_v].to_numpy(float)
        v_span = np.nanmax(v) - np.nanmin(v)
        if v_span > 0.05:
            if col_t and col_t in sub_df.columns:
                t = sub_df[col_t].to_numpy(float)
                dt = np.diff(t)
                dv = np.abs(np.diff(v))
                taxa = np.where(dt > 1e-6, dv / np.maximum(dt, 1e-6), 0.0)
                taxa_ref = float(np.nanpercentile(taxa[taxa > 0], 75)) if np.any(taxa > 0) else 0.0
                if taxa_ref > 0 and taxa[0] < (taxa_ref * 0.25):
                    ativos_taxa = np.where(taxa > (taxa_ref * 0.35))[0]
                    for cand in ativos_taxa:
                        if cand + 2 < len(taxa) and np.all(taxa[cand : cand + 3] > (taxa_ref * 0.35)):
                            if cand > 0:
                                sub_df = sub_df.iloc[cand:].copy()
                            break
            else:
                dv = np.abs(np.diff(v))
                if dv[0] < (v_span * 0.0005):
                    idx_subida = np.where(dv > (v_span * 0.0015))[0]
                    if len(idx_subida) > 0 and idx_subida[0] > 0:
                        sub_df = sub_df.iloc[idx_subida[0]:].copy()

    return sub_df


def _identificar_carga_descarga_grupo(grupo, col_ewe, col_i, col_hc, col_oxred):
    if col_i and col_i in grupo.columns:
        i_vals = grupo[col_i].to_numpy(float)
        if np.any(i_vals > 1e-6) and np.any(i_vals < -1e-6):
            chg = grupo[grupo[col_i] > 1e-6].copy()
            dchg = grupo[grupo[col_i] < -1e-6].copy()
            if not chg.empty and not dchg.empty:
                return chg, dchg

    if col_hc and col_hc in grupo.columns and grupo[col_hc].nunique() >= 2:
        hcs = sorted(grupo[col_hc].unique())
        g1 = grupo[grupo[col_hc] == hcs[0]].copy()
        g2 = grupo[grupo[col_hc] == hcs[1]].copy()
        if col_ewe and not g1.empty and not g2.empty:
            if (g1[col_ewe].iloc[-1] - g1[col_ewe].iloc[0]) >= (g2[col_ewe].iloc[-1] - g2[col_ewe].iloc[0]):
                return g1, g2
            return g2, g1

    if col_oxred and col_oxred in grupo.columns and grupo[col_oxred].nunique() > 1:
        chg = grupo[grupo[col_oxred] == 1].copy()
        dchg = grupo[grupo[col_oxred] == 0].copy()
        if not chg.empty and not dchg.empty:
            return chg, dchg

    if col_ewe and col_ewe in grupo.columns and len(grupo) > 2:
        v_arr = grupo[col_ewe].to_numpy(float)
        idx_pico = int(np.nanargmax(v_arr))
        if 0 < idx_pico < len(grupo) - 1:
            return grupo.iloc[: idx_pico + 1].copy(), grupo.iloc[idx_pico:].copy()

    return grupo.copy(), pd.DataFrame(columns=grupo.columns)


def _extrair_gcd_mpr_multi(lista_arquivos_mpr, massa_mg, mapa_ciclos_usuario=None):
    blocos_series = []
    ciclos_estruturados = []
    multi_arq = len(lista_arquivos_mpr) > 1
    massa_g = max(massa_mg, 1e-6) / 1000.0

    for arq in lista_arquivos_mpr:
        df_raw = _ler_mpr_para_dataframe(arq["bytes"])
        nome_amostra = Path(arq["nome"]).stem
        cols = [str(c) for c in df_raw.columns]

        col_ewe = next((c for c in cols if "Ewe" in c), None)
        col_i = _encontrar_coluna_corrente(cols)
        col_t = next((c for c in cols if "time" in c.lower() and "step" not in c.lower()), None) or next((c for c in cols if "time" in c.lower()), None)
        col_q = next((c for c in cols if "Q charge/discharge" in c or "(Q-Qo)" in c or "dq/" in c.lower()), None)
        col_hc = next((c for c in cols if "half cycle" in c.lower()), None)
        col_oxred = next((c for c in cols if "ox/red" in c.lower()), None)

        if not (col_ewe and col_t):
            continue

        df = df_raw.copy()
        df["_ciclo"] = _obter_serie_ciclos(df)
        ciclos_disp = sorted(int(x) for x in df["_ciclo"].dropna().unique())
        ciclos_alvo = (mapa_ciclos_usuario or {}).get(nome_amostra)
        if not ciclos_alvo:
            ciclos_completos = [c for c in ciclos_disp if _ciclo_tem_carga_e_descarga(df[df["_ciclo"] == c], col_ewe)]
            ciclos_alvo = [ciclos_completos[-1]] if ciclos_completos else ([ciclos_disp[-1]] if ciclos_disp else [1])

        for ciclo_id in ciclos_alvo:
            grupo = df[df["_ciclo"] == ciclo_id]
            if grupo.empty:
                continue
            grupo = _recortar_inicio_ativo_ciclo(grupo, col_t, col_ewe)

            chg, dchg = _identificar_carga_descarga_grupo(grupo, col_ewe, col_i, col_hc, col_oxred)
            if chg.empty and dchg.empty:
                continue

            if col_q and ("Q charge/discharge" in col_q or "(Q-Qo)" in col_q):
                cap_chg = np.abs(chg[col_q].to_numpy(float) - chg[col_q].to_numpy(float)[0]) / massa_g if not chg.empty else np.array([])
                cap_dchg = np.abs(dchg[col_q].to_numpy(float) - dchg[col_q].to_numpy(float)[0]) / massa_g if not dchg.empty else np.array([])
            elif col_i:
                dt_chg = np.diff(chg[col_t].to_numpy(float), prepend=chg[col_t].to_numpy(float)[0]) / 3600.0 if not chg.empty else np.array([])
                cap_chg = np.cumsum(np.abs(chg[col_i].to_numpy(float)) * dt_chg) / massa_g if not chg.empty else np.array([])
                dt_dchg = np.diff(dchg[col_t].to_numpy(float), prepend=dchg[col_t].to_numpy(float)[0]) / 3600.0 if not dchg.empty else np.array([])
                cap_dchg = np.cumsum(np.abs(dchg[col_i].to_numpy(float)) * dt_dchg) / massa_g if not dchg.empty else np.array([])
            else:
                cap_chg = (chg[col_t].to_numpy(float) - chg[col_t].to_numpy(float)[0]) if not chg.empty else np.array([])
                cap_dchg = (dchg[col_t].to_numpy(float) - dchg[col_t].to_numpy(float)[0]) if not dchg.empty else np.array([])

            v_chg = chg[col_ewe].to_numpy(float) if not chg.empty else np.array([])
            v_dchg = dchg[col_ewe].to_numpy(float) if not dchg.empty else np.array([])

            if multi_arq and len(ciclos_alvo) == 1:
                nome_curva = nome_amostra
            elif multi_arq:
                nome_curva = f"{nome_amostra} (Ciclo {int(ciclo_id)})"
            else:
                nome_curva = f"Ciclo {int(ciclo_id)}" if len(ciclos_alvo) > 1 else nome_amostra

            ciclos_estruturados.append({
                "nome": nome_curva,
                "x_chg": cap_chg,
                "y_chg": v_chg,
                "x_dchg": cap_dchg,
                "y_dchg": v_dchg,
            })

            blocos_series.extend([
                pd.Series(cap_chg, name=f"{nome_curva}_Cap_Chg"),
                pd.Series(v_chg, name=f"{nome_curva}_V_Chg"),
                pd.Series(cap_dchg, name=f"{nome_curva}_Cap_Dchg"),
                pd.Series(v_dchg, name=f"{nome_curva}_V_Dchg"),
            ])

    df_out = pd.concat(blocos_series, axis=1) if blocos_series else pd.DataFrame()
    return df_out, [str(c) for c in df_out.columns], ciclos_estruturados


def _calcular_capacidade_por_ciclo_mpr(df_raw, massa_mg):
    """
    Calcula a Capacidade Específica de Descarga (mAh/g) ciclo a ciclo para Rate Capability (Bateria),
    mantendo exatamente a ordem original da análise (sem reordenar).
    """
    cols = [str(c) for c in df_raw.columns]
    col_ewe = next((c for c in cols if "Ewe" in c), None)
    col_i = _encontrar_coluna_corrente(cols)
    col_t = next((c for c in cols if "time" in c.lower() and "step" not in c.lower()), None) or next((c for c in cols if "time" in c.lower()), None)
    col_q = next((c for c in cols if "Q charge/discharge" in c), None)
    col_qqo = next((c for c in cols if "(Q-Qo)" in c), None)
    col_dq = next((c for c in cols if "dq/" in c.lower()), None)
    col_hc = next((c for c in cols if "half cycle" in c.lower()), None)
    col_oxred = next((c for c in cols if "ox/red" in c.lower()), None)

    massa_g = max(massa_mg, 1e-6) / 1000.0
    df = df_raw.copy()
    df["_ciclo"] = _obter_serie_ciclos(df)

    resultados = []
    for ciclo_id, grupo in df.groupby("_ciclo", sort=True):
        if len(grupo) < 2:
            continue

        _, dchg = _identificar_carga_descarga_grupo(grupo, col_ewe, col_i, col_hc, col_oxred)
        if dchg.empty:
            dchg = grupo

        q_mAh = 0.0
        if col_q:
            q_vals = np.abs(dchg[col_q].to_numpy(float))
            q_mAh = float(np.nanmax(q_vals) - np.nanmin(q_vals)) if len(q_vals) > 1 else (float(q_vals[-1]) if len(q_vals) else 0.0)
            if q_mAh == 0 and len(q_vals) > 0:
                q_mAh = float(np.nanmax(np.abs(grupo[col_q].to_numpy(float))))
        elif col_qqo:
            q_vals = dchg[col_qqo].to_numpy(float)
            dq_raw = float(abs(q_vals[-1] - q_vals[0])) if len(q_vals) > 1 else 0.0
            q_mAh = dq_raw / 3.6 if ("/C" in col_qqo and "mA.h" not in col_qqo) else dq_raw
        elif col_dq:
            q_mAh = float(np.nansum(np.abs(dchg[col_dq].to_numpy(float))))
        elif col_i and col_t and len(dchg) > 1:
            dt_h = np.diff(dchg[col_t].to_numpy(float), prepend=dchg[col_t].to_numpy(float)[0]) / 3600.0
            q_mAh = float(np.nansum(np.abs(dchg[col_i].to_numpy(float)) * dt_h))

        val = q_mAh / massa_g
        if val > 0 and np.isfinite(val):
            resultados.append({"Ciclo": int(ciclo_id), "Valor": float(val)})

    df_res = pd.DataFrame(resultados)
    if not df_res.empty:
        df_res["Ciclo"] = np.arange(1, len(df_res) + 1, dtype=int)
    return df_res


def _consolidar_rate_mpr(lista_arquivos_mpr, massa_mg):
    """
    Consolida arquivos .mpr para Rate Capability (Bateria) preservando exatamente a ordem
    em que o ensaio foi executado (sem reordenar taxas).
    """
    dfs_extraidos = []
    for arq in lista_arquivos_mpr:
        df_i = _ler_mpr_para_dataframe(arq["bytes"])
        nome_amostra = Path(arq["nome"]).stem
        df_rate = _calcular_capacidade_por_ciclo_mpr(df_i, massa_mg)
        if not df_rate.empty:
            dfs_extraidos.append((nome_amostra, df_rate))

    if not dfs_extraidos:
        return pd.DataFrame(), []

    # Caso 1: Múltiplos arquivos onde cada arquivo é uma etapa/degrau da mesma amostra (<= 12 ciclos)
    max_ciclos_por_arq = max(len(df_r) for _, df_r in dfs_extraidos)
    if len(dfs_extraidos) >= 2 and max_ciclos_por_arq <= 12:
        valores_concat = []
        limites_etapas = []
        ciclo_acumulado = 0
        for _, df_r in dfs_extraidos:
            vals = df_r["Valor"].to_numpy(float)
            n_pts = len(vals)
            inicio = ciclo_acumulado + 0.5
            fim = ciclo_acumulado + n_pts + 0.5
            limites_etapas.append({"start": inicio, "end": fim, "mid": (inicio + fim) / 2.0})
            valores_concat.extend(vals)
            ciclo_acumulado += n_pts

        st.session_state["_rate_mpr_zonas_dinamicas"] = limites_etapas
        ciclos_seq = np.arange(1, len(valores_concat) + 1, dtype=int)
        nome_base = re.sub(r"[_-]?\d+[_-]?GCPL.*", "", dfs_extraidos[0][0], flags=re.IGNORECASE).strip("_- ")
        if not nome_base:
            nome_base = dfs_extraidos[0][0]
        df_out = pd.DataFrame({"Ciclo": ciclos_seq, nome_base: valores_concat})
        return df_out, ["Ciclo", nome_base]

    # Caso 2: Cada arquivo é uma amostra completa
    st.session_state.pop("_rate_mpr_zonas_dinamicas", None)
    series_pareadas = []
    tokens_pareados = []
    max_len = max(len(df_r) for _, df_r in dfs_extraidos)
    ciclos_base = pd.Series(np.arange(1, max_len + 1, dtype=int), name="Ciclo")
    series_pareadas.append(ciclos_base)
    tokens_pareados.append("Ciclo")

    for nome_amostra, df_r in dfs_extraidos:
        s_val = pd.Series(df_r["Valor"].to_numpy(float), name=nome_amostra)
        series_pareadas.append(s_val)
        tokens_pareados.append(nome_amostra)

    return pd.concat(series_pareadas, axis=1), tokens_pareados


def _extrair_ciclabilidade_mpr(df_raw, massa_mg):
    cols = [str(c) for c in df_raw.columns]
    col_ewe = next((c for c in cols if "Ewe" in c), None)
    col_i = _encontrar_coluna_corrente(cols)
    col_t = next((c for c in cols if "time" in c.lower() and "step" not in c.lower()), None) or next((c for c in cols if "time" in c.lower()), None)
    col_q = next((c for c in cols if "Q charge/discharge" in c or "(Q-Qo)" in c), None)
    col_hc = next((c for c in cols if "half cycle" in c.lower()), None)
    col_oxred = next((c for c in cols if "ox/red" in c.lower()), None)

    massa_g = max(massa_mg, 1e-6) / 1000.0
    df = df_raw.copy()
    df["_ciclo"] = _obter_serie_ciclos(df)

    registros = []
    for ciclo_id, grupo in df.groupby("_ciclo", sort=True):
        chg, dchg = _identificar_carga_descarga_grupo(grupo, col_ewe, col_i, col_hc, col_oxred)
        if dchg.empty:
            continue

        q_chg_total, q_dchg_total = 0.0, 0.0
        if col_q:
            if not chg.empty:
                q_c = np.abs(chg[col_q].to_numpy(float))
                q_chg_total = np.nanmax(q_c) - np.nanmin(q_c)
            q_d = np.abs(dchg[col_q].to_numpy(float))
            q_dchg_total = np.nanmax(q_d) - np.nanmin(q_d)
        elif col_i and col_t:
            if not chg.empty:
                dt_c = np.diff(chg[col_t].to_numpy(float), prepend=chg[col_t].to_numpy(float)[0]) / 3600.0
                q_chg_total = np.nansum(np.abs(chg[col_i].to_numpy(float)) * dt_c)
            dt_d = np.diff(dchg[col_t].to_numpy(float), prepend=dchg[col_t].to_numpy(float)[0]) / 3600.0
            q_dchg_total = np.nansum(np.abs(dchg[col_i].to_numpy(float)) * dt_d)

        cap_dchg_esp = q_dchg_total / massa_g
        eficiencia = (q_dchg_total / q_chg_total * 100.0) if q_chg_total > 0 else 100.0

        if eficiencia > 120.0 or cap_dchg_esp <= 0:
            continue

        registros.append({
            "Ciclo": int(ciclo_id),
            "Cap_Descarga": cap_dchg_esp,
            "Eficiencia": eficiencia,
        })

    df_out = pd.DataFrame(registros)
    return df_out, ["Ciclo", "Cap_Descarga", "Eficiencia"]


def _extrair_sc_2e_mpr_multi(lista_arquivos_mpr, mapa_ciclos_usuario=None):
    series_list = []
    tokens = []
    multi_arq = len(lista_arquivos_mpr) > 1

    for arq in lista_arquivos_mpr:
        df_raw = _ler_mpr_para_dataframe(arq["bytes"])
        nome_amostra = Path(arq["nome"]).stem
        cols = [str(c) for c in df_raw.columns]

        col_t = next((c for c in cols if "time" in c.lower() and "step" not in c.lower()), None) or next((c for c in cols if "time" in c.lower()), None)
        v_celula = _obter_potencial_celula_ou_ewe(df_raw)
        if col_t is None or v_celula is None:
            continue

        df = df_raw.copy()
        df["_ecell_calc"] = v_celula
        df["_ciclo"] = _obter_serie_ciclos(df)
        ciclos_disp = sorted(int(x) for x in df["_ciclo"].dropna().unique())

        ciclos_completos = [
            c for c in ciclos_disp
            if _ciclo_tem_carga_e_descarga(df[df["_ciclo"] == c], "_ecell_calc")
        ]

        ciclos_alvo = (mapa_ciclos_usuario or {}).get(nome_amostra)
        if not ciclos_alvo:
            ciclos_alvo = [ciclos_completos[-1]] if ciclos_completos else ([ciclos_disp[-1]] if ciclos_disp else [1])
        elif len(ciclos_alvo) == 1 and ciclos_alvo[0] == ciclos_disp[-1] and ciclos_completos and (ciclos_alvo[0] not in ciclos_completos):
            ciclos_alvo = [ciclos_completos[-1]]

        for cid in ciclos_alvo:
            sub = df[df["_ciclo"] == cid].dropna(subset=[col_t, "_ecell_calc"])
            if sub.empty:
                continue
            sub = _recortar_inicio_ativo_ciclo(sub, col_t, "_ecell_calc")
            if sub.empty:
                continue

            t_rel = sub[col_t].to_numpy(float) - sub[col_t].to_numpy(float)[0]
            v_cell = sub["_ecell_calc"].to_numpy(float)

            if multi_arq and len(ciclos_alvo) == 1:
                nome_curva = nome_amostra
            elif multi_arq:
                nome_curva = f"{nome_amostra} (Ciclo {int(cid)})"
            else:
                nome_curva = f"Ciclo {int(cid)}" if len(ciclos_alvo) > 1 else nome_amostra

            series_list.extend([
                pd.Series(t_rel, name=f"time_{nome_curva}"),
                pd.Series(v_cell, name=nome_curva),
            ])
            tokens.extend(["time/s", nome_curva])

    df_out = pd.concat(series_list, axis=1) if series_list else pd.DataFrame()
    return df_out, tokens


def _extrair_bode_mpr_multi(lista_arquivos_mpr, mapa_ciclos_usuario=None):
    """
    Extrai blocos de 3 colunas [|Z|/Ohm, freq/Hz, Phase(Z)/deg] por amostra/arquivo .mpr
    para a técnica EIE - Bode, inserindo NaN entre ciclos consecutivos para que o último ponto
    de um ciclo nunca se conecte ao primeiro ponto do próximo ciclo.
    """
    series_list = []
    tokens = []

    for arq in lista_arquivos_mpr:
        df_i = _ler_mpr_para_dataframe(arq["bytes"])
        nome_amostra = Path(arq["nome"]).stem
        c_i = [str(c) for c in df_i.columns]
        ciclos_amostra = (mapa_ciclos_usuario or {}).get(nome_amostra)

        col_f = next((c for c in c_i if "freq" in c.lower()), None)
        col_modz = next((c for c in c_i if "|Z|" in c), None)
        col_phase = next((c for c in c_i if "phase" in c.lower()), None)
        col_rez = next((c for c in c_i if "Re(Z)" in c), None)
        col_neg_imz = next((c for c in c_i if "-Im(Z)" in c), None)
        col_imz = next((c for c in c_i if "Im(Z)" in c and "-Im(Z)" not in c), None)

        if col_f is None:
            continue

        s_cic = _obter_serie_ciclos(df_i)
        if not ciclos_amostra:
            c_disp = sorted(int(x) for x in s_cic.dropna().unique())
            ciclos_amostra = [c_disp[-1]] if c_disp else [1]

        df_work = pd.DataFrame({"_cic": s_cic.values, "freq": df_i[col_f].to_numpy(float)})

        if col_modz is not None:
            df_work["modz"] = df_i[col_modz].to_numpy(float)
        elif col_rez is not None and (col_neg_imz is not None or col_imz is not None):
            rez = df_i[col_rez].to_numpy(float)
            imz = -df_i[col_neg_imz].to_numpy(float) if col_neg_imz else df_i[col_imz].to_numpy(float)
            df_work["modz"] = np.hypot(rez, imz)
        else:
            continue

        if col_phase is not None:
            df_work["phase"] = df_i[col_phase].to_numpy(float)
        elif col_rez is not None and (col_neg_imz is not None or col_imz is not None):
            rez = df_i[col_rez].to_numpy(float)
            imz = -df_i[col_neg_imz].to_numpy(float) if col_neg_imz else df_i[col_imz].to_numpy(float)
            df_work["phase"] = np.degrees(np.arctan2(imz, rez))
        else:
            df_work["phase"] = 0.0

        df_work = df_work.replace([np.inf, -np.inf], np.nan).dropna(subset=["freq", "modz", "phase"])
        df_work = df_work[df_work["freq"] > 0]
        df_work = df_work[df_work["_cic"].isin(ciclos_amostra)]

        if df_work.empty:
            continue

        cic_vals = df_work["_cic"].to_numpy()
        f_vals = df_work["freq"].to_numpy(float)
        z_vals = df_work["modz"].to_numpy(float)
        p_vals = df_work["phase"].to_numpy(float)

        log_f = np.log10(f_vals)
        med_step = float(np.nanmedian(np.diff(log_f)[np.diff(log_f) != 0])) if len(log_f) > 2 and np.any(np.diff(log_f) != 0) else -0.1

        f_out, z_out, p_out = [], [], []
        for i in range(len(f_vals)):
            if i > 0:
                mudou_cic = (cic_vals[i] != cic_vals[i - 1])
                dlog = log_f[i] - log_f[i - 1]
                # Se a varredura desce (alta -> baixa freq), um salto para cima indica novo ciclo;
                # Se a varredura sobe (baixa -> alta freq), um salto para baixo indica novo ciclo
                salto_freq = (dlog > 0.35) if med_step < 0 else (dlog < -0.35)
                if mudou_cic or salto_freq:
                    f_out.append(np.nan)
                    z_out.append(np.nan)
                    p_out.append(np.nan)
            f_out.append(f_vals[i])
            z_out.append(z_vals[i])
            p_out.append(p_vals[i])

        series_list.extend([
            pd.Series(z_out, name=f"|Z|_{nome_amostra}"),
            pd.Series(f_out, name=f"Freq_{nome_amostra}"),
            pd.Series(p_out, name=nome_amostra),
        ])
        tokens.extend(["|Z|/Ohm", "Freq/Hz", nome_amostra])

    df_out = pd.concat(series_list, axis=1) if series_list else pd.DataFrame()
    return df_out, tokens


def consolidar_arquivos_mpr(lista_arquivos_mpr, tecnica_idx, massa_mg=1.0):
    primeiro_arq = lista_arquivos_mpr[0]
    df_primeiro = _ler_mpr_para_dataframe(primeiro_arq["bytes"])
    cols = [str(c) for c in df_primeiro.columns]
    mapa_ciclos_usuario = st.session_state.get("mpr_ciclos_por_amostra", {})

    col_ewe = next((c for c in cols if "Ewe" in c), None)
    col_ece = next((c for c in cols if "Ece" in c), None)
    col_t = next((c for c in cols if "time" in c.lower() and "step" not in c.lower()), None) or next((c for c in cols if "time" in c.lower()), None)

    # (3) GCD Bateria (1 ou múltiplos arquivos .mpr)
    if tecnica_idx == 2:
        df_out, tokens, ciclos_mpr = _extrair_gcd_mpr_multi(lista_arquivos_mpr, massa_mg, mapa_ciclos_usuario)
        st.session_state["_ciclos_gcd_mpr_cache"] = ciclos_mpr
        return df_out, tokens

    # (4) Rate Capability (Bateria)
    if tecnica_idx == 3:
        df_rate_out, tokens_rate = _consolidar_rate_mpr(lista_arquivos_mpr, massa_mg)
        if not df_rate_out.empty:
            return df_rate_out, tokens_rate

    # (6) Ciclabilidade & Eficiência Individual (Bateria)
    if tecnica_idx == 5:
        return _extrair_ciclabilidade_mpr(df_primeiro, massa_mg)

    # (7) CGCD Supercapacitor (2 Eletrodos / Janelas - usa Ecell = Ewe - Ece)
    if tecnica_idx == 6:
        return _extrair_sc_2e_mpr_multi(lista_arquivos_mpr, mapa_ciclos_usuario)

    # (8) CGCD Supercapacitor (3 Eletrodos: Ecell, Ewe, Ece)
    if tecnica_idx == 7 and col_t and col_ewe and col_ece:
        nome_amostra = Path(primeiro_arq["nome"]).stem
        s_cic = _obter_serie_ciclos(df_primeiro)
        ciclos_disp = sorted(int(x) for x in s_cic.dropna().unique())
        ciclos_completos = [c for c in ciclos_disp if _ciclo_tem_carga_e_descarga(df_primeiro[s_cic == c], col_ewe)]

        ciclos_alvo = mapa_ciclos_usuario.get(nome_amostra)
        if not ciclos_alvo:
            ciclos_alvo = [ciclos_completos[-1]] if ciclos_completos else ([ciclos_disp[-1]] if ciclos_disp else [1])
        elif len(ciclos_alvo) == 1 and ciclos_alvo[0] == ciclos_disp[-1] and ciclos_completos and (ciclos_alvo[0] not in ciclos_completos):
            ciclos_alvo = [ciclos_completos[-1]]

        df_sub = df_primeiro[s_cic.isin(ciclos_alvo)].copy()
        if df_sub.empty:
            df_sub = df_primeiro.copy()
        df_sub = _recortar_inicio_ativo_ciclo(df_sub, col_t, col_ewe)

        t_vals = df_sub[col_t].to_numpy(float)
        if len(t_vals) > 0:
            t_vals = t_vals - t_vals[0]

        df_out = pd.DataFrame({
            "time": t_vals,
            "Ecell": df_sub[col_ewe].to_numpy(float) - df_sub[col_ece].to_numpy(float),
            "Ewe": df_sub[col_ewe].to_numpy(float),
            "Ece": df_sub[col_ece].to_numpy(float),
        }).dropna()
        return df_out, ["time/s", "Ecell/V", "Ewe/V", "Ece/V"]

    # (10) EIE - Bode (|Z|, Freq, Fase)
    if tecnica_idx == 9:
        df_bode, tokens_bode = _extrair_bode_mpr_multi(lista_arquivos_mpr, mapa_ciclos_usuario)
        if not df_bode.empty:
            return df_bode, tokens_bode

    series_pareadas = []
    tokens_pareados = []

    for arq in lista_arquivos_mpr:
        df_i = _ler_mpr_para_dataframe(arq["bytes"])
        nome_amostra = Path(arq["nome"]).stem
        c_i = [str(c) for c in df_i.columns]
        ciclos_amostra = mapa_ciclos_usuario.get(nome_amostra)

        if tecnica_idx == 0:
            cx = next((c for c in c_i if "Ewe" in c), None)
            cy = _encontrar_coluna_corrente(c_i)
            if cx and cy:
                s_cic = _obter_serie_ciclos(df_i)
                if not ciclos_amostra:
                    c_disp = sorted(int(x) for x in s_cic.dropna().unique())
                    ciclos_amostra = [c_disp[-1]] if c_disp else [1]
                sx, sy = _filtrar_e_quebrar_ciclos(df_i, s_cic, ciclos_amostra, cx, cy, quebrar_salto_x=False)
                if not sx.empty:
                    series_pareadas.extend([sx, sy])
                    tokens_pareados.extend([cx, nome_amostra])

        elif tecnica_idx == 1:
            cx = next((c for c in c_i if "Re(Z)" in c), None)
            cy = next((c for c in c_i if "-Im(Z)" in c), None)
            if cx and cy:
                s_cic = _obter_serie_ciclos(df_i)
                if not ciclos_amostra:
                    c_disp = sorted(int(x) for x in s_cic.dropna().unique())
                    ciclos_amostra = [c_disp[-1]] if c_disp else [1]
                sx, sy = _filtrar_e_quebrar_ciclos(df_i, s_cic, ciclos_amostra, cx, cy, quebrar_salto_x=True)
                if not sx.empty:
                    series_pareadas.extend([sx, sy])
                    tokens_pareados.extend([cx, nome_amostra])

        elif tecnica_idx == 4:
            df_cic = _calcular_capacidade_por_ciclo_mpr(df_i, massa_mg)
            if not df_cic.empty:
                series_pareadas.extend([df_cic["Ciclo"], df_cic["Valor"]])
                tokens_pareados.extend(["Ciclo", nome_amostra])

    if series_pareadas:
        return pd.concat(series_pareadas, axis=1), tokens_pareados

    raise ValueError("Não foi possível extrair a curva para esta técnica a partir do arquivo .mpr selecionado.")


def exportar_txt_compativel_mpr(lista_arquivos_mpr, tecnica_idx, massa_mg=1.0, idioma="Português"):
    """
    Gera o conteúdo de um arquivo .txt delimitado por tabulação (padrão Origin/PhVolt)
    contendo exatamente as curvas extraídas para a técnica selecionada a partir dos arquivos .mpr.
    """
    df_out, tokens = consolidar_arquivos_mpr(lista_arquivos_mpr, tecnica_idx, massa_mg)
    if df_out.empty:
        raise ValueError("Não há dados extraídos para exportar.")

    num_cols = df_out.shape[1]
    if len(tokens) == num_cols:
        cabecalho = [str(t) for t in tokens]
    else:
        cabecalho = [str(c) for c in df_out.columns]

    linhas_txt = ["\t".join(cabecalho)]

    # Formata linha a linha com tabulação, deixando células vazias onde houver NaN (separador de ciclos ou tamanhos diferentes)
    matriz = df_out.to_numpy(dtype=float)
    for row in matriz:
        celulas = []
        for val in row:
            if np.isnan(val) or np.isinf(val):
                celulas.append("")
            else:
                s_num = f"{val:.8g}"
                if idioma == "Português":
                    s_num = s_num.replace(".", ",")
                celulas.append(s_num)
        linhas_txt.append("\t".join(celulas))

    return "\n".join(linhas_txt) + "\n"


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
    arquivos_mpr = st.session_state.get("arquivos_mpr_lista", [])
    if arquivos_mpr and arquivos_mpr[0]["nome"].lower().endswith(".mpr"):
        tecnica_atual = st.session_state.get("tecnica_idx", 0)
        massa_mg = st.session_state.get("mpr_massa_ativa_mg", 1.0)
        return consolidar_arquivos_mpr(arquivos_mpr, tecnica_atual, massa_mg)

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

    return pd.DataFrame(matriz), tokens_limpos


def extrair_ciclos_gcd(fonte_dados, df):
    arquivos_mpr = st.session_state.get("arquivos_mpr_lista", [])
    if arquivos_mpr and arquivos_mpr[0]["nome"].lower().endswith(".mpr"):
        return st.session_state.get("_ciclos_gcd_mpr_cache", [])

    linhas = extrair_linhas_arquivo(fonte_dados)
    nomes_blocos = []
    for l in linhas[:6]:
        tokens = [t.strip() for t in l.split("\t") if t.strip()]
        if any(re.search(r"\d+\s*[Cc]", t) for t in tokens):
            nomes_blocos = tokens
            break

    num_cols = df.shape[1]
    ciclos = []
    for bloco_idx, col_inicio in enumerate(range(0, num_cols, 4)):
        if col_inicio + 3 >= num_cols:
            break
        sub_chg = df.iloc[:, [col_inicio, col_inicio + 1]].dropna()
        sub_dchg = df.iloc[:, [col_inicio + 2, col_inicio + 3]].dropna()
        if len(sub_chg) == 0 and len(sub_dchg) == 0:
            continue

        nome = nomes_blocos[bloco_idx] if bloco_idx < len(nomes_blocos) else f"Ciclo {bloco_idx + 1}"
        ciclos.append({
            "nome": nome,
            "x_chg": sub_chg.iloc[:, 0].to_numpy(float) if len(sub_chg) > 0 else np.array([]),
            "y_chg": sub_chg.iloc[:, 1].to_numpy(float) if len(sub_chg) > 0 else np.array([]),
            "x_dchg": sub_dchg.iloc[:, 0].to_numpy(float) if len(sub_dchg) > 0 else np.array([]),
            "y_dchg": sub_dchg.iloc[:, 1].to_numpy(float) if len(sub_dchg) > 0 else np.array([]),
        })
    return ciclos


def identificar_amostras(df, tokens_limpos, tecnica_idx):
    tokens_limpos = [str(t) for t in tokens_limpos]
    num_cols = df.shape[1]
    if tecnica_idx == 2:
        arquivos_mpr = st.session_state.get("arquivos_mpr_lista", [])
        if arquivos_mpr and arquivos_mpr[0]["nome"].lower().endswith(".mpr"):
            cache = st.session_state.get("_ciclos_gcd_mpr_cache", [])
            return [c["nome"] for c in cache] if cache else ["Ciclo 1"]
        num_blocos = max(1, num_cols // 4)
        return [f"Ciclo {i+1}" for i in range(num_blocos)]
    elif tecnica_idx == 3:
        num_curvas = max(1, num_cols - 1)
        legendas = tokens_limpos[1:] if len(tokens_limpos) > num_curvas else tokens_limpos
        if len(legendas) < num_curvas:
            legendas = [f"Sample {i+1}" for i in range(num_curvas)]
        return legendas[:num_curvas]
    elif tecnica_idx == 5:
        return ["Discharge Capacity", "Coulombic Efficiency"]
    elif tecnica_idx == 7:
        return ["Ecell", "Ewe (Positivo)", "Ece (Negativo)"]
    elif tecnica_idx == 9:
        # EIE - Bode: blocos de 3 colunas (|Z|, Freq, Fase)
        num_blocos = max(1, num_cols // 3)
        nomes = []
        for b in range(num_blocos):
            idx_tok = b * 3 + 2
            if idx_tok < len(tokens_limpos) and tokens_limpos[idx_tok].strip().upper() not in ["FASE", "PHASE", "DEG", ""]:
                nomes.append(tokens_limpos[idx_tok].strip())
            else:
                nomes.append(f"Sample {b + 1}")
        return nomes
    else:
        num_amostras = num_cols // 2 if num_cols >= 2 else num_cols
        if len(tokens_limpos) >= 2:
            nomes = [tokens_limpos[k] for k in range(1, len(tokens_limpos), 2)]
        else:
            nomes = tokens_limpos
        if len(nomes) < num_amostras:
            nomes = nomes + [f"Sample {i+1}" for i in range(len(nomes), num_amostras)]
        return nomes[:num_amostras]
