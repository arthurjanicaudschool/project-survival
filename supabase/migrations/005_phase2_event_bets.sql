begin;
alter table experiments drop constraint if exists experiments_status_check;
alter table experiments add constraint experiments_status_check check(status in ('READY','RUNNING','CLOSING','FINISHED'));
alter table experiments alter column started_at drop not null;
alter table experiments alter column end_at drop not null;
alter table experiments drop constraint if exists phase2_start_timestamps;
alter table experiments add constraint phase2_start_timestamps check (
 (status='READY' and started_at is null and end_at is null) or
 (status<>'READY' and started_at is not null and end_at is not null)
);
alter table agents drop constraint if exists agents_initial_eur_check;
alter table agents add constraint agents_initial_eur_check check(initial_eur in (10,50,100));
commit;
