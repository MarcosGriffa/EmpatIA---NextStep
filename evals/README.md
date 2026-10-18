# Evals del motor de matching

Evaluación offline del ranking de NextStep (etapa 1: embeddings de Cohere,
etapa 2: LLM en Groq) sobre un dataset **sintético** cuya respuesta correcta
se conoce de antemano.

**Qué responde:**
- ¿Cuántas ofertas buenas llegan a las 10 que ve el LLM? (recall@10)
- ¿El LLM ordena mejor que los embeddings solos? (nDCG@10)
- ¿Un score de 80 significa un buen match? (calibración, precisión por umbral)
- ¿Se deja engañar por palabras clave de otro rubro? (trampas)
- ¿Funciona igual en inglés, en todos los rubros y con todos los seniorities?
- ¿Da el mismo score si se le pregunta dos veces? (consistencia)
- ¿Cuánto cuesta y tarda cada búsqueda? ¿Cuánto ahorra el filtro de la etapa 1?

## Cómo correrlo

Desde la raíz del repo, con un `.env` que tenga `GROQ_API_KEY` y `COHERE_API_KEY`:

```bash
pip install groq cohere numpy python-dotenv
python evals/generar_dataset.py        # 40 CVs, 200 ofertas, 8.000 pares etiquetados
python evals/run_evals.py              # corre el motor real + métricas + reporte
```

Para probar el circuito sin gastar API: `python evals/run_evals.py --mock`.

**Comparar dos versiones del motor** (por ejemplo, antes y después de un cambio en
`semantic_match.py`): correr cada versión en su propia carpeta y después

```bash
python evals/run_evals.py --salida evals/salida_v2
python evals/comparar.py evals/salida evals/salida_v2
```

**Límites de Groq:** la corrida completa hace ~470 llamadas al modelo grande. En
el plan gratuito puede cortarse por el tope diario de tokens: lo hecho queda
guardado y volver a correr el mismo comando retoma desde donde quedó. Para una
prueba corta: `python evals/run_evals.py --cvs 10`.

## Salidas (`evals/salida/`)

| Archivo | Para qué |
|---|---|
| `reporte.html` | reporte interactivo, se abre con doble clic |
| `bi/*.csv` | modelo estrella para Power BI (ver `powerbi/GUIA.md` y `powerbi/medidas.dax`) |
| `resumen.json` | todas las métricas juntas |
| `etapa1.jsonl`, `etapa2.jsonl` | resultados crudos de cada llamada (permiten retomar) |

## Diseño

- **Etiquetas por reglas, no por LLM** (`generar_dataset.py → etiqueta()`): si
  la "verdad" la pusiera un LLM, el sistema se estaría corrigiendo a sí mismo.
  3 = mismo rol, mismo seniority, cubre ≥60% de lo pedido · 2 = mismo rol, un
  paso de seniority, cubre ≥40% · 1 = relacionado · 0 = otro rubro.
- **Motor sin modificar:** se llaman `prefilter_by_embeddings` y `explain_match`
  de `semantic_match.py` tal cual; sólo se envuelven los clientes de las APIs
  para medir tokens y latencia (`run_evals.py → instrumentar()`).
- **Dificultad a propósito:** la mitad de los CVs no tiene sección de skills,
  ~20% de las ofertas tech y de marketing están en inglés, y hay 16 trampas
  (ofertas de un rubro escritas con el vocabulario de otro).
- **Límite conocido:** el texto sintético es más prolijo que el real, así que los
  números sirven para comparar versiones del motor entre sí, no como medida
  absoluta de calidad en producción.
