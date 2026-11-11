"""Os testes que conferem o banco por dentro usam o SQLite.

As duas versões do banco são comparadas em test_banco_contrato.py, que roda o MongoDB à parte.
Definido aqui, antes de qualquer import, também vale para os processos que os testes iniciam.
"""
import os

os.environ.setdefault("ESTACAO_BANCO", "sqlite")
