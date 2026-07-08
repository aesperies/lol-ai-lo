"use client";

import { useEffect, useId, useState } from "react";
import { useI18n } from "@/components/I18nProvider";
import {
  Badge,
  Banner,
  Button,
  Card,
  Input,
  Label,
  PageHeader,
  Select,
  Spinner,
  type BadgeTone,
} from "@/components/ui";
import {
  ApiError,
  createFund,
  createVehicle,
  deleteFund,
  deleteVehicle,
  getFunds,
  getVehicles,
  updateFund,
  updateVehicle,
} from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import type { DictKey } from "@/lib/i18n";
import {
  VEHICLE_TYPES,
  type Fund,
  type Vehicle,
  type VehicleType,
} from "@/lib/types";

/** Badge tone per vehicle type (stable visual key across the page). */
const VEHICLE_TYPE_TONES: Record<VehicleType, BadgeTone> = {
  spv: "sky",
  feeder: "violet",
  coinvest: "amber",
  holdco: "indigo",
  other: "slate",
};

function vehicleTypeKey(type: VehicleType): DictKey {
  return `funds.vehicleType.${type}` as DictKey;
}

/** Surfaces the backend `detail` (Spanish 409 messages) when available. */
function errorMessage(err: unknown, fallback: string): string {
  return err instanceof ApiError && err.message ? err.message : fallback;
}

interface FundsData {
  funds: Fund[];
  vehiclesByFund: Record<string, Vehicle[]>;
}

/**
 * "Mis fondos" (client): the gestora's funds with their SPVs/vehicles.
 * Cards are expandable; every create/rename/delete uses inline forms and
 * refetches the directory afterwards (single source of truth: the API).
 */
export default function FundsPage() {
  const { t } = useI18n();

  const { data, loading, error, reload } = useAsync<FundsData>(async () => {
    const funds = await getFunds();
    const lists = await Promise.all(
      funds.map((f) => getVehicles(f.id).catch(() => [] as Vehicle[])),
    );
    const vehiclesByFund: Record<string, Vehicle[]> = {};
    funds.forEach((f, i) => {
      vehiclesByFund[f.id] = lists[i];
    });
    return { funds, vehiclesByFund };
  }, []);

  const [showNewFund, setShowNewFund] = useState(false);

  return (
    <div>
      <PageHeader
        title={t("funds.title")}
        subtitle={t("funds.subtitle")}
        actions={
          <Button onClick={() => setShowNewFund((v) => !v)}>
            {t("funds.new")}
          </Button>
        }
      />

      {showNewFund ? (
        <NewFundForm
          onDone={() => {
            setShowNewFund(false);
            reload();
          }}
          onCancel={() => setShowNewFund(false)}
        />
      ) : null}

      {loading ? (
        <div className="flex justify-center py-16">
          <Spinner />
        </div>
      ) : error ? (
        <Banner tone="danger">{t("common.error")}</Banner>
      ) : !data || data.funds.length === 0 ? (
        <Card className="text-center text-sm text-ink-500">
          {t("funds.empty")}
        </Card>
      ) : (
        <div className="space-y-4">
          {data.funds.map((fund) => (
            <FundCard
              key={fund.id}
              fund={fund}
              vehicles={data.vehiclesByFund[fund.id] ?? []}
              onChanged={reload}
            />
          ))}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* New fund (inline form)                                               */
/* ------------------------------------------------------------------ */

function NewFundForm({
  onDone,
  onCancel,
}: {
  onDone: () => void;
  onCancel: () => void;
}) {
  const { t } = useI18n();
  const formId = useId();
  const [name, setName] = useState("");
  const [jurisdiction, setJurisdiction] = useState("España");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  return (
    <Card className="mb-6">
      <form
        className="flex flex-wrap items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (busy || name.trim().length === 0) return;
          setBusy(true);
          setErr(null);
          createFund({
            name: name.trim(),
            jurisdiction: jurisdiction.trim() || undefined,
          })
            .then(onDone)
            .catch((error: unknown) =>
              setErr(errorMessage(error, t("common.error"))),
            )
            .finally(() => setBusy(false));
        }}
      >
        <div className="min-w-[240px] flex-1">
          <Label htmlFor={`${formId}-name`}>{t("funds.name")}</Label>
          <Input
            id={`${formId}-name`}
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Esperies Capital Fund II, FCR"
            required
          />
        </div>
        <div className="w-44">
          <Label htmlFor={`${formId}-jur`}>{t("funds.jurisdiction")}</Label>
          <Input
            id={`${formId}-jur`}
            value={jurisdiction}
            onChange={(e) => setJurisdiction(e.target.value)}
          />
        </div>
        <Button type="submit" disabled={busy || name.trim().length === 0}>
          {t("funds.create")}
        </Button>
        <Button type="button" variant="ghost" onClick={onCancel}>
          {t("common.cancel")}
        </Button>
        {err ? <p className="w-full text-sm text-red-600">{err}</p> : null}
      </form>
    </Card>
  );
}

/* ------------------------------------------------------------------ */
/* Fund card (expandable, with its vehicles)                            */
/* ------------------------------------------------------------------ */

function FundCard({
  fund,
  vehicles,
  onChanged,
}: {
  fund: Fund;
  vehicles: Vehicle[];
  onChanged: () => void;
}) {
  const { t } = useI18n();
  const formId = useId();

  const [expanded, setExpanded] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editName, setEditName] = useState(fund.name);
  const [editJurisdiction, setEditJurisdiction] = useState(fund.jurisdiction);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [showNewVehicle, setShowNewVehicle] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // A fresh fund object after reload resets the edit buffer.
  useEffect(() => {
    setEditName(fund.name);
    setEditJurisdiction(fund.jurisdiction);
  }, [fund.name, fund.jurisdiction]);

  function run(action: () => Promise<unknown>) {
    setBusy(true);
    setErr(null);
    action()
      .then(() => onChanged())
      .catch((error: unknown) => setErr(errorMessage(error, t("common.error"))))
      .finally(() => setBusy(false));
  }

  return (
    <Card>
      {/* Header row */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        {editing ? (
          <form
            className="flex flex-1 flex-wrap items-end gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              if (busy || editName.trim().length === 0) return;
              run(() =>
                updateFund(fund.id, {
                  name: editName.trim(),
                  jurisdiction: editJurisdiction.trim() || undefined,
                }),
              );
              setEditing(false);
            }}
          >
            <div className="min-w-[220px] flex-1">
              <Label htmlFor={`${formId}-editname`}>{t("funds.name")}</Label>
              <Input
                id={`${formId}-editname`}
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
                required
              />
            </div>
            <div className="w-40">
              <Label htmlFor={`${formId}-editjur`}>
                {t("funds.jurisdiction")}
              </Label>
              <Input
                id={`${formId}-editjur`}
                value={editJurisdiction}
                onChange={(e) => setEditJurisdiction(e.target.value)}
              />
            </div>
            <Button type="submit" disabled={busy || editName.trim().length === 0}>
              {t("common.save")}
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                setEditing(false);
                setEditName(fund.name);
                setEditJurisdiction(fund.jurisdiction);
              }}
            >
              {t("common.cancel")}
            </Button>
          </form>
        ) : (
          <div className="min-w-0">
            <p className="truncate text-base font-semibold text-ink-900">
              {fund.name}
            </p>
            <p className="mt-0.5 text-sm text-ink-500">
              {fund.jurisdiction} ·{" "}
              {vehicles.length === 1
                ? t("funds.vehicleCountOne")
                : t("funds.vehicleCount", { count: vehicles.length })}
            </p>
          </div>
        )}

        {!editing ? (
          <div className="flex flex-wrap items-center gap-2">
            <Button
              type="button"
              variant="secondary"
              onClick={() => setExpanded((v) => !v)}
              aria-expanded={expanded}
            >
              {expanded ? t("funds.hideVehicles") : t("funds.showVehicles")}
            </Button>
            <Button
              type="button"
              variant="secondary"
              onClick={() => setEditing(true)}
            >
              {t("common.edit")}
            </Button>
            {confirmDelete ? (
              <span className="flex items-center gap-2 text-sm text-ink-600">
                {t("funds.confirmDelete")}
                <Button
                  type="button"
                  variant="danger"
                  disabled={busy}
                  onClick={() => {
                    setConfirmDelete(false);
                    run(() => deleteFund(fund.id));
                  }}
                >
                  {t("funds.confirmDeleteYes")}
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => setConfirmDelete(false)}
                >
                  {t("common.cancel")}
                </Button>
              </span>
            ) : (
              <Button
                type="button"
                variant="ghost"
                className="text-red-600 hover:bg-red-50"
                onClick={() => setConfirmDelete(true)}
              >
                {t("funds.delete")}
              </Button>
            )}
          </div>
        ) : null}
      </div>

      {err ? (
        <Banner tone="danger" className="mt-3">
          {err}
        </Banner>
      ) : null}

      {/* Vehicles */}
      {expanded ? (
        <div className="mt-4 border-t border-ink-200 pt-4">
          <div className="mb-3 flex items-center justify-between gap-3">
            <h3 className="text-sm font-semibold text-ink-800">
              {t("funds.vehicles")}
            </h3>
            {!showNewVehicle ? (
              <button
                type="button"
                className="text-sm font-medium text-brand-700 underline-offset-2 hover:underline"
                onClick={() => setShowNewVehicle(true)}
              >
                {t("funds.addVehicle")}
              </button>
            ) : null}
          </div>

          {showNewVehicle ? (
            <NewVehicleForm
              fundId={fund.id}
              onDone={() => {
                setShowNewVehicle(false);
                onChanged();
              }}
              onCancel={() => setShowNewVehicle(false)}
            />
          ) : null}

          {vehicles.length === 0 && !showNewVehicle ? (
            <p className="text-sm text-ink-500">{t("funds.noVehicles")}</p>
          ) : (
            <ul className="divide-y divide-ink-100">
              {vehicles.map((v) => (
                <VehicleRow key={v.id} vehicle={v} onChanged={onChanged} />
              ))}
            </ul>
          )}
        </div>
      ) : null}
    </Card>
  );
}

/* ------------------------------------------------------------------ */
/* New vehicle (inline form)                                            */
/* ------------------------------------------------------------------ */

function VehicleTypeSelect({
  id,
  value,
  onChange,
}: {
  id: string;
  value: VehicleType;
  onChange: (v: VehicleType) => void;
}) {
  const { t } = useI18n();
  return (
    <Select
      id={id}
      value={value}
      onChange={(e) => onChange(e.target.value as VehicleType)}
    >
      {VEHICLE_TYPES.map((type) => (
        <option key={type} value={type}>
          {t(vehicleTypeKey(type))}
        </option>
      ))}
    </Select>
  );
}

function NewVehicleForm({
  fundId,
  onDone,
  onCancel,
}: {
  fundId: string;
  onDone: () => void;
  onCancel: () => void;
}) {
  const { t } = useI18n();
  const formId = useId();
  const [name, setName] = useState("");
  const [vehicleType, setVehicleType] = useState<VehicleType>("spv");
  const [jurisdiction, setJurisdiction] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  return (
    <form
      className="mb-4 flex flex-wrap items-end gap-3 rounded-lg border border-ink-200 bg-ink-50 p-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (busy || name.trim().length === 0) return;
        setBusy(true);
        setErr(null);
        createVehicle(fundId, {
          name: name.trim(),
          vehicleType,
          jurisdiction: jurisdiction.trim() || undefined,
        })
          .then(onDone)
          .catch((error: unknown) =>
            setErr(errorMessage(error, t("common.error"))),
          )
          .finally(() => setBusy(false));
      }}
    >
      <div className="min-w-[200px] flex-1">
        <Label htmlFor={`${formId}-vname`}>{t("funds.vehicleName")}</Label>
        <Input
          id={`${formId}-vname`}
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Iberia SPV Delta, S.L."
          required
        />
      </div>
      <div className="w-40">
        <Label htmlFor={`${formId}-vtype`}>{t("funds.vehicleTypeLabel")}</Label>
        <VehicleTypeSelect
          id={`${formId}-vtype`}
          value={vehicleType}
          onChange={setVehicleType}
        />
      </div>
      <div className="w-40">
        <Label htmlFor={`${formId}-vjur`}>{t("funds.jurisdiction")}</Label>
        <Input
          id={`${formId}-vjur`}
          value={jurisdiction}
          onChange={(e) => setJurisdiction(e.target.value)}
        />
      </div>
      <Button type="submit" disabled={busy || name.trim().length === 0}>
        {t("funds.createVehicle")}
      </Button>
      <Button type="button" variant="ghost" onClick={onCancel}>
        {t("common.cancel")}
      </Button>
      {err ? <p className="w-full text-sm text-red-600">{err}</p> : null}
    </form>
  );
}

/* ------------------------------------------------------------------ */
/* Vehicle row (inline edit / delete)                                   */
/* ------------------------------------------------------------------ */

function VehicleRow({
  vehicle,
  onChanged,
}: {
  vehicle: Vehicle;
  onChanged: () => void;
}) {
  const { t } = useI18n();
  const formId = useId();

  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(vehicle.name);
  const [vehicleType, setVehicleType] = useState<VehicleType>(
    vehicle.vehicleType,
  );
  const [jurisdiction, setJurisdiction] = useState(vehicle.jurisdiction ?? "");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setName(vehicle.name);
    setVehicleType(vehicle.vehicleType);
    setJurisdiction(vehicle.jurisdiction ?? "");
  }, [vehicle.name, vehicle.vehicleType, vehicle.jurisdiction]);

  function run(action: () => Promise<unknown>) {
    setBusy(true);
    setErr(null);
    action()
      .then(() => onChanged())
      .catch((error: unknown) => setErr(errorMessage(error, t("common.error"))))
      .finally(() => setBusy(false));
  }

  return (
    <li className="py-3">
      {editing ? (
        <form
          className="flex flex-wrap items-end gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (busy || name.trim().length === 0) return;
            run(() =>
              updateVehicle(vehicle.id, {
                name: name.trim(),
                vehicleType,
                jurisdiction: jurisdiction.trim(),
              }),
            );
            setEditing(false);
          }}
        >
          <div className="min-w-[200px] flex-1">
            <Label htmlFor={`${formId}-name`}>{t("funds.vehicleName")}</Label>
            <Input
              id={`${formId}-name`}
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
          </div>
          <div className="w-40">
            <Label htmlFor={`${formId}-type`}>
              {t("funds.vehicleTypeLabel")}
            </Label>
            <VehicleTypeSelect
              id={`${formId}-type`}
              value={vehicleType}
              onChange={setVehicleType}
            />
          </div>
          <div className="w-40">
            <Label htmlFor={`${formId}-jur`}>{t("funds.jurisdiction")}</Label>
            <Input
              id={`${formId}-jur`}
              value={jurisdiction}
              onChange={(e) => setJurisdiction(e.target.value)}
            />
          </div>
          <Button type="submit" disabled={busy || name.trim().length === 0}>
            {t("common.save")}
          </Button>
          <Button
            type="button"
            variant="ghost"
            onClick={() => {
              setEditing(false);
              setName(vehicle.name);
              setVehicleType(vehicle.vehicleType);
              setJurisdiction(vehicle.jurisdiction ?? "");
            }}
          >
            {t("common.cancel")}
          </Button>
        </form>
      ) : (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <span className="truncate text-sm font-medium text-ink-800">
              {vehicle.name}
            </span>
            <Badge tone={VEHICLE_TYPE_TONES[vehicle.vehicleType]}>
              {t(vehicleTypeKey(vehicle.vehicleType))}
            </Badge>
            {vehicle.jurisdiction ? (
              <span className="text-xs text-ink-400">
                {vehicle.jurisdiction}
              </span>
            ) : null}
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              className="text-sm font-medium text-brand-700 underline-offset-2 hover:underline"
              onClick={() => setEditing(true)}
            >
              {t("common.edit")}
            </button>
            {confirmDelete ? (
              <span className="flex items-center gap-2 text-xs text-ink-600">
                {t("funds.confirmDelete")}
                <button
                  type="button"
                  disabled={busy}
                  className="font-medium text-red-600 underline-offset-2 hover:underline disabled:text-ink-300"
                  onClick={() => {
                    setConfirmDelete(false);
                    run(() => deleteVehicle(vehicle.id));
                  }}
                >
                  {t("funds.confirmDeleteYes")}
                </button>
                <button
                  type="button"
                  className="text-ink-500 underline-offset-2 hover:underline"
                  onClick={() => setConfirmDelete(false)}
                >
                  {t("common.cancel")}
                </button>
              </span>
            ) : (
              <button
                type="button"
                className="text-sm font-medium text-red-600 underline-offset-2 hover:underline"
                onClick={() => setConfirmDelete(true)}
              >
                {t("funds.delete")}
              </button>
            )}
          </div>
        </div>
      )}
      {err ? (
        <Banner tone="danger" className="mt-2">
          {err}
        </Banner>
      ) : null}
    </li>
  );
}
