# 📊 Guia de Estruturas de Dados Compatíveis — PhVolt

Este documento descreve o formato de colunas, cabeçalhos e separadores aceitos pelo **PhVolt** para cada uma das **10 técnicas** suportadas.

---

## ⚙️ Regras Gerais de Formatação de Arquivos

* **Extensões aceitas:** `.txt`, `.dat` e `.csv`.
* **Delimitadores:** Tabulação (`\t`), espaços múltiplos ou vírgula/ponto e vírgula (em arquivos `.csv`).
* **Separador decimal:** O leitor converte automaticamente tanto **ponto (`.`)** quanto **vírgula (`,`)** para ponto flutuante.
* **Células vazias e colunas incompletas:** Valores ausentes, células em branco ou marcadores como `--` e `NaN` são tratados automaticamente sem interromper a plotagem.
* **Identificação de cabeçalhos:**
  * Caso o arquivo seja exportado diretamente do **Origin** (contendo linhas de metadados como `Long Name`, `Units` ou `Comments`), o sistema extrai os nomes das curvas a partir da linha `Long Name` (ou `Comments`).
  * Caso contrário, o sistema utiliza a primeira linha de texto não numérico como rótulo das curvas (que também podem ser renomeadas livremente na interface do aplicativo).

---

## 🔬 Estrutura por Técnica

### 1. Voltametria Cíclica (CV)
Aceita dois layouts de colunas:

* **Layout A — Pareado $(X_1, Y_1, X_2, Y_2, \dots)$ [Recomendado]:** Cada amostra possui sua própria coluna de Potencial ($E$) seguida da sua coluna de Corrente ($I$).
  ```text
  Potencial   Amostra_1   Potencial   Amostra_2
  -1,00       -0,0012     -1,00       -0,0015
  -0,99       -0,0011     -0,99       -0,0014
  -0,98       -0,0009     -0,98       -0,0012
  ```
* **Layout B — Eixo X Compartilhado $(X, Y_1, Y_2, \dots)$:** Uma única coluna de Potencial na esquerda seguida por múltiplas colunas de Corrente.

---

### 2. Espectroscopia de Impedância Eletroquímica (EIE / Nyquist)
* **Layout Pareado $(Z'_{\text{Real}}, -Z''_{\text{Im}})$:** Pares consecutivos de colunas contendo a parte real da impedância ($Z'$) e o negativo da parte imaginária ($-Z''$) para cada amostra ou condição.
  ```text
  Z_Real   Amostra_A   Z_Real   Amostra_B
  1,45     0,12        2,10     0,35
  1,62     0,48        2,45     0,89
  1,85     1,10        3,02     1,64
  ```
* *Nota:* Certifique-se de que os valores de $-Z''$ estejam positivos no primeiro quadrante (padrão de Nyquist).

---

### 3. Carga/Descarga Galvanostática — GCD (Bateria)
* **Layout em Blocos de 4 Colunas por Taxa/Ciclo:** Cada taxa de ciclagem (ex.: `0,1C`, `0,2C`, `0,5C`, `1C`) ocupa **4 colunas consecutivas**:
  `[Capacidade_Carga, Potencial_Carga, Capacidade_Descarga, Potencial_Descarga]`.
  * **Linha 0:** Nome da taxa/ciclo na primeira coluna de cada bloco de 4 colunas.
  * **Linha 1:** Subcabeçalhos contendo `Carga` / `Descarga` (ou `Charge` / `Discharge`).
  * **Linha 2+:** Dados numéricos.
  ```text
  0,1C                            0,2C
  Carga           Descarga        Carga           Descarga
  0,001   1,71    0,001   2,69    0,003   1,72    0,003   2,68
  0,139   1,72    0,139   2,67    0,093   1,73    0,093   2,66
  0,280   1,74    0,280   2,65    0,185   1,75    0,185   2,64
  ```
* *Nota:* Se uma determinada taxa não tiver dados (colunas preenchidas com `--`), o bloco inteiro é ignorado automaticamente.

---

### 4. Rate Capability (Bateria)
* **Layout Eixo X Compartilhado $(X, Y_1, Y_2, \dots)$:**
  * **Coluna 1:** Número de Ciclos (padrão de 30 ciclos divididos em 6 degraus de 5 ciclos: `0,1 C`, `0,2 C`, `0,5 C`, `1 C`, `2 C`, `0,1 C`).
  * **Colunas 2+:** Capacidade Específica ($\mathrm{mAh\ g^{-1}}$) de cada amostra.
  ```text
  Ciclo   Amostra_1   Amostra_2   Amostra_3
  1       850,2       790,5       910,0
  2       835,0       782,1       895,4
  3       828,4       779,0       889,2
  ```

---

### 5. Ciclabilidade Multiplot (Bateria)
Aceita tanto o **Layout Pareado** (ideal quando as amostras possuem números diferentes de ciclos) quanto o **Layout Eixo X Compartilhado**:
```text
Ciclo   Material_A   Ciclo   Material_B
1       920,5        1       880,0
2       905,1        2       872,3
3       898,0        3       865,9
```

---

### 6. Ciclabilidade & Eficiência Individual (Bateria)
Aceita arquivos contendo **3 ou 4 colunas** para uma única amostra:
* **Layout de 3 Colunas:** `[Ciclo, Capacidade_Descarga, Eficiência_Coulômbica]`
* **Layout de 4 Colunas (Exportação Padrão EC-Lab/Origin):** `[Ciclo, Capacidade_Carga, Capacidade_Descarga, Eficiência_Coulômbica]` *(o sistema ignora a 2ª coluna e lê automaticamente a 1ª, 3ª e 4ª colunas)*.
  ```text
  Ciclo   Cap_Carga   Cap_Descarga   Eficiencia(%)
  1       760,2       755,0          99,3
  2       690,5       688,1          99,6
  3       685,0       684,2          99,8
  ```

---

### 7. CGCD Supercapacitor (2 Eletrodos / Janelas de Potencial)
* **Layout Pareado $(X_1, Y_1, X_2, Y_2, \dots)$:** Pares consecutivos de `[Tempo (s), Potencial da Célula (V)]` para cada janela de potencial ou densidade de corrente avaliada.
  ```text
  time/s   1,8 V   time/s   2,0 V   time/s   2,5 V
  0,0      0,00    0,0      0,00    0,0      0,00
  0,5      0,04    0,5      0,05    0,5      0,06
  1,0      0,08    1,0      0,10    1,0      0,12
  ```
* *Nota:* Também é compatível com blocos de 4 colunas (`Carga` / `Descarga`) caso os ramos sejam exportados separadamente.

---

### 8. CGCD Supercapacitor (3 Eletrodos: $E_{\text{cell}}, E_{\text{we}}, E_{\text{ce}}$)
* **Layout de Tempo Compartilhado (4 Colunas):**
  * **Coluna 1:** Tempo (`time/s`).
  * **Coluna 2:** Potencial total da célula (`Ecell/V`) — plotado automaticamente no **Eixo $Y_1$ (esquerdo)**.
  * **Coluna 3:** Potencial do eletrodo de trabalho (`Ewe/V`) — plotado automaticamente no **Eixo $Y_2$ (direito)**.
  * **Coluna 4:** Potencial do contra-eletrodo (`Ece/V`) — plotado automaticamente no **Eixo $Y_2$ (direito)**.
  ```text
  time/s   Ecell/V   Ewe/V    Ece/V
  0,0      0,000     0,150    0,150
  1,0      0,025     0,162    0,137
  2,0      0,050     0,175    0,125
  ```

---

### 9. Rate Capability (Supercapacitor)
* **Layout Eixo X Compartilhado $(X, Y_1, Y_2, \dots)$:**
  * **Coluna 1:** Número de Ciclos.
  * **Colunas 2+:** Capacitância Específica ($\mathrm{F\ g^{-1}}$) de cada amostra nos diferentes degraus de densidade de corrente ($\mathrm{A\ g^{-1}}$).
  ```text
  Ciclo   Eletrodo_1   Eletrodo_2
  1       245,0        210,5
  2       243,8        209,1
  3       242,9        208,4
  ```

---

### 10. Isotermas BET (Adsorção / Dessorção)
* **Layout Pareado $(p/p_0, \text{Quantidade Adsorvida})$:** Cada amostra ocupa um par de colunas contendo a pressão relativa ($0 \to 1 \to 0$) e o volume adsorvido ($\mathrm{cm^3\ g^{-1}\ STP}$).
  * O PhVolt identifica automaticamente o ponto de pressão máxima ($p/p_0$ de pico) para separar o ramo de **Adsorção** (pontos preenchidos) do ramo de **Dessorção** (pontos vazados).
  ```text
  p/p0      Amostra_1   p/p0      Amostra_2
  0,010     120,5       0,010     85,2
  0,500     310,4       0,500     205,0
  0,990     640,8       0,990     410,0
  0,950     615,2       0,950     398,4
  0,500     345,0       0,500     228,1
  ```