-- ============================================================
-- 015 — SPVs / Vehículos por fondo + CRUD completo de fondos
--
-- * vehicles: vehículos de inversión colgando de un fondo (SPV, feeder,
--   co-inversión, holdco...). Aislamiento heredado del fondo (fund_id).
-- * requests.vehicle_id: una solicitud puede referirse a un vehículo
--   concreto del fondo (opcional; se valida vehicle ∈ fund en el intake).
-- * Nuevas acciones de auditoría para el ciclo de vida de fondos/vehículos.
-- ============================================================

create table vehicles (
  id uuid primary key default uuid_generate_v4(),
  fund_id uuid not null references funds(id) on delete cascade,
  name varchar(200) not null,
  vehicle_type text not null default 'spv'
    check (vehicle_type in ('spv', 'feeder', 'coinvest', 'holdco', 'other')),
  jurisdiction varchar(100),
  created_at timestamptz not null default now()
);
create index idx_vehicles_fund on vehicles(fund_id);
alter table vehicles enable row level security;

alter table requests
  add column if not exists vehicle_id uuid references vehicles(id) on delete set null;

alter type audit_action add value if not exists 'vehicle_created';
alter type audit_action add value if not exists 'vehicle_updated';
alter type audit_action add value if not exists 'vehicle_deleted';
alter type audit_action add value if not exists 'fund_updated';
alter type audit_action add value if not exists 'fund_deleted';
alter type audit_resource_type add value if not exists 'vehicle';
