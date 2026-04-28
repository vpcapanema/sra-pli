"""Pontos de entrada CLI dos jobs de notificação.

Cada submódulo expõe uma função ``main()`` invocável tanto pelo Render Cron
(``python -m app.cron.JOB``) quanto por um cron externo via HTTP no
endpoint ``/admin/cron/...`` (registrado em ``app/routes/cron_admin.py``).
"""
