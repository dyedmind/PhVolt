# ⚡ PhVolt — Análise Eletroquímica e Caracterização

Aplicação web em **Streamlit** para processamento automatizado e geração de gráficos científicos de alta resolução (PNG 300 DPI e SVG vetorial).

## Estrutura do Projeto
```text
PhVolt/
├── app.py                   # Ponto de entrada Streamlit (UI e roteamento)
├── requirements.txt         # Dependências Python
├── core/
│   ├── __init__.py
│   ├── config.py            # Paletas, marcadores, textos PT/EN e temas (Light/Dark)
│   ├── io_readers.py        # Leitura tabular (.txt/.dat/.csv) e BioLogic (.mpr via galvani)
│   └── plot_utils.py        # Estilização de eixos, separador decimal, limites e legendas
└── tecnicas/
    ├── __init__.py
    ├── cv.py                # (1) Voltametria Cíclica (CV)
    ├── eie.py               # (2) Espectroscopia de Impedância (EIE / Nyquist)
    ├── gcd_bateria.py       # (3) GCD — Carga/Descarga (Bateria)
    ├── rate_capability.py   # (4) e (9) Rate Capability (Bateria e Supercapacitor)
    ├── ciclabilidade.py     # (5) Multiplot e (6) Individual & Eficiência Coulômbica
    ├── supercapacitor.py    # (7) CGCD 2 Eletrodos e (8) CGCD 3 Eletrodos
    └── bet.py               # (10) Isotermas BET (Adsorção / Dessorção)
```

## Instalação e Execução
```bash
pip install -r requirements.txt
streamlit run app.py
```
