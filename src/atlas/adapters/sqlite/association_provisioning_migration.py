"""V27: immutable provenance for offline Project/Environment provisioning."""

from atlas.adapters.sqlite.database import SQLiteMigration


CORE_SCHEMA_V27 = SQLiteMigration(
    version=27,
    name="offline_project_environment_association_provisioning_ledger",
    sql="""
    ALTER TABLE atlas_project_environments
        ADD COLUMN provisioning_event_id TEXT
        REFERENCES atlas_project_environment_provisioning_events(event_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
        DEFERRABLE INITIALLY DEFERRED;

    CREATE UNIQUE INDEX atlas_project_environment_provisioning_binding
        ON atlas_project_environments(
            provisioning_event_id, project_id, environment_id
        );

    CREATE TABLE atlas_project_environment_provisioning_events (
        event_id TEXT PRIMARY KEY CHECK (
            length(event_id) = 36 AND event_id = lower(event_id)
            AND length(replace(event_id, '-', '')) = 32
            AND substr(event_id, 9, 1) = '-'
            AND substr(event_id, 14, 1) = '-'
            AND substr(event_id, 19, 1) = '-'
            AND substr(event_id, 24, 1) = '-'
            AND substr(event_id, 15, 1) = '4'
            AND substr(event_id, 20, 1) IN ('8', '9', 'a', 'b')
            AND event_id NOT GLOB '*[^0-9a-f-]*'
        ),
        operation_id TEXT NOT NULL UNIQUE CHECK (
            length(operation_id) = 36 AND operation_id = lower(operation_id)
            AND length(replace(operation_id, '-', '')) = 32
            AND substr(operation_id, 9, 1) = '-'
            AND substr(operation_id, 14, 1) = '-'
            AND substr(operation_id, 19, 1) = '-'
            AND substr(operation_id, 24, 1) = '-'
            AND substr(operation_id, 15, 1) = '4'
            AND substr(operation_id, 20, 1) IN ('8', '9', 'a', 'b')
            AND operation_id NOT GLOB '*[^0-9a-f-]*'
        ),
        project_id TEXT NOT NULL,
        environment_id TEXT NOT NULL,
        reason TEXT NOT NULL CHECK (
            length(reason) BETWEEN 1 AND 500
            AND reason = trim(reason)
            AND instr(reason, char(0)) = 0
            AND instr(reason, char(9)) = 0
            AND instr(reason, char(10)) = 0
            AND instr(reason, char(13)) = 0
        ),
        real_uid INTEGER NOT NULL CHECK (real_uid > 0),
        effective_uid INTEGER NOT NULL CHECK (effective_uid = 0),
        terminal_id TEXT NOT NULL CHECK (
            length(terminal_id) BETWEEN 1 AND 256
            AND terminal_id = trim(terminal_id)
            AND instr(terminal_id, char(0)) = 0
            AND instr(terminal_id, char(9)) = 0
            AND instr(terminal_id, char(10)) = 0
            AND instr(terminal_id, char(13)) = 0
        ),
        occurred_at TEXT NOT NULL CHECK (length(trim(occurred_at)) > 0),
        UNIQUE (event_id, project_id, environment_id),
        FOREIGN KEY (project_id) REFERENCES atlas_projects(project_id)
            ON UPDATE RESTRICT ON DELETE RESTRICT,
        FOREIGN KEY (environment_id) REFERENCES atlas_environments(environment_id)
            ON UPDATE RESTRICT ON DELETE RESTRICT,
        FOREIGN KEY (event_id, project_id, environment_id)
            REFERENCES atlas_project_environments(
                provisioning_event_id, project_id, environment_id
            )
            ON UPDATE RESTRICT ON DELETE RESTRICT
            DEFERRABLE INITIALLY DEFERRED
    );

    CREATE INDEX atlas_project_environment_provisioning_by_scope
        ON atlas_project_environment_provisioning_events(
            project_id, environment_id, occurred_at
        );

    CREATE TRIGGER atlas_project_environment_provisioning_event_scope
    BEFORE INSERT ON atlas_project_environment_provisioning_events
    WHEN EXISTS (
        SELECT 1 FROM atlas_project_environments association
        WHERE association.project_id = NEW.project_id
          AND association.environment_id = NEW.environment_id
    )
    BEGIN
        SELECT RAISE(ABORT, 'Project/Environment association already exists');
    END;

    CREATE TRIGGER atlas_project_environment_provisioning_event_no_update
    BEFORE UPDATE ON atlas_project_environment_provisioning_events
    BEGIN
        SELECT RAISE(ABORT, 'Project/Environment provisioning events are immutable');
    END;

    CREATE TRIGGER atlas_project_environment_provisioning_event_no_delete
    BEFORE DELETE ON atlas_project_environment_provisioning_events
    BEGIN
        SELECT RAISE(ABORT, 'Project/Environment provisioning events are retained');
    END;

    CREATE TRIGGER atlas_project_environment_requires_provisioning_event
    BEFORE INSERT ON atlas_project_environments
    WHEN NEW.status != 'active'
      OR NEW.revision != 1
      OR NEW.provisioning_event_id IS NULL
      OR NOT EXISTS (
          SELECT 1
          FROM atlas_project_environment_provisioning_events event
          WHERE event.event_id = NEW.provisioning_event_id
            AND event.project_id = NEW.project_id
            AND event.environment_id = NEW.environment_id
      )
    BEGIN
        SELECT RAISE(ABORT, 'initial association requires its exact offline provisioning event');
    END;

    CREATE TRIGGER atlas_project_environment_provisioning_binding_immutable
    BEFORE UPDATE OF provisioning_event_id ON atlas_project_environments
    WHEN NEW.provisioning_event_id IS NOT OLD.provisioning_event_id
    BEGIN
        SELECT RAISE(ABORT, 'association provisioning provenance is immutable');
    END;
    """,
)
