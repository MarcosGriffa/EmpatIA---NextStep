# Motor v1 (línea base)

Copia del `semantic_match.py` y de las constantes de `pipeline.py` tal como
estaban antes del cambio del 13/10/2026 (el LLM leía 10, temperature 0.3,
llamadas en serie). Sirve para reproducir la línea base de las evals:

    python evals/run_evals.py --motor evals/motor_v1
