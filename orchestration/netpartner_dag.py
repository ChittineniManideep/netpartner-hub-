"""
netpartner_dag.py
------------------
Airflow DAG that orchestrates the full partner-data lifecycle:

  1. migrate_legacy_contacts  (PHP script normalizes the wiki dump)
  2. ingest_sources           (Python ETL loads CSV/JSON into the warehouse)
  3. run_data_quality_checks  (dedup, orphan, staleness, missing-field audit)
  4. alert_on_findings        (branches to an alerting step only if issues found)
  5. publish_dashboard        (regenerates the data-quality HTML dashboard)

This mirrors the "job scheduling and orchestration tools (Airflow, cron, or
similar)" requirement and the "automated alerting for stale data" /
"scheduled reports for leadership" asks in the JD. It's written as a
standard Airflow 2.x DAG; drop it into $AIRFLOW_HOME/dags to run it for
real, or read it as documentation of the intended pipeline shape.
"""
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator, BranchPythonOperator
from airflow.operators.bash import BashOperator
from airflow.operators.empty import EmptyOperator

default_args = {
    "owner": "netpartner-platform",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": True,
}

with DAG(
    dag_id="netpartner_daily_sync",
    description="Daily partner data migration, ingestion, quality audit, and alerting",
    default_args=default_args,
    schedule_interval="0 6 * * *",  # 06:00 daily
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["network-partners", "data-quality", "etl"],
) as dag:

    migrate_legacy_contacts = BashOperator(
        task_id="migrate_legacy_contacts",
        bash_command="php {{ params.project_root }}/legacy_migration/migrate_contacts.php "
                     "{{ params.project_root }}/data/contacts_wiki_dump.csv "
                     "{{ params.project_root }}/data/contacts_clean.json",
        params={"project_root": "/opt/netpartner-hub"},
    )

    def _ingest():
        from etl.ingest import run
        run()

    ingest_sources = PythonOperator(
        task_id="ingest_sources",
        python_callable=_ingest,
    )

    def _validate(**context):
        from etl.validate import run_all
        report = run_all()
        issue_count = sum(len(v) for v in report.values())
        context["ti"].xcom_push(key="issue_count", value=issue_count)
        context["ti"].xcom_push(key="report", value=report)
        return report

    run_data_quality_checks = PythonOperator(
        task_id="run_data_quality_checks",
        python_callable=_validate,
    )

    def _branch_on_findings(**context):
        issue_count = context["ti"].xcom_pull(task_ids="run_data_quality_checks", key="issue_count")
        return "alert_on_findings" if issue_count and issue_count > 0 else "no_issues_found"

    branch = BranchPythonOperator(
        task_id="branch_on_findings",
        python_callable=_branch_on_findings,
    )

    def _alert(**context):
        report = context["ti"].xcom_pull(task_ids="run_data_quality_checks", key="report")
        # In production this would post to Slack/PagerDuty/email; kept as a
        # log line here since this repo has no messaging integration wired up.
        print(f"[ALERT] Data quality issues found: "
              f"{ {k: len(v) for k, v in report.items()} }")

    alert_on_findings = PythonOperator(
        task_id="alert_on_findings",
        python_callable=_alert,
    )

    no_issues_found = EmptyOperator(task_id="no_issues_found")

    def _publish_dashboard():
        from monitoring.dashboard import build_dashboard
        build_dashboard()

    publish_dashboard = PythonOperator(
        task_id="publish_dashboard",
        python_callable=_publish_dashboard,
        trigger_rule="none_failed_min_one_success",
    )

    migrate_legacy_contacts >> ingest_sources >> run_data_quality_checks >> branch
    branch >> alert_on_findings >> publish_dashboard
    branch >> no_issues_found >> publish_dashboard
