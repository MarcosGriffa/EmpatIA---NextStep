# Dashboard de Power BI — EmpatÍA | NextStep

Este dashboard es una pieza de **portfolio**: muestra que el proyecto tiene
un modelo de datos analizable de verdad (no solo una web que funciona) y
que se sabe armar un tablero de BI prolijo sobre él — pensado para que un
reclutador lo vea en 30 segundos y entienda de qué se trata.

> ⚠️ **Los datos que se ven en la captura son sintéticos.** El proyecto
> recién arrancó (26/08/2026) y todavía no hay volumen real de uso como
> para que los gráficos cuenten algo interesante. En vez de esperar meses
> o mostrar un tablero vacío, se generó un dataset inventado pero con la
> **forma exacta** del modelo real: mismas columnas, mismas fuentes de
> empleo reales del proyecto (Jooble, Computrabajo, RemoteOK, Jobicy,
> Himalayas, WeWorkRemotely), proporciones y rangos de score verosímiles.
> El día que haya datos de usuarios reales, el modelo de Power BI
> (relaciones, medidas DAX, visuales) queda igual — solo cambia el origen
> de datos (ver [última sección](#cuando-haya-datos-reales)). Esto está
> aclarado también dentro del propio dashboard (ver Paso 6, punto J).

![Dashboard de Power BI del proyecto](capturas/dashboard-portfolio.png)

---

## 1. El esquema real detrás de esto

Supabase tiene 3 tablas relevantes para este análisis (ver
`supabase/schema.sql`):

- **`cv_profiles`** — un CV subido por fila. `profile` es un jsonb con
  `area`, `is_tech`, `seniority`, `skills[]`.
- **`match_results`** — una corrida de matching por fila. `results` es un
  jsonb con un **array de hasta 10 ofertas evaluadas** (`SHOW_TOP_N` en
  `pipeline.py`), cada una con `job_id`, `title`, `company`, `location`,
  `source`, `similarity` (filtro por embeddings), `score` (veredicto del
  LLM, 0-100), `matches[]`, `gaps[]`.
- **`applied_jobs`** — qué ofertas se marcaron como "ya aplicado", con
  fecha. **Es la única fuente confiable** de ese dato: el campo `applied`
  que viaja dentro del jsonb de `match_results` nunca se actualiza después
  de guardarse (queda siempre en `false`), así que no sirve para
  analítica histórica.

## 2. Modelo de datos (esquema estrella)

**Grano del hecho:** una fila = una oferta evaluada en una búsqueda.

```
                 ┌────────────────┐
                 │   Dim_CV       │
                 │ cv_id (PK)     │
                 │ area           │
                 │ is_tech        │
                 │ seniority      │
                 └───────┬────────┘
                         │ 1
                         │
                         │ *
                 ┌───────┴────────┐        ┌──────────────────┐
                 │  Fact_Ofertas   │        │ Dim_CV_Skills     │
                 │ match_id        │        │ cv_id (FK)        │
                 │ cv_id (FK)      │        │ skill             │
                 │ fecha_busqueda  │        └──────────────────┘
                 │ job_id          │             ▲
                 │ titulo/empresa  │             │ 1
                 │ fuente          │─────────────┘ (mismo cv_id que Dim_CV)
                 │ similarity      │
                 │ score           │        ┌──────────────────┐
                 │ cantidad_gaps   │───*───1│ Dim_Calendario    │
                 │ aplicada        │        │ fecha (PK)        │
                 │ aplicada_en     │───*───1│ (2ª relación,     │
                 └─────────────────┘        │  inactiva)        │
                                             └──────────────────┘
```

Las 3 vistas SQL en `bi/sql/` le dan a Power BI estas tablas ya "planas"
(sin tener que expandir jsonb a mano en Power Query):

| Vista | Reemplaza a | Grano |
|---|---|---|
| `vw_bi_cv_profiles` | `Dim_CV` | 1 fila por CV |
| `vw_bi_cv_skills` | `Dim_CV_Skills` | 1 fila por skill de cada CV |
| `vw_bi_ofertas` | `Fact_Ofertas` | 1 fila por oferta evaluada |

Para la demo de portfolio, en vez de conectar contra esas vistas (que hoy
tendrían muy pocas filas), se generaron 3 CSV con **las mismas columnas
exactas** — ver `bi/datos_demo/generar_datos_demo.py`. Correrlo de nuevo
es reproducible (semilla fija) y no toca Supabase para nada.

---

## 3. Medidas DAX

Todas viven en una tabla separada `Medidas` (ver Paso 5 del armado). Las
últimas tres (`Búsquedas mes anterior`, `Variación % búsquedas MoM`,
`Aplicaciones por fecha real`) dependen de las anteriores — pegalas en
orden.

```dax
Total de búsquedas = DISTINCTCOUNT(Fact_Ofertas[match_id])
```
Cuántas veces se corrió el matching completo — el pulso de uso real del
sitio (no confundir con "ofertas evaluadas": una búsqueda trae varias).

```dax
Ofertas evaluadas = COUNTROWS(Fact_Ofertas)
```

```dax
CVs analizados = DISTINCTCOUNT(Dim_CV[cv_id])
```

```dax
Score promedio = AVERAGE(Fact_Ofertas[score])
```
El indicador central: qué tan bien está matcheando el motor, en promedio,
según el veredicto del LLM (etapa 2).

```dax
Similarity promedio = AVERAGE(Fact_Ofertas[similarity])
```
Lo mismo pero de la etapa 1 (embeddings) — comparado contra el score,
muestra si el prefiltro barato y el LLM caro tienden a estar de acuerdo.

> `similarity` nace como similitud coseno de 0 a 1, pero tanto la vista
> `vw_bi_ofertas` como el generador de demo la exponen **escalada a 0-100**,
> igual que `score`. Así las dos métricas del pipeline quedan en la misma
> unidad (el scatter se lee directo, la diagonal es "coinciden") y se evita
> un decimal que Power BI en español malinterpreta al importar CSV: leería
> el punto de `0.6511` como separador de miles, entendiendo `6511`.

```dax
% Alta compatibilidad = 
DIVIDE(
    CALCULATE(COUNTROWS(Fact_Ofertas), Fact_Ofertas[score] >= 80),
    [Ofertas evaluadas]
)
```
Formatear como porcentaje. Cuenta qué proporción de lo que se le muestra
a la gente es realmente un buen match, no solo "algo relacionado".

```dax
Ofertas aplicadas = CALCULATE(COUNTROWS(Fact_Ofertas), Fact_Ofertas[aplicada] = TRUE())
```

```dax
Tasa de aplicación = DIVIDE([Ofertas aplicadas], [Ofertas evaluadas])
```
Formatear como porcentaje. La métrica de negocio real: de lo que el motor
recomienda, ¿cuánto termina en una aplicación real?

```dax
Aplicaciones por fecha real = 
CALCULATE(
    [Ofertas aplicadas],
    USERELATIONSHIP(Dim_Calendario[fecha], Fact_Ofertas[aplicada_en])
)
```
Usa la relación inactiva del calendario contra `aplicada_en` en vez de
`fecha_busqueda` — sirve para un gráfico de "aplicaciones por día", que es
una fecha distinta a "cuándo se mostró la oferta".

```dax
Gaps promedio por oferta = AVERAGE(Fact_Ofertas[cantidad_gaps])
```
Cuántas cosas le faltan, en promedio, a la persona para el puesto que se
le mostró — sirve para leer "el motor no solo dice sí/no, mide brechas".

```dax
CVs con esta skill = DISTINCTCOUNT(Dim_CV_Skills[cv_id])
```
Se usa con `Dim_CV_Skills[skill]` en el eje — arma el ranking de skills
más comunes entre quienes usaron la plataforma.

```dax
Búsquedas mes anterior = CALCULATE([Total de búsquedas], DATEADD(Dim_Calendario[fecha], -1, MONTH))
```

```dax
Variación % búsquedas MoM = DIVIDE([Total de búsquedas] - [Búsquedas mes anterior], [Búsquedas mes anterior])
```
Formatear como porcentaje. Crecimiento mes a mes — la métrica que más le
importa a un reclutador para ver si "esto se usa cada vez más".

---

## 4. Paso a paso en Power BI Desktop (desde el lienzo vacío)

Asume que ya tenés `empatIANextStep.pbix` abierto, conectado a Supabase,
con las 3 tablas (`public applied_jobs`, `public cv_profiles`,
`public match_results`) en el panel Datos y el lienzo vacío.

### Paso 1 — Cargar los datos de demo

1. Esas 3 tablas conectadas a Supabase traen los campos jsonb sin
   aplanar — no sirven directo para visuales. Sacalas del modelo por
   ahora: panel **Datos** → clic derecho en cada una → **Quitar**. (La
   conexión a Supabase queda guardada igual; el día de mañana volvés a
   traer datos, pero apuntando a las vistas — ver la última sección.)
2. Cinta **Inicio → Obtener datos → Texto o CSV**.
3. Elegí `bi/datos_demo/cv_profiles_demo.csv` → **Abrir** → en la vista
   previa, botón **Transformar datos** (no "Cargar" directo).
4. Repetí Obtener datos → Texto o CSV → Transformar datos para
   `cv_skills_demo.csv` y `ofertas_demo.csv`. Quedan las 3 consultas
   abiertas en el Editor de Poder Query.

### Paso 2 — Tipos y nombres en Power Query

Con las 3 consultas abiertas en el editor:

- `cv_profiles_demo` → doble clic en el nombre (panel Consultas) →
  renombrar a **`Dim_CV`**. Revisá el tipo de cada columna (el ícono en
  el encabezado): `is_tech` = Verdadero/Falso, `created_at` = Fecha,
  `cantidad_skills` = Número entero.
- `cv_skills_demo` → renombrar a **`Dim_CV_Skills`**.
- `ofertas_demo` → renombrar a **`Fact_Ofertas`**. Revisá:
  `fecha_busqueda` y `aplicada_en` = Fecha/hora, `aplicada` =
  Verdadero/Falso, `similarity` / `score` / `cantidad_matches` /
  `cantidad_gaps` = Número entero. Si `aplicada_en`
  quedó como texto (puede pasar por las filas vacías de las ofertas no
  aplicadas), seleccioná la columna → pestaña **Transformar** → **Tipo
  de datos** → **Fecha/hora**.
- Cinta **Inicio → Cerrar y aplicar**.

### Paso 3 — Relaciones

1. Vista **Modelo** (ícono de tres cuadrados conectados, columna
   izquierda).
2. Arrastrá `Dim_CV[cv_id]` sobre `Fact_Ofertas[cv_id]` → en el diálogo,
   confirmá cardinalidad **Uno a varios (1:*)**, una sola dirección de
   filtro → **Aceptar**.
3. Arrastrá `Dim_CV[cv_id]` sobre `Dim_CV_Skills[cv_id]` → mismo tipo de
   relación.

### Paso 4 — Tabla calendario

1. Con la vista Modelo activa, cinta **Inicio → Nueva tabla**, pegá:

```dax
Dim_Calendario =
ADDCOLUMNS (
    CALENDAR ( DATE(2026,1,1), DATE(2026,12,31) ),
    "Año", YEAR ( [Date] ),
    "NúmeroMes", MONTH ( [Date] ),
    "Mes", FORMAT ( [Date], "mmm" ),
    "AñoMes", FORMAT ( [Date], "yyyy-mm" )
)
```

2. Doble clic en el encabezado de la columna `Date` → renombrala a
   **`fecha`**.
3. Con `Dim_Calendario` seleccionada en el panel Datos → cinta
   **Herramientas de tabla → Marcar como tabla de fechas** → columna
   `fecha` → **Aceptar**.
4. Arrastrá `Dim_Calendario[fecha]` sobre `Fact_Ofertas[fecha_busqueda]`
   → queda **activa** (línea continua).
5. Arrastrá `Dim_Calendario[fecha]` sobre `Fact_Ofertas[aplicada_en]` →
   Power BI la crea **inactiva** solo (línea punteada), porque ya hay una
   relación activa entre esas dos tablas. Es la que usa la medida
   `Aplicaciones por fecha real` con `USERELATIONSHIP`.

### Paso 5 — Tabla de medidas

1. Cinta **Inicio → Introducir datos**. Nombre de la tabla: `Medidas`,
   una columna `Aux` con cualquier valor (por ejemplo `0`) → **Cargar**.
2. Panel Datos → clic derecho en `Medidas[Aux]` → **Ocultar en la vista
   de informe** (es solo la "percha" para las medidas, no se usa).
3. Con `Medidas` seleccionada, cinta **Inicio → Nueva medida** y pegá
   cada una de las 13 medidas de la sección 3, una por una.

### Paso 6 — Visuales, en el lienzo vacío

**A) Fila de tarjetas KPI** (arriba del todo): Visualizaciones → ícono
**Tarjeta**, una por medida. Arrastrar al campo "Datos" de cada tarjeta:
`Total de búsquedas`, `Ofertas evaluadas`, `CVs analizados`,
`Score promedio`, `Tasa de aplicación`. Alinearlas en fila (podés usar
Ctrl+clic para seleccionar varias y "Formato → Alinear → Distribuir
horizontalmente").

**B) Evolución mensual de búsquedas** — Gráfico de líneas. Eje X:
`Dim_Calendario[AñoMes]`. Valores: `Total de búsquedas`. Cuenta si el
proyecto crece mes a mes (agregá `Variación % búsquedas MoM` como
etiqueta o en el tooltip).

**C) Ofertas evaluadas por fuente** — Gráfico de anillos (donut).
Leyenda: `Fact_Ofertas[fuente]`. Valores: `Ofertas evaluadas`. Muestra la
diversidad real de portales (Jooble, Computrabajo + las 4 tech).

**D) Score promedio por área** — Gráfico de barras horizontales. Eje Y:
`Dim_CV[area]`. Valores: `Score promedio`. Muestra en qué rubros el
matching encuentra mejores oportunidades.

**E) Similarity vs. Score (dispersión)** — Gráfico de dispersión. Eje X:
`similarity`, Eje Y: `score`, campo **Detalles**: `job_id` (clic en el
campo dentro de "Valores" → **No resumir**, para que cada punto sea una
oferta y no un promedio). Leyenda: `fuente`. Cuenta si el filtro barato
(embeddings) y el veredicto caro (LLM) tienden a coincidir: como las dos
métricas están en escala 0-100, los puntos cerca de la diagonal son
ofertas donde ambas etapas coincidieron.

**F) Skills más pedidas** — Gráfico de barras horizontales. Eje Y:
`Dim_CV_Skills[skill]`. Valores: `CVs con esta skill`. Clic derecho →
**Ordenar por** esa medida, descendente. Opcional: panel Filtros → tipo
**Top N** → 10.

**G) Distribución de seniority** — Gráfico de anillos. Leyenda:
`Dim_CV[seniority]`. Valores: `CVs analizados`.

**H) Tabla de mejores matches** — Tabla. Columnas: `titulo`, `empresa`,
`fuente`, `score`, `aplicada`. Ordenar por `score` descendente (clic en
el encabezado). Formato condicional: clic derecho en `score` dentro de
"Valores" → **Formato condicional → Barras de datos**.

**I) Segmentadores** — uno por: `Dim_CV[area]`, `Dim_CV[seniority]`,
`Fact_Ofertas[fuente]`, y uno de fecha con `Dim_Calendario[fecha]`
(formato "Entre").

**J) Encabezado y aclaración de datos** — Insertar → Elementos de texto →
Cuadro de texto: título del dashboard arriba, y debajo, en tamaño chico,
la leyenda **"Datos de demostración — dataset sintético generado para
portfolio, no refleja usuarios reales"**. Dejarla visible siempre, no en
un tooltip escondido.

### Paso 7 — Guardar y sacar la captura para el repo

1. Guardá el `.pbix` como venís haciendo. **No se commitea** (ver
   `.gitignore` — es un binario, puede pesar varios MB y puede embeber
   datos en su caché interno).
2. Cinta **Vista → Vista de lectura** (pantalla completa del reporte).
3. Windows: `Win + Shift + S` → recortar el reporte completo → guardar
   como PNG en `bi/capturas/dashboard-portfolio.png`.
4. `git add bi/capturas/dashboard-portfolio.png` — es la única prueba
   visual que entra al repo.

---

## 5. Cuando haya datos reales

El día que haya usuarios de verdad:

1. Corré los 3 archivos de `bi/sql/` en el SQL Editor de Supabase (igual
   que se corrió `supabase/schema.sql` — pegar y Run, es seguro repetirlo).
2. En Power BI: **Inicio → Transformar datos → Configuración de origen de
   datos**, o directamente agregar un nuevo origen **Obtener datos →
   Base de datos → PostgreSQL** apuntando al host de Supabase, y elegir
   las 3 vistas (`vw_bi_cv_profiles`, `vw_bi_cv_skills`,
   `vw_bi_ofertas`) en vez de los CSV de demo.
3. Como las columnas tienen el mismo nombre y tipo que los CSV, **no hace
   falta tocar relaciones ni medidas DAX** — el modelo entero sigue
   funcionando igual.
4. Sacá una nueva captura y reemplazá `bi/capturas/dashboard-portfolio.png`
   (y quitá la leyenda de "datos de demostración").
