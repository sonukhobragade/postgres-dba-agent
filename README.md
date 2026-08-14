# postgres-dba-agent

Watches a PostgreSQL instance, and when something looks wrong, asks an LLM to
write the tuning advice — then posts it to Slack as a readable card rather than
a metric that fires at 3am and means nothing.

Ships with Prometheus, `postgres_exporter` and Grafana wired up in Compose, so
it stands up as a whole monitoring stack rather than a script you have to find a
home for.

## The idea

Postgres monitoring usually stops at "connections are at 85%". That is a fact,
not a next step. Knowing what to *do* means reading `pg_stat_statements`,
spotting the sequential scan on a large table, and writing the `CREATE INDEX`.

This closes that gap. It collects the diagnostic context an experienced DBA
would gather, hands it to a model, and posts back concrete recommendations:
which index to add, which query to rewrite as an upsert, which table has grown
enough to want partitioning.

## What it watches

Connection saturation against `max_connections`, slow queries via
`pg_stat_statements` with their cache hit ratio, and dead tuple accumulation.
Thresholds are environment variables, not constants.

Growth-rate tracking is not implemented: it needs size history the monitor does
not yet keep.

`monitor_and_alert.py` is the loop. `dba_ai_agent.py` builds the analysis and
calls the model. `slack_notifier.py` formats it.

## Running it

```bash
cp .env.example .env      # fill in
docker compose up -d
./start-monitoring.sh     # restart the stack after a config change
```

Grafana comes up with dashboards and alert rules provisioned from
`grafana/provisioning/`. `init-scripts/` creates this project's own metrics
store; the synthetic seed data in `02-test-data.sql` uses `generate_series` so
the dashboards have something to draw before real data arrives.

## Use a read-only role

The agent only reads catalogues and statistics. Give it `pg_monitor` and nothing
more. Nothing here needs write access to the database it is observing, and a
monitoring tool with write credentials is a monitoring tool that can cause the
incident it was meant to detect.

## The recommendations are drafts

The advice is generated, which means it is fluent and sometimes wrong. It cannot
see your workload's shape, your write amplification, your maintenance windows,
or the index it is proposing to duplicate.

An index recommendation in particular deserves scepticism: adding one is not
free, it costs write throughput and disk on every insert forever. Read the
suggestion, check it against `pg_stat_user_indexes` for something similar that
already exists, and try it somewhere that isn't production.

Treat the output as a starting point for a DBA conversation, not a change to
apply.

## Example advice format

Recommendations arrive grouped: index suggestions with the `CREATE INDEX`
statement, query rewrites with the SQL, and partitioning candidates with the
table and the growth figure that triggered it. Table and column names in those
examples are generic placeholders; yours will reflect your own schema.

## License

MIT. See [LICENSE](LICENSE).
