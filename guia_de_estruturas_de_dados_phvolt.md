# ⚡ PhVolt — Guia de Estrutura de Dados Atualizado

Este documento detalha o formato exato das tabelas de dados de entrada (`.txt`, `.dat`, `.csv`) suportadas pelo **PhVolt**, garantindo a compatibilidade correta com cada técnica eletroquímica modularizada.

---

## 📋 Regras Gerais de Formatação
* **Delimitadores:** Arquivos separados por tabulação (`\t`) ou espaços.
* **Separador Decimal:** O PhVolt reconhece automaticamente tanto **ponto (`.`)** quanto **vírgula (`,`)**.
* **Células Vazias / Omissas:** Células marcadas como `--`, `NaN` ou vazias são ignoradas sem interromper o processamento da curva.
* **Cabeçalhos:** Se o arquivo foi exportado de softwares como *Origin* (contendo linhas de *Long Name*, *Units* e *Comments*), o sistema limpa e extrai os rótulos automaticamente; caso contrário, utiliza a primeira linha como cabeçalho.

---

## 📊 Estruturas Compatíveis por Técnica

### 1. Voltametria Cíclica (CV)
Suporta dois arranjos de colunas:
* **Formato Pareado $(X_1, Y_1, X_2, Y_2 \dots)$ — Recomendado:** Cada amostra possui sua coluna de Potencial ($E$) seguida da respectiva coluna de Corrente ($I$).
```text
Potencial   Amostra_1   Potencial   Amostra_2
-1,0        -0,0012     -1,0        -0,0015
-0,99       -0,0011     -0,99       -0,0014
```
* **Formato Compartilhado $(X, Y_1, Y_2 \dots)$:** Uma única coluna de Potencial compartilhada à esquerda e várias colunas de Corrente à direita.

---

### 2. Espectroscopia de Impedância (EIE / Nyquist)
* **Formato Pareado $(Z'_{\text{Real}}, -Z''_{\text{Im}})$:** Pares consecutivos de colunas contendo a impedância real e o negativo da impedância imaginária.
```text
Z_Real   Amostra_A   Z_Real   Amostra_B
1,45     0,12        2,10     0,35
1,62     0,48        2,45     0,89
```

---

### 3. Carga/Descarga Galvanostática — GCD (Bateria)
* **Formato em Blocos de 4 Colunas por Taxa/Ciclo (Padrão Origin / EC-Lab):** Cada condição de taxa ocupa exatamente **4 colunas consecutivas**: `[Capacidade_Carga, Potencial_Carga, Capacidade_Descarga, Potencial_Descarga]`.
```text
0,1C                            0,2C
Carga           Descarga        Carga           Descarga
0,001   1,71    0,001   2,69    0,003   1,72    0,003   2,68
0,139   1,72    0,139   2,67    0,093   1,73    0,093   2,66
```

---

### 4. Rate Capability (Bateria e Supercapacitor)
* **Formato Eixo X Compartilhado $(X, Y_1, Y_2 \dots)$:** A **Coluna 1** contém o Número de Ciclos (organizados em blocos por taxa, ex: de $1$ a $30$) e as colunas seguintes trazem a capacidade específica de cada amostra.
```text
Ciclo   Amostra_1   Amostra_2   Amostra_3
1       850,2       790,5       910,0
2       835,0       782,1       895,4
```

---

### 5. Ciclabilidade Multiplot
Suporta tanto **Pares** $(X_1, Y_1, X_2, Y_2 \dots)$ quanto **Eixo X Compartilhado** $(X, Y_1, Y_2 \dots)$:
```text
Ciclo   Material_A   Ciclo   Material_B
1       920,5        1       880,0
2       905,1        2       872,3
```

---

### 6. Ciclabilidade & Eficiência Individual
Aceita arquivos com **3 ou 4 colunas** para uma única amostra:
* **Formato de 3 Colunas:** `[Ciclo, Capacidade_Descarga, Eficiência_Coulômbica]`
* **Formato de 4 Colunas (Padrão EC-Lab/Origin):** `[Ciclo, Capacidade_Carga, Capacidade_Descarga, Eficiência_Coulômbica]` *(o PhVolt lê automaticamente a 1ª, 3ª e 4ª colunas)*.
```text
Ciclo   Cap_Carga   Cap_Descarga   Eficiencia(%)
1       760,2       755,0          99,3
2       690,5       688,1          99,6
```
