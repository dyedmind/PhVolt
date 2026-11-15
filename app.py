from datetime import datetime
import inspect
import io
from pathlib import Path
import matplotlib.pyplot as plt
import streamlit as st

from core import (
    PALETAS_DISPONIVEIS,
    PRESETS_REVISTAS,
    TEXTOS_PADRAO,
    aplicar_preset_revista_figura,
    calcular_resumo_parametros,
    exportar_txt_compativel_mpr,
    identificar_amostras,
    listar_ciclos_disponiveis_mpr,
    obter_tema_visual,
    processar_cabecalho_e_dados,
)
from tecnicas import (
    gerar_plot_bet,
    gerar_plot_bode,
    gerar_plot_bode_capacitancia,
    gerar_plot_ciclabilidade,
    gerar_plot_ciclabilidade_eficiencia,
    gerar_plot_cinetica_cv,
    gerar_plot_cv,
    gerar_plot_dqdv,
    gerar_plot_eie,
    gerar_plot_gcd,
    gerar_plot_ragone_sc,
    gerar_plot_rate,
    gerar_plot_rate_sc,
    gerar_plot_sc_2e,
    gerar_plot_sc_3e,
)

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


def _converter_float(val_str):
    if val_str and val_str.strip():
        try:
            return float(val_str.replace(",", "."))
        except ValueError:
            return None
    return None


def _parsear_sequencia_floats(texto_seq):
    if not texto_seq or not str(texto_seq).strip():
        return []
    txt = str(texto_seq).strip()
    sep = ";" if ";" in txt else ("," if txt.count(",") > 1 and "." in txt else (";" if ";" in txt else " "))
    if ";" in txt:
        partes = txt.split(";")
    elif "\t" in txt:
        partes = txt.split("\t")
    elif " " in txt and "," not in txt:
        partes = txt.split()
    else:
        partes = txt.split(";")
    vals = []
    for p in partes:
        v = _converter_float(p)
        if v is not None and v > 0:
            vals.append(v)
    return vals


def _chamar_plot_seguro(fn, *args, **kwargs):
    sig = inspect.signature(fn).parameters
    aceita_var_kw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.values())
    if aceita_var_kw:
        return fn(*args, **kwargs)
    kwargs_filtrados = {k: v for k, v in kwargs.items() if k in sig}
    return fn(*args, **kwargs_filtrados)


def main():
    if caminho_icone.exists():
        st.sidebar.image(str(caminho_icone), width=105)

    st.sidebar.title("⚡ PhVolt")
    st.sidebar.caption("Processamento e Gráficos Automatizados")

    # 1. Idioma
    idioma = st.sidebar.radio("🌐 Idioma / Language:", ["Português", "Inglês"], key="app_lang")
    textos = TEXTOS_PADRAO[idioma]



    # 2. Upload de Arquivo(s) — mantém sempre os arquivos carregados ao alternar entre técnicas
    if "uploader_reset_counter" not in st.session_state:
        st.session_state["uploader_reset_counter"] = 0

    arquivos_raw = st.sidebar.file_uploader(
        "📁 Carregue arquivo(s) (.txt, .dat, .csv, .mpr):" if idioma == "Português" else "📁 Upload data file(s) (.txt, .dat, .csv, .mpr):",
        type=["txt", "dat", "csv", "mpr"],
        accept_multiple_files=True,
        key=f"main_file_uploader_{st.session_state['uploader_reset_counter']}",
    )

    if arquivos_raw is None:
        arquivos_upload = []
    elif hasattr(arquivos_raw, "name") and hasattr(arquivos_raw, "getvalue"):
        arquivos_upload = [arquivos_raw]
    elif isinstance(arquivos_raw, (list, tuple)):
        arquivos_upload = [f for f in arquivos_raw if hasattr(f, "name") and hasattr(f, "getvalue")]
    else:
        arquivos_upload = []

    if arquivos_upload:
        if len(arquivos_upload) > 1:
            if st.sidebar.button(
                "🗑️ Limpar todos os arquivos" if idioma == "Português" else "🗑️ Clear all uploaded files",
                use_container_width=True,
                key="btn_clear_all_files",
            ):
                st.session_state["uploader_reset_counter"] += 1
                for k in [
                    "dados_carregados",
                    "nome_arquivo_anterior",
                    "arquivos_mpr_lista",
                    "assinatura_arquivos_anterior",
                    "mpr_ciclos_por_amostra",
                    "_rate_mpr_zonas_dinamicas",
                    "_ciclos_gcd_mpr_cache",
                ]:
                    st.session_state.pop(k, None)
                plt.close("all")
                st.rerun()

        assinatura_atual = tuple((f.name, getattr(f, "size", len(f.getvalue()))) for f in arquivos_upload)
        if assinatura_atual != st.session_state.get("assinatura_arquivos_anterior"):
            st.session_state["arquivos_mpr_lista"] = [{"nome": f.name, "bytes": f.getvalue()} for f in arquivos_upload]
            st.session_state["dados_carregados"] = arquivos_upload[0].getvalue()
            st.session_state["nome_arquivo_anterior"] = arquivos_upload[0].name
            st.session_state["assinatura_arquivos_anterior"] = assinatura_atual
            plt.close("all")
    else:
        for k in [
            "dados_carregados",
            "nome_arquivo_anterior",
            "arquivos_mpr_lista",
            "assinatura_arquivos_anterior",
            "mpr_ciclos_por_amostra",
            "_rate_mpr_zonas_dinamicas",
            "_ciclos_gcd_mpr_cache",
        ]:
            if k in st.session_state:
                del st.session_state[k]

    dados_bytes = st.session_state.get("dados_carregados")
    arquivos_lista = st.session_state.get("arquivos_mpr_lista", [])
    from core.io_readers import _eh_arquivo_ciclador_chines
    modo_mpr_ativo = bool(arquivos_lista and arquivos_lista[0]["nome"].lower().endswith(".mpr"))
    modo_ciclador_chines = bool(arquivos_lista and _eh_arquivo_ciclador_chines(arquivos_lista[0]["bytes"]))

    st.sidebar.markdown("---")

    # 3. Seleção do Sistema (Bateria, Supercapacitor ou Outros) e depois Técnica
    sistemas_opcoes = ["🔋 Bateria", "⚡ Supercapacitor", "🔬 Outros"] if idioma == "Português" else ["🔋 Battery", "⚡ Supercapacitor", "🔬 Others"]
    sistema_escolhido = st.sidebar.radio(
        "Sistema / Categoria:" if idioma == "Português" else "System / Category:",
        sistemas_opcoes,
        horizontal=True,
        key="seletor_sistema",
    )
    eh_supercap = "Supercapacitor" in sistema_escolhido
    tag_sis = "sc" if eh_supercap else ("bat" if ("Bateria" in sistema_escolhido or "Battery" in sistema_escolhido) else "out")

    if "Bateria" in sistema_escolhido or "Battery" in sistema_escolhido:
        opcoes_cat = [
            ("Voltametria Cíclica (CV)" if idioma == "Português" else "Cyclic Voltammetry (CV)", 0),
            ("Análise Cinética CV (b-value & Dunn)" if idioma == "Português" else "CV Kinetic Analysis (b-value & Dunn)", 11),
            ("EIE / Nyquist", 1),
            ("EIE - Bode", 9),
            ("GCD — Carga/Descarga (Bateria)" if idioma == "Português" else "GCD — Charge/Discharge (Battery)", 2),
            ("Análise Incremental de Capacidade (dQ/dV)" if idioma == "Português" else "Incremental Capacity Analysis (dQ/dV)", 10),
            ("Rate Capability (Bateria)" if idioma == "Português" else "Rate Capability (Battery)", 3),
            ("Ciclabilidade Multiplot (Bateria)" if idioma == "Português" else "Multiplot Cyclability (Battery)", 4),
            ("Ciclabilidade & Eficiência Individual" if idioma == "Português" else "Cyclability & Efficiency Individual", 5),
        ]
    elif eh_supercap:
        opcoes_cat = [
            ("Voltametria Cíclica (CV)" if idioma == "Português" else "Cyclic Voltammetry (CV)", 0),
            ("Análise Cinética CV (b-value & Dunn)" if idioma == "Português" else "CV Kinetic Analysis (b-value & Dunn)", 11),
            ("EIE / Nyquist", 1),
            ("EIE - Bode", 9),
            ("EIE - Bode (Capacitância Diferencial C' / C'')" if idioma == "Português" else "EIS - Bode (Differential Capacitance C' / C'')", 16),
            ("CGCD (2 Eletrodos / Janelas)" if idioma == "Português" else "GCD (2-Electrode / Windows)", 6),
            ("CGCD (3 Eletrodos: Ecell, Ewe, Ece)" if idioma == "Português" else "GCD (3-Electrode: Ecell, Ewe, Ece)", 7),
            ("Gráfico de Ragone (Energia vs. Potência)" if idioma == "Português" else "Ragone Plot (Energy vs. Power)", 12),
            ("Rate Capability (Capacitância vs. Corrente)" if idioma == "Português" else "Rate Capability (Capacitance vs. Current)", 13),
            ("Ciclabilidade Multiplot (Supercapacitor)" if idioma == "Português" else "Multiplot Cyclability (Supercapacitor)", 14),
            ("Ciclabilidade & Eficiência Individual (Supercapacitor)" if idioma == "Português" else "Cyclability & Efficiency Individual (Supercapacitor)", 15),
        ]
    else:
        opcoes_cat = [
            ("BET (Adsorção / Dessorção)" if idioma == "Português" else "BET (Adsorption / Desorption)", 8),
        ]

    nomes_opcoes_cat = [item[0] for item in opcoes_cat]
    escolha_tecnica = st.sidebar.selectbox(
        "Selecione a técnica:" if idioma == "Português" else "Select Technique:",
        nomes_opcoes_cat,
        key=f"sel_tec_{sistema_escolhido}",
    )
    tecnica_idx = dict(opcoes_cat)[escolha_tecnica]
    st.session_state["tecnica_idx"] = tecnica_idx

    tags_tecnicas = ["cv", "eie", "gcd", "rate_bat", "cicl", "ce_ind", "sc_2e", "sc_3e", "bet", "bode", "dqdv", "cv_kin", "ragone", "rate_sc", "sc_cicl", "sc_ce_ind", "bode_cap"]
    tag_tec = tags_tecnicas[tecnica_idx]

    # Controles exclusivos para arquivos brutos BioLogic (.mpr) ou Ciclador Chinês (.txt bruto)
    if modo_mpr_ativo or modo_ciclador_chines:
        if modo_ciclador_chines:
            st.sidebar.info(
                f"🔋 Ciclador Bruto (.txt): {len(arquivos_lista)} arquivo(s) — ciclos reais corrigidos"
                if idioma == "Português"
                else f"🔋 Raw Cycler (.txt): {len(arquivos_lista)} file(s) — true cycles corrected"
            )
            from core.io_readers import _parsear_ciclador_chines_bruto
            tem_c1_incompleto = False
            for _arq_ch in arquivos_lista:
                if _eh_arquivo_ciclador_chines(_arq_ch["bytes"]):
                    _, _has_c1 = _parsear_ciclador_chines_bruto(_arq_ch["bytes"])
                    if _has_c1:
                        tem_c1_incompleto = True
                        break
            if tem_c1_incompleto:
                st.sidebar.checkbox(
                    "Incluir primeiro ciclo da célula" if idioma == "Português" else "Include cell's first cycle",
                    value=False,
                    key="chines_incluir_primeiro_ciclo",
                    help="O 1º ciclo deste arquivo inicia já parcialmente carregado (formação). Por padrão ele é omitido."
                    if idioma == "Português"
                    else "The 1st cycle in this file starts partially charged (formation). Omitted by default.",
                )
        elif tecnica_idx == 7 and len(arquivos_lista) > 1:
            st.sidebar.info(
                f"🔌 BioLogic (.mpr): plotando o 1º arquivo ({arquivos_lista[0]['nome']})"
                if idioma == "Português"
                else f"🔌 BioLogic (.mpr): plotting 1st file ({arquivos_lista[0]['nome']})"
            )
        else:
            st.sidebar.info(f"🔌 BioLogic (.mpr): {len(arquivos_lista)} arquivo(s)")

        tecs_com_ciclo = [2, 10] if modo_ciclador_chines else [0, 1, 2, 6, 7, 9, 10, 11, 12, 13, 16]
        if tecnica_idx in tecs_com_ciclo:
            # Em CGCD 3 Eletrodos, lista ciclos apenas do 1º arquivo sem apagar os demais da lista
            arquivos_para_ciclos = [arquivos_lista[0]] if tecnica_idx == 7 else arquivos_lista
            info_ciclos = listar_ciclos_disponiveis_mpr(arquivos_para_ciclos)
            mapa_ciclos_sel = {}
            # Menu de Ciclos por Curva fechado por padrão (expanded=False)
            with st.sidebar.expander("🔄 " + ("Ciclo(s) por Curva (Padrão: Último)" if idioma == "Português" else "Cycle(s) per Curve (Default: Last)"), expanded=False):
                for nome_arq_base, lista_cic in info_ciclos.items():
                    ultimo_cic = [lista_cic[-1]] if lista_cic else [1]
                    modo_cic = st.radio(
                        f"📌 {nome_arq_base} ({len(lista_cic)} ciclo(s)):",
                        ["Último ciclo", "Todos os ciclos", "Escolher ciclo(s)"] if idioma == "Português" else ["Last cycle", "All cycles", "Select cycle(s)"],
                        index=0,
                        horizontal=True,
                        key=f"modo_cic_{tag_tec}_{nome_arq_base}",
                    )
                    if modo_cic in ["Último ciclo", "Last cycle"]:
                        if modo_ciclador_chines:
                            continue
                        mapa_ciclos_sel[nome_arq_base] = ultimo_cic
                    elif modo_cic in ["Todos os ciclos", "All cycles"]:
                        mapa_ciclos_sel[nome_arq_base] = lista_cic
                    else:
                        escolhidos = st.multiselect(
                            f"Ciclos ({nome_arq_base}):",
                            options=lista_cic,
                            default=ultimo_cic,
                            key=f"sel_cic_{tag_tec}_{nome_arq_base}",
                        )
                        mapa_ciclos_sel[nome_arq_base] = escolhidos if escolhidos else ultimo_cic
            st.session_state["mpr_ciclos_por_amostra"] = mapa_ciclos_sel



    # 4. Menu Suspenso Separado: Design
    estilos_padrao_por_tecnica = {
        0: "Linhas (Lines)",       # CV
        1: "Scatter + Lines",      # EIE / Nyquist
        2: "Linhas (Lines)",       # GCD Bateria
        3: "Pontos (Scatter)",     # Rate Capability Bateria
        4: "Linhas (Lines)",       # Ciclabilidade Multiplot
        5: "Scatter + Lines",      # Ciclabilidade & Eficiência Individual
        6: "Linhas (Lines)",       # CGCD 2E
        7: "Linhas (Lines)",       # CGCD 3E
        8: "Scatter + Lines",      # BET
        9: "Scatter + Lines",      # EIE - Bode
        10: "Linhas (Lines)",      # dQ/dV
        11: "Linhas (Lines)",      # Cinética CV
        12: "Scatter + Lines",     # Ragone SC
        13: "Scatter + Lines",     # Rate Capability SC
        14: "Linhas (Lines)",      # Ciclabilidade Multiplot SC
        15: "Scatter + Lines",     # Ciclabilidade & Eficiência Individual SC
        16: "Scatter + Lines",     # Bode Capacitância Diferencial
    }
    opcoes_tracado = ["Pontos (Scatter)", "Linhas (Lines)", "Scatter + Lines"]
    idx_tracado_padrao = opcoes_tracado.index(estilos_padrao_por_tecnica[tecnica_idx])

    mapa_cores, mapa_estilos, mapa_nomes, amostras_detectadas = {}, {}, {}, []
    with st.sidebar.expander("🎨 Design", expanded=False):
        with st.expander("📰 " + ("Preset Editorial, Tema & Estilo" if idioma == "Português" else "Journal Preset, Theme & Style"), expanded=False):
            nome_preset_revista = st.selectbox(
                "Preset de Revista Científica:" if idioma == "Português" else "Scientific Journal Preset:",
                list(PRESETS_REVISTAS.keys()),
                index=0,
                key="journal_preset_selector",
            )
            preset_revista_ativo = PRESETS_REVISTAS[nome_preset_revista]

            dark_mode_ativo = st.toggle(
                "🌙 Dark Mode (Gráfico Escuro)" if idioma == "Português" else "🌙 Dark Mode (Dark Plot)",
                value=False, key="plot_dark_mode",
            )
            tema_visual = obter_tema_visual(dark_mode_ativo)

            nome_paleta_escolhida = st.selectbox(
                "Paleta Global:" if idioma == "Português" else "Global Palette:",
                list(PALETAS_DISPONIVEIS.keys()), index=0, key="global_palette_selector",
            )
            paleta_ativa = PALETAS_DISPONIVEIS[nome_paleta_escolhida]

            modo_tracado_selecionado = st.radio(
                "Estilo de Plotagem:" if idioma == "Português" else "Plot Style:",
                opcoes_tracado,
                index=idx_tracado_padrao,
                horizontal=True,
                key=f"modo_tracado_design_{tag_tec}",
            )

        if dados_bytes is not None:
            try:
                df_temp, tokens_temp = processar_cabecalho_e_dados(dados_bytes)
                amostras_detectadas = identificar_amostras(df_temp, tokens_temp, tecnica_idx)

                with st.expander("🖌️ " + ("Cores, Nomes e Tracejado por Amostra" if idioma == "Português" else "Custom Colors, Names & Dashed Lines"), expanded=False):
                    nome_arq_seg = st.session_state.get("nome_arquivo_anterior", "def")
                    for i, nome_amostra in enumerate(amostras_detectadas):
                        c_nome, c_cor, c_dash = st.columns([2.2, 1.0, 1.2])
                        novo_nome = c_nome.text_input(
                            f"Curva {i+1}", value=nome_amostra, label_visibility="collapsed",
                            key=f"nm_{nome_arq_seg}_{tag_tec}_{nome_amostra}_{i}",
                        )
                        mapa_nomes[nome_amostra] = novo_nome.strip() if novo_nome.strip() else nome_amostra

                        cor_padrao = paleta_ativa[i % len(paleta_ativa)]
                        if dark_mode_ativo and cor_padrao in ["#334155", "#0f172a"]:
                            cor_padrao = "#e2e8f0"
                        mapa_cores[nome_amostra] = c_cor.color_picker(
                            f"Cor {i+1}", cor_padrao, label_visibility="collapsed",
                            key=f"cp_{nome_arq_seg}_{tag_tec}_{nome_paleta_escolhida}_{dark_mode_ativo}_{nome_amostra}_{i}",
                        )

                        default_dash = True if ((tecnica_idx == 5 and i == 0) or (tecnica_idx == 7 and i == 2)) else False
                        e_tracejado = c_dash.checkbox(
                            "---", value=default_dash,
                            key=f"chk_dash_{nome_arq_seg}_{tag_tec}_{nome_amostra}_{i}",
                        )
                        mapa_estilos[nome_amostra] = "--" if e_tracejado else "-"
            except Exception:
                pass

    # 5. Configuração dos Eixos & Legenda
    cv_x_padrao = textos["cv_x_sc"] if eh_supercap else textos["cv_x"]
    rotulos_default_x = [
        cv_x_padrao, textos["eie_x"], textos["gcd_x"], textos["rate_bat_x"],
        textos["cicl_x"], textos["ce_x"], textos["sc_2e_x"], textos["sc_3e_x"],
        textos["bet_x"], textos["bode_x"], textos["dqdv_x"], textos["cv_kin_x"], textos["ragone_x"], textos["sc_rate_x"],
        textos["sc_cicl_x"], textos["sc_ce_x"], textos["bode_cap_x"],
    ]
    rotulos_default_y = [
        textos["cv_y"], textos["eie_y"], textos["gcd_y"], textos["rate_bat_y"],
        textos["cicl_y"], textos["ce_y1"], textos["sc_2e_y"], textos["sc_3e_y1"],
        textos["bet_y"], textos["bode_y1"], textos["dqdv_y"], textos["cv_kin_y"], textos["ragone_y"], textos["sc_rate_y"],
        textos["sc_cicl_y"], textos["sc_ce_y1"], textos["bode_cap_y1"],
    ]

    with st.sidebar.expander("⚙️ " + ("Configuração dos Eixos & Legenda" if idioma == "Português" else "Axis & Legend Settings"), expanded=False):
        eixo_x_input = st.text_input("Eixo X" if idioma == "Português" else "X Axis", rotulos_default_x[tecnica_idx], key=f"eixo_x_{tag_tec}_{tag_sis}_{idioma}")
        eixo_y_input = st.text_input("Eixo Y1" if tecnica_idx in [5, 7, 9] else "Eixo Y", rotulos_default_y[tecnica_idx], key=f"eixo_y_{tag_tec}_{tag_sis}_{idioma}")

        eixo_y2_input = ""
        if tecnica_idx in [5, 7, 9, 15, 16]:
            default_y2 = textos["ce_y2"] if tecnica_idx == 5 else (textos["sc_ce_y2"] if tecnica_idx == 15 else (textos["sc_3e_y2"] if tecnica_idx == 7 else (textos["bode_cap_y2"] if tecnica_idx == 16 else textos["bode_y2"])))
            eixo_y2_input = st.text_input("Eixo Y2" if idioma == "Português" else "Y2 Axis", default_y2, key=f"eixo_y2_{tag_tec}_{idioma}")

        with st.expander("📐 " + ("Limites dos Eixos (Mín / Máx)" if idioma == "Português" else "Axis Limits (Min / Max)"), expanded=False):
            cx1, cx2 = st.columns(2)
            xlim_min = _converter_float(cx1.text_input("X Mín:", "", key=f"xlim_min_{tag_tec}"))
            xlim_max = _converter_float(cx2.text_input("X Máx:", "", key=f"xlim_max_{tag_tec}"))

            cy1, cy2 = st.columns(2)
            ylim_min = _converter_float(cy1.text_input("Y1 Mín:" if tecnica_idx in [5, 7, 9] else "Y Mín:", "", key=f"ylim_min_{tag_tec}"))
            ylim_max = _converter_float(cy2.text_input("Y1 Máx:" if tecnica_idx in [5, 7, 9] else "Y Máx:", "", key=f"ylim_max_{tag_tec}"))

            y2lim_min, y2lim_max = None, None
            if tecnica_idx in [5, 7, 9, 15, 16]:
                cy2_1, cy2_2 = st.columns(2)
                def_y2_min = "0" if tecnica_idx in [5, 15] else ""
                def_y2_max = "110" if tecnica_idx in [5, 15] else ""
                y2lim_min = _converter_float(cy2_1.text_input("Y2 Mín:", def_y2_min, key=f"y2lim_min_{tag_tec}"))
                y2lim_max = _converter_float(cy2_2.text_input("Y2 Máx:", def_y2_max, key=f"y2lim_max_{tag_tec}"))

        with st.expander("📏 " + ("Passo e Subdivisões dos Eixos" if idioma == "Português" else "Axis Step & Subdivisions"), expanded=False):
            st.caption("Vazio = automático" if idioma == "Português" else "Blank = automatic")
            cs_x, cm_x = st.columns(2)
            x_step = _converter_float(cs_x.text_input("Passo X (ex: 100):" if idioma == "Português" else "X Step (e.g. 100):", "", key=f"x_step_{tag_tec}"))
            x_minor = _converter_float(cm_x.text_input("Subdiv. X (ex: 2):" if idioma == "Português" else "X Subdiv. (e.g. 2):", "", key=f"x_minor_{tag_tec}"))

            cs_y, cm_y = st.columns(2)
            y_step = _converter_float(cs_y.text_input("Passo Y1:" if tecnica_idx in [5, 7, 9] else "Passo Y:", "", key=f"y_step_{tag_tec}"))
            y_minor = _converter_float(cm_y.text_input("Subdiv. Y1:" if tecnica_idx in [5, 7, 9] else "Subdiv. Y:", "", key=f"y_minor_{tag_tec}"))

            y2_step, y2_minor = None, None
            if tecnica_idx in [5, 7, 9, 15, 16]:
                cs_y2, cm_y2 = st.columns(2)
                y2_step = _converter_float(cs_y2.text_input("Passo Y2:", "", key=f"y2_step_{tag_tec}"))
                y2_minor = _converter_float(cm_y2.text_input("Subdiv. Y2:", "", key=f"y2_minor_{tag_tec}"))

        posicao_legenda = None
        legenda_horizontal = False
        legenda_xy = None
        if tecnica_idx not in [5, 15]:
            opcoes_legenda = (
                ["best", "upper right", "upper left", "lower right", "lower left", "Personalizada (X, Y)", "Ocultar / Hide"]
                if idioma == "Português"
                else ["best", "upper right", "upper left", "lower right", "lower left", "Custom (X, Y)", "Ocultar / Hide"]
            )
            posicao_legenda = st.selectbox("Posição da Legenda:" if idioma == "Português" else "Legend Position:", opcoes_legenda, index=0, key=f"leg_pos_{tag_tec}")
            if posicao_legenda in ["Personalizada (X, Y)", "Custom (X, Y)"]:
                c_lx, c_ly = st.columns(2)
                legenda_xy = (
                    c_lx.slider("X Legenda" if idioma == "Português" else "Legend X", 0.0, 1.0, 0.78, 0.02, key=f"leg_x_{tag_tec}"),
                    c_ly.slider("Y Legenda" if idioma == "Português" else "Legend Y", 0.0, 1.0, 0.82, 0.02, key=f"leg_y_{tag_tec}"),
                )
            legenda_horizontal = st.checkbox(
                "Legenda em 1 linha (Horizontal)" if idioma == "Português" else "Single-row Legend (Horizontal)",
                value=False,
                disabled=(posicao_legenda == "Ocultar / Hide"),
                key=f"leg_horiz_{tag_tec}",
            )

        limites_manuais = {
            "xlim": (xlim_min, xlim_max),
            "ylim": (ylim_min, ylim_max),
            "y2lim": (y2lim_min, y2lim_max),
            "x_step": x_step,
            "y_step": y_step,
            "y2_step": y2_step,
            "x_minor": x_minor,
            "y_minor": y_minor,
            "y2_minor": y2_minor,
            "legenda_xy": legenda_xy,
        }

    # 6. Parâmetros Específicos da Técnica
    params = {}
    precisa_massa_ativa = (not modo_ciclador_chines) and ((tecnica_idx in [2, 3, 4, 5, 6, 7, 10, 12, 13, 14, 15, 16]) or (tecnica_idx == 0 and eh_supercap))
    with st.sidebar.expander("🔬 " + ("Parâmetros da Técnica" if idioma == "Português" else "Technique Parameters"), expanded=False):
        if precisa_massa_ativa:
            with st.expander("⚖️ " + ("Massa Ativa (mg)" if idioma == "Português" else "Active Mass (mg)"), expanded=True):
                if tecnica_idx in [12, 13] and len(amostras_detectadas) > 1:
                    massas_am_dict = {}
                    for idx_m, am_nome in enumerate(amostras_detectadas):
                        rot_exib = mapa_nomes.get(am_nome, am_nome)
                        val_m = st.number_input(
                            f"{rot_exib} (mg):",
                            min_value=0.001,
                            value=float(st.session_state.get("mpr_massa_ativa_mg", 1.000)),
                            step=0.100,
                            format="%.3f",
                            key=f"mass_am_{tag_tec}_{am_nome}_{idx_m}",
                        )
                        massas_am_dict[am_nome] = float(val_m)
                    params["massas_por_amostra"] = massas_am_dict
                else:
                    st.number_input(
                        "Massa ativa total / célula (mg):" if (idioma == "Português" and tecnica_idx == 7)
                        else ("Total / cell active mass (mg):" if tecnica_idx == 7
                        else ("Massa ativa (mg):" if idioma == "Português" else "Active mass (mg):")),
                        min_value=0.001,
                        value=float(st.session_state.get("mpr_massa_ativa_mg", 1.000)),
                        step=0.100,
                        format="%.3f",
                        key="mpr_massa_ativa_mg",
                    )
                    if tecnica_idx in [12, 13] and len(amostras_detectadas) == 1:
                        params["massas_por_amostra"] = {amostras_detectadas[0]: float(st.session_state.get("mpr_massa_ativa_mg", 1.000))}
                if tecnica_idx == 7:
                    cm_pos, cm_neg = st.columns(2)
                    params["massa_pos_mg"] = cm_pos.number_input(
                        "Massa Ewe (+) [mg]:" if idioma == "Português" else "Mass Ewe (+) [mg]:",
                        min_value=0.001,
                        value=round(float(st.session_state.get("mpr_massa_ativa_mg", 1.000)) / 2.0, 3),
                        step=0.100,
                        format="%.3f",
                        key="sc3e_massa_pos_mg",
                    )
                    params["massa_neg_mg"] = cm_neg.number_input(
                        "Massa Ece (-) [mg]:" if idioma == "Português" else "Mass Ece (-) [mg]:",
                        min_value=0.001,
                        value=round(float(st.session_state.get("mpr_massa_ativa_mg", 1.000)) / 2.0, 3),
                        step=0.100,
                        format="%.3f",
                        key="sc3e_massa_neg_mg",
                    )
        if tecnica_idx == 0:
            taxas_cv_dict = {}
            if not modo_mpr_ativo:
                st.caption("⚡ " + ("Taxa de Varredura para Cálculos (mV/s)" if idioma == "Português" else "Scan Rate for Calculations (mV/s)"))
                modo_taxa_cv = st.radio(
                    "Modo de entrada (Taxa CV):" if idioma == "Português" else "Scan Rate input mode:",
                    ["Taxa única (mV/s)", "Discriminada por curva"] if idioma == "Português" else ["Single rate (mV/s)", "Per curve"],
                    horizontal=True,
                    key="cv_modo_taxa_input",
                )
                if modo_taxa_cv in ["Taxa única (mV/s)", "Single rate (mV/s)"]:
                    taxa_unica_cv = _converter_float(
                        st.text_input(
                            "Taxa de varredura (mV/s):" if idioma == "Português" else "Scan rate (mV/s):",
                            value="",
                            placeholder="ex: 10",
                            key="cv_taxa_unica_num",
                        )
                    )
                    if taxa_unica_cv is not None and taxa_unica_cv > 0:
                        taxas_cv_dict["__unica__"] = taxa_unica_cv
                else:
                    for idx_c, am_nome in enumerate(amostras_detectadas):
                        rot_exib = mapa_nomes.get(am_nome, am_nome)
                        t_c_val = _converter_float(
                            st.text_input(
                                f"{rot_exib} (mV/s):",
                                value="",
                                placeholder="ex: 10",
                                key=f"cv_taxa_curva_{am_nome}_{idx_c}",
                            )
                        )
                        if t_c_val is not None and t_c_val > 0:
                            taxas_cv_dict[am_nome] = t_c_val
                st.markdown("---")
            params["taxas_por_curva"] = taxas_cv_dict
            with st.expander("📍 " + ("Anotações & Setas no Gráfico" if idioma == "Português" else "Plot Badges & Arrows"), expanded=False):
                params["exibir_balao_cv"] = st.checkbox(
                    "Exibir balão de velocidade no gráfico" if idioma == "Português" else "Show scan rate badge on plot",
                    value=False,
                    key="cv_balao_chk",
                )
                if params["exibir_balao_cv"]:
                    default_txt_balao = ""
                    if "__unica__" in taxas_cv_dict:
                        v_fmt = f"{taxas_cv_dict['__unica__']:g}".replace(".", ",") if idioma == "Português" else f"{taxas_cv_dict['__unica__']:g}"
                        default_txt_balao = rf"{v_fmt}\ \mathrm{{mV\ s^{{-1}}}}"
                    params["velocidade"] = st.text_input(
                        "Texto do balão:" if idioma == "Português" else "Badge text:",
                        value=default_txt_balao,
                        key=f"cv_v_{idioma}",
                    )
                    cv_v1, cv_v2 = st.columns(2)
                    params["pos_velocidade"] = (
                        cv_v1.slider("X Velocidade", 0.0, 0.90, 0.04, 0.02, key="cv_vx"),
                        cv_v2.slider("Y Velocidade", 0.0, 0.95, 0.93, 0.02, key="cv_vy"),
                    )
                else:
                    params["velocidade"] = ""

                params["exibir_setas"] = st.checkbox("Exibir Carga / Descarga" if idioma == "Português" else "Show Charge / Discharge", True, key="cv_arrows")
                if params["exibir_setas"]:
                    c1, c2 = st.columns(2)
                    params["pos_carga"] = (c1.slider("X Carga", 0.0, 0.95, 0.35, 0.02, key="cv_cx"), c2.slider("Y Carga", 0.0, 0.95, 0.58, 0.02, key="cv_cy"))
                    c3, c4 = st.columns(2)
                    params["pos_descarga"] = (c3.slider("X Desc.", 0.0, 0.95, 0.65, 0.02, key="cv_dx"), c4.slider("Y Desc.", 0.0, 0.95, 0.38, 0.02, key="cv_dy"))

        elif tecnica_idx == 1:
            params["aspect_equal"] = st.checkbox("Proporção 1:1 (Aspect Equal)" if idioma == "Português" else "1:1 Aspect Ratio", True, key="eie_aspect_eq")
            with st.expander("🔍 " + ("Inset (Altas Frequências)" if idioma == "Português" else "High-Frequency Inset"), expanded=False):
                params["exibir_inset"] = st.checkbox("Exibir Inset (Altas Frequências)" if idioma == "Português" else "Show Inset (High Frequencies)", False, key="eie_inset_chk")
                if params["exibir_inset"]:
                    ci1, ci2 = st.columns(2)
                    ix = ci1.slider("Inset X", 0.05, 0.65, 0.48, 0.02, key="eie_ix")
                    iy = ci2.slider("Inset Y", 0.05, 0.65, 0.42, 0.02, key="eie_iy")
                    params["inset_bbox"] = (ix, iy, 0.44, 0.42)
                    cx1, cx2 = st.columns(2)
                    cy1, cy2 = st.columns(2)
                    params["inset_limites"] = {
                        "xmin": _converter_float(cx1.text_input("Inset X Mín:", "", key="eie_ixmin")),
                        "xmax": _converter_float(cx2.text_input("Inset X Máx:", "", key="eie_ixmax")),
                        "ymin": _converter_float(cy1.text_input("Inset Y Mín:", "", key="eie_iymin")),
                        "ymax": _converter_float(cy2.text_input("Inset Y Máx:", "", key="eie_iymax")),
                    }
            with st.expander("🔌 " + ("Circuito Equivalente (Imagem)" if idioma == "Português" else "Equivalent Circuit (Image)"), expanded=False):
                params["circuito"] = st.file_uploader("Circuito Equivalente (PNG/JPG)", type=["png", "jpg", "jpeg"], key="circuit_uploader")
                if params["circuito"] is not None:
                    cc1, cc2 = st.columns(2)
                    params["pos_circuito"] = (cc1.slider("Circuito X", 0.05, 0.95, 0.62, 0.02, key="eie_cx"), cc2.slider("Circuito Y", 0.05, 0.95, 0.78, 0.02, key="eie_cy"))
                    params["zoom_circuito"] = st.slider("Zoom Circuito", 0.15, 0.80, 0.36, 0.02, key="eie_cz")

        elif tecnica_idx == 2:
            params["exibir_delta_e"] = st.checkbox("Exibir indicador ΔE" if idioma == "Português" else "Show ΔE indicator", False, key="gcd_de_chk")
            if params["exibir_delta_e"]:
                params["delta_e_texto"] = st.text_input("Texto ΔE:", value=r"$\Delta E$", key="gcd_de_txt")
                params["delta_e_x"] = st.slider("Posição X:", 0.05, 0.90, 0.40, 0.01, key="gcd_de_x")
                cd1, cd2 = st.columns(2)
                params["delta_e_topo"] = cd1.slider("Topo (Carga):", 0.05, 0.95, 0.58, 0.01, key="gcd_de_top")
                params["delta_e_base"] = cd2.slider("Base (Descarga):", 0.05, 0.95, 0.46, 0.01, key="gcd_de_bot")
                params["delta_e_lado"] = st.radio("Lado do texto:", ["Direita / Right", "Esquerda / Left"], horizontal=True, key="gcd_de_side")

        elif tecnica_idx == 3:
            def_taxas = "0,1 C; 0,2 C; 0,5 C; 1 C; 2 C; 0,1 C" if idioma == "Português" else "0.1 C; 0.2 C; 0.5 C; 1 C; 2 C; 0.1 C"
            taxas_str = st.text_input(
                "Rótulos das Zonas (separados por ;):" if idioma == "Português" else "Zone Labels (separated by ;):",
                value=def_taxas,
                key=f"rate_z_bat6_{idioma}",
            )
            sep = ";" if ";" in taxas_str else ","
            partes = [t.strip() for t in taxas_str.split(sep) if t.strip()]
            params["labels_zonas"] = partes if len(partes) >= 1 else None

        elif tecnica_idx in [4, 14]:
            def_rate_tag = r"1\ \mathrm{A\ g^{-1}}" if tecnica_idx == 14 else textos["cicl_rate"]
            params["rate_tag"] = st.text_input("Tag de Taxa / Corrente:" if idioma == "Português" else "Rate / Current Tag:", def_rate_tag, key=f"cicl_rt_{tag_tec}_{idioma}")
            cr1, cr2 = st.columns(2)
            params["pos_rate"] = (cr1.slider("X Taxa", 0.0, 0.90, 0.04, 0.02, key=f"cicl_rx_{tag_tec}"), cr2.slider("Y Taxa", 0.0, 0.95, 0.93, 0.02, key=f"cicl_ry_{tag_tec}"))

        elif tecnica_idx in [5, 15]:
            def_rate_ind = r"1\ \mathrm{A\ g^{-1}}" if tecnica_idx == 15 else textos["cicl_rate"]
            params["rate_tag"] = st.text_input("Tag de Taxa / Corrente:" if idioma == "Português" else "Rate / Current Tag:", def_rate_ind, key=f"ce_rt_{tag_tec}_{idioma}")
            cr1, cr2 = st.columns(2)
            params["pos_rate"] = (cr1.slider("X Taxa", 0.0, 0.90, 0.04, 0.02, key=f"ce_rx_{tag_tec}"), cr2.slider("Y Taxa", 0.0, 0.95, 0.78, 0.02, key=f"ce_ry_{tag_tec}"))
            key_nm_ind = "sc_ce_nm" if tecnica_idx == 15 else "ce_nm"
            params["nome_amostra"] = st.text_input("Nome da Amostra:", Path(st.session_state.get("nome_arquivo_anterior", "Amostra")).stem, key=key_nm_ind)
            params["patamar_ref"] = _converter_float(st.text_input("Patamar de Referência (0 = off):", "0", key=f"ce_pat_{tag_tec}")) or 0.0
            tem_ee_disponivel = False
            if dados_bytes is not None:
                try:
                    from tecnicas.ciclabilidade import extrair_dados_ciclabilidade_individual
                    _, _, _, _ee_probe = extrair_dados_ciclabilidade_individual(dados_bytes, idioma=idioma)
                    tem_ee_disponivel = bool(_ee_probe is not None and len(_ee_probe) > 0)
                except Exception:
                    tem_ee_disponivel = False

            if tem_ee_disponivel:
                params["exibir_eficiencia_energetica"] = st.checkbox(
                    "Exibir Eficiência Energética (%) no eixo Y2" if idioma == "Português" else "Show Energy Efficiency (%) on Y2 axis",
                    value=True,
                    key=f"ce_show_ee_{tag_tec}",
                )
            else:
                params["exibir_eficiencia_energetica"] = False

        elif tecnica_idx == 6:
            dens_sc2_dict = {}
            if not modo_mpr_ativo:
                st.caption("⚡ " + ("Densidade de Corrente para Cálculos (A/g)" if idioma == "Português" else "Current Density for Calculations (A/g)"))
                modo_j_sc2 = st.radio(
                    "Modo de entrada (Densidade I):" if idioma == "Português" else "Current Density input mode:",
                    ["Densidade única (A/g)", "Discriminada por curva"] if idioma == "Português" else ["Single density (A/g)", "Per curve"],
                    horizontal=True,
                    key="sc2e_modo_j_input",
                )
                if modo_j_sc2 in ["Densidade única (A/g)", "Single density (A/g)"]:
                    j_unica_val = _converter_float(
                        st.text_input(
                            "Densidade de corrente (A/g):" if idioma == "Português" else "Current density (A/g):",
                            value="",
                            placeholder="ex: 1,0",
                            key="sc2e_j_unica_num",
                        )
                    )
                    if j_unica_val is not None and j_unica_val > 0:
                        dens_sc2_dict["__unica__"] = j_unica_val
                else:
                    for idx_c, am_nome in enumerate(amostras_detectadas):
                        rot_exib = mapa_nomes.get(am_nome, am_nome)
                        j_c_val = _converter_float(
                            st.text_input(
                                f"{rot_exib} (A/g):",
                                value="",
                                placeholder="ex: 1,0",
                                key=f"sc2e_j_curva_{am_nome}_{idx_c}",
                            )
                        )
                        if j_c_val is not None and j_c_val > 0:
                            dens_sc2_dict[am_nome] = j_c_val
                st.markdown("---")
            params["densidades_por_curva"] = dens_sc2_dict
            params["exibir_densidade_corrente"] = st.checkbox(
                "Exibir balão de densidade no gráfico" if idioma == "Português" else "Show current density badge on plot",
                value=False,
                key="sc2e_j_badge_chk",
            )
            if params["exibir_densidade_corrente"]:
                def_j_txt = r"1\ \mathrm{A\ g^{-1}}"
                if "__unica__" in dens_sc2_dict:
                    j_fmt = f"{dens_sc2_dict['__unica__']:g}".replace(".", ",") if idioma == "Português" else f"{dens_sc2_dict['__unica__']:g}"
                    def_j_txt = rf"{j_fmt}\ \mathrm{{A\ g^{{-1}}}}"
                params["texto_densidade_corrente"] = st.text_input(
                    "Texto do balão:" if idioma == "Português" else "Badge text:",
                    value=def_j_txt,
                    key="sc2e_j_badge_txt",
                )
                cj1, cj2 = st.columns(2)
                params["pos_densidade_corrente"] = (
                    cj1.slider("X Balão", 0.0, 0.90, 0.05, 0.02, key="sc2e_jx"),
                    cj2.slider("Y Balão", 0.0, 0.95, 0.90, 0.02, key="sc2e_jy"),
                )

        elif tecnica_idx == 7:
            j_unica_sc3 = None
            if not modo_mpr_ativo:
                j_unica_sc3 = _converter_float(
                    st.text_input(
                        "⚡ Densidade de corrente (A/g):" if idioma == "Português" else "⚡ Current density (A/g):",
                        value="",
                        placeholder="ex: 1,0",
                        key="sc3e_j_unica_num",
                    )
                )
                st.markdown("---")
            params["densidades_por_curva"] = {"__unica__": j_unica_sc3} if (j_unica_sc3 is not None and j_unica_sc3 > 0) else {}
            params["tag_amostra"] = st.text_input("Identificação da Amostra:" if idioma == "Português" else "Sample Badge:", Path(st.session_state.get("nome_arquivo_anterior", "")).stem, key="sc3_tag")
            cs1, cs2 = st.columns(2)
            params["pos_amostra"] = (cs1.slider("X Amostra", 0.0, 0.90, 0.05, 0.02, key="sc3_ax"), cs2.slider("Y Amostra", 0.0, 0.95, 0.90, 0.02, key="sc3_ay"))
            params["exibir_zero_y2"] = st.checkbox("Linha de referência 0 V (Y2)" if idioma == "Português" else "0 V reference line (Y2)", True, key="sc3_z0")

            params["exibir_densidade_corrente"] = st.checkbox(
                "Exibir balão de densidade no gráfico" if idioma == "Português" else "Show current density badge on plot",
                value=False,
                key="sc3e_j_badge_chk",
            )
            if params["exibir_densidade_corrente"]:
                def_j3_txt = r"1\ \mathrm{A\ g^{-1}}"
                if j_unica_sc3 is not None and j_unica_sc3 > 0:
                    j3_fmt = f"{j_unica_sc3:g}".replace(".", ",") if idioma == "Português" else f"{j_unica_sc3:g}"
                    def_j3_txt = rf"{j3_fmt}\ \mathrm{{A\ g^{{-1}}}}"
                params["texto_densidade_corrente"] = st.text_input(
                    "Texto do balão:" if idioma == "Português" else "Badge text:",
                    value=def_j3_txt,
                    key="sc3e_j_badge_txt",
                )
                cj3_1, cj3_2 = st.columns(2)
                params["pos_densidade_corrente"] = (
                    cj3_1.slider("X Densidade", 0.0, 0.90, 0.05, 0.02, key="sc3e_jx"),
                    cj3_2.slider("Y Densidade", 0.0, 0.95, 0.80, 0.02, key="sc3e_jy"),
                )

        elif tecnica_idx == 8:
            areas_bet = {}
            for amostra in amostras_detectadas:
                val = _converter_float(st.text_input(f"{amostra} (m²/g):", "", placeholder="ex: 1200", key=f"bet_a_{amostra}"))
                if val is not None:
                    areas_bet[amostra] = val
            params["areas_bet"] = areas_bet
            params["exibir_inset"] = st.checkbox("Exibir Inset (Zoom)" if idioma == "Português" else "Show Inset (Zoom)", False, key="bet_ins_chk")
            if params["exibir_inset"]:
                ci1, ci2 = st.columns(2)
                params["inset_bbox"] = (ci1.slider("Inset X", 0.05, 0.65, 0.54, 0.02, key="bet_ix"), ci2.slider("Inset Y", 0.05, 0.65, 0.22, 0.02, key="bet_iy"), 0.38, 0.28)
                cx1, cx2 = st.columns(2)
                cy1, cy2 = st.columns(2)
                params["inset_limites"] = {
                    "xmin": _converter_float(cx1.text_input("Inset X Mín:", "", key="bet_ixmin")),
                    "xmax": _converter_float(cx2.text_input("Inset X Máx:", "", key="bet_ixmax")),
                    "ymin": _converter_float(cy1.text_input("Inset Y Mín:", "", key="bet_iymin")),
                    "ymax": _converter_float(cy2.text_input("Inset Y Máx:", "", key="bet_iymax")),
                }

        elif tecnica_idx == 9:
            params["bode_y1_log"] = st.checkbox(
                "Eixo Y1 (|Z|) em escala logarítmica" if idioma == "Português" else "Y1 Axis (|Z|) in logarithmic scale",
                value=True,
                key="bode_y1_log_chk",
            )
            params["exibir_freq_joelho"] = st.checkbox(
                "Marcar Frequência de Joelho (f₀, Fase = -45°)" if idioma == "Português" else "Mark Knee Frequency (f₀, Phase = -45°)",
                value=eh_supercap,
                key=f"bode_f0_chk_{tag_sis}",
            )
            if params["exibir_freq_joelho"]:
                f0_manual_str = st.text_input(
                    "Frequência de joelho manual em Hz (vazio = auto -45°):" if idioma == "Português" else "Manual knee frequency in Hz (blank = auto -45°):",
                    value="",
                    key="bode_f0_manual_input",
                )
                params["freq_joelho_manual"] = _converter_float(f0_manual_str)

        elif tecnica_idx == 10:
            params["dqdv_janela"] = st.slider(
                "Suavização (pontos da janela):" if idioma == "Português" else "Smoothing (window points):",
                min_value=1,
                max_value=51,
                value=11,
                step=2,
                key="dqdv_smooth_win",
            )
            params["dqdv_passo_mv"] = st.number_input(
                "Passo de potencial dV (mV):" if idioma == "Português" else "Potential step dV (mV):",
                min_value=0.5,
                max_value=25.0,
                value=3.0,
                step=0.5,
                format="%.1f",
                key="dqdv_dv_step",
            )
            cdq1, cdq2 = st.columns(2)
            params["dqdv_exibir_carga"] = cdq1.checkbox("Exibir Carga (+)" if idioma == "Português" else "Show Charge (+)", True, key="dqdv_show_chg")
            params["dqdv_exibir_descarga"] = cdq2.checkbox("Exibir Descarga (-)" if idioma == "Português" else "Show Discharge (-)", True, key="dqdv_show_dchg")

        elif tecnica_idx == 11:
            opcoes_kin = (
                [
                    "Decomposição de Dunn (Capacitivo vs. Difusional)",
                    "Lei de Potência (b-value: log ip vs. log v)",
                    "Barras Empilhadas (% Capacitivo vs. Difusional)",
                ]
                if idioma == "Português"
                else [
                    "Dunn Decomposition (Capacitive vs. Diffusion)",
                    "Power Law (b-value: log ip vs. log v)",
                    "Stacked Bars (% Capacitive vs. Diffusion)",
                ]
            )
            params["modo_grafico_cinetica"] = st.selectbox(
                "Visualização Cinética:" if idioma == "Português" else "Kinetic View:",
                opcoes_kin,
                index=0,
                key=f"cv_kin_view_{idioma}",
            )
            taxa_alvo_dunn = _converter_float(
                st.text_input(
                    "Taxa alvo para sombreado de Dunn (mV/s) [vazio = central]:"
                    if idioma == "Português"
                    else "Target scan rate for Dunn shading (mV/s) [blank = middle]:",
                    value="",
                    placeholder="ex: 20",
                    key="cv_kin_target_rate",
                )
            )
            params["taxa_alvo_dunn_mvs"] = taxa_alvo_dunn

            opcoes_esr_ui = (
                ["Sem compensação (0 Ω)", "Estimativa automática pelos CVs", "Valor manual (Ω)"]
                if idioma == "Português"
                else ["No compensation (0 Ω)", "Auto-estimate from CVs", "Manual value (Ω)"]
            )
            escolha_esr_ui = st.selectbox(
                "⚡ Compensação de Queda Ôhmica (IR / ESR):" if idioma == "Português" else "⚡ Ohmic Drop Compensation (IR / ESR):",
                opcoes_esr_ui,
                index=0,
                key=f"cv_kin_esr_mode_{idioma}",
            )
            if "automática" in escolha_esr_ui or "Auto-estimate" in escolha_esr_ui:
                params["modo_esr"] = "auto"
                params["valor_esr_ohm"] = 0.0
            elif "manual" in escolha_esr_ui or "Manual" in escolha_esr_ui:
                params["modo_esr"] = "manual"
                params["valor_esr_ohm"] = _converter_float(
                    st.text_input(
                        "Valor de ESR (Ω):" if idioma == "Português" else "ESR value (Ω):",
                        value="5,0" if idioma == "Português" else "5.0",
                        key="cv_kin_esr_manual_val",
                    )
                ) or 0.0
            else:
                params["modo_esr"] = "sem"
                params["valor_esr_ohm"] = 0.0

            taxas_kin_dict = {}
            if not modo_mpr_ativo:
                with st.expander("📝 " + ("Taxas manuais por curva (.txt / .dat)" if idioma == "Português" else "Manual scan rates per curve (.txt / .dat)"), expanded=False):
                    for idx_k, am_nome in enumerate(amostras_detectadas):
                        rot_exib = mapa_nomes.get(am_nome, am_nome)
                        tk_val = _converter_float(
                            st.text_input(
                                f"{rot_exib} (mV/s):",
                                value="",
                                placeholder="ex: 10",
                                key=f"cv_kin_rate_{am_nome}_{idx_k}",
                            )
                        )
                        if tk_val is not None and tk_val > 0:
                            taxas_kin_dict[am_nome] = tk_val
            params["taxas_por_curva"] = taxas_kin_dict

        elif tecnica_idx in [12, 13]:
            params["agrupar_por_amostra"] = st.checkbox(
                "Agrupar curvas por amostra (comparar múltiplos materiais)"
                if idioma == "Português"
                else "Group curves by sample (compare multiple materials)",
                value=True,
                key=f"sc_rr_group_{tag_tec}",
            )
            if tecnica_idx == 12:
                crg1, crg2 = st.columns(2)
                params["escala_log_ragone"] = crg1.checkbox("Escala Log-Log" if idioma == "Português" else "Log-Log Scale", True, key="ragone_log_chk")
                params["exibir_tempos_descarga"] = crg2.checkbox("Linhas de tempo (1s–1000s)" if idioma == "Português" else "Discharge time lines (1s–1000s)", True, key="ragone_tau_chk")
            else:
                crt1, crt2 = st.columns(2)
                params["usar_capacitancia_integral"] = crt1.checkbox("Capacitância Integral" if idioma == "Português" else "Integral Capacitance", True, key="sc_rate_int_chk")
                params["exibir_retencao_badge"] = crt2.checkbox("Exibir Retenção (%) na legenda" if idioma == "Português" else "Show Retention (%) in legend", True, key="sc_rate_ret_chk")

            dens_lista_amostra = {}
            if not modo_mpr_ativo:
                with st.expander("⚡ " + ("Sequência de densidades de corrente por amostra (A/g)" if idioma == "Português" else "Current density sequence per sample (A/g)"), expanded=False):
                    st.caption(
                        "Separe os valores por ponto e vírgula (ex: 0,05; 0,1; 0,2; 0,5; 1; 2; 4)"
                        if idioma == "Português"
                        else "Separate values with semicolons (e.g. 0.05; 0.1; 0.2; 0.5; 1; 2; 4)"
                    )
                    for idx_r, am_nome in enumerate(amostras_detectadas):
                        rot_exib = mapa_nomes.get(am_nome, am_nome)
                        seq_str = st.text_input(
                            f"{rot_exib} (A/g):",
                            value="",
                            placeholder="0,05; 0,1; 0,2; 0,5; 1; 2; 4",
                            key=f"sc_rr_seq_{tag_tec}_{am_nome}_{idx_r}",
                        )
                        seq_vals = _parsear_sequencia_floats(seq_str)
                        if seq_vals:
                            dens_lista_amostra[am_nome] = seq_vals
            params["densidades_lista_por_amostra"] = dens_lista_amostra
            params["densidades_por_curva"] = {}

        elif tecnica_idx == 16:
            params["exibir_freq_joelho"] = st.checkbox(
                "Marcar Frequência de Joelho f₀ (Fase = -45°) e τ₀" if idioma == "Português" else "Mark Knee Frequency f₀ (Phase = -45°) & τ₀",
                value=True,
                key="bode_cap_f0_chk",
            )
            if params["exibir_freq_joelho"]:
                f0_cap_str = st.text_input(
                    "Frequência de joelho manual em Hz (vazio = auto -45°):" if idioma == "Português" else "Manual knee frequency in Hz (blank = auto -45°):",
                    value="",
                    key="bode_cap_f0_manual_input",
                )
                params["freq_joelho_manual"] = _converter_float(f0_cap_str)


    st.title(f"{sistema_escolhido} — {escolha_tecnica}")

    # 7. Roteamento e Renderização
    if dados_bytes is not None:
        try:
            fig = None
            if tecnica_idx == 0:
                fig = _chamar_plot_seguro(gerar_plot_cv, 
                    dados_bytes, params["velocidade"], eixo_x_input, eixo_y_input,
                    textos["cv_charge"], textos["cv_discharge"], mapa_cores, mapa_estilos, mapa_nomes,
                    limites_manuais, posicao_legenda, tema_visual, idioma=idioma,
                    exibir_setas=params["exibir_setas"], pos_carga=params.get("pos_carga", (0.35, 0.58)),
                    pos_descarga=params.get("pos_descarga", (0.65, 0.38)),
                    modo_tracado=modo_tracado_selecionado,
                    pos_velocidade=params.get("pos_velocidade", (0.04, 0.93)),
                    legenda_horizontal=legenda_horizontal,
                )
            elif tecnica_idx == 1:
                fig = _chamar_plot_seguro(gerar_plot_eie, 
                    dados_bytes, params.get("circuito"), eixo_x_input, eixo_y_input,
                    mapa_cores, mapa_estilos, mapa_nomes, limites_manuais, posicao_legenda, tema_visual,
                    idioma=idioma, pos_circuito=params.get("pos_circuito", (0.62, 0.78)),
                    zoom_circuito=params.get("zoom_circuito", 0.36),
                    modo_tracado=modo_tracado_selecionado,
                    aspect_equal=params["aspect_equal"], exibir_inset=params["exibir_inset"],
                    inset_bbox=params.get("inset_bbox", (0.48, 0.42, 0.44, 0.42)),
                    inset_limites=params.get("inset_limites"),
                    legenda_horizontal=legenda_horizontal,
                )
            elif tecnica_idx == 2:
                fig = _chamar_plot_seguro(gerar_plot_gcd, 
                    dados_bytes, eixo_x_input, eixo_y_input, mapa_cores, mapa_estilos, mapa_nomes,
                    limites_manuais, posicao_legenda, tema_visual, idioma=idioma,
                    exibir_delta_e=params["exibir_delta_e"], delta_e_texto=params.get("delta_e_texto", r"$\Delta E$"),
                    delta_e_x_frac=params.get("delta_e_x", 0.40), delta_e_y_topo=params.get("delta_e_topo", 0.58),
                    delta_e_y_base=params.get("delta_e_base", 0.46), delta_e_lado_texto=params.get("delta_e_lado", "Direita / Right"),
                    modo_tracado=modo_tracado_selecionado,
                    legenda_horizontal=legenda_horizontal,
                )
            elif tecnica_idx == 14:
                fig = _chamar_plot_seguro(gerar_plot_ciclabilidade,
                    dados_bytes, params["rate_tag"], params["pos_rate"], eixo_x_input, eixo_y_input,
                    mapa_cores, mapa_estilos, mapa_nomes, limites_manuais, posicao_legenda, tema_visual,
                    idioma=idioma, unidade_y=r"F\ g^{-1}", modo_tracado=modo_tracado_selecionado,
                    legenda_horizontal=legenda_horizontal,
                )
            elif tecnica_idx == 16:
                fig = _chamar_plot_seguro(gerar_plot_bode_capacitancia,
                    dados_bytes, eixo_x_input, eixo_y_input, eixo_y2_input,
                    mapa_cores, mapa_estilos, mapa_nomes, limites_manuais, posicao_legenda, tema_visual,
                    idioma=idioma,
                    massa_mg=st.session_state.get("mpr_massa_ativa_mg", 1.0),
                    modo_tracado=modo_tracado_selecionado,
                    exibir_freq_joelho=params.get("exibir_freq_joelho", True),
                    freq_joelho_manual=params.get("freq_joelho_manual"),
                    legenda_horizontal=legenda_horizontal,
                )
            elif tecnica_idx == 3:
                fig = _chamar_plot_seguro(gerar_plot_rate, 
                    dados_bytes, eixo_x_input, eixo_y_input, mapa_cores, mapa_estilos, mapa_nomes,
                    limites_manuais, posicao_legenda, tema_visual, idioma=idioma,
                    labels_zonas=params.get("labels_zonas"),
                    modo_tracado=modo_tracado_selecionado,
                    legenda_horizontal=legenda_horizontal,
                )
            elif tecnica_idx == 14:
                fig = _chamar_plot_seguro(gerar_plot_ciclabilidade,
                    dados_bytes, params["rate_tag"], params["pos_rate"], eixo_x_input, eixo_y_input,
                    mapa_cores, mapa_estilos, mapa_nomes, limites_manuais, posicao_legenda, tema_visual,
                    idioma=idioma, unidade_y=r"F\ g^{-1}", modo_tracado=modo_tracado_selecionado,
                    legenda_horizontal=legenda_horizontal,
                )
            elif tecnica_idx == 16:
                fig = _chamar_plot_seguro(gerar_plot_bode_capacitancia,
                    dados_bytes, eixo_x_input, eixo_y_input, eixo_y2_input,
                    mapa_cores, mapa_estilos, mapa_nomes, limites_manuais, posicao_legenda, tema_visual,
                    idioma=idioma,
                    massa_mg=st.session_state.get("mpr_massa_ativa_mg", 1.0),
                    modo_tracado=modo_tracado_selecionado,
                    exibir_freq_joelho=params.get("exibir_freq_joelho", True),
                    freq_joelho_manual=params.get("freq_joelho_manual"),
                    legenda_horizontal=legenda_horizontal,
                )
            elif tecnica_idx == 4:
                fig = _chamar_plot_seguro(gerar_plot_ciclabilidade, 
                    dados_bytes, params["rate_tag"], params["pos_rate"], eixo_x_input, eixo_y_input,
                    mapa_cores, mapa_estilos, mapa_nomes, limites_manuais, posicao_legenda, tema_visual,
                    idioma=idioma, modo_tracado=modo_tracado_selecionado,
                    legenda_horizontal=legenda_horizontal,
                )
            elif tecnica_idx in [5, 15]:
                cor_cap_def = "#e2e8f0" if dark_mode_ativo else "#0f172a"
                cor_eff_def = "#38bdf8" if dark_mode_ativo else "#2563eb"
                cor_ee_def = "#10b981"
                un_y_ind = r"F\ g^{-1}" if tecnica_idx == 15 else r"mAh\ g^{-1}"
                fig = _chamar_plot_seguro(gerar_plot_ciclabilidade_eficiencia, 
                    dados_bytes, eixo_x_input, eixo_y_input, eixo_y2_input,
                    nome_amostra=params["nome_amostra"], rate_tag=params["rate_tag"], pos_rate=params["pos_rate"],
                    cor_capacidade=mapa_cores.get("Discharge Capacity", cor_cap_def),
                    cor_eficiencia=mapa_cores.get("Coulombic Efficiency", cor_eff_def),
                    estilo_capacidade=mapa_estilos.get("Discharge Capacity", "--"),
                    estilo_eficiencia=mapa_estilos.get("Coulombic Efficiency", "-"),
                    exibir_eficiencia_energetica=params.get("exibir_eficiencia_energetica", False),
                    modo_tracado=modo_tracado_selecionado,
                    limites_manuais=limites_manuais, patamar_ref=params["patamar_ref"],
                    tema=tema_visual, idioma=idioma,
                    unidade_y=un_y_ind,
                )
            elif tecnica_idx == 6:
                sig_sc2 = inspect.signature(gerar_plot_sc_2e).parameters
                kwargs_sc2 = {"idioma": idioma, "modo_tracado": modo_tracado_selecionado, "legenda_horizontal": legenda_horizontal}
                if "exibir_densidade_corrente" in sig_sc2 or any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig_sc2.values()):
                    kwargs_sc2["exibir_densidade_corrente"] = params.get("exibir_densidade_corrente", False)
                    kwargs_sc2["texto_densidade_corrente"] = params.get("texto_densidade_corrente", r"1\ \mathrm{A\ g^{-1}}")
                    kwargs_sc2["pos_densidade_corrente"] = params.get("pos_densidade_corrente", (0.05, 0.90))
                fig = _chamar_plot_seguro(gerar_plot_sc_2e, 
                    dados_bytes, eixo_x_input, eixo_y_input, mapa_cores, mapa_estilos, mapa_nomes,
                    limites_manuais, posicao_legenda, tema_visual, **kwargs_sc2,
                )
            elif tecnica_idx == 7:
                sig_sc3 = inspect.signature(gerar_plot_sc_3e).parameters
                kwargs_sc3 = {
                    "idioma": idioma,
                    "tag_amostra": params["tag_amostra"],
                    "pos_amostra": params["pos_amostra"],
                    "exibir_zero_y2": params["exibir_zero_y2"],
                    "modo_tracado": modo_tracado_selecionado,
                    "legenda_horizontal": legenda_horizontal,
                }
                if "exibir_densidade_corrente" in sig_sc3 or any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig_sc3.values()):
                    kwargs_sc3["exibir_densidade_corrente"] = params.get("exibir_densidade_corrente", False)
                    kwargs_sc3["texto_densidade_corrente"] = params.get("texto_densidade_corrente", r"1\ \mathrm{A\ g^{-1}}")
                    kwargs_sc3["pos_densidade_corrente"] = params.get("pos_densidade_corrente", (0.05, 0.80))
                fig = _chamar_plot_seguro(gerar_plot_sc_3e, 
                    dados_bytes, eixo_x_input, eixo_y_input, eixo_y2_input, mapa_cores, mapa_estilos, mapa_nomes,
                    limites_manuais, posicao_legenda, tema_visual, **kwargs_sc3,
                )
            elif tecnica_idx == 8:
                titulo_leg = textos["bet_legenda_area"] if params.get("areas_bet") else textos["bet_legenda"]
                fig = _chamar_plot_seguro(gerar_plot_bet, 
                    dados_bytes, eixo_x_input, eixo_y_input, textos["bet_ads"], textos["bet_des"],
                    titulo_leg, textos["bet_inset"], mapa_cores, mapa_estilos, mapa_nomes,
                    limites_manuais, posicao_legenda, tema_visual, idioma=idioma,
                    areas_bet=params.get("areas_bet"), exibir_inset=params["exibir_inset"],
                    inset_bbox=params.get("inset_bbox", (0.54, 0.22, 0.38, 0.28)),
                    inset_limites=params.get("inset_limites"),
                    modo_tracado=modo_tracado_selecionado,
                    legenda_horizontal=legenda_horizontal,
                )
            elif tecnica_idx == 14:
                fig = _chamar_plot_seguro(gerar_plot_ciclabilidade,
                    dados_bytes, params["rate_tag"], params["pos_rate"], eixo_x_input, eixo_y_input,
                    mapa_cores, mapa_estilos, mapa_nomes, limites_manuais, posicao_legenda, tema_visual,
                    idioma=idioma, unidade_y=r"F\ g^{-1}", modo_tracado=modo_tracado_selecionado,
                    legenda_horizontal=legenda_horizontal,
                )
            elif tecnica_idx == 16:
                fig = _chamar_plot_seguro(gerar_plot_bode_capacitancia,
                    dados_bytes, eixo_x_input, eixo_y_input, eixo_y2_input,
                    mapa_cores, mapa_estilos, mapa_nomes, limites_manuais, posicao_legenda, tema_visual,
                    idioma=idioma,
                    massa_mg=st.session_state.get("mpr_massa_ativa_mg", 1.0),
                    modo_tracado=modo_tracado_selecionado,
                    exibir_freq_joelho=params.get("exibir_freq_joelho", True),
                    freq_joelho_manual=params.get("freq_joelho_manual"),
                    legenda_horizontal=legenda_horizontal,
                )
            elif tecnica_idx == 9:
                fig = _chamar_plot_seguro(gerar_plot_bode, 
                    dados_bytes, eixo_x_input, eixo_y_input, eixo_y2_input,
                    mapa_cores, mapa_estilos, mapa_nomes, limites_manuais, posicao_legenda, tema_visual,
                    idioma=idioma, modo_tracado=modo_tracado_selecionado,
                    y1_log=params.get("bode_y1_log", True),
                    exibir_freq_joelho=params.get("exibir_freq_joelho", eh_supercap),
                    freq_joelho_manual=params.get("freq_joelho_manual"),
                    legenda_horizontal=legenda_horizontal,
                )
            elif tecnica_idx == 10:
                fig = _chamar_plot_seguro(gerar_plot_dqdv,
                    dados_bytes, eixo_x_input, eixo_y_input,
                    mapa_cores, mapa_estilos, mapa_nomes, limites_manuais, posicao_legenda, tema_visual,
                    idioma=idioma,
                    janela_suavizacao=params.get("dqdv_janela", 11),
                    passo_potencial_mv=params.get("dqdv_passo_mv", 3.0),
                    exibir_carga=params.get("dqdv_exibir_carga", True),
                    exibir_descarga=params.get("dqdv_exibir_descarga", True),
                    modo_tracado=modo_tracado_selecionado,
                    legenda_horizontal=legenda_horizontal,
                )
            elif tecnica_idx == 14:
                fig = _chamar_plot_seguro(gerar_plot_ciclabilidade,
                    dados_bytes, params["rate_tag"], params["pos_rate"], eixo_x_input, eixo_y_input,
                    mapa_cores, mapa_estilos, mapa_nomes, limites_manuais, posicao_legenda, tema_visual,
                    idioma=idioma, unidade_y=r"F\ g^{-1}", modo_tracado=modo_tracado_selecionado,
                    legenda_horizontal=legenda_horizontal,
                )
            elif tecnica_idx == 16:
                fig = _chamar_plot_seguro(gerar_plot_bode_capacitancia,
                    dados_bytes, eixo_x_input, eixo_y_input, eixo_y2_input,
                    mapa_cores, mapa_estilos, mapa_nomes, limites_manuais, posicao_legenda, tema_visual,
                    idioma=idioma,
                    massa_mg=st.session_state.get("mpr_massa_ativa_mg", 1.0),
                    modo_tracado=modo_tracado_selecionado,
                    exibir_freq_joelho=params.get("exibir_freq_joelho", True),
                    freq_joelho_manual=params.get("freq_joelho_manual"),
                    legenda_horizontal=legenda_horizontal,
                )
            elif tecnica_idx == 11:
                fig = _chamar_plot_seguro(gerar_plot_cinetica_cv,
                    dados_bytes, eixo_x_input, eixo_y_input,
                    mapa_cores, mapa_estilos, mapa_nomes, limites_manuais, posicao_legenda, tema_visual,
                    idioma=idioma,
                    modo_grafico_cinetica=params.get("modo_grafico_cinetica", "Decomposição de Dunn (Capacitivo vs. Difusional)"),
                    taxas_manuais=params.get("taxas_por_curva"),
                    taxa_alvo_dunn_mvs=params.get("taxa_alvo_dunn_mvs"),
                    modo_esr=params.get("modo_esr", "sem"),
                    valor_esr_ohm=params.get("valor_esr_ohm", 0.0),
                    legenda_horizontal=legenda_horizontal,
                )
            elif tecnica_idx == 12:
                fig = _chamar_plot_seguro(gerar_plot_ragone_sc,
                    dados_bytes, eixo_x_input, eixo_y_input,
                    mapa_cores, mapa_estilos, mapa_nomes, limites_manuais, posicao_legenda, tema_visual,
                    idioma=idioma,
                    massa_mg=st.session_state.get("mpr_massa_ativa_mg", 1.0),
                    densidades_por_curva=params.get("densidades_por_curva"),
                    densidades_lista_por_amostra=params.get("densidades_lista_por_amostra"),
                    massas_por_amostra=params.get("massas_por_amostra"),
                    escala_log_ragone=params.get("escala_log_ragone", True),
                    exibir_tempos_descarga=params.get("exibir_tempos_descarga", True),
                    agrupar_por_amostra=params.get("agrupar_por_amostra", True),
                    modo_tracado=modo_tracado_selecionado,
                    legenda_horizontal=legenda_horizontal,
                )
            elif tecnica_idx == 14:
                fig = _chamar_plot_seguro(gerar_plot_ciclabilidade,
                    dados_bytes, params["rate_tag"], params["pos_rate"], eixo_x_input, eixo_y_input,
                    mapa_cores, mapa_estilos, mapa_nomes, limites_manuais, posicao_legenda, tema_visual,
                    idioma=idioma, unidade_y=r"F\ g^{-1}", modo_tracado=modo_tracado_selecionado,
                    legenda_horizontal=legenda_horizontal,
                )
            elif tecnica_idx == 16:
                fig = _chamar_plot_seguro(gerar_plot_bode_capacitancia,
                    dados_bytes, eixo_x_input, eixo_y_input, eixo_y2_input,
                    mapa_cores, mapa_estilos, mapa_nomes, limites_manuais, posicao_legenda, tema_visual,
                    idioma=idioma,
                    massa_mg=st.session_state.get("mpr_massa_ativa_mg", 1.0),
                    modo_tracado=modo_tracado_selecionado,
                    exibir_freq_joelho=params.get("exibir_freq_joelho", True),
                    freq_joelho_manual=params.get("freq_joelho_manual"),
                    legenda_horizontal=legenda_horizontal,
                )
            elif tecnica_idx == 13:
                fig = _chamar_plot_seguro(gerar_plot_rate_sc,
                    dados_bytes, eixo_x_input, eixo_y_input,
                    mapa_cores, mapa_estilos, mapa_nomes, limites_manuais, posicao_legenda, tema_visual,
                    idioma=idioma,
                    massa_mg=st.session_state.get("mpr_massa_ativa_mg", 1.0),
                    densidades_por_curva=params.get("densidades_por_curva"),
                    densidades_lista_por_amostra=params.get("densidades_lista_por_amostra"),
                    massas_por_amostra=params.get("massas_por_amostra"),
                    usar_capacitancia_integral=params.get("usar_capacitancia_integral", True),
                    exibir_retencao_badge=params.get("exibir_retencao_badge", True),
                    agrupar_por_amostra=params.get("agrupar_por_amostra", True),
                    modo_tracado=modo_tracado_selecionado,
                    legenda_horizontal=legenda_horizontal,
                )
            elif tecnica_idx == 14:
                fig = _chamar_plot_seguro(gerar_plot_ciclabilidade,
                    dados_bytes, params["rate_tag"], params["pos_rate"], eixo_x_input, eixo_y_input,
                    mapa_cores, mapa_estilos, mapa_nomes, limites_manuais, posicao_legenda, tema_visual,
                    idioma=idioma, unidade_y=r"F\ g^{-1}", modo_tracado=modo_tracado_selecionado,
                    legenda_horizontal=legenda_horizontal,
                )
            elif tecnica_idx == 16:
                fig = _chamar_plot_seguro(gerar_plot_bode_capacitancia,
                    dados_bytes, eixo_x_input, eixo_y_input, eixo_y2_input,
                    mapa_cores, mapa_estilos, mapa_nomes, limites_manuais, posicao_legenda, tema_visual,
                    idioma=idioma,
                    massa_mg=st.session_state.get("mpr_massa_ativa_mg", 1.0),
                    modo_tracado=modo_tracado_selecionado,
                    exibir_freq_joelho=params.get("exibir_freq_joelho", True),
                    freq_joelho_manual=params.get("freq_joelho_manual"),
                    legenda_horizontal=legenda_horizontal,
                )

            if fig is not None:
                if nome_preset_revista != "Padrão PhVolt (Tela / Relatório)" and len(fig.axes) > 0:
                    ax_p1 = fig.axes[0]
                    ax_p2 = fig.axes[1] if len(fig.axes) > 1 else None
                    aplicar_preset_revista_figura(fig, ax_p1, preset_revista_ativo, eixo_y2=ax_p2)
                    fig.tight_layout()

                st.pyplot(fig)

                dpi_export = int(preset_revista_ativo.get("dpi", 300))

                buf_png = io.BytesIO()
                fig.savefig(buf_png, format="png", dpi=dpi_export, bbox_inches="tight", facecolor=fig.get_facecolor())
                png_bytes = buf_png.getvalue()

                buf_svg = io.BytesIO()
                fig.savefig(buf_svg, format="svg", bbox_inches="tight", facecolor=fig.get_facecolor())
                svg_bytes = buf_svg.getvalue()

                buf_pdf = io.BytesIO()
                fig.savefig(buf_pdf, format="pdf", dpi=dpi_export, bbox_inches="tight", facecolor=fig.get_facecolor())
                pdf_bytes = buf_pdf.getvalue()

                # Gera TIFF 600 DPI via Pillow (ou fallback Matplotlib) sem bloquear o backend Agg
                tiff_bytes = None
                try:
                    from PIL import Image
                    buf_png_600 = io.BytesIO()
                    fig.savefig(buf_png_600, format="png", dpi=600, bbox_inches="tight", facecolor=fig.get_facecolor())
                    buf_png_600.seek(0)
                    with Image.open(buf_png_600) as im:
                        buf_tiff = io.BytesIO()
                        im.save(buf_tiff, format="TIFF", compression="tiff_lzw", dpi=(600, 600))
                        tiff_bytes = buf_tiff.getvalue()
                except Exception:
                    try:
                        buf_tiff = io.BytesIO()
                        fig.savefig(buf_tiff, format="tiff", dpi=600, bbox_inches="tight", facecolor=fig.get_facecolor())
                        tiff_bytes = buf_tiff.getvalue()
                    except Exception:
                        tiff_bytes = None

                # Fecha a figura imediatamente para evitar vazamento de memória e travamento em reruns rápidos
                plt.close(fig)

                tem_export_txt = True
                assinatura_calc = (
                    st.session_state.get("assinatura_arquivos_anterior"),
                    tecnica_idx,
                    eh_supercap,
                    st.session_state.get("mpr_massa_ativa_mg", 1.0),
                    str(params),
                    str(mapa_nomes),
                )
                chave_cache_metricas = f"_cache_metricas_{tag_tec}_{tag_sis}"
                chave_sig_metricas = f"_sig_metricas_{tag_tec}_{tag_sis}"

                col_acao_exp, col_acao_calc = st.columns([1.35, 1.0])

                with col_acao_exp:
                    with st.expander("📥 " + ("Exportar Gráfico & Dados" if idioma == "Português" else "Export Plot & Data"), expanded=False):
                        c_exp1, c_exp2 = st.columns(2)
                        c_exp1.download_button(
                            label=f"🖼️ PNG ({dpi_export} DPI)",
                            data=png_bytes, file_name=f"grafico_{tag_tec}.png", mime="image/png",
                            use_container_width=True,
                        )
                        if tiff_bytes:
                            c_exp2.download_button(
                                label="🖼️ TIFF (600 DPI)",
                                data=tiff_bytes, file_name=f"grafico_{tag_tec}.tiff", mime="image/tiff",
                                use_container_width=True,
                            )
                        else:
                            c_exp2.download_button(
                                label="📐 SVG (Vetorial)" if idioma == "Português" else "📐 SVG (Vector)",
                                data=svg_bytes, file_name=f"grafico_{tag_tec}.svg", mime="image/svg+xml",
                                use_container_width=True,
                            )

                        c_exp3, c_exp4 = st.columns(2)
                        if tiff_bytes:
                            c_exp3.download_button(
                                label="📐 SVG (Vetorial)" if idioma == "Português" else "📐 SVG (Vector)",
                                data=svg_bytes, file_name=f"grafico_{tag_tec}.svg", mime="image/svg+xml",
                                use_container_width=True,
                            )
                            c_exp4.download_button(
                                label="📄 PDF (Publicação)" if idioma == "Português" else "📄 PDF (Publication)",
                                data=pdf_bytes, file_name=f"grafico_{tag_tec}.pdf", mime="application/pdf",
                                use_container_width=True,
                            )
                        else:
                            c_exp3.download_button(
                                label="📄 PDF (Publicação)" if idioma == "Português" else "📄 PDF (Publication)",
                                data=pdf_bytes, file_name=f"grafico_{tag_tec}.pdf", mime="application/pdf",
                                use_container_width=True,
                            )

                        if tem_export_txt:
                            massa_mg = st.session_state.get("mpr_massa_ativa_mg", 1.0)
                            txt_conteudo = exportar_txt_compativel_mpr(
                                arquivos_lista,
                                tecnica_idx,
                                massa_mg=massa_mg,
                                idioma=idioma,
                                fonte_dados=dados_bytes,
                            )
                            st.download_button(
                                label="🧾 Exportar Dados (.txt)" if idioma == "Português" else "🧾 Export Data (.txt)",
                                data=txt_conteudo.encode("utf-8"),
                                file_name=f"dados_{tag_tec}.txt",
                                mime="text/plain",
                                use_container_width=True,
                            )

                with col_acao_calc:
                    btn_calc_label = (
                        "📊 Calcular Parâmetros Eletroquímicos"
                        if idioma == "Português"
                        else "📊 Calculate Electrochemical Parameters"
                    )
                    clicou_calcular = st.button(
                        btn_calc_label,
                        key=f"btn_calc_params_{tag_tec}_{tag_sis}",
                        use_container_width=True,
                    )

                if clicou_calcular:
                    massa_atual_mg = st.session_state.get("mpr_massa_ativa_mg", 1.0)
                    df_calc = calcular_resumo_parametros(
                        dados_bytes,
                        tecnica_idx=tecnica_idx,
                        mapa_nomes=mapa_nomes,
                        massa_mg=massa_atual_mg,
                        eh_supercap=eh_supercap,
                        params=params,
                    )
                    st.session_state[chave_cache_metricas] = df_calc
                    st.session_state[chave_sig_metricas] = assinatura_calc

                if st.session_state.get(chave_sig_metricas) == assinatura_calc:
                    df_metricas = st.session_state.get(chave_cache_metricas)
                    if df_metricas is not None and not df_metricas.empty:
                        st.subheader("📊 " + ("Parâmetros Calculados" if idioma == "Português" else "Calculated Parameters"))
                        st.dataframe(df_metricas, use_container_width=True, hide_index=True)

                        sep_csv = ";" if idioma == "Português" else ","
                        dec_csv = "," if idioma == "Português" else "."
                        csv_bytes = df_metricas.to_csv(index=False, sep=sep_csv, decimal=dec_csv).encode("utf-8-sig")
                        st.download_button(
                            label="📥 Baixar Tabela de Parâmetros (.csv)" if idioma == "Português" else "📥 Download Parameters Table (.csv)",
                            data=csv_bytes,
                            file_name=f"parametros_{tag_tec}.csv",
                            mime="text/csv",
                            key=f"dl_metrics_{tag_tec}_{tag_sis}",
                        )

        except Exception as e:
            plt.close("all")
            st.error(f"Erro ao processar arquivo: {e}" if idioma == "Português" else f"Error processing file: {e}")
    else:
        st.info("👈 Carregue um ou mais arquivos no topo da barra lateral para gerar o gráfico correspondente." if idioma == "Português" else "👈 Upload one or more files at the top of the sidebar to generate the plot.")


if __name__ == "__main__":
    main()
