from datetime import datetime
import inspect
import io
from pathlib import Path
import matplotlib.pyplot as plt
import streamlit as st

from core import (
    PALETAS_DISPONIVEIS,
    TEXTOS_PADRAO,
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
    gerar_plot_ciclabilidade,
    gerar_plot_ciclabilidade_eficiencia,
    gerar_plot_cv,
    gerar_plot_eie,
    gerar_plot_gcd,
    gerar_plot_rate,
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
            st.rerun()
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
    modo_mpr_ativo = bool(arquivos_lista and arquivos_lista[0]["nome"].lower().endswith(".mpr"))

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
            ("EIE / Nyquist", 1),
            ("EIE - Bode", 9),
            ("GCD — Carga/Descarga (Bateria)" if idioma == "Português" else "GCD — Charge/Discharge (Battery)", 2),
            ("Rate Capability (Bateria)" if idioma == "Português" else "Rate Capability (Battery)", 3),
            ("Ciclabilidade Multiplot (Bateria)" if idioma == "Português" else "Multiplot Cyclability (Battery)", 4),
            ("Ciclabilidade & Eficiência Individual" if idioma == "Português" else "Cyclability & Efficiency Individual", 5),
        ]
    elif eh_supercap:
        opcoes_cat = [
            ("Voltametria Cíclica (CV)" if idioma == "Português" else "Cyclic Voltammetry (CV)", 0),
            ("EIE / Nyquist", 1),
            ("EIE - Bode", 9),
            ("CGCD (2 Eletrodos / Janelas)" if idioma == "Português" else "GCD (2-Electrode / Windows)", 6),
            ("CGCD (3 Eletrodos: Ecell, Ewe, Ece)" if idioma == "Português" else "GCD (3-Electrode: Ecell, Ewe, Ece)", 7),
        ]
    else:
        opcoes_cat = [
            ("BET (Adsorção / Dessorção)" if idioma == "Português" else "BET (Adsorption / Desorption)", 8),
            ("Voltametria Cíclica (CV)" if idioma == "Português" else "Cyclic Voltammetry (CV)", 0),
            ("EIE / Nyquist", 1),
            ("EIE - Bode", 9),
        ]

    nomes_opcoes_cat = [item[0] for item in opcoes_cat]
    escolha_tecnica = st.sidebar.selectbox(
        "Selecione a técnica:" if idioma == "Português" else "Select Technique:",
        nomes_opcoes_cat,
        key=f"sel_tec_{sistema_escolhido}",
    )
    tecnica_idx = dict(opcoes_cat)[escolha_tecnica]
    st.session_state["tecnica_idx"] = tecnica_idx

    tags_tecnicas = ["cv", "eie", "gcd", "rate_bat", "cicl", "ce_ind", "sc_2e", "sc_3e", "bet", "bode"]
    tag_tec = tags_tecnicas[tecnica_idx]

    # Controles exclusivos para arquivos brutos BioLogic (.mpr)
    if modo_mpr_ativo:
        if tecnica_idx == 7 and len(arquivos_lista) > 1:
            st.sidebar.info(
                f"🔌 BioLogic (.mpr): plotando o 1º arquivo ({arquivos_lista[0]['nome']})"
                if idioma == "Português"
                else f"🔌 BioLogic (.mpr): plotting 1st file ({arquivos_lista[0]['nome']})"
            )
        else:
            st.sidebar.info(f"🔌 BioLogic (.mpr): {len(arquivos_lista)} arquivo(s)")

        if tecnica_idx in [0, 1, 2, 6, 7, 9]:
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
    }
    opcoes_tracado = ["Pontos (Scatter)", "Linhas (Lines)", "Scatter + Lines"]
    idx_tracado_padrao = opcoes_tracado.index(estilos_padrao_por_tecnica[tecnica_idx])

    mapa_cores, mapa_estilos, mapa_nomes, amostras_detectadas = {}, {}, {}, []
    with st.sidebar.expander("🎨 Design", expanded=False):
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

                st.markdown("---")
                st.caption("🖌️ " + ("Cores, Nomes e Tracejado por Amostra" if idioma == "Português" else "Custom Colors, Names & Dashed Lines"))
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
        textos["bet_x"], textos["bode_x"],
    ]
    rotulos_default_y = [
        textos["cv_y"], textos["eie_y"], textos["gcd_y"], textos["rate_bat_y"],
        textos["cicl_y"], textos["ce_y1"], textos["sc_2e_y"], textos["sc_3e_y1"],
        textos["bet_y"], textos["bode_y1"],
    ]

    with st.sidebar.expander("⚙️ " + ("Configuração dos Eixos & Legenda" if idioma == "Português" else "Axis & Legend Settings"), expanded=False):
        eixo_x_input = st.text_input("Eixo X" if idioma == "Português" else "X Axis", rotulos_default_x[tecnica_idx], key=f"eixo_x_{tag_tec}_{tag_sis}_{idioma}")
        eixo_y_input = st.text_input("Eixo Y1" if tecnica_idx in [5, 7, 9] else "Eixo Y", rotulos_default_y[tecnica_idx], key=f"eixo_y_{tag_tec}_{tag_sis}_{idioma}")

        eixo_y2_input = ""
        if tecnica_idx in [5, 7, 9]:
            default_y2 = textos["ce_y2"] if tecnica_idx == 5 else (textos["sc_3e_y2"] if tecnica_idx == 7 else textos["bode_y2"])
            eixo_y2_input = st.text_input("Eixo Y2" if idioma == "Português" else "Y2 Axis", default_y2, key=f"eixo_y2_{tag_tec}_{idioma}")

        st.markdown("---")
        cx1, cx2 = st.columns(2)
        xlim_min = _converter_float(cx1.text_input("X Mín:", "", key=f"xlim_min_{tag_tec}"))
        xlim_max = _converter_float(cx2.text_input("X Máx:", "", key=f"xlim_max_{tag_tec}"))

        cy1, cy2 = st.columns(2)
        ylim_min = _converter_float(cy1.text_input("Y1 Mín:" if tecnica_idx in [5, 7, 9] else "Y Mín:", "", key=f"ylim_min_{tag_tec}"))
        ylim_max = _converter_float(cy2.text_input("Y1 Máx:" if tecnica_idx in [5, 7, 9] else "Y Máx:", "", key=f"ylim_max_{tag_tec}"))

        y2lim_min, y2lim_max = None, None
        if tecnica_idx in [5, 7, 9]:
            cy2_1, cy2_2 = st.columns(2)
            def_y2_min = "0" if tecnica_idx == 5 else ""
            def_y2_max = "110" if tecnica_idx == 5 else ""
            y2lim_min = _converter_float(cy2_1.text_input("Y2 Mín:", def_y2_min, key=f"y2lim_min_{tag_tec}"))
            y2lim_max = _converter_float(cy2_2.text_input("Y2 Máx:", def_y2_max, key=f"y2lim_max_{tag_tec}"))

        st.markdown("---")
        st.caption("📏 " + ("Passo e Subdivisões dos Eixos (vazio = auto)" if idioma == "Português" else "Axis Step & Subdivisions (blank = auto)"))
        cs_x, cm_x = st.columns(2)
        x_step = _converter_float(cs_x.text_input("Passo X (ex: 100):" if idioma == "Português" else "X Step (e.g. 100):", "", key=f"x_step_{tag_tec}"))
        x_minor = _converter_float(cm_x.text_input("Subdiv. X (ex: 2):" if idioma == "Português" else "X Subdiv. (e.g. 2):", "", key=f"x_minor_{tag_tec}"))

        cs_y, cm_y = st.columns(2)
        y_step = _converter_float(cs_y.text_input("Passo Y1:" if tecnica_idx in [5, 7, 9] else "Passo Y:", "", key=f"y_step_{tag_tec}"))
        y_minor = _converter_float(cm_y.text_input("Subdiv. Y1:" if tecnica_idx in [5, 7, 9] else "Subdiv. Y:", "", key=f"y_minor_{tag_tec}"))

        y2_step, y2_minor = None, None
        if tecnica_idx in [5, 7, 9]:
            cs_y2, cm_y2 = st.columns(2)
            y2_step = _converter_float(cs_y2.text_input("Passo Y2:", "", key=f"y2_step_{tag_tec}"))
            y2_minor = _converter_float(cm_y2.text_input("Subdiv. Y2:", "", key=f"y2_minor_{tag_tec}"))

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
        }

        posicao_legenda = None
        legenda_horizontal = False
        if tecnica_idx != 5:
            opcoes_legenda = ["best", "upper right", "upper left", "lower right", "lower left", "Ocultar / Hide"]
            posicao_legenda = st.selectbox("Posição da Legenda:" if idioma == "Português" else "Legend Position:", opcoes_legenda, index=0, key=f"leg_pos_{tag_tec}")
            legenda_horizontal = st.checkbox(
                "Legenda em 1 linha (Horizontal)" if idioma == "Português" else "Single-row Legend (Horizontal)",
                value=False,
                disabled=(posicao_legenda == "Ocultar / Hide"),
                key=f"leg_horiz_{tag_tec}",
            )

    # 6. Parâmetros Específicos da Técnica
    params = {}
    precisa_massa_ativa = (tecnica_idx in [2, 3, 4, 5, 6, 7]) or (tecnica_idx == 0 and eh_supercap)
    with st.sidebar.expander("🔬 " + ("Parâmetros da Técnica" if idioma == "Português" else "Technique Parameters"), expanded=False):
        if precisa_massa_ativa:
            st.number_input(
                "⚖️ Massa ativa total / célula (mg):" if (idioma == "Português" and tecnica_idx == 7)
                else ("⚖️ Total / cell active mass (mg):" if tecnica_idx == 7
                else ("⚖️ Massa ativa (mg):" if idioma == "Português" else "⚖️ Active mass (mg):")),
                min_value=0.001,
                value=float(st.session_state.get("mpr_massa_ativa_mg", 1.000)),
                step=0.100,
                format="%.3f",
                key="mpr_massa_ativa_mg",
            )
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
            st.markdown("---")
        if tecnica_idx == 0:
            st.caption("⚡ " + ("Taxa de Varredura para Cálculos (mV/s)" if idioma == "Português" else "Scan Rate for Calculations (mV/s)"))
            modo_taxa_cv = st.radio(
                "Modo de entrada (Taxa CV):" if idioma == "Português" else "Scan Rate input mode:",
                ["Taxa única (mV/s)", "Discriminada por curva"] if idioma == "Português" else ["Single rate (mV/s)", "Per curve"],
                horizontal=True,
                key="cv_modo_taxa_input",
            )
            taxas_cv_dict = {}
            if modo_taxa_cv in ["Taxa única (mV/s)", "Single rate (mV/s)"]:
                taxa_unica_cv = _converter_float(
                    st.text_input(
                        "Taxa de varredura (mV/s):" if idioma == "Português" else "Scan rate (mV/s):",
                        value="",
                        placeholder="ex: 10 (vazio = auto .mpr / nome)",
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
            params["taxas_por_curva"] = taxas_cv_dict

            st.markdown("---")
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
            params["circuito"] = st.file_uploader("Circuito Equivalente (PNG/JPG)", type=["png", "jpg", "jpeg"], key="circuit_uploader")
            if params["circuito"] is not None:
                cc1, cc2 = st.columns(2)
                params["pos_circuito"] = (cc1.slider("Circuito X", 0.05, 0.95, 0.62, 0.02, key="eie_cx"), cc2.slider("Circuito Y", 0.05, 0.95, 0.78, 0.02, key="eie_cy"))
                params["zoom_circuito"] = st.slider("Zoom Circuito", 0.15, 0.80, 0.36, 0.02, key="eie_cz")

        elif tecnica_idx == 2:
            params["exibir_delta_e"] = st.checkbox("Exibir indicador ΔE" if idioma == "Português" else "Show ΔE indicator", True, key="gcd_de_chk")
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

        elif tecnica_idx == 4:
            params["rate_tag"] = st.text_input("Tag de Taxa:", textos["cicl_rate"], key=f"cicl_rt_{idioma}")
            cr1, cr2 = st.columns(2)
            params["pos_rate"] = (cr1.slider("X Taxa", 0.0, 0.90, 0.04, 0.02, key="cicl_rx"), cr2.slider("Y Taxa", 0.0, 0.95, 0.93, 0.02, key="cicl_ry"))

        elif tecnica_idx == 5:
            params["rate_tag"] = st.text_input("Tag de Taxa:", textos["cicl_rate"], key=f"ce_rt_{idioma}")
            cr1, cr2 = st.columns(2)
            params["pos_rate"] = (cr1.slider("X Taxa", 0.0, 0.90, 0.04, 0.02, key="ce_rx"), cr2.slider("Y Taxa", 0.0, 0.95, 0.78, 0.02, key="ce_ry"))
            params["nome_amostra"] = st.text_input("Nome da Amostra:", Path(st.session_state.get("nome_arquivo_anterior", "Amostra")).stem, key="ce_nm")
            params["patamar_ref"] = _converter_float(st.text_input("Patamar de Referência (0 = off):", "0", key="ce_pat")) or 0.0

        elif tecnica_idx == 6:
            st.caption("⚡ " + ("Densidade de Corrente para Cálculos (A/g)" if idioma == "Português" else "Current Density for Calculations (A/g)"))
            modo_j_sc2 = st.radio(
                "Modo de entrada (Densidade I):" if idioma == "Português" else "Current Density input mode:",
                ["Densidade única (A/g)", "Discriminada por curva"] if idioma == "Português" else ["Single density (A/g)", "Per curve"],
                horizontal=True,
                key="sc2e_modo_j_input",
            )
            dens_sc2_dict = {}
            if modo_j_sc2 in ["Densidade única (A/g)", "Single density (A/g)"]:
                j_unica_val = _converter_float(
                    st.text_input(
                        "Densidade de corrente (A/g):" if idioma == "Português" else "Current density (A/g):",
                        value="",
                        placeholder="ex: 1,0 (vazio = auto .mpr)",
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
            params["densidades_por_curva"] = dens_sc2_dict

            st.markdown("---")
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
            j_unica_sc3 = _converter_float(
                st.text_input(
                    "⚡ Densidade de corrente (A/g) [vazio = auto .mpr]:" if idioma == "Português" else "⚡ Current density (A/g) [blank = auto .mpr]:",
                    value="",
                    placeholder="ex: 1,0",
                    key="sc3e_j_unica_num",
                )
            )
            params["densidades_por_curva"] = {"__unica__": j_unica_sc3} if (j_unica_sc3 is not None and j_unica_sc3 > 0) else {}

            st.markdown("---")
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
            elif tecnica_idx == 3:
                fig = _chamar_plot_seguro(gerar_plot_rate, 
                    dados_bytes, eixo_x_input, eixo_y_input, mapa_cores, mapa_estilos, mapa_nomes,
                    limites_manuais, posicao_legenda, tema_visual, idioma=idioma,
                    labels_zonas=params.get("labels_zonas"),
                    modo_tracado=modo_tracado_selecionado,
                    legenda_horizontal=legenda_horizontal,
                )
            elif tecnica_idx == 4:
                fig = _chamar_plot_seguro(gerar_plot_ciclabilidade, 
                    dados_bytes, params["rate_tag"], params["pos_rate"], eixo_x_input, eixo_y_input,
                    mapa_cores, mapa_estilos, mapa_nomes, limites_manuais, posicao_legenda, tema_visual,
                    idioma=idioma, modo_tracado=modo_tracado_selecionado,
                    legenda_horizontal=legenda_horizontal,
                )
            elif tecnica_idx == 5:
                cor_cap_def = "#e2e8f0" if dark_mode_ativo else "#0f172a"
                cor_eff_def = "#38bdf8" if dark_mode_ativo else "#2563eb"
                fig = _chamar_plot_seguro(gerar_plot_ciclabilidade_eficiencia, 
                    dados_bytes, eixo_x_input, eixo_y_input, eixo_y2_input,
                    nome_amostra=params["nome_amostra"], rate_tag=params["rate_tag"], pos_rate=params["pos_rate"],
                    cor_capacidade=mapa_cores.get("Discharge Capacity", cor_cap_def),
                    cor_eficiencia=mapa_cores.get("Coulombic Efficiency", cor_eff_def),
                    estilo_capacidade=mapa_estilos.get("Discharge Capacity", "--"),
                    estilo_eficiencia=mapa_estilos.get("Coulombic Efficiency", "-"),
                    modo_tracado=modo_tracado_selecionado,
                    limites_manuais=limites_manuais, patamar_ref=params["patamar_ref"],
                    tema=tema_visual, idioma=idioma,
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

            if fig is not None:
                st.pyplot(fig)

                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

                if modo_mpr_ativo:
                    col1, col2, col3 = st.columns(3)
                else:
                    col1, col2 = st.columns(2)

                buf_png = io.BytesIO()
                fig.savefig(buf_png, format="png", dpi=300, bbox_inches="tight", facecolor=fig.get_facecolor())
                col1.download_button(
                    label="📥 Baixar PNG (300 DPI)" if idioma == "Português" else "📥 Download PNG (300 DPI)",
                    data=buf_png.getvalue(), file_name=f"grafico_{timestamp}.png", mime="image/png",
                )

                buf_svg = io.BytesIO()
                fig.savefig(buf_svg, format="svg", bbox_inches="tight", facecolor=fig.get_facecolor())
                col2.download_button(
                    label="📥 Baixar SVG (Vetorial)" if idioma == "Português" else "📥 Download SVG (Vector)",
                    data=buf_svg.getvalue(), file_name=f"grafico_{timestamp}.svg", mime="image/svg+xml",
                )

                if modo_mpr_ativo:
                    massa_mg = st.session_state.get("mpr_massa_ativa_mg", 1.0)
                    txt_conteudo = exportar_txt_compativel_mpr(arquivos_lista, tecnica_idx, massa_mg=massa_mg, idioma=idioma)
                    col3.download_button(
                        label="📄 Exportar Dados (.txt)" if idioma == "Português" else "📄 Export Data (.txt)",
                        data=txt_conteudo.encode("utf-8"),
                        file_name=f"dados_{tag_tec}_{timestamp}.txt",
                        mime="text/plain",
                    )

                # Painel de Cálculo Automático de Parâmetros Eletroquímicos
                massa_atual_mg = st.session_state.get("mpr_massa_ativa_mg", 1.0)
                df_metricas = calcular_resumo_parametros(
                    dados_bytes,
                    tecnica_idx=tecnica_idx,
                    mapa_nomes=mapa_nomes,
                    massa_mg=massa_atual_mg,
                    eh_supercap=eh_supercap,
                    params=params,
                )
                if df_metricas is not None and not df_metricas.empty:
                    st.markdown("---")
                    st.subheader("📊 " + ("Parâmetros Calculados Automaticamente" if idioma == "Português" else "Automatically Calculated Parameters"))
                    st.dataframe(df_metricas, use_container_width=True, hide_index=True)

                    sep_csv = ";" if idioma == "Português" else ","
                    dec_csv = "," if idioma == "Português" else "."
                    csv_bytes = df_metricas.to_csv(index=False, sep=sep_csv, decimal=dec_csv).encode("utf-8-sig")
                    st.download_button(
                        label="📥 Baixar Tabela de Parâmetros (.csv)" if idioma == "Português" else "📥 Download Parameters Table (.csv)",
                        data=csv_bytes,
                        file_name=f"parametros_{tag_tec}_{timestamp}.csv",
                        mime="text/csv",
                        key=f"dl_metrics_{tag_tec}_{timestamp}",
                    )

        except Exception as e:
            st.error(f"Erro ao processar arquivo: {e}" if idioma == "Português" else f"Error processing file: {e}")
    else:
        st.info("👈 Carregue um ou mais arquivos no topo da barra lateral para gerar o gráfico correspondente." if idioma == "Português" else "👈 Upload one or more files at the top of the sidebar to generate the plot.")


if __name__ == "__main__":
    main()
