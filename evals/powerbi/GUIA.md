# Tablero de evals en Power BI

Los CSV salen de `python evals/metricas.py` en `evals/salida/bi/`. Están en
UTF-8 con BOM, así que Power BI respeta los acentos sin tocar nada.

## 1. Cargar los datos

Inicio → Obtener datos → Texto/CSV, y cargar los 6 archivos:

| Tabla | Grano (una fila =) |
|---|---|
| `fact_pares` | un par CV × oferta (8.000 filas) |
| `fact_llm_llamadas` | una llamada al LLM |
| `fact_metricas_cv` | una búsqueda (un CV) con sus métricas ya calculadas |
| `dim_cv` | un CV sintético |
| `dim_oferta` | una oferta sintética |
| `dim_relevancia` | un nivel de la escala 0-3 |

En Power Query, revisá que `score_llm`, `similarity` y las columnas de
métricas queden como **número decimal**. Si tu Windows usa coma decimal,
cambiá la configuración regional del archivo a "Inglés (Estados Unidos)"
al importar: los CSV usan punto.

## 2. Relaciones (vista Modelo)

```
dim_cv[cv_id]                 1 ──* fact_pares[cv_id]
dim_cv[cv_id]                 1 ──* fact_llm_llamadas[cv_id]
dim_cv[cv_id]                 1 ──* fact_metricas_cv[cv_id]
dim_oferta[oferta_id]         1 ──* fact_pares[oferta_id]
dim_oferta[oferta_id]         1 ──* fact_llm_llamadas[oferta_id]
dim_relevancia[relevancia]    1 ──* fact_pares[relevancia]
```

Todas de un solo sentido, de la dimensión al hecho. Es el mismo esquema
estrella que el tablero de producto de `bi/`, así que en una entrevista
podés mostrar los dos y explicar que siguen la misma lógica.

## 3. Medidas

Crear una tabla vacía `_Medidas` y pegar las medidas de `medidas.dax`.
Para las de umbral, primero crear el parámetro: Modelado → Nuevo
parámetro → Rango numérico, nombre `Umbral`, de 40 a 95, incremento 5.

## 4. Páginas sugeridas

**Página 1 · Resumen**
- Segmentadores arriba, en una fila: `dim_cv[rubro]`, `dim_cv[seniority]`, `dim_oferta[idioma]`.
- 4 tarjetas: Recall@10, nDCG@10 final, Precisión@5, Costo cada 1.000 búsquedas.
- Gráfico de embudo con [Relevantes], [Relevantes en top 30] y [Relevantes en top 10].
- Barras agrupadas: [nDCG@10 embeddings] vs [nDCG@10 final], para mostrar cuánto aporta el LLM.

**Página 2 · Calibración**
- Gráfico de dispersión: eje X `fact_llm_llamadas[relevancia]`, eje Y `score`,
  detalles `llamada_id`. Muestra que el score sube con la relevancia (o no).
- Columnas: [Score LLM promedio] por `dim_relevancia[etiqueta]`, ordenado por `relevancia`.
- Segmentador del parámetro Umbral + gráfico de líneas con [Precisión sobre umbral]
  y [Recall sobre umbral]. Es la página más "impactante": al mover el umbral se ve
  el trade-off en vivo.

**Página 3 · Rubros**
- Matriz: filas `dim_cv[rubro]`, valores Recall@10, nDCG@10 final, Precisión@5,
  % trampas que pasan. Formato condicional → escala de color de fondo (una sola
  escala azul, de claro a oscuro).

**Página 4 · Detalle**
- Tabla con `fact_pares` filtrada a `evaluado_llm = 1`: CV, oferta, relevancia,
  motivo, score_llm, rank_final.
- Configurarla como página de **obtención de detalles** (drillthrough) por
  `dim_cv[cv_id]`, así desde cualquier visual se puede ir a una búsqueda puntual.

## 5. Para el portfolio

El `.pbix` está en el `.gitignore` (es binario y pesado). Al repo sube
una captura del tablero en `evals/capturas/` y el link al reporte HTML.
