import io
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


@st.cache_data(show_spinner=False, max_entries=64)
def _ler_mpr_para_dataframe(dados_bytes):
    """
    Usa o leitor oficial BioLogic.MPRfile do galvani (com fallback para v11+)
    e remove qualquer tempo morto/OCV inicial antes do começo real do Ciclo 1.
    Cacheado por hash de bytes para evitar I/O repetido e bloqueios em reruns rápidos.
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
        nome_stem = Path(arq["nome"]).stem
        if arq["nome"].lower().endswith(".mpr"):
            try:
                df_i = _ler_mpr_para_dataframe(arq["bytes"])
                s_cic = _obter_serie_ciclos(df_i)
                ciclos_unicos = sorted(int(x) for x in s_cic.dropna().unique())
                info[nome_stem] = ciclos_unicos if ciclos_unicos else [1]
            except Exception:
                info[nome_stem] = [1]
        elif _eh_arquivo_ciclador_chines(arq["bytes"]):
            try:
                incluir_c1 = bool(st.session_state.get("chines_incluir_primeiro_ciclo", False))
                ciclos_reais, _, _ = _obter_ciclos_filtrados_ciclador_chines(arq["bytes"], incluir_primeiro_ciclo=incluir_c1)
                info[nome_stem] = [c["ciclo"] for c in ciclos_reais] if ciclos_reais else [1]
            except Exception:
                info[nome_stem] = [1]
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


def _calcular_energia_ciclo_mpr(sub_df, col_v, col_i, col_t, col_q):
    """Calcula a energia integrada (mWh) de um ramo (carga ou descarga) a partir de V, I, t ou Q."""
    if sub_df is None or len(sub_df) < 2 or col_v is None or col_v not in sub_df.columns:
        return 0.0
    v_arr = sub_df[col_v].to_numpy(float)
    mask_v = np.isfinite(v_arr)
    if np.sum(mask_v) < 2:
        return 0.0
    trapz_fn = getattr(np, "trapezoid", getattr(np, "trapz", None))

    if col_t and col_t in sub_df.columns and col_i and col_i in sub_df.columns:
        t_arr = sub_df[col_t].to_numpy(float)
        i_arr = np.abs(sub_df[col_i].to_numpy(float))
        m = np.isfinite(v_arr) & np.isfinite(t_arr) & np.isfinite(i_arr)
        if np.sum(m) >= 2:
            return abs(float(trapz_fn(v_arr[m] * i_arr[m], t_arr[m]))) / 3600.0

    if col_q and col_q in sub_df.columns:
        q_arr = np.abs(sub_df[col_q].to_numpy(float))
        m = np.isfinite(v_arr) & np.isfinite(q_arr)
        if np.sum(m) >= 2:
            q_mah = q_arr[m] / 3.6 if ("/C" in col_q and "mA.h" not in col_q) else q_arr[m]
            return abs(float(trapz_fn(v_arr[m], q_mah)))

    return 0.0


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
                if "/C" in col_q and "mA.h" not in col_q:
                    q_chg_total /= 3.6
            q_d = np.abs(dchg[col_q].to_numpy(float))
            q_dchg_total = np.nanmax(q_d) - np.nanmin(q_d)
            if "/C" in col_q and "mA.h" not in col_q:
                q_dchg_total /= 3.6
        elif col_i and col_t:
            if not chg.empty:
                dt_c = np.diff(chg[col_t].to_numpy(float), prepend=chg[col_t].to_numpy(float)[0]) / 3600.0
                q_chg_total = np.nansum(np.abs(chg[col_i].to_numpy(float)) * dt_c)
            dt_d = np.diff(dchg[col_t].to_numpy(float), prepend=dchg[col_t].to_numpy(float)[0]) / 3600.0
            q_dchg_total = np.nansum(np.abs(dchg[col_i].to_numpy(float)) * dt_d)

        cap_dchg_esp = q_dchg_total / massa_g
        eficiencia = (q_dchg_total / q_chg_total * 100.0) if q_chg_total > 0 else 100.0

        e_chg_mwh = _calcular_energia_ciclo_mpr(chg, col_ewe, col_i, col_t, col_q)
        e_dchg_mwh = _calcular_energia_ciclo_mpr(dchg, col_ewe, col_i, col_t, col_q)
        eficiencia_energetica = (e_dchg_mwh / e_chg_mwh * 100.0) if e_chg_mwh > 1e-9 else np.nan

        if eficiencia > 120.0 or cap_dchg_esp <= 0:
            continue

        registros.append({
            "Ciclo": int(ciclo_id),
            "Cap_Descarga": cap_dchg_esp,
            "Eficiencia": eficiencia,
            "Eficiencia_Energetica": eficiencia_energetica if (np.isfinite(eficiencia_energetica) and 0 < eficiencia_energetica <= 120.0) else np.nan,
        })

    df_out = pd.DataFrame(registros)
    return df_out, ["Ciclo", "Cap_Descarga", "Eficiencia", "Eficiencia_Energetica"]


def _extrair_ciclabilidade_sc_mpr(df_raw, massa_mg):
    """
    Extrai Ciclo, Capacitância Específica de Descarga (F/g), Eficiência Coulômbica (%)
    e Eficiência Energética (%) ciclo a ciclo para Supercapacitores (.mpr).
    """
    cols = [str(c) for c in df_raw.columns]
    col_i = _encontrar_coluna_corrente(cols)
    col_t = next((c for c in cols if "time" in c.lower() and "step" not in c.lower()), None) or next((c for c in cols if "time" in c.lower()), None)
    col_q = next((c for c in cols if "Q charge/discharge" in c or "(Q-Qo)" in c), None)
    col_hc = next((c for c in cols if "half cycle" in c.lower()), None)
    col_oxred = next((c for c in cols if "ox/red" in c.lower()), None)

    v_celula = _obter_potencial_celula_ou_ewe(df_raw)
    if v_celula is None or col_t is None:
        return pd.DataFrame(), ["Ciclo", "Cap_Descarga", "Eficiencia", "Eficiencia_Energetica"]

    massa_g = max(massa_mg, 1e-6) / 1000.0
    df = df_raw.copy()
    df["_v_cell"] = v_celula
    df["_ciclo"] = _obter_serie_ciclos(df)
    trapz_fn = getattr(np, "trapezoid", getattr(np, "trapz", None))

    registros = []
    for ciclo_id, grupo in df.groupby("_ciclo", sort=True):
        chg, dchg = _identificar_carga_descarga_grupo(grupo, "_v_cell", col_i, col_hc, col_oxred)
        if dchg.empty or len(dchg) < 3:
            continue

        t_d = dchg[col_t].to_numpy(float)
        v_d = dchg["_v_cell"].to_numpy(float)
        m_d = np.isfinite(t_d) & np.isfinite(v_d)
        t_d, v_d = t_d[m_d], v_d[m_d]
        if len(t_d) < 3:
            continue

        dt_d = float(max(1e-6, t_d[-1] - t_d[0]))
        i_dchg_amp = 0.0
        if col_i and col_i in dchg.columns:
            ic_arr = np.abs(dchg[col_i].to_numpy(float))
            ic_at = ic_arr[np.isfinite(ic_arr) & (ic_arr > 1e-6)]
            if len(ic_at) > 0:
                i_dchg_amp = float(np.median(ic_at)) / 1000.0
        if i_dchg_amp <= 1e-7 and col_q and col_q in dchg.columns:
            q_d = np.abs(dchg[col_q].to_numpy(float))
            dq = float(np.nanmax(q_d) - np.nanmin(q_d))
            q_coulombs = dq if ("/C" in col_q and "mA.h" not in col_q) else (dq * 3.6)
            i_dchg_amp = q_coulombs / dt_d

        if i_dchg_amp <= 1e-7:
            continue

        v_ini = float(v_d[0])
        v_fim = float(v_d[-1])
        v_ref_min = max(0.0, v_fim) if v_fim >= -0.02 else v_fim
        dv_ef = max(v_ini - v_ref_min, 1e-3)
        int_v_dt = abs(float(trapz_fn(np.maximum(0.0, v_d - v_ref_min), t_d)))
        c_sp_fg = (2.0 * i_dchg_amp * int_v_dt) / (massa_g * (dv_ef ** 2))
        if not np.isfinite(c_sp_fg) or c_sp_fg <= 0:
            continue

        q_dchg_c = i_dchg_amp * dt_d
        q_chg_c = 0.0
        if not chg.empty and len(chg) >= 2:
            t_c = chg[col_t].to_numpy(float)
            dt_c = float(max(0.0, t_c[-1] - t_c[0]))
            i_chg_amp = i_dchg_amp
            if col_i and col_i in chg.columns:
                ic_c = np.abs(chg[col_i].to_numpy(float))
                ic_c_at = ic_c[np.isfinite(ic_c) & (ic_c > 1e-6)]
                if len(ic_c_at) > 0:
                    i_chg_amp = float(np.median(ic_c_at)) / 1000.0
            q_chg_c = i_chg_amp * dt_c

        eff_coul = (q_dchg_c / q_chg_c * 100.0) if q_chg_c > 1e-9 else 100.0
        if eff_coul > 120.0:
            continue

        e_chg_mwh = _calcular_energia_ciclo_mpr(chg, "_v_cell", col_i, col_t, col_q)
        e_dchg_mwh = _calcular_energia_ciclo_mpr(dchg, "_v_cell", col_i, col_t, col_q)
        eff_energ = (e_dchg_mwh / e_chg_mwh * 100.0) if e_chg_mwh > 1e-9 else np.nan

        registros.append({
            "Ciclo": int(ciclo_id),
            "Cap_Descarga": float(c_sp_fg),
            "Eficiencia": float(eff_coul),
            "Eficiencia_Energetica": float(eff_energ) if (np.isfinite(eff_energ) and 0 < eff_energ <= 120.0) else np.nan,
        })

    df_out = pd.DataFrame(registros)
    if not df_out.empty:
        df_out["Ciclo"] = np.arange(1, len(df_out) + 1, dtype=int)
    return df_out, ["Ciclo", "Cap_Descarga", "Eficiencia", "Eficiencia_Energetica"]


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
    if tecnica_idx in [2, 10]:
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

    # (15) Ciclabilidade & Eficiência Individual (Supercapacitor)
    if tecnica_idx == 15:
        return _extrair_ciclabilidade_sc_mpr(df_primeiro, massa_mg)

    # (7) CGCD Supercapacitor (2 Eletrodos / Janelas - usa Ecell = Ewe - Ece)
    if tecnica_idx in [6, 12, 13]:
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

    # (10) EIE - Bode (|Z|, Freq, Fase) e (16) Bode Capacitância Diferencial SC
    if tecnica_idx in [9, 16]:
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

        if tecnica_idx in [0, 11]:
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

        elif tecnica_idx == 14:
            df_cic_sc, _ = _extrair_ciclabilidade_sc_mpr(df_i, massa_mg)
            if not df_cic_sc.empty:
                series_pareadas.extend([df_cic_sc["Ciclo"], df_cic_sc["Cap_Descarga"]])
                tokens_pareados.extend(["Ciclo", nome_amostra])

    if series_pareadas:
        return pd.concat(series_pareadas, axis=1), tokens_pareados

    raise ValueError("Não foi possível extrair a curva para esta técnica a partir do arquivo .mpr selecionado.")


def exportar_txt_compativel_mpr(lista_arquivos_mpr, tecnica_idx, massa_mg=1.0, idioma="Português", fonte_dados=None):
    """
    Gera o conteúdo de um arquivo .txt delimitado por tabulação (padrão Origin/PhVolt)
    contendo exatamente as curvas extraídas/unificadas para a técnica selecionada em TODOS os cenários
    (.mpr, múltiplos .txt/.dat/.csv unificados, ciclador chinês simplificado ou arquivo único).
    """
    if lista_arquivos_mpr:
        primeiro_nome = lista_arquivos_mpr[0]["nome"].lower()
        if primeiro_nome.endswith(".mpr"):
            df_out, tokens = consolidar_arquivos_mpr(lista_arquivos_mpr, tecnica_idx, massa_mg)
        else:
            df_out, tokens = processar_cabecalho_e_dados(lista_arquivos_mpr[0]["bytes"])
    elif fonte_dados is not None:
        df_out, tokens = processar_cabecalho_e_dados(fonte_dados)
    else:
        raise ValueError("Não há dados carregados para exportar.")

    if df_out is None or df_out.empty:
        raise ValueError("Não há dados extraídos para exportar.")

    num_cols = df_out.shape[1]
    if len(tokens) == num_cols:
        cabecalho = [str(t) for t in tokens]
    else:
        cabecalho = [str(c) for c in df_out.columns]

    linhas_txt = ["\t".join(cabecalho)]

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


def _decodificar_bytes_texto(raw_bytes):
    if raw_bytes.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw_bytes.decode("utf-16", errors="ignore")
    # Verifica presença de bytes nulos típicos de UTF-16 sem BOM
    if b"\x00" in raw_bytes[:200]:
        for enc in ["utf-16-le", "utf-16-be"]:
            try:
                return raw_bytes.decode(enc)
            except Exception:
                pass
    for enc in ["utf-8-sig", "utf-8", "latin1"]:
        try:
            return raw_bytes.decode(enc)
        except Exception:
            pass
    return raw_bytes.decode("utf-8", errors="ignore")


def extrair_linhas_arquivo(fonte_dados):
    if hasattr(fonte_dados, "getvalue"):
        texto = _decodificar_bytes_texto(fonte_dados.getvalue())
    elif isinstance(fonte_dados, (bytes, bytearray)):
        texto = _decodificar_bytes_texto(bytes(fonte_dados))
    else:
        with open(fonte_dados, "rb") as f:
            texto = _decodificar_bytes_texto(f.read())
    return [l.rstrip("\r\n") for l in texto.splitlines() if l.strip()]


@st.cache_data(show_spinner=False, max_entries=32)
def _parse_arquivo_texto_unico(fonte_dados):
    linhas = extrair_linhas_arquivo(fonte_dados)
    if not linhas:
        return pd.DataFrame(), []

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
        "PRESSÃO RELATIVA", "RELATIVE PRESSURE", "QUANTIDADE ADSORVIDA", "QUANTITY ADSORVIDA"
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




def _eh_arquivo_ciclador_chines(fonte_dados):
    """Detecta se o arquivo .txt possui o cabeçalho tabular bruto do ciclador (Step Type, Current(A), Voltage(V), Chg. Spec. Cap.)."""
    try:
        if hasattr(fonte_dados, "getvalue"):
            head_bytes = fonte_dados.getvalue()[:600]
        elif isinstance(fonte_dados, (bytes, bytearray)):
            head_bytes = bytes(fonte_dados[:600])
        else:
            with open(fonte_dados, "rb") as f:
                head_bytes = f.read(600)
        head_txt = _decodificar_bytes_texto(head_bytes)
        primeira_linha = head_txt.splitlines()[0] if head_txt.splitlines() else ""
        return ("Step Type" in primeira_linha) and ("Voltage(V)" in primeira_linha) and ("Current(A)" in primeira_linha)
    except Exception:
        return False


def _total_time_para_segundos(serie_tempo):
    """Converte strings 'HH:MM:SS' (incluindo horas > 24, ex: '125:40:10') para segundos."""
    s = serie_tempo.astype(str).str.strip()
    partes = s.str.split(":", expand=True)
    if partes.shape[1] >= 3:
        h = pd.to_numeric(partes[0], errors="coerce").fillna(0.0).to_numpy(float)
        m = pd.to_numeric(partes[1], errors="coerce").fillna(0.0).to_numpy(float)
        sec = pd.to_numeric(partes[2], errors="coerce").fillna(0.0).to_numpy(float)
        return h * 3600.0 + m * 60.0 + sec
    return pd.to_numeric(s, errors="coerce").fillna(0.0).to_numpy(float)


@st.cache_data(show_spinner=False, max_entries=16)
def _parsear_ciclador_chines_bruto(dados_bytes):
    """
    Decifra o arquivo bruto do ciclador chinês (UTF-16 / UTF-8) e corrige o bug
    em que o firmware sobrepõe o último ciclo de uma densidade de corrente com o
    primeiro ciclo da próxima densidade dentro do mesmo `Cycle Index`.

    Retorna uma lista de dicionários (1 por ciclo real cronológico) e as zonas
    de densidade de corrente detectadas automaticamente.
    """
    texto = _decodificar_bytes_texto(dados_bytes)
    df = pd.read_csv(io.StringIO(texto), sep="\t")
    df.columns = [str(c).strip() for c in df.columns]

    col_step = next((c for c in df.columns if "step type" in c.lower()), None)
    col_i = next((c for c in df.columns if "current" in c.lower()), None)
    col_v = next((c for c in df.columns if "voltage" in c.lower()), None)
    col_t = next((c for c in df.columns if "total time" in c.lower() or "time" in c.lower()), None)
    col_qchg = next((c for c in df.columns if "chg" in c.lower() and "dchg" not in c.lower() and "cap" in c.lower()), None)
    col_qdchg = next((c for c in df.columns if "dchg" in c.lower() and "cap" in c.lower()), None)

    if not (col_step and col_i and col_v and col_qchg and col_qdchg):
        return [], []

    # Mantém apenas passos ativos (ignora 'Rest' onde o ciclador pausa entre patamares de corrente)
    step_str = df[col_step].astype(str).str.strip()
    mask_ativo = step_str.str.contains("Chg|DChg", case=False, regex=True)
    df_act = df[mask_ativo].copy()
    if df_act.empty:
        return [], []

    step_clean = df_act[col_step].astype(str).str.strip()
    eh_dchg = step_clean.str.contains("DChg", case=False)
    tipo_ramo = np.where(eh_dchg, "DChg", "Chg")

    # Cada bloco contíguo de Chg ou DChg é separado cronologicamente
    bloco_id = (pd.Series(tipo_ramo, index=df_act.index) != pd.Series(tipo_ramo, index=df_act.index).shift()).cumsum()

    t_sec_all = _total_time_para_segundos(df_act[col_t]) if col_t else np.arange(len(df_act), dtype=float)
    df_act["_t_sec"] = t_sec_all
    df_act["_tipo"] = tipo_ramo
    df_act["_bloco"] = bloco_id

    blocos = []
    for _, bdf in df_act.groupby("_bloco", sort=True):
        t_b = bdf["_tipo"].iloc[0]
        i_med = float(np.nanmedian(np.abs(pd.to_numeric(bdf[col_i], errors="coerce").to_numpy(float))))
        v_arr = pd.to_numeric(bdf[col_v], errors="coerce").to_numpy(float)
        t_arr = bdf["_t_sec"].to_numpy(float)
        q_col = col_qdchg if t_b == "DChg" else col_qchg
        q_arr = pd.to_numeric(bdf[q_col], errors="coerce").to_numpy(float)

        m_val = np.isfinite(v_arr) & np.isfinite(q_arr)
        v_arr = v_arr[m_val]
        q_arr = q_arr[m_val]
        t_arr = t_arr[m_val]
        if len(v_arr) < 2:
            continue

        # Garante que a capacidade do ramo comece em 0 caso haja algum resíduo acumulado
        q_rel = np.maximum(0.0, q_arr - float(q_arr[0]))
        cap_max = float(np.max(q_rel))
        dt_h = float(t_arr[-1] - t_arr[0]) / 3600.0 if len(t_arr) >= 2 else 0.0
        # Densidade de corrente real J (mA/g) = dQ / dt, imune ao truncamento de 4 casas decimais em Current(A)
        j_mag = (cap_max / dt_h) if (dt_h > 1e-6 and cap_max > 0.5) else (i_med * 1000.0)
        blocos.append({
            "tipo": t_b,
            "i_amp": i_med,
            "j_mag": j_mag,
            "q": q_rel,
            "v": v_arr,
            "t": t_arr,
            "cap_max": cap_max,
        })

    # Pareia blocos cronológicos em ciclos reais completos (Chg -> DChg)
    # Sempre que aparece um novo 'Chg' após um 'DChg' (mesmo dentro do mesmo Cycle Index!),
    # inicia-se um novo ciclo real, eliminando 100% da sobreposição do ciclador!
    ciclos_reais = []
    ciclo_atual = None

    for blk in blocos:
        if blk["tipo"] == "Chg":
            if ciclo_atual is not None and (ciclo_atual["chg"] is not None or ciclo_atual["dchg"] is not None):
                ciclos_reais.append(ciclo_atual)
            ciclo_atual = {"chg": blk, "dchg": None}
        else:  # DChg
            if ciclo_atual is None:
                ciclo_atual = {"chg": None, "dchg": blk}
            elif ciclo_atual["dchg"] is None:
                ciclo_atual["dchg"] = blk
                ciclos_reais.append(ciclo_atual)
                ciclo_atual = None
            else:
                ciclos_reais.append(ciclo_atual)
                ciclo_atual = {"chg": None, "dchg": blk}

    if ciclo_atual is not None and (ciclo_atual["chg"] is not None or ciclo_atual["dchg"] is not None):
        ciclos_reais.append(ciclo_atual)

    trapz_fn = getattr(np, "trapezoid", getattr(np, "trapz", None))
    resultados = []
    for idx_c, item in enumerate(ciclos_reais, 1):
        b_chg = item["chg"]
        b_dchg = item["dchg"]

        i_amp = (
            b_dchg["i_amp"]
            if (b_dchg is not None and b_dchg["i_amp"] > 0)
            else (b_chg["i_amp"] if b_chg is not None else 0.0)
        )
        i_ma = i_amp * 1000.0
        # Prefere o ramo de descarga (CC DChg) ou o maior J entre carga e descarga para evitar
        # que uma etapa CV/taper ou queda momentânea na carga distorça a densidade de corrente do degrau
        if b_chg is not None and b_dchg is not None and b_chg["cap_max"] > 5.0 and b_dchg["cap_max"] > 5.0:
            j_mag = max(b_chg["j_mag"], b_dchg["j_mag"])
        elif b_dchg is not None and b_dchg["j_mag"] > 0:
            j_mag = b_dchg["j_mag"]
        elif b_chg is not None and b_chg["j_mag"] > 0:
            j_mag = b_chg["j_mag"]
        else:
            j_mag = i_ma

        cap_chg = b_chg["cap_max"] if b_chg is not None else 0.0
        cap_dchg = b_dchg["cap_max"] if b_dchg is not None else 0.0

        # Ignora ciclos sem descarga válida
        if cap_dchg <= 0.1:
            continue

        eff_coul = (cap_dchg / cap_chg * 100.0) if cap_chg > 1.0 else np.nan
        # Para o 1º ciclo de formação (quando a célula já inicia parcialmente carregada, cap_chg << cap_dchg),
        # evita distorcer a escala de eficiência coulômbica com valores > 120%
        if np.isfinite(eff_coul) and eff_coul > 120.0:
            eff_coul = np.nan

        e_chg = abs(float(trapz_fn(b_chg["v"], b_chg["q"]))) if (b_chg is not None and len(b_chg["q"]) > 1) else 0.0
        e_dchg = abs(float(trapz_fn(b_dchg["v"], b_dchg["q"]))) if (b_dchg is not None and len(b_dchg["q"]) > 1) else 0.0
        eff_energ = (e_dchg / e_chg * 100.0) if (e_chg > 1e-6 and e_dchg > 0) else np.nan
        if np.isfinite(eff_energ) and eff_energ > 120.0:
            eff_energ = np.nan

        resultados.append({
            "ciclo": len(resultados) + 1,
            "i_amp": i_amp,
            "i_ma": round(i_ma, 4),
            "j_mag": round(j_mag, 2),
            "q_chg": b_chg["q"] if b_chg is not None else np.array([]),
            "v_chg": b_chg["v"] if b_chg is not None else np.array([]),
            "q_dchg": b_dchg["q"] if b_dchg is not None else np.array([]),
            "v_dchg": b_dchg["v"] if b_dchg is not None else np.array([]),
            "cap_chg": cap_chg,
            "cap_dchg": cap_dchg,
            "eff_coul": eff_coul,
            "eff_energ": eff_energ,
        })

    # Detecta se o 1º ciclo é incompleto (célula já "nasceu" carregada: carga inicial < 30% da descarga)
    tem_primeiro_incompleto = False
    if len(resultados) >= 2:
        r0 = resultados[0]
        if r0["cap_dchg"] > 0 and r0["cap_chg"] < (0.30 * r0["cap_dchg"]):
            tem_primeiro_incompleto = True

    return resultados, tem_primeiro_incompleto


def _calcular_zonas_rate_chines(ciclos_filtrados):
    zonas_rate = []
    if not ciclos_filtrados:
        return zonas_rate
    j_brutos = [float(r.get("j_mag", r["i_ma"])) for r in ciclos_filtrados]
    n_c = len(j_brutos)
    # Filtro de mediana de janela 3 (mantendo bordas) para eliminar qualquer glitch isolado de 1 ciclo
    j_suave = []
    for i in range(n_c):
        if 0 < i < n_c - 1:
            j_suave.append(float(np.median([j_brutos[i - 1], j_brutos[i], j_brutos[i + 1]])))
        else:
            j_suave.append(j_brutos[i])

    inicio_z = 0.5
    j_ref = j_suave[0]
    c_prev = ciclos_filtrados[0]["ciclo"]
    for idx_r in range(1, n_c):
        r = ciclos_filtrados[idx_r]
        j_cur = j_suave[idx_r]
        if abs(j_cur - j_ref) > max(1.0, 0.35 * max(j_ref, 1e-4)):
            fim_z = c_prev + 0.5
            zonas_rate.append({
                "start": inicio_z,
                "end": fim_z,
                "mid": (inicio_z + fim_z) / 2.0,
                "i_ma": r["i_ma"],
                "j_mag": j_ref,
            })
            inicio_z = fim_z
            j_ref = j_cur
        c_prev = r["ciclo"]
    fim_z = c_prev + 0.5
    zonas_rate.append({
        "start": inicio_z,
        "end": fim_z,
        "mid": (inicio_z + fim_z) / 2.0,
        "i_ma": ciclos_filtrados[-1]["i_ma"],
        "j_mag": j_ref,
    })
    return zonas_rate


def _obter_ciclos_filtrados_ciclador_chines(dados_bytes, incluir_primeiro_ciclo=False):
    ciclos_brutos, tem_primeiro_incompleto = _parsear_ciclador_chines_bruto(dados_bytes)
    if not ciclos_brutos:
        return [], [], False

    if tem_primeiro_incompleto and not incluir_primeiro_ciclo:
        lista_uso = [dict(c) for c in ciclos_brutos[1:]]
        for idx_n, c in enumerate(lista_uso, 1):
            c["ciclo"] = idx_n
    else:
        lista_uso = [dict(c) for c in ciclos_brutos]

    zonas_rate = _calcular_zonas_rate_chines(lista_uso)
    return lista_uso, zonas_rate, tem_primeiro_incompleto


def _consolidar_ciclador_chines(lista_arquivos, tecnica_idx, mapa_ciclos_usuario=None):
    """
    Adapta os dados corrigidos do ciclador chinês para qualquer técnica de bateria do PhVolt:
    - GCD Bateria (2) e dQ/dV (10)
    - Rate Capability Bateria (3)
    - Ciclabilidade Multiplot (4)
    - Ciclabilidade & Eficiência Individual (5)
    """
    primeiro = lista_arquivos[0]
    nome_base = Path(primeiro["nome"]).stem
    incluir_c1 = bool(st.session_state.get("chines_incluir_primeiro_ciclo", False))
    ciclos_reais, zonas_rate, _ = _obter_ciclos_filtrados_ciclador_chines(primeiro["bytes"], incluir_primeiro_ciclo=incluir_c1)
    if not ciclos_reais:
        return pd.DataFrame(), []

    # Técnica 2 (GCD Bateria) e Técnica 10 (dQ/dV)
    if tecnica_idx in [2, 10]:
        ciclos_disp = [c["ciclo"] for c in ciclos_reais]
        ciclos_alvo = (mapa_ciclos_usuario or {}).get(nome_base)
        if not ciclos_alvo:
            # Se for um ensaio de Rate Capability (vários patamares de corrente), seleciona por padrão
            # um ciclo estabilizado de cada patamar de corrente; caso contrário, o último ciclo!
            if len(zonas_rate) > 1:
                selecionados = []
                for z in zonas_rate:
                    c_no_degrau = [c["ciclo"] for c in ciclos_reais if z["start"] <= c["ciclo"] <= z["end"]]
                    if c_no_degrau:
                        selecionados.append(c_no_degrau[-1])
                ciclos_alvo = selecionados if selecionados else [ciclos_disp[-1]]
            else:
                ciclos_alvo = [ciclos_disp[-1]]

        mapa_por_id = {c["ciclo"]: c for c in ciclos_reais}
        blocos_series = []
        ciclos_estruturados = []

        for cid in ciclos_alvo:
            c_obj = mapa_por_id.get(int(cid))
            if c_obj is None:
                continue
            i_str = f"{c_obj['j_mag']:.0f} mA/g" if c_obj.get("j_mag", 0) > 10 else f"{c_obj['i_ma']:g} mA"
            rotulo = f"Ciclo {cid} ({i_str})" if len(zonas_rate) > 1 else f"Ciclo {cid}"
            blocos_series.extend([
                pd.Series(c_obj["q_chg"], name=f"Q_chg_{rotulo}"),
                pd.Series(c_obj["v_chg"], name=f"V_chg_{rotulo}"),
                pd.Series(c_obj["q_dchg"], name=f"Q_dchg_{rotulo}"),
                pd.Series(c_obj["v_dchg"], name=f"V_dchg_{rotulo}"),
            ])
            ciclos_estruturados.append({
                "nome": rotulo,
                "x_chg": c_obj["q_chg"],
                "y_chg": c_obj["v_chg"],
                "x_dchg": c_obj["q_dchg"],
                "y_dchg": c_obj["v_dchg"],
            })

        st.session_state["_ciclos_gcd_mpr_cache"] = ciclos_estruturados
        df_out = pd.concat(blocos_series, axis=1) if blocos_series else pd.DataFrame()
        return df_out, [c["nome"] for c in ciclos_estruturados]

    # Técnica 3: Rate Capability (Bateria)
    if tecnica_idx == 3:
        if len(zonas_rate) > 1:
            st.session_state["_rate_mpr_zonas_dinamicas"] = zonas_rate
        else:
            st.session_state.pop("_rate_mpr_zonas_dinamicas", None)

        series_pareadas = []
        tokens_pareados = []
        max_len = 0
        dados_amostras = []

        for arq in lista_arquivos:
            if not _eh_arquivo_ciclador_chines(arq["bytes"]):
                continue
            c_list, _, _ = _obter_ciclos_filtrados_ciclador_chines(arq["bytes"], incluir_primeiro_ciclo=incluir_c1)
            if not c_list:
                continue
            nm = Path(arq["nome"]).stem
            vals = [c["cap_dchg"] for c in c_list]
            max_len = max(max_len, len(vals))
            dados_amostras.append((nm, vals))

        if not dados_amostras:
            return pd.DataFrame(), []

        series_pareadas.append(pd.Series(np.arange(1, max_len + 1, dtype=int), name="Ciclo"))
        tokens_pareados.append("Ciclo")
        for nm, vals in dados_amostras:
            series_pareadas.append(pd.Series(vals, name=nm))
            tokens_pareados.append(nm)

        return pd.concat(series_pareadas, axis=1), tokens_pareados

    # Técnica 4: Ciclabilidade Multiplot (Bateria)
    if tecnica_idx == 4:
        series_pareadas = []
        tokens_pareados = []
        for arq in lista_arquivos:
            if not _eh_arquivo_ciclador_chines(arq["bytes"]):
                continue
            c_list, _, _ = _obter_ciclos_filtrados_ciclador_chines(arq["bytes"], incluir_primeiro_ciclo=incluir_c1)
            if not c_list:
                continue
            nm = Path(arq["nome"]).stem
            s_cic = pd.Series([c["ciclo"] for c in c_list], name=f"Ciclo_{nm}")
            s_cap = pd.Series([c["cap_dchg"] for c in c_list], name=nm)
            series_pareadas.extend([s_cic, s_cap])
            tokens_pareados.extend(["Ciclo", nm])

        df_out = pd.concat(series_pareadas, axis=1) if series_pareadas else pd.DataFrame()
        return df_out, tokens_pareados

    # Técnica 5: Ciclabilidade & Eficiência Individual (Bateria)
    if tecnica_idx == 5:
        df_out = pd.DataFrame({
            "Ciclo": [c["ciclo"] for c in ciclos_reais],
            "Cap_Descarga": [c["cap_dchg"] for c in ciclos_reais],
            "Eficiencia": [c["eff_coul"] if np.isfinite(c["eff_coul"]) else 100.0 for c in ciclos_reais],
            "Eficiencia_Energetica": [c["eff_energ"] for c in ciclos_reais],
        })
        return df_out, ["Ciclo", "Cap_Descarga", "Eficiencia", "Eficiencia_Energetica"]

    return pd.DataFrame(), []


def processar_cabecalho_e_dados(fonte_dados):
    arquivos_lista = st.session_state.get("arquivos_mpr_lista", [])
    if arquivos_lista:
        primeiro_arq = arquivos_lista[0]
        primeiro_nome = primeiro_arq["nome"].lower()
        tecnica_atual = st.session_state.get("tecnica_idx", 0)
        if primeiro_nome.endswith(".mpr"):
            massa_mg = st.session_state.get("mpr_massa_ativa_mg", 1.0)
            return consolidar_arquivos_mpr(arquivos_lista, tecnica_atual, massa_mg)
        elif _eh_arquivo_ciclador_chines(primeiro_arq["bytes"]) and tecnica_atual in [2, 3, 4, 5, 10]:
            mapa_ciclos_usuario = st.session_state.get("mpr_ciclos_por_amostra", {})
            return _consolidar_ciclador_chines(arquivos_lista, tecnica_atual, mapa_ciclos_usuario)
        elif len(arquivos_lista) > 1 and (
            primeiro_nome.endswith(".txt")
            or primeiro_nome.endswith(".dat")
            or primeiro_nome.endswith(".csv")
        ):
            return consolidar_arquivos_texto(arquivos_lista, tecnica_atual)

    if _eh_arquivo_ciclador_chines(fonte_dados):
        raw_b = fonte_dados.getvalue() if hasattr(fonte_dados, "getvalue") else (bytes(fonte_dados) if isinstance(fonte_dados, (bytes, bytearray)) else open(fonte_dados, "rb").read())
        tecnica_atual = st.session_state.get("tecnica_idx", 0)
        mapa_ciclos_usuario = st.session_state.get("mpr_ciclos_por_amostra", {})
        return _consolidar_ciclador_chines([{"nome": "amostra.txt", "bytes": raw_b}], tecnica_atual, mapa_ciclos_usuario)

    return _parse_arquivo_texto_unico(fonte_dados)


def extrair_ciclos_gcd(fonte_dados, df):
    arquivos_mpr = st.session_state.get("arquivos_mpr_lista", [])
    if arquivos_mpr and (arquivos_mpr[0]["nome"].lower().endswith(".mpr") or _eh_arquivo_ciclador_chines(arquivos_mpr[0]["bytes"])):
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
    if tecnica_idx in [2, 10]:
        arquivos_mpr = st.session_state.get("arquivos_mpr_lista", [])
        if arquivos_mpr and (arquivos_mpr[0]["nome"].lower().endswith(".mpr") or _eh_arquivo_ciclador_chines(arquivos_mpr[0]["bytes"])):
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
    elif tecnica_idx in [5, 15]:
        return ["Discharge Capacity", "Coulombic Efficiency"]
    elif tecnica_idx == 7:
        return ["Ecell", "Ewe (Positivo)", "Ece (Negativo)"]
    elif tecnica_idx in [9, 16]:
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
        nomes_brutos = nomes[:num_amostras]

        if tecnica_idx in [12, 13]:
            tag_t = "ragone" if tecnica_idx == 12 else "rate_sc"
            agrupar = st.session_state.get(f"sc_rr_group_{tag_t}", True)
            if agrupar:
                from tecnicas.ragone_rate_sc import _extrair_grupo_amostra_sc
                grupos_unicos = []
                for nb in nomes_brutos:
                    grp = _extrair_grupo_amostra_sc(nb)
                    if grp not in grupos_unicos:
                        grupos_unicos.append(grp)
                if len(grupos_unicos) == len(nomes_brutos) and len(nomes_brutos) >= 2:
                    nome_def = Path(st.session_state.get("nome_arquivo_anterior", "Supercapacitor")).stem
                    return [nome_def]
                return grupos_unicos
        return nomes_brutos


def consolidar_arquivos_texto(arquivos_lista, tecnica_idx):
    """
    Lê e consolida múltiplos arquivos de texto (.txt, .dat, .csv) carregados em paralelo
    em um único DataFrame unificado, adequado para cada técnica eletroquímica.
    """
    dfs_processados = []
    tokens_globais = ["Cycle"] if tecnica_idx == 3 else ["Index"]
    nomes_usados = {}

    for idx, arq in enumerate(arquivos_lista):
        try:
            df_i, _ = _parse_arquivo_texto_unico(arq["bytes"])
            nome_base = Path(arq["nome"]).stem
            if nome_base in nomes_usados:
                nomes_usados[nome_base] += 1
                nome_unico = f"{nome_base}_{nomes_usados[nome_base]}"
            else:
                nomes_usados[nome_base] = 1
                nome_unico = nome_base

            if df_i.empty or df_i.shape[1] < 2:
                continue

            if tecnica_idx == 3:
                # Rate capability: Coluna 0 = Ciclo, Coluna 1 = Capacidade (alinhados por Ciclo)
                sub_rc = df_i.iloc[:, :2].dropna().copy()
                sub_rc.columns = ["Ciclo", nome_unico]
                dfs_processados.append(sub_rc)
                tokens_globais.append(nome_unico)
            elif tecnica_idx in [2, 10]:
                # GCD Bateria / dQ/dV: cada arquivo traz 4 colunas [Q_chg, V_chg, Q_dchg, V_dchg]
                if df_i.shape[1] >= 4:
                    df_g = df_i.iloc[:, :4].copy()
                    df_g.columns = [f"Qc_{idx}", f"Vc_{idx}", f"Qd_{idx}", f"Vd_{idx}"]
                    dfs_processados.append(df_g)
                    tokens_globais.extend([nome_unico, "", "", ""])
            elif tecnica_idx in [9, 16]:
                # Bode: blocos de 3 colunas (|Z|, Freq, Fase) por arquivo
                if df_i.shape[1] >= 3:
                    df_b = df_i.iloc[:, :3].copy()
                    df_b.columns = [f"Z_{idx}", f"Freq_{idx}", f"Phase_{idx}"]
                    dfs_processados.append(df_b)
                    tokens_globais.extend([f"|Z| ({nome_unico})", f"Freq ({nome_unico})", nome_unico])
            else:
                # CV, EIE Nyquist, CGCD 2E, BET: Pares de colunas (X, Y) por arquivo
                df_p = df_i.iloc[:, :2].copy()
                df_p.columns = [f"X_{idx}", f"Y_{idx}"]
                dfs_processados.append(df_p)
                tokens_globais.extend([f"X ({nome_unico})", nome_unico])
        except Exception:
            pass

    if not dfs_processados:
        return pd.DataFrame(), ["Index", "Data"]

    if tecnica_idx == 3:
        # Combina Rate / Ciclabilidade pelo eixo X (Ciclo)
        df_final = dfs_processados[0]
        for d in dfs_processados[1:]:
            df_final = pd.merge(df_final, d, on="Ciclo", how="outer")
        df_final = df_final.sort_values("Ciclo").reset_index(drop=True)
        return df_final, tokens_globais
    else:
        df_final = pd.concat(dfs_processados, axis=1)
        return df_final, tokens_globais
