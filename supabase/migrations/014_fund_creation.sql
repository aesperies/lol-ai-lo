-- 014: alta de fondos/vehículos desde la app (POST /api/funds).
--   - Nueva acción de auditoría fund_created y tipo de recurso fund.
-- Nota: ALTER TYPE ... ADD VALUE debe ejecutarse fuera de una transacción
-- con otros usos del tipo; se aplica en su propia sentencia (idempotente).

alter type audit_action add value if not exists 'fund_created';
alter type audit_resource_type add value if not exists 'fund';
