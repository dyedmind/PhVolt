from matplotlib.ticker import AutoMinorLocator, FuncFormatter, MultipleLocator


def configurar_separador_decimal(ax, idioma="Português", eixo_y2=None):
    """Formata ticks numéricos com vírgula em Português e ponto em Inglês (preservando escalas log)."""
    if idioma != "Português":
        return

    def _fmt_pt(val, _pos):
        if abs(val) < 1e-12:
            val = 0.0
        texto = f"{val:g}"
        if "e" in texto or "E" in texto:
            texto = f"{val:.4f}".rstrip("0").rstrip(".")
        return texto.replace(".", ",")

    formatter = FuncFormatter(_fmt_pt)
    if ax.get_xscale() != "log":
        ax.xaxis.set_major_formatter(formatter)
    if ax.get_yscale() != "log":
        ax.yaxis.set_major_formatter(formatter)
    if eixo_y2 is not None and eixo_y2.get_yscale() != "log":
        eixo_y2.yaxis.set_major_formatter(formatter)


def aplicar_subdivisoes_eixos(ax, limites_manuais, eixo_y2=None):
    """
    Aplica intervalos principais (MultipleLocator) e subdivisões menores (AutoMinorLocator)
    nos eixos X, Y/Y1 e Y2 quando configurados pelo usuário.
    """
    if not limites_manuais:
        return

    # Passo principal (ex: 100 -> 0, 100, 200, 300...)
    x_step = limites_manuais.get("x_step")
    if x_step is not None and x_step > 0 and ax.get_xscale() != "log":
        ax.xaxis.set_major_locator(MultipleLocator(x_step))

    y_step = limites_manuais.get("y_step")
    if y_step is not None and y_step > 0 and ax.get_yscale() != "log":
        ax.yaxis.set_major_locator(MultipleLocator(y_step))

    y2_step = limites_manuais.get("y2_step")
    if eixo_y2 is not None and y2_step is not None and y2_step > 0 and eixo_y2.get_yscale() != "log":
        eixo_y2.yaxis.set_major_locator(MultipleLocator(y2_step))

    # Subdivisões menores entre marcas principais (ex: 2, 4, 5 subdivisões)
    x_minor = limites_manuais.get("x_minor")
    if x_minor is not None and x_minor >= 2 and ax.get_xscale() != "log":
        ax.xaxis.set_minor_locator(AutoMinorLocator(int(x_minor)))
        ax.tick_params(axis="x", which="minor", length=3.5, width=1.0)

    y_minor = limites_manuais.get("y_minor")
    if y_minor is not None and y_minor >= 2 and ax.get_yscale() != "log":
        ax.yaxis.set_minor_locator(AutoMinorLocator(int(y_minor)))
        ax.tick_params(axis="y", which="minor", length=3.5, width=1.0)

    y2_minor = limites_manuais.get("y2_minor")
    if eixo_y2 is not None and y2_minor is not None and y2_minor >= 2 and eixo_y2.get_yscale() != "log":
        eixo_y2.yaxis.set_minor_locator(AutoMinorLocator(int(y2_minor)))
        eixo_y2.tick_params(axis="y", which="minor", length=3.5, width=1.0)


def estilar_figura_e_eixos(fig, ax, tema, y_color=None, idioma="Português", eixo_y2=None):
    fig.patch.set_facecolor(tema["fig_bg"])
    ax.set_facecolor(tema["ax_bg"])
    ax.xaxis.label.set_color(tema["text"])
    ax.yaxis.label.set_color(y_color if y_color else tema["text"])
    ax.tick_params(axis="x", which="both", colors=tema["subtext"])
    ax.tick_params(axis="y", which="both", colors=y_color if y_color else tema["subtext"])
    if eixo_y2 is not None:
        eixo_y2.tick_params(axis="y", which="minor", colors=eixo_y2.yaxis.label.get_color())
    for spine_name, spine in ax.spines.items():
        if spine_name == "right" and y_color:
            continue
        spine.set_color(tema["spine"])
        spine.set_linewidth(1.4)
    configurar_separador_decimal(ax, idioma=idioma, eixo_y2=eixo_y2)


def aplicar_ajustes_eixos_e_legenda(
    ax,
    limites_manuais,
    posicao_legenda,
    tema,
    handles=None,
    title_legenda=None,
    fontsize_leg=10.0,
    legenda_horizontal=False,
    eixo_y2=None,
):
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

        aplicar_subdivisoes_eixos(ax, limites_manuais, eixo_y2=eixo_y2)

    if posicao_legenda == "Ocultar / Hide":
        leg = ax.get_legend()
        if leg:
            leg.remove()
    elif posicao_legenda:
        if handles is not None:
            n_itens = len(handles)
        else:
            h_auto, _ = ax.get_legend_handles_labels()
            n_itens = len(h_auto)

        ncol = max(1, n_itens) if legenda_horizontal else 1

        kwargs_leg = dict(
            loc=posicao_legenda,
            frameon=True,
            facecolor=tema["box_bg"],
            edgecolor=tema["box_edge"],
            fontsize=fontsize_leg,
            ncol=ncol,
            columnspacing=1.2 if legenda_horizontal else 2.0,
            handletextpad=0.5 if legenda_horizontal else 0.8,
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
