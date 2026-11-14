# PhVolt v2.3
Creating eletrochemistry graphs 

# ⚡ PhVolt — Análise Eletroquímica e Caracterização Automatizada

**PhVolt** é uma aplicação web interativa construída em **Python**, **Streamlit** e **Matplotlib** para o processamento automatizado de dados científicos e geração de gráficos prontos para publicação acadêmica (dissertações, teses e artigos) ou apresentações técnicas.

O sistema realiza leitura inteligente de cabeçalhos exportados por potenciostatos e softwares de análise (como *Origin*, *EC-Lab/BioLogic* e *Nova/Metrohm*), oferecendo personalização completa de eixos, paletas de cores, estilos de traçado e anotações flutuantes.

---

## 🚀 Funcionalidades Principais

### 🔬 10 Técnicas Suportadas
Organizadas por família eletroquímica e caracterização física:
1. **Voltametria Cíclica (CV):** Múltiplas curvas sobrepostas, linha de referência em $0\text{ mA}$, tag de velocidade de varredura ($\nu$) e setas reposicionáveis de *Carga* e *Descarga*.
2. **Espectroscopia de Impedância Eletroquímica (EIE / Nyquist):** Diagramas de Nyquist com suporte a **Inset 1:1 para altas frequências**, modo *Apenas Linha* ou *Pontos + Linha*, proporção 1:1 opcional no gráfico principal e sobreposição de imagem do circuito equivalente.
3. **Carga/Descarga Galvanostática — GCD (Bateria):** Leitura automática de blocos pareados (Carga + Descarga por taxa) com indicador de polarização ($\Delta E$) totalmente ajustável em posição, tamanho e alinhamento.
4. **Rate Capability (Bateria):** Zonas sombreadas intercaladas para protocolos de taxa C ($0,1\text{ C} \to 0,2\text{ C} \to 0,5\text{ C} \to 1\text{ C} \to 2\text{ C} \to 0,1\text{ C}$).
5. **Ciclabilidade Multiplot (Bateria):** Comparação de múltiplas amostras com cálculo dinâmico de capacidade final e retenção percentual (%) ajustado automaticamente ao último ciclo visível na escala.
6. **Ciclabilidade & Eficiência Individual (Bateria):** Eixo duplo ($Y_1$ Capacidade de Descarga e $Y_2$ Eficiência Coulômbica), linha de patamar opcional, alternância entre *Pontos + Linha* e *Apenas Linha*, balão de taxa reposicionável e cálculo automático de retenção.
7. **CGCD Supercapacitor (2 Eletrodos / Janelas):** Perfis triangulares galvanostáticos ($V$ vs. tempo) com indicador opcional de queda ôhmica ($IR_{\text{drop}}$).
8. **CGCD Supercapacitor (3 Eletrodos: $E_{\text{cell}}, E_{\text{we}}, E_{\text{ce}}$):** Eixo duplo separando o potencial total da célula ($Y_1$) dos potenciais individuais dos eletrodos de trabalho e contra-eletrodo ($Y_2$), com linha de referência em $0\text{ V}$ e balão de identificação da amostra.
9. **Rate Capability (Supercapacitor):** Capacitância específica ($\mathrm{F\ g^{-1}}$) por degrau de densidade de corrente ($\mathrm{A\ g^{-1}}$) totalmente configurável.
10. **Isotermas BET (Adsorção / Dessorção):** Distinção visual IUPAC (marcadores fechados para adsorção, abertos para dessorção), exibição opcional da área superficial específica ($S_{\text{BET}}$) na legenda e **Inset** configurável para regiões de baixo volume de poros.

---

### 🎨 Personalização e Fluxo de Trabalho
* **Suporte Bilíngue (Português / Inglês):** Adapta automaticamente os rótulos padrão dos eixos e o separador decimal (**vírgula** em Português, **ponto** em Inglês).
* **Tema Claro (Light) e Escuro (Dark Mode):** Alternância instantânea entre fundo branco para artigos e fundo escuro (`#0f172a`) de alto contraste para slides e projeções.
* **Controle Individual por Curva:** Renomeação livre das legendas, seletor de cor (*color picker*) e alternância entre linha contínua (`-`) e tracejada (`--`).
* **Limites Manuais e Legenda:** Controle fino de $X_{\min}, X_{\max}, Y_{\min}, Y_{\max}, Y_{2\min}, Y_{2\max}$ e posicionamento da legenda.
* **Exportação em Alta Resolução:** Download direto em **PNG (300 DPI)** e **SVG (Vetorial)**.

---

## 📦 Instalação e Execução

### Pré-requisitos
Certifique-se de ter o **Python 3.9+** instalado em seu ambiente.

### 1. Instalar dependências
```bash
pip install streamlit pandas numpy matplotlib
