-- Paper-only collateral conversion and explicit non-cash abandonment.
-- Existing immutable journal entries and append-only triggers are unchanged.
alter table ledger_entries drop constraint if exists ledger_entries_kind_check;
alter table ledger_entries add constraint ledger_entries_kind_check
check (kind in ('INITIAL','BUY','SELL','RESOLUTION','SPLIT','ABANDONMENT'));
